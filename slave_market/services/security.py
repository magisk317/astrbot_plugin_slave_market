"""Bodyguard helpers."""

from __future__ import annotations

from ..config import GameConfig, GuardProfile
from ..errors import GameError
from ..models import GuardContract, Player
from ..repository import GameRepository
from ..utils import format_currency, now_ts


class GuardService:
    def __init__(self, repo: GameRepository, config: GameConfig):
        self.repo = repo
        self.config = config

    def _guard(self, name: str) -> GuardProfile:
        for guard in self.config.guards:
            if guard.name == name:
                return guard
        raise GameError(
            "未知保镖，可选：" + ",".join(g.name for g in self.config.guards)
        )

    def catalog(self) -> str:
        lines = ["保镖市场："]
        for guard in self.config.guards:
            lines.append(
                f"{guard.name} - {guard.duration_hours} 小时 - {format_currency(guard.hourly_cost)}"
            )
        return "\n".join(lines)

    async def hire(self, player: Player, name: str) -> str:
        guard = self._guard(name)
        cost = guard.hourly_cost
        admins = await self.repo.list_admins()
        if player.player_id not in admins:
            if player.balance < cost:
                raise GameError("余额不足。")
            player.balance -= cost
        player.guard = GuardContract(
            name=guard.name,
            expires_at=now_ts() + guard.duration_hours * 3600,
            protection_bonus=guard.protection_bonus,
        )
        await self.repo.save_player(player)
        return f"已雇佣 {guard.name}，持续 {guard.duration_hours} 小时"

    async def status(self, player: Player) -> str:
        if not player.guard or not player.guard.active():
            return "暂无保镖保护。"
        remain = int((player.guard.expires_at - now_ts()) / 3600)
        return f"当前保镖 {player.guard.name}，剩余 {remain} 小时"


__all__ = ["GuardService"]
