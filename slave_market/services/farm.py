"""Farming gameplay helpers."""

from __future__ import annotations

import random

from ..config import GameConfig, CropProfile
from ..errors import GameError
from ..models import Player, CropPlot
from ..repository import GameRepository
from ..utils import now_ts, format_currency
from .ledger import LedgerService


class FarmService:
    def __init__(
        self,
        repo: GameRepository,
        config: GameConfig,
        ledger: LedgerService | None = None,
    ):
        self.repo = repo
        self.config = config
        self.ledger = ledger

    def _get_crop(self, keyword: str) -> CropProfile:
        keyword = keyword.strip()
        for crop in self.config.crops:
            if crop.name == keyword:
                return crop
        raise GameError(
            "未知作物，可选：" + ",".join(c.name for c in self.config.crops)
        )

    async def plant(self, player: Player, crop_name: str) -> str:
        if player.farmland and not player.farmland.ready():
            raise GameError("作物仍在生长中。")
        crop = self._get_crop(crop_name)
        player.farmland = CropPlot(
            crop_name=crop.name,
            emoji=crop.emoji,
            planted_at=now_ts(),
            grow_hours=crop.grow_hours,
            yield_min=crop.yield_min,
            yield_max=crop.yield_max,
        )
        await self.repo.save_player(player)
        return f"已种下 {crop.emoji}{crop.name}，预计 {crop.grow_hours} 小时后成熟。"

    async def status(self, player: Player) -> str:
        if not player.farmland:
            return "暂无作物，请先种地。"
        crop = player.farmland
        progress = max(0, now_ts() - crop.planted_at)
        duration = max(1, crop.grow_hours * 3600)
        percent = min(100, int(progress / duration * 100))
        ready = "已成熟" if crop.ready() else "成长中"
        return f"{crop.emoji}{crop.crop_name} - {ready}，进度 {percent}%"

    async def harvest(self, player: Player) -> str:
        if not player.farmland:
            raise GameError("您还没有种地。")
        crop = player.farmland
        if not crop.ready():
            raise GameError("作物尚未成熟。")
        gain = random.randint(crop.yield_min, crop.yield_max)
        player.balance += gain
        player.farmland = None
        await self.repo.save_player(player)
        if self.ledger:
            await self.ledger.record(
                player,
                category="农务",
                amount=gain,
                direction="income",
                description="收获作物",
            )
        return f"丰收啦，获得 {format_currency(gain)}"


__all__ = ["FarmService"]
