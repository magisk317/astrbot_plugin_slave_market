"""Dataclasses representing the in-memory game state."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional
import time


def _ts() -> float:
    return time.time()


@dataclass(slots=True)
class OwnedSlave:
    user_id: str
    nickname: str
    price: int
    loyalty: float = 0.5

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "OwnedSlave":
        return cls(**data)


@dataclass(slots=True)
class CropPlot:
    crop_name: str
    emoji: str
    planted_at: float
    grow_hours: int
    yield_min: int
    yield_max: int

    def ready(self) -> bool:
        return time.time() - self.planted_at >= self.grow_hours * 3600

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "CropPlot":
        return cls(**data)


@dataclass(slots=True)
class GuardContract:
    name: str
    expires_at: float
    protection_bonus: float

    def active(self) -> bool:
        return time.time() < self.expires_at

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "GuardContract":
        return cls(**data)


@dataclass(slots=True)
class Loan:
    amount: int
    rate: float
    issued_at: float
    repaid: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Loan":
        return cls(**data)


@dataclass(slots=True)
class Player:
    player_id: str
    platform: str
    user_id: str
    nickname: str
    group_id: str | None
    balance: int = 0
    bank_balance: int = 0
    credit_level: int = 1
    deposit_limit: int = 10000
    interest_ready_at: float = 0.0
    owner_id: str | None = None
    owned_slaves: Dict[str, OwnedSlave] = field(default_factory=dict)
    last_work_time: float = 0.0
    last_rob_time: float = 0.0
    farmland: CropPlot | None = None
    guard: GuardContract | None = None
    vip_until: float = 0.0
    loan: Loan | None = None
    jail_until: float = 0.0
    jail_cooldown_end: float = 0.0
    jail_coin: int = 0
    jail_reason: str = ""
    auto_tasks: Dict[str, bool] = field(default_factory=dict)
    stats: Dict[str, int] = field(default_factory=dict)
    inventory: Dict[str, int] = field(default_factory=dict)
    achievements: Dict[str, bool] = field(default_factory=dict)
    created_at: float = field(default_factory=_ts)
    updated_at: float = field(default_factory=_ts)
    last_auto_task: float = 0.0
    last_training_time: float = 0.0
    welfare_level: int = 0
    last_welfare_time: float = 0.0
    welfare_income: int = 0
    title: str = "普通公民"
    signature: str = "热爱生活"

    def to_dict(self) -> dict:
        data = asdict(self)
        if self.farmland:
            data["farmland"] = self.farmland.to_dict()
        if self.guard:
            data["guard"] = self.guard.to_dict()
        if self.loan:
            data["loan"] = self.loan.to_dict()
        data["owned_slaves"] = {k: v.to_dict() for k, v in self.owned_slaves.items()}
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Player":
        farmland = data.get("farmland")
        guard = data.get("guard")
        loan = data.get("loan")
        owned = data.get("owned_slaves", {})
        data = dict(data)
        if farmland:
            data["farmland"] = CropPlot.from_dict(farmland)
        if guard:
            data["guard"] = GuardContract.from_dict(guard)
        if loan:
            data["loan"] = Loan.from_dict(loan)
        data["owned_slaves"] = {
            slave_id: OwnedSlave.from_dict(slave_data)
            for slave_id, slave_data in owned.items()
        }
        data.setdefault("inventory", {})
        data.setdefault("stats", {})
        data.setdefault("last_auto_task", 0.0)
        data.setdefault("last_training_time", 0.0)
        data.setdefault("welfare_level", 0)
        data.setdefault("last_welfare_time", 0.0)
        data.setdefault("welfare_income", 0)
        data.setdefault("title", "普通公民")
        data.setdefault("signature", "热爱生活")
        data.setdefault("achievements", {})
        return cls(**data)


@dataclass(slots=True)
class VipCard:
    code: str
    card_type: str
    hours: int
    created_at: float
    redeemed_by: str | None = None
    redeemed_at: float | None = None
    duration_override: Optional[int] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "VipCard":
        return cls(**data)


@dataclass(slots=True)
class RedPacket:
    packet_id: str
    sender_id: str
    total_amount: int
    parts: int
    created_at: float
    fee_rate: float
    claimed_amount: int = 0
    claimed_by: Dict[str, int] = field(default_factory=dict)

    def finished(self) -> bool:
        return (
            len(self.claimed_by) >= self.parts
            or self.claimed_amount >= self.total_amount
        )

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "RedPacket":
        return cls(**data)


__all__ = [
    "Player",
    "OwnedSlave",
    "CropPlot",
    "GuardContract",
    "Loan",
    "VipCard",
    "RedPacket",
]
