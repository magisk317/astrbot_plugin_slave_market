"""High risk entertainment systems."""

from __future__ import annotations

import random

from ..config import GameConfig
from ..errors import GameError
from ..models import Player
from ..repository import GameRepository
from ..utils import format_currency
from .ledger import LedgerService


class GamblingService:
    def __init__(
        self,
        repo: GameRepository,
        config: GameConfig,
        ledger: LedgerService | None = None,
    ):
        self.repo = repo
        self.config = config
        self.ledger = ledger

    def _require_bet(self, amount: int) -> int:
        if amount < self.config.gambling_min_bet:
            raise GameError(f"下注至少 {self.config.gambling_min_bet}")
        if amount > self.config.gambling_max_bet:
            raise GameError(f"单次下注最多 {self.config.gambling_max_bet}")
        return amount

    async def _log(self, player: Player, amount: int, direction: str, desc: str):
        if self.ledger:
            await self.ledger.record(
                player,
                category="高风险娱乐",
                amount=amount,
                direction=direction,
                description=desc,
            )

    async def coin_toss(self, player: Player, amount: int) -> str:
        amount = self._require_bet(amount)
        if player.balance < amount:
            raise GameError("余额不足。")
        player.balance -= amount
        win = random.random() > 0.55
        if win:
            reward = amount * 2
            player.balance += reward
            await self.repo.save_player(player)
            await self._log(player, reward, "income", "猜硬币胜利")
            return f"恭喜胜出，获得 {format_currency(reward)}"
        await self.repo.save_player(player)
        await self._log(player, amount, "expense", "猜硬币失败")
        return "惜败，金币悉数输掉。"

    async def dice(self, player: Player, amount: int) -> str:
        amount = self._require_bet(amount)
        if player.balance < amount:
            raise GameError("余额不足。")
        player.balance -= amount
        player_roll = random.randint(1, 6)
        dealer_roll = random.randint(1, 6)
        if player_roll >= dealer_roll:
            reward = int(amount * 2.5)
            player.balance += reward
            await self.repo.save_player(player)
            await self._log(player, reward, "income", "掷骰胜利")
            return f"你的点数 {player_roll} 对抗庄家 {dealer_roll}，赢得 {format_currency(reward)}"
        await self.repo.save_player(player)
        await self._log(player, amount, "expense", "掷骰失败")
        return f"你的点数 {player_roll} 不敌庄家 {dealer_roll}，输掉全部押注。"
