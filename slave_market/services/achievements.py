"""Achievement tracking service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Iterable

from ..models import Player
from ..repository import GameRepository


@dataclass(slots=True)
class Achievement:
    key: str
    name: str
    description: str
    checker: Callable[[Player], bool]


class AchievementService:
    def __init__(self, repo: GameRepository, achievements: Iterable[Achievement]):
        self.repo = repo
        self._achievements: Dict[str, Achievement] = {
            ach.key: ach for ach in achievements
        }

    async def evaluate(self, player: Player) -> list[str]:
        unlocked = []
        for ach in self._achievements.values():
            if player.achievements.get(ach.key):
                continue
            if ach.checker(player):
                player.achievements[ach.key] = True
                unlocked.append(ach.name)
        if unlocked:
            await self.repo.save_player(player)
        return unlocked

    def progress(self, player: Player) -> str:
        unlocked = [
            self._achievements[k].name
            for k in player.achievements
            if k in self._achievements
        ]
        remaining = [
            ach.name
            for ach in self._achievements.values()
            if ach.key not in player.achievements
        ]
        lines = ["=== 成就进度 ==="]
        if unlocked:
            lines.append("已解锁：" + ", ".join(unlocked))
        else:
            lines.append("已解锁：暂无")
        if remaining:
            lines.append("待解锁：" + ", ".join(remaining))
        return "\n".join(lines)
