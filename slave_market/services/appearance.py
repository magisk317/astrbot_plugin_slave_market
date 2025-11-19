"""玩家外观/称号配置。"""

from __future__ import annotations

from ..errors import GameError
from ..models import Player
from ..repository import GameRepository


class AppearanceService:
    def __init__(self, repo: GameRepository):
        self.repo = repo
        self.max_length = 20

    def _validate(self, text: str) -> str:
        text = text.strip()
        if not text:
            raise GameError("内容不能为空。")
        if len(text) > self.max_length:
            raise GameError(f"内容请在 {self.max_length} 字以内。")
        return text

    async def set_title(self, player: Player, title: str) -> str:
        player.title = self._validate(title)
        await self.repo.save_player(player)
        return player.title

    async def set_signature(self, player: Player, text: str) -> str:
        player.signature = self._validate(text)
        await self.repo.save_player(player)
        return player.signature

    async def profile(self, player: Player) -> str:
        return f"称号：{player.title}\n签名：{player.signature}"
