"""抽奖服务。"""

from __future__ import annotations

import random

from ..config import GameConfig, LotteryReward
from ..errors import GameError
from ..models import Player
from ..repository import GameRepository
from ..utils import format_currency
from .ledger import LedgerService


class LotteryService:
    def __init__(
        self,
        repo: GameRepository,
        config: GameConfig,
        ledger: LedgerService | None = None,
    ):
        self.repo = repo
        self.config = config
        self.ledger = ledger

    def _pick_reward(self) -> LotteryReward:
        rewards = self.config.lottery_rewards
        total_weight = sum(r.weight for r in rewards)
        if total_weight <= 0:
            raise GameError("奖池未配置。")
        roll = random.uniform(0, total_weight)
        upto = 0.0
        for reward in rewards:
            upto += reward.weight
            if roll <= upto:
                return reward
        return rewards[-1]

    async def draw(self, player: Player) -> str:
        cost = self.config.lottery_cost
        if player.balance < cost:
            raise GameError("余额不足，抽奖需 " + format_currency(cost))
        player.balance -= cost
        reward = self._pick_reward()
        gain = random.randint(reward.min_amount, reward.max_amount)
        player.balance += gain
        await self.repo.save_player(player)
        await self.repo.adjust_system_balance(cost - gain)
        if self.ledger:
            await self.ledger.record(
                player,
                category="抽奖",
                amount=cost,
                direction="expense",
                description="抽奖花费",
            )
            if gain > 0:
                await self.ledger.record(
                    player,
                    category="抽奖",
                    amount=gain,
                    direction="income",
                    description=reward.label,
                )
        if gain <= 0:
            return f"很遗憾，{reward.label}，本次未中奖。"
        return f"{reward.label}：获得 {format_currency(gain)}，净收益 {format_currency(gain - cost)}"
