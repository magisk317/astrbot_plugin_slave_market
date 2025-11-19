"""道具商城相关逻辑。"""

from __future__ import annotations

from ..config import GameConfig, ShopItem
from ..errors import GameError
from ..models import Player
from ..repository import GameRepository
from .training import TrainingService
from .ledger import LedgerService


class ShopService:
    def __init__(
        self,
        repo: GameRepository,
        config: GameConfig,
        training: TrainingService,
        ledger: LedgerService | None = None,
    ):
        self.repo = repo
        self.config = config
        self.training = training
        self.ledger = ledger
        self._catalog = {item.item_id: item for item in config.shop_items}

    def list_items(self) -> str:
        if not self._catalog:
            return "商城暂无道具。"
        lines = ["=== 道具商城 ==="]
        for item in self._catalog.values():
            lines.append(
                f"{item.item_id} - {item.name} - {item.price} 金币\n{item.description}"
            )
        return "\n".join(lines)

    def _get_item(self, item_id: str) -> ShopItem:
        item = self._catalog.get(item_id)
        if not item:
            raise GameError("未找到该道具。")
        return item

    async def buy(self, player: Player, item_id: str) -> str:
        item = self._get_item(item_id)
        if player.balance < item.price:
            raise GameError("余额不足以购买该道具。")
        player.balance -= item.price
        player.inventory[item.item_id] = player.inventory.get(item.item_id, 0) + 1
        await self.repo.save_player(player)
        await self.repo.adjust_system_balance(item.price)
        if self.ledger:
            await self.ledger.record(
                player,
                category="商城购买",
                amount=item.price,
                direction="expense",
                description=item.name,
            )
        return f"已购买 {item.name}，剩余金币 {player.balance}"

    async def use(self, player: Player, item_id: str) -> str:
        item = self._get_item(item_id)
        owned = player.inventory.get(item.item_id, 0)
        if owned <= 0:
            raise GameError("背包中没有该道具。")
        if item.effect_type == "stat" and item.target_stat:
            await self.training.apply_stat_bonus(
                player, item.target_stat, item.effect_value
            )
        else:
            raise GameError("该道具效果暂未实装。")
        player.inventory[item.item_id] = owned - 1
        await self.repo.save_player(player)
        if self.ledger:
            await self.ledger.record(
                player,
                category="道具使用",
                amount=0,
                direction="income",
                description=f"使用 {item.name}",
            )
        return f"使用 {item.name} 成功，剩余 {player.inventory[item.item_id]} 件"

    def inventory(self, player: Player) -> str:
        if not player.inventory:
            return "背包空空如也。"
        lines = ["=== 我的道具 ==="]
        for item_id, count in player.inventory.items():
            item = self._catalog.get(item_id)
            name = item.name if item else item_id
            lines.append(f"{name} x{count}")
        return "\n".join(lines)


__all__ = ["ShopService"]
