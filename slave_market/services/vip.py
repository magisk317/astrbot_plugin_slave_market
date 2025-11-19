"""VIP card operations."""

from __future__ import annotations

import random
from typing import List

from ..config import GameConfig, VipDefinition
from ..errors import GameError
from ..models import Player, VipCard
from ..repository import GameRepository
from ..utils import now_ts


class VipService:
    def __init__(self, repo: GameRepository, config: GameConfig):
        self.repo = repo
        self.config = config

    def _definition(self, card_type: str) -> VipDefinition:
        for definition in self.config.vip_definitions:
            if definition.key == card_type:
                return definition
        raise GameError(
            "未知卡种，可选：" + ",".join(d.key for d in self.config.vip_definitions)
        )

    async def generate(
        self, card_type: str, amount: int, duration_hint: str | None = None
    ) -> List[VipCard]:
        if amount <= 0 or amount > 20:
            raise GameError("数量需在 1~20 之间。")
        definition = self._definition(card_type)
        cards: List[VipCard] = []
        for _ in range(amount):
            hours = definition.hours
            if card_type == "小时卡" and duration_hint:
                hours = self._parse_range(duration_hint)
            code = self.repo.generate_code("vip")
            cards.append(
                VipCard(
                    code=code,
                    card_type=card_type,
                    hours=hours,
                    created_at=now_ts(),
                    duration_override=hours if card_type == "小时卡" else None,
                )
            )
        for card in cards:
            await self.repo.register_vip_card(card)
        return cards

    def _parse_range(self, text: str) -> int:
        if "-" in text:
            start, end = text.split("-", 1)
            return random.randint(int(start), int(end))
        return int(text)

    async def redeem(self, player: Player, code: str) -> str:
        cards = await self.repo.list_vip_cards()
        for card in cards:
            if card.code == code:
                if card.redeemed_by:
                    raise GameError("该卡密已被使用。")
                card.redeemed_by = player.player_id
                card.redeemed_at = now_ts()
                await self.repo.update_vip_card(card)
                duration = card.hours * 3600
                player.vip_until = max(player.vip_until, now_ts()) + duration
                await self.repo.save_player(player)
                return f"VIP 激活成功，剩余 {int((player.vip_until - now_ts()) / 3600)} 小时"
        raise GameError("未找到该卡密。")

    async def status(self, player: Player) -> str:
        if player.vip_until <= now_ts():
            return "您还不是 VIP。"
        hours = int((player.vip_until - now_ts()) / 3600)
        tasks = ", ".join(
            f"{k}:{'开' if v else '关'}" for k, v in player.auto_tasks.items()
        )
        return f"VIP 剩余 {hours} 小时\n自动任务：{tasks}"


__all__ = ["VipService"]
