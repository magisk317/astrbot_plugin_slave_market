"""福利补助系统。"""

from __future__ import annotations

from ..config import GameConfig
from ..errors import GameError
from ..models import Player
from ..repository import GameRepository
from ..utils import format_currency, now_ts
from .ledger import LedgerService


class WelfareService:
    def __init__(
        self,
        repo: GameRepository,
        config: GameConfig,
        ledger: LedgerService | None = None,
    ):
        self.repo = repo
        self.config = config
        self.ledger = ledger

    def _eligible(self, player: Player) -> bool:
        total_asset = player.balance + player.bank_balance
        return total_asset <= self.config.welfare_threshold

    def _cooldown(self, player: Player) -> int:
        now = now_ts()
        remain = int(
            self.config.welfare_interval_seconds - (now - player.last_welfare_time)
        )
        return max(0, remain)

    def preview(self, player: Player) -> str:
        if not self._eligible(player):
            return "资产已超过补助线，无法领取。"
        remain = self._cooldown(player)
        if remain > 0:
            return f"尚需等待 {remain} 秒再领取补助。"
        amount = self._calc_amount(player)
        return f"当前补助额度：{format_currency(amount)}"

    def _calc_amount(self, player: Player) -> int:
        return (
            self.config.welfare_base_amount
            + player.welfare_level * self.config.welfare_growth
        )

    async def claim(self, player: Player) -> str:
        if not self._eligible(player):
            raise GameError("你太富裕了，无法领取福利。")
        remain = self._cooldown(player)
        if remain > 0:
            raise GameError(f"还需等待 {remain} 秒。")
        amount = self._calc_amount(player)
        player.balance += amount
        player.last_welfare_time = now_ts()
        player.welfare_income += amount
        player.welfare_level = min(player.welfare_level + 1, 10)
        await self.repo.save_player(player)
        await self.repo.adjust_system_balance(-amount)
        if self.ledger:
            await self.ledger.record(
                player,
                category="福利",
                amount=amount,
                direction="income",
                description="领取补助",
            )
        return f"补助到账 {format_currency(amount)}，累计领取 {format_currency(player.welfare_income)}"
