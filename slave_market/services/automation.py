"""Automated VIP helper tasks."""

from __future__ import annotations

from typing import Callable, Awaitable

from astrbot.api import logger

from ..config import GameConfig
from ..errors import GameError
from ..models import Player
from ..repository import GameRepository
from ..utils import now_ts
from .economy import EconomyService
from .farm import FarmService


class AutomationService:
    def __init__(
        self,
        repo: GameRepository,
        config: GameConfig,
        economy: EconomyService,
        farm: FarmService,
    ):
        self.repo = repo
        self.config = config
        self.economy = economy
        self.farm = farm
        self.task_handlers: dict[str, Callable[[Player], Awaitable[Player]]] = {
            "打工": self._auto_work,
            "收获": self._auto_harvest,
            "存款": self._auto_deposit,
        }

    async def run_cycle(self) -> None:
        now = now_ts()
        players = await self.repo.list_players()
        for player in players:
            if player.vip_until <= now:
                continue
            if not any(player.auto_tasks.values()):
                continue
            if (
                player.last_auto_task
                and now - player.last_auto_task < self.config.auto_task_interval_seconds
            ):
                continue
            await self._run_for_player(player, now)

    async def _run_for_player(self, player: Player, timestamp: float) -> None:
        current = player
        for name, enabled in list(current.auto_tasks.items()):
            if not enabled:
                continue
            handler = self.task_handlers.get(name)
            if not handler:
                continue
            try:
                current = await handler(current)
            except GameError as exc:
                logger.debug("自动任务 %s 被跳过：%s", name, exc)
            except Exception:
                logger.exception("自动任务 %s 执行异常", name)
        current.last_auto_task = timestamp
        await self.repo.save_player(current)

    async def _auto_work(self, player: Player) -> Player:
        await self.economy.work(player)
        return await self._reload(player)

    async def _auto_harvest(self, player: Player) -> Player:
        await self.farm.harvest(player)
        return await self._reload(player)

    async def _auto_deposit(self, player: Player) -> Player:
        refreshed = await self._reload(player)
        player = refreshed
        available = min(player.balance, player.deposit_limit - player.bank_balance)
        if available <= 0:
            raise GameError("余额不足以存款。")
        await self.economy.deposit(player, available)
        return await self._reload(player)

    async def _reload(self, player: Player) -> Player:
        latest = await self.repo.get_player(player.player_id)
        return latest or player


__all__ = ["AutomationService"]
