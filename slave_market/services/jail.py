"""Light-weight jail and prison related helpers."""

from __future__ import annotations

import random
from typing import Callable

from ..config import GameConfig
from ..errors import GameError
from ..models import Player
from ..repository import GameRepository
from ..utils import format_currency, now_ts


class JailService:
    def __init__(
        self,
        repo: GameRepository,
        config: GameConfig,
        price_evaluator: Callable[[Player], int],
    ):
        self.repo = repo
        self.config = config
        self.price_evaluator = price_evaluator
        self.term_seconds = config.jail_term_seconds
        self.cooldown = config.jail_work_cooldown_seconds

    def _is_in_jail(self, player: Player) -> bool:
        return player.jail_until > now_ts()

    def _bail_cost(self, player: Player) -> int:
        value = self.price_evaluator(player)
        return max(200, int(value * 0.5))

    async def work(self, player: Player) -> str:
        now = now_ts()
        if not self._is_in_jail(player):
            player.jail_until = now + self.term_seconds
            if not player.jail_reason:
                player.jail_reason = "因赌博入狱"
        if now < player.jail_cooldown_end:
            wait = int(player.jail_cooldown_end - now)
            raise GameError(f"缝纫机冷却中，请 {wait} 秒后再试。")
        gain = random.randint(120, 360)
        player.balance += gain
        player.jail_coin += gain
        player.jail_cooldown_end = now + self.cooldown
        # 减少刑期，直至归零视为出狱
        player.jail_until = max(now, player.jail_until - self.cooldown)
        release_note = ""
        remain_minutes = 0
        if player.jail_until <= now:
            player.jail_until = 0
            player.jail_reason = ""
            release_note = "你完成了劳动任务，成功出狱。"
        else:
            remain_minutes = int((player.jail_until - now) / 60)
            release_note = f"剩余刑期 {remain_minutes} 分钟。"
        await self.repo.save_player(player)
        return (
            f"踩缝纫机赚到 {format_currency(gain)}，累计收益 {format_currency(player.jail_coin)}"
            f"\n{release_note}"
        )

    async def status(self, player: Player) -> str:
        if not self._is_in_jail(player):
            return "当前没有刑期，可自由行动。"
        remain = int((player.jail_until - now_ts()) / 60)
        bail = self._bail_cost(player)
        reason = player.jail_reason or "未知"
        return (
            f"=== 监狱状态 ===\n剩余刑期：{remain} 分钟\n缘由：{reason}\n"
            f"保释金：{format_currency(bail)}\n已获收益：{format_currency(player.jail_coin)}"
        )

    async def bail(self, player: Player) -> str:
        if not self._is_in_jail(player):
            raise GameError("你当前不在监狱中。")
        cost = self._bail_cost(player)
        if player.balance < cost:
            raise GameError("余额不足以交保，需要 " + format_currency(cost))
        player.balance -= cost
        player.jail_until = 0
        player.jail_reason = ""
        await self.repo.save_player(player)
        return f"交保成功，支付 {format_currency(cost)} 即刻出狱。"

    async def inmates(self) -> str:
        players = await self.repo.list_players()
        inmates = [p for p in players if self._is_in_jail(p)]
        if not inmates:
            return "监狱空空如也。"
        lines = ["当前在押："]
        now = now_ts()
        for player in inmates:
            remain = int((player.jail_until - now) / 60)
            lines.append(f"{player.nickname} - {remain} 分钟")
        return "\n".join(lines)


__all__ = ["JailService"]
