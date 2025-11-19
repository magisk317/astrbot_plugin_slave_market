"""Operations around owning and trading players."""

from __future__ import annotations

from typing import List, Tuple

from ..config import GameConfig
from ..errors import GameError
from ..models import Player, OwnedSlave
from ..repository import GameRepository
from ..utils import format_currency, now_ts
from .ledger import LedgerService


class MarketService:
    def __init__(
        self,
        repo: GameRepository,
        config: GameConfig,
        ledger: LedgerService | None = None,
    ):
        self.repo = repo
        self.config = config
        self.ledger = ledger

    async def _log(
        self,
        player: Player,
        category: str,
        amount: int,
        direction: str,
        description: str,
    ) -> None:
        if self.ledger:
            await self.ledger.record(
                player,
                category=category,
                amount=amount,
                direction=direction,
                description=description,
            )

    @staticmethod
    def evaluate_player(player: Player) -> int:
        base = 800 + player.balance // 2 + player.bank_balance // 4
        base += len(player.owned_slaves) * 300
        if player.vip_until > now_ts():
            base *= 1.2
        return max(500, int(base))

    async def list_market(
        self, exclude_owner: str | None = None, limit: int = 8
    ) -> str:
        players = await self.repo.list_players()
        candidates: List[Tuple[Player, int]] = []
        for player in players:
            if player.owner_id:
                continue
            if exclude_owner and player.player_id == exclude_owner:
                continue
            candidates.append((player, self.evaluate_player(player)))
        candidates.sort(key=lambda item: item[1], reverse=True)
        if not candidates:
            return "暂无待售玩家。"
        lines = ["牛马市场"]
        for player, price in candidates[:limit]:
            lines.append(f"{player.nickname} - {format_currency(price)}")
        return "\n".join(lines)

    async def list_owned(self, player: Player) -> str:
        if not player.owned_slaves:
            return "您还没有牛马。"
        lines = ["我的牛马："]
        for slave in player.owned_slaves.values():
            lines.append(f"{slave.nickname} - {format_currency(slave.price)}")
        return "\n".join(lines)

    async def slave_status(self, keyword: str) -> str:
        players = await self.repo.list_players()
        for player in players:
            if player.nickname == keyword or player.player_id == keyword:
                price = self.evaluate_player(player)
                owner = player.owner_id or "无"
                return (
                    f"{player.nickname}\n身价：{format_currency(price)}\n主人：{owner}"
                )
        raise GameError("未找到该玩家。")

    async def _change_owner(
        self,
        buyer: Player,
        target: Player,
        price: int,
    ) -> str:
        if buyer.player_id == target.player_id:
            raise GameError("不能购买自己。")
        if target.owner_id == buyer.player_id:
            raise GameError("他已经是您的牛马了。")
        discount = 0
        admins = await self.repo.list_admins()
        if buyer.player_id in admins:
            discount = price
        payable = max(0, price - discount)
        if payable > buyer.balance:
            raise GameError("余额不足，购买失败。")
        buyer.balance -= payable
        slave_entry = OwnedSlave(
            user_id=target.player_id,
            nickname=target.nickname,
            price=price,
        )
        buyer.owned_slaves[target.player_id] = slave_entry
        if target.owner_id:
            prev_owner = await self.repo.get_player(target.owner_id)
            if prev_owner:
                prev_owner.owned_slaves.pop(target.player_id, None)
                prev_owner.balance += price
                await self.repo.save_player(prev_owner)
                await self._log(
                    prev_owner, "出售牛马", price, "income", target.nickname
                )
        target.owner_id = buyer.player_id
        await self.repo.save_player(target)
        await self.repo.save_player(buyer)
        await self._log(buyer, "购买牛马", payable, "expense", target.nickname)
        return f"成功购入 {target.nickname}，花费 {format_currency(payable)}"

    async def buy(self, buyer: Player, target: Player) -> str:
        price = self.evaluate_player(target)
        return await self._change_owner(buyer, target, price)

    async def snatch(self, buyer: Player, target: Player) -> str:
        price = int(self.evaluate_player(target) * 2)
        return await self._change_owner(buyer, target, price)

    async def release(self, owner: Player, target: Player) -> str:
        if target.player_id not in owner.owned_slaves:
            raise GameError("他不是您的牛马。")
        owner.owned_slaves.pop(target.player_id, None)
        target.owner_id = None
        await self.repo.save_player(owner)
        await self.repo.save_player(target)
        return f"已放生 {target.nickname}"

    async def redeem(self, player: Player) -> str:
        if not player.owner_id:
            raise GameError("您已经自由了。")
        price = int(self.evaluate_player(player) * 0.6)
        if player.balance < price:
            raise GameError("余额不足以赎身。")
        player.balance -= price
        owner_id = player.owner_id
        player.owner_id = None
        await self.repo.save_player(player)
        await self._log(player, "赎身", price, "expense", "赎身")
        if owner_id:
            owner = await self.repo.get_player(owner_id)
            if owner:
                owner.balance += price
                owner.owned_slaves.pop(player.player_id, None)
                await self.repo.save_player(owner)
                await self._log(owner, "赎身收益", price, "income", player.nickname)
        return f"赎身成功，支付 {format_currency(price)}"


__all__ = ["MarketService"]
