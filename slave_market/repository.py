"""Persistence helpers built around a JSON document."""

from __future__ import annotations

import asyncio
import json
import secrets
from dataclasses import asdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional
import time

from .config import GameConfig
from .errors import NotFound
from .models import Player, VipCard, RedPacket


class GameRepository:
    """Thread-safe repository that keeps all state in a JSON blob."""

    def __init__(self, config: GameConfig):
        self.config = config
        self.base_dir = config.data_dir
        self.state_path = self.base_dir / "state.json"
        self.backup_dir = self.base_dir / "backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()
        self._state: dict | None = None

    async def load(self) -> None:
        async with self._lock:
            if not self.state_path.exists():
                self._state = self._empty_state()
                await self._write_state()
            else:
                raw = await asyncio.to_thread(self.state_path.read_text, "utf-8")
                if not raw.strip():
                    self._state = self._empty_state()
                else:
                    self._state = json.loads(raw)

    def _empty_state(self) -> dict:
        return {
            "players": {},
            "vip_cards": [],
            "red_packets": {},
            "admins": [],
            "transactions": {},
            "system_balance": 0,
            "tax_pool": {"amount": 0, "updated_at": 0},
            "plugin_disabled": False,
            "event_state": {},
        }

    async def _write_state(self) -> None:
        if self._state is None:
            return
        payload = json.dumps(self._state, ensure_ascii=False, indent=2)
        await asyncio.to_thread(self.state_path.write_text, payload, "utf-8")

    async def _ensure_loaded(self) -> None:
        if self._state is None:
            await self.load()

    async def list_players(self) -> List[Player]:
        await self._ensure_loaded()
        assert self._state is not None
        return [Player.from_dict(data) for data in self._state["players"].values()]

    async def get_player(self, player_id: str) -> Optional[Player]:
        await self._ensure_loaded()
        assert self._state is not None
        data = self._state["players"].get(player_id)
        if not data:
            return None
        return Player.from_dict(data)

    async def save_player(self, player: Player) -> Player:
        await self._ensure_loaded()
        assert self._state is not None
        self._state["players"][player.player_id] = player.to_dict()
        await self._write_state()
        return player

    async def delete_player(self, player_id: str) -> None:
        await self._ensure_loaded()
        assert self._state is not None
        self._state["players"].pop(player_id, None)
        await self._write_state()

    async def list_admins(self) -> List[str]:
        await self._ensure_loaded()
        assert self._state is not None
        return list(self._state.get("admins", []))

    async def add_admin(self, player_id: str) -> None:
        await self._ensure_loaded()
        assert self._state is not None
        admins = set(self._state.get("admins", []))
        admins.add(player_id)
        self._state["admins"] = list(admins)
        await self._write_state()

    async def remove_admin(self, player_id: str) -> None:
        await self._ensure_loaded()
        assert self._state is not None
        admins = set(self._state.get("admins", []))
        admins.discard(player_id)
        self._state["admins"] = list(admins)
        await self._write_state()

    async def register_vip_card(self, card: VipCard) -> VipCard:
        await self._ensure_loaded()
        assert self._state is not None
        self._state["vip_cards"].append(card.to_dict())
        await self._write_state()
        return card

    async def update_vip_card(self, card: VipCard) -> None:
        await self._ensure_loaded()
        assert self._state is not None
        cards = self._state["vip_cards"]
        for idx, data in enumerate(cards):
            if data["code"] == card.code:
                cards[idx] = card.to_dict()
                await self._write_state()
                return
        raise NotFound("未找到指定的 VIP 卡密。")

    async def list_vip_cards(self) -> List[VipCard]:
        await self._ensure_loaded()
        assert self._state is not None
        return [VipCard.from_dict(data) for data in self._state["vip_cards"]]

    async def add_red_packet(self, packet: RedPacket) -> RedPacket:
        await self._ensure_loaded()
        assert self._state is not None
        self._state["red_packets"][packet.packet_id] = packet.to_dict()
        await self._write_state()
        return packet

    async def get_red_packet(self, packet_id: str) -> Optional[RedPacket]:
        await self._ensure_loaded()
        assert self._state is not None
        data = self._state["red_packets"].get(packet_id)
        if not data:
            return None
        return RedPacket.from_dict(data)

    async def update_red_packet(self, packet: RedPacket) -> None:
        await self._ensure_loaded()
        assert self._state is not None
        self._state["red_packets"][packet.packet_id] = packet.to_dict()
        await self._write_state()

    async def purge_red_packet(self, packet_id: str) -> None:
        await self._ensure_loaded()
        assert self._state is not None
        self._state["red_packets"].pop(packet_id, None)
        await self._write_state()

    async def create_backup(self) -> Path:
        await self._ensure_loaded()
        assert self._state is not None
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        backup_path = self.backup_dir / f"backup_{timestamp}.json"
        payload = json.dumps(self._state, ensure_ascii=False, indent=2)
        await asyncio.to_thread(backup_path.write_text, payload, "utf-8")
        backups = sorted(self.backup_dir.glob("backup_*.json"))
        if len(backups) > self.config.backups_to_keep:
            for path in backups[: len(backups) - self.config.backups_to_keep]:
                path.unlink(missing_ok=True)
        return backup_path

    async def list_backups(self) -> List[Path]:
        await self._ensure_loaded()
        backups = sorted(self.backup_dir.glob("backup_*.json"))
        return backups

    async def restore_backup(self, file_name: str) -> None:
        target = self.backup_dir / file_name
        if not target.exists():
            raise NotFound("未找到指定的备份文件。")
        raw = await asyncio.to_thread(target.read_text, "utf-8")
        async with self._lock:
            self._state = json.loads(raw)
            await self._write_state()

    async def reset(self) -> None:
        async with self._lock:
            self._state = self._empty_state()
            await self._write_state()

    async def append_transaction(self, player_id: str, entry: dict, max_entries: int = 30) -> None:
        await self._ensure_loaded()
        assert self._state is not None
        tx_map = self._state.setdefault("transactions", {})
        entries = tx_map.setdefault(player_id, [])
        entries.append(entry)
        if len(entries) > max_entries:
            del entries[:-max_entries]
        await self._write_state()

    async def get_transactions(self, player_id: str, limit: int = 10) -> list[dict]:
        await self._ensure_loaded()
        assert self._state is not None
        tx_map = self._state.get("transactions", {})
        entries = tx_map.get(player_id, [])
        return list(entries)[-limit:][::-1]

    async def adjust_system_balance(self, amount: int) -> None:
        await self._ensure_loaded()
        assert self._state is not None
        self._state["system_balance"] = self._state.get("system_balance", 0) + amount
        await self._write_state()

    async def get_system_balance(self) -> int:
        await self._ensure_loaded()
        assert self._state is not None
        return int(self._state.get("system_balance", 0))

    async def adjust_tax_pool(self, amount: int) -> None:
        await self._ensure_loaded()
        assert self._state is not None
        pool = self._state.setdefault("tax_pool", {"amount": 0, "updated_at": 0})
        pool["amount"] = max(0, pool.get("amount", 0) + amount)
        pool["updated_at"] = time.time()
        await self._write_state()

    async def get_tax_pool(self) -> dict:
        await self._ensure_loaded()
        assert self._state is not None
        pool = self._state.get("tax_pool", {"amount": 0, "updated_at": 0})
        return {
            "amount": pool.get("amount", 0),
            "updated_at": pool.get("updated_at", 0),
        }

    async def set_plugin_disabled(self, disabled: bool) -> None:
        await self._ensure_loaded()
        assert self._state is not None
        self._state["plugin_disabled"] = bool(disabled)
        await self._write_state()

    async def is_plugin_disabled(self) -> bool:
        await self._ensure_loaded()
        assert self._state is not None
        return bool(self._state.get("plugin_disabled", False))

    async def get_event_state(self) -> dict:
        await self._ensure_loaded()
        assert self._state is not None
        return dict(self._state.get("event_state", {}))

    async def save_event_state(self, state: dict) -> None:
        await self._ensure_loaded()
        assert self._state is not None
        self._state["event_state"] = state
        await self._write_state()

    @staticmethod
    def generate_code(prefix: str = "vip") -> str:
        return prefix + secrets.token_hex(4)


__all__ = ["GameRepository"]
