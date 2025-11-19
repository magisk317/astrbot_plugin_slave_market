"""Daily event system (e.g., black market auction)."""

from __future__ import annotations

import random
from datetime import datetime

from ..models import Player
from ..repository import GameRepository
from ..utils import format_currency
from .ledger import LedgerService


class EventService:
    def __init__(
        self,
        repo: GameRepository,
        ledger: LedgerService | None = None,
    ):
        self.repo = repo
        self.ledger = ledger
        self.events = [
            {
                "name": "black_market",
                "title": "黑市拍卖",
                "description": "今日限量道具竞拍，出价最高者获得 5000 金币奖励。",
                "reward": 5000,
            },
        ]

    def _today(self) -> str:
        return datetime.utcnow().strftime("%Y-%m-%d")

    async def _settle(self, state: dict) -> None:
        if not state or state.get("name") != "black_market":
            return
        top_id = state.get("top_player")
        reward = state.get("reward", 0)
        if not top_id or reward <= 0:
            return
        player = await self.repo.get_player(top_id)
        if not player:
            return
        player.balance += reward
        await self.repo.save_player(player)
        if self.ledger:
            await self.ledger.record(
                player,
                category="黑市拍卖",
                amount=reward,
                direction="income",
                description="黑市竞拍奖励",
            )

    async def refresh(self) -> dict:
        state = await self.repo.get_event_state()
        if state.get("day") == self._today() and state.get("name"):
            return state
        await self._settle(state)
        event = random.choice(self.events)
        new_state = {
            "day": self._today(),
            "name": event["name"],
            "title": event["title"],
            "description": event["description"],
            "reward": event["reward"],
            "top_bid": 0,
            "top_player": None,
        }
        await self.repo.save_event_state(new_state)
        return new_state

    async def describe(self) -> str:
        state = await self.refresh()
        title = state.get("title", "今日事件")
        desc = state.get("description", "")
        if state.get("name") == "black_market" and state.get("top_bid"):
            desc += f"\n当前最高出价：{format_currency(state['top_bid'])}"
        return f"=== {title} ===\n{desc}"

    async def bid_black_market(self, player: Player, amount: int) -> str:
        if amount <= 0:
            raise ValueError("金额需大于 0。")
        state = await self.refresh()
        if state.get("name") != "black_market":
            raise ValueError("当前没有黑市拍卖。")
        if amount <= state.get("top_bid", 0):
            raise ValueError("出价必须超过当前最高价。")
        if amount > player.balance:
            raise ValueError("余额不足。")
        player.balance -= amount
        refund_notice = ""
        top_id = state.get("top_player")
        top_bid = state.get("top_bid", 0)
        if top_id and top_bid:
            prev = await self.repo.get_player(top_id)
            if prev:
                prev.balance += top_bid
                await self.repo.save_player(prev)
                refund_notice = f"，已退还 {prev.nickname} 的押金"
                if self.ledger:
                    await self.ledger.record(
                        prev,
                        category="黑市拍卖",
                        amount=top_bid,
                        direction="income",
                        description="黑市押金退回",
                    )
        state["top_player"] = player.player_id
        state["top_bid"] = amount
        await self.repo.save_event_state(state)
        await self.repo.save_player(player)
        if self.ledger:
            await self.ledger.record(
                player,
                category="黑市拍卖",
                amount=amount,
                direction="expense",
                description="黑市竞拍押金",
            )
        return f"出价成功{refund_notice}。当前领先：{format_currency(amount)}"
