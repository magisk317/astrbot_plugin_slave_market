"""训练与决斗系统。"""

from __future__ import annotations

import random

from ..config import GameConfig
from ..errors import GameError
from ..models import Player
from ..repository import GameRepository
from ..utils import format_currency, now_ts
from .ledger import LedgerService


class TrainingService:
    ATTRIBUTES = {
        "力量": "力量",
        "power": "力量",
        "体魄": "体魄",
        "耐力": "体魄",
        "endurance": "体魄",
        "敏捷": "敏捷",
        "agility": "敏捷",
    }

    def __init__(
        self,
        repo: GameRepository,
        config: GameConfig,
        ledger: LedgerService | None = None,
    ):
        self.repo = repo
        self.config = config
        self.ledger = ledger

    def _ensure_stats(self, player: Player) -> None:
        for key in {"力量", "体魄", "敏捷"}:
            player.stats.setdefault(key, 0)

    def _resolve_attr(self, keyword: str) -> str:
        attr = self.ATTRIBUTES.get(keyword, keyword)
        if attr not in {"力量", "体魄", "敏捷"}:
            raise GameError("未知属性，仅支持 力量/体魄/敏捷。")
        return attr

    def _training_cost(self, player: Player) -> int:
        self._ensure_stats(player)
        total = sum(player.stats.get(k, 0) for k in ("力量", "体魄", "敏捷"))
        return self.config.training_base_cost + total * self.config.training_cost_growth

    async def train(self, player: Player, keyword: str) -> str:
        attr = self._resolve_attr(keyword)
        now = now_ts()
        if now - player.last_training_time < self.config.training_cooldown_seconds:
            remaining = int(
                self.config.training_cooldown_seconds
                - (now - player.last_training_time)
            )
            raise GameError(f"训练冷却中，{remaining} 秒后再来。")
        cost = self._training_cost(player)
        if player.balance < cost:
            raise GameError("余额不足，训练费用为 " + format_currency(cost))
        player.balance -= cost
        gain = random.randint(
            self.config.training_gain_min, self.config.training_gain_max
        )
        self._ensure_stats(player)
        player.stats[attr] += gain
        player.last_training_time = now
        await self.repo.save_player(player)
        await self.repo.adjust_system_balance(cost)
        if self.ledger:
            await self.ledger.record(
                player,
                category="训练",
                amount=cost,
                direction="expense",
                description=f"训练 {attr}",
            )
        return f"训练完成！{attr}+{gain}，花费 {format_currency(cost)}"

    async def stats_sheet(self, player: Player) -> str:
        self._ensure_stats(player)
        cost = self._training_cost(player)
        lines = [
            "=== 属性面板 ===",
            f"力量：{player.stats['力量']}",
            f"体魄：{player.stats['体魄']}",
            f"敏捷：{player.stats['敏捷']}",
            f"下次训练费用：{format_currency(cost)}",
        ]
        return "\n".join(lines)

    def _combat_power(self, player: Player) -> float:
        self._ensure_stats(player)
        base = (
            player.stats["力量"] * 1.4
            + player.stats["敏捷"] * 1.2
            + player.stats["体魄"] * 1.1
        )
        return base + random.uniform(-5, 5)

    async def duel(self, attacker: Player, defender: Player) -> str:
        if attacker.player_id == defender.player_id:
            raise GameError("不能和自己决斗。")
        atk_power = self._combat_power(attacker)
        def_power = self._combat_power(defender)
        total_asset = max(1, defender.balance + defender.bank_balance)
        reward = max(500, int(total_asset * self.config.duel_reward_ratio))
        if atk_power == def_power:
            atk_power += random.uniform(-1, 1)
        if atk_power > def_power:
            loot = min(reward, defender.balance)
            defender.balance -= loot
            attacker.balance += loot
            await self.repo.save_player(defender)
            await self.repo.save_player(attacker)
            if self.ledger:
                await self.ledger.record(
                    attacker,
                    category="决斗",
                    amount=loot,
                    direction="income",
                    description=f"击败 {defender.nickname}",
                )
                await self.ledger.record(
                    defender,
                    category="决斗",
                    amount=loot,
                    direction="expense",
                    description=f"输给 {attacker.nickname}",
                )
            return f"{attacker.nickname} 胜利，掠夺 {format_currency(loot)}！"
        else:
            fine = min(reward // 2, attacker.balance)
            attacker.balance -= fine
            defender.balance += fine
            await self.repo.save_player(attacker)
            await self.repo.save_player(defender)
            if self.ledger:
                await self.ledger.record(
                    attacker,
                    category="决斗",
                    amount=fine,
                    direction="expense",
                    description=f"输给 {defender.nickname}",
                )
                await self.ledger.record(
                    defender,
                    category="决斗",
                    amount=fine,
                    direction="income",
                    description=f"击败 {attacker.nickname}",
                )
            return f"{defender.nickname} 守住了尊严，反向收取 {format_currency(fine)}！"

    async def apply_stat_bonus(self, player: Player, attr: str, amount: int) -> Player:
        attr_name = self._resolve_attr(attr)
        self._ensure_stats(player)
        player.stats[attr_name] += amount
        await self.repo.save_player(player)
        return player


__all__ = ["TrainingService"]
