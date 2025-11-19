"""Player centric helpers."""

from __future__ import annotations

from dataclasses import replace
from typing import List, Optional

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from ..config import GameConfig
from ..errors import GameError, PermissionDenied
from ..models import Player
from ..repository import GameRepository
from ..utils import format_currency, now_ts


class PlayerService:
    def __init__(self, repo: GameRepository, config: GameConfig):
        self.repo = repo
        self.config = config

    @staticmethod
    def player_id(platform_id: str, user_id: str) -> str:
        return f"{platform_id}:{user_id}"

    async def ensure_player(self, event: AstrMessageEvent) -> Player:
        player_id = self.player_id(event.get_platform_id(), event.get_sender_id())
        record = await self.repo.get_player(player_id)
        nickname = event.get_sender_name() or f"玩家{event.get_sender_id()}"
        group_id = event.get_group_id() or ""
        if record is None:
            player = Player(
                player_id=player_id,
                platform=event.get_platform_id(),
                user_id=event.get_sender_id(),
                nickname=nickname,
                group_id=group_id,
                balance=self.config.starting_balance,
                bank_balance=0,
                deposit_limit=self.config.credit_levels[0].deposit_limit,
                auto_tasks=dict(self.config.default_auto_tasks),
            )
            await self.repo.save_player(player)
            logger.info("registered new trader %s", player_id)
            return player

        changed = False
        if nickname and nickname != record.nickname:
            record.nickname = nickname
            changed = True
        if group_id and group_id != (record.group_id or ""):
            record.group_id = group_id
            changed = True
        if changed:
            record.updated_at = now_ts()
            await self.repo.save_player(record)
        return record

    async def get_player(self, player_id: str) -> Optional[Player]:
        return await self.repo.get_player(player_id)

    async def find_by_keyword(self, keyword: str) -> Optional[Player]:
        keyword = keyword.strip()
        if not keyword:
            return None
        players = await self.repo.list_players()
        for player in players:
            if player.player_id == keyword or player.nickname == keyword:
                return player
        for player in players:
            if keyword in player.nickname:
                return player
        return None

    async def reset_player(self, player: Player) -> Player:
        previous_owner = player.owner_id
        fresh = replace(
            player,
            balance=self.config.starting_balance,
            bank_balance=0,
            owned_slaves={},
            owner_id=None,
            farmland=None,
            loan=None,
            guard=None,
            jail_coin=0,
            jail_until=0,
            jail_cooldown_end=0,
            vip_until=0,
        )
        fresh.updated_at = now_ts()
        for slave_id in player.owned_slaves.keys():
            slave = await self.repo.get_player(slave_id)
            if slave:
                slave.owner_id = None
                await self.repo.save_player(slave)
        if previous_owner:
            owner = await self.repo.get_player(previous_owner)
            if owner:
                owner.owned_slaves.pop(player.player_id, None)
                await self.repo.save_player(owner)
        fresh.owner_id = None
        await self.repo.save_player(fresh)
        return fresh

    async def snapshot(self, player: Player) -> str:
        owner_str = "自由人" if not player.owner_id else f"隶属 {player.owner_id}"
        vip_state = (
            "未激活"
            if player.vip_until <= now_ts()
            else f"剩余 {int((player.vip_until - now_ts()) / 3600)} 小时"
        )
        lines = [
            f"昵称：{player.nickname}",
            f"余额：{format_currency(player.balance)}",
            f"银行：{format_currency(player.bank_balance)} / 上限 {format_currency(player.deposit_limit)}",
            f"信用等级：Lv.{player.credit_level}",
            f"身份：{owner_str}",
            f"牛马数量：{len(player.owned_slaves)}",
            f"VIP：{vip_state}",
        ]
        if player.farmland:
            lines.append(
                f"作物：{player.farmland.emoji}{player.farmland.crop_name} 已种植 {int((now_ts() - player.farmland.planted_at) / 3600)} 小时"
            )
        if player.loan and not player.loan.repaid:
            lines.append(
                f"贷款：{format_currency(player.loan.amount)} 利率 {player.loan.rate * 100:.1f}%"
            )
        return "\n".join(lines)

    async def require_admin(self, player: Player) -> None:
        admins = await self.repo.list_admins()
        if player.player_id not in admins:
            raise PermissionDenied("仅限管理员执行该操作。")

    async def add_admin(self, player_id: str) -> None:
        await self.repo.add_admin(player_id)

    async def remove_admin(self, player_id: str) -> None:
        await self.repo.remove_admin(player_id)

    async def list_admins(self) -> List[str]:
        return await self.repo.list_admins()

    async def ranking(self, key: str, limit: int = 10) -> str:
        players = await self.repo.list_players()
        if key == "wealth":
            players.sort(key=lambda p: p.balance + p.bank_balance, reverse=True)
            title = "资金排行"
            attr = lambda p: format_currency(p.balance + p.bank_balance)
        elif key == "value":
            players.sort(
                key=lambda p: p.balance + p.bank_balance + len(p.owned_slaves) * 600,
                reverse=True,
            )
            title = "身价排行"
            attr = lambda p: format_currency(
                p.balance + p.bank_balance + len(p.owned_slaves) * 600
            )
        else:
            players.sort(key=lambda p: len(p.owned_slaves), reverse=True)
            title = "牛马排行"
            attr = lambda p: f"{len(p.owned_slaves)} 头"
        lines = [title]
        for idx, player in enumerate(players[:limit], 1):
            lines.append(f"{idx}. {player.nickname} - {attr(player)}")
        return "\n".join(lines)

    async def stats_overview(self) -> str:
        players = await self.repo.list_players()
        online = len(players)
        owners = sum(1 for p in players if p.owned_slaves)
        enslaved = sum(1 for p in players if p.owner_id)
        return f"玩家总数：{online}\n雇主：{owners}\n牛马：{enslaved}"

    async def search(self, keyword: str, limit: int = 5) -> list[Player]:
        keyword = keyword.strip()
        if not keyword:
            raise GameError("请输入关键字。")
        players = await self.repo.list_players()
        matches = [p for p in players if keyword in p.nickname]
        return matches[:limit]

    async def economy_overview(self) -> str:
        players = await self.repo.list_players()
        total_gold = sum(p.balance for p in players)
        total_deposit = sum(p.bank_balance for p in players)
        total_loans = sum(
            p.loan.amount for p in players if p.loan and not p.loan.repaid
        )
        vip_count = sum(1 for p in players if p.vip_until > now_ts())
        richest = max(
            players,
            key=lambda p: p.balance + p.bank_balance,
            default=None,
        )
        lines = [
            f"流通金币：{format_currency(total_gold)}",
            f"银行存款：{format_currency(total_deposit)}",
            f"未偿贷款：{format_currency(total_loans)}",
            f"VIP 数量：{vip_count}",
        ]
        if richest:
            lines.append(
                f"首富：{richest.nickname}（{format_currency(richest.balance + richest.bank_balance)}）"
            )
        return "\n".join(lines)

    async def toggle_auto_task(
        self, player: Player, task_name: str, enabled: bool
    ) -> str:
        alias = {"work": "打工", "harvest": "收获", "deposit": "存款"}
        normalized = alias.get(task_name, task_name)
        if normalized not in player.auto_tasks:
            raise GameError(
                "未知自动任务，可用任务：" + ",".join(player.auto_tasks.keys())
            )
        player.auto_tasks[normalized] = enabled
        await self.repo.save_player(player)
        return normalized

    async def backup(self) -> str:
        path = await self.repo.create_backup()
        return f"已创建备份：{path.name}"

    async def list_backups(self) -> str:
        backups = await self.repo.list_backups()
        if not backups:
            return "暂无备份"
        return "\n".join(path.name for path in backups)

    async def restore_backup(self, file_name: str) -> str:
        await self.repo.restore_backup(file_name)
        return "备份恢复完成"


__all__ = ["PlayerService"]
