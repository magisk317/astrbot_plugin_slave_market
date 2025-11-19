"""玩家账单记录服务。"""

from __future__ import annotations

from ..models import Player
from ..repository import GameRepository
from ..utils import now_ts


class LedgerService:
    def __init__(self, repo: GameRepository, max_entries: int = 30):
        self.repo = repo
        self.max_entries = max_entries

    async def record(
        self,
        player: Player,
        *,
        category: str,
        amount: int,
        direction: str,
        description: str,
    ) -> None:
        entry = {
            "ts": now_ts(),
            "category": category,
            "amount": amount,
            "direction": direction,
            "description": description,
            "balance": player.balance,
            "bank_balance": player.bank_balance,
        }
        await self.repo.append_transaction(player.player_id, entry, self.max_entries)

    async def history(self, player: Player, limit: int = 10) -> list[dict]:
        return await self.repo.get_transactions(player.player_id, limit)
