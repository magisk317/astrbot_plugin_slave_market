"""Configuration objects shared across the slave market plugin."""

from __future__ import annotations

from dataclasses import dataclass, field
from copy import deepcopy
from pathlib import Path
from typing import Dict, List


def _data_dir() -> Path:
    root = Path(__file__).resolve().parent.parent / "data"
    root.mkdir(parents=True, exist_ok=True)
    (root / "slave_market").mkdir(parents=True, exist_ok=True)
    return root / "slave_market"


@dataclass(slots=True)
class RobberyStrategy:
    """Represents a robbery strategy entry."""

    key: str
    label: str
    success_rate: float
    reward_multiplier: float
    penalty_multiplier: float


@dataclass(slots=True)
class CropProfile:
    name: str
    emoji: str
    grow_hours: int
    yield_min: int
    yield_max: int


@dataclass(slots=True)
class GuardProfile:
    name: str
    hourly_cost: int
    duration_hours: int
    protection_bonus: float


@dataclass(slots=True)
class CreditLevel:
    level: int
    upgrade_cost: int
    deposit_limit: int
    loan_limit: int


@dataclass(slots=True)
class VipDefinition:
    key: str
    hours: int
    description: str


@dataclass(slots=True)
class ShopItem:
    item_id: str
    name: str
    price: int
    description: str
    effect_type: str
    effect_value: int
    target_stat: str | None = None


@dataclass(slots=True)
class LotteryReward:
    label: str
    min_amount: int
    max_amount: int
    weight: float


@dataclass(slots=True)
class GameConfig:
    starting_balance: int = 2000
    work_reward_min: int = 300
    work_reward_max: int = 900
    work_cooldown_seconds: int = 300
    rob_cooldown_seconds: int = 600
    rob_strategies: List[RobberyStrategy] = field(default_factory=list)
    deposit_interest_rate: float = 0.015
    interest_cooldown_seconds: int = 1800
    crops: List[CropProfile] = field(default_factory=list)
    guards: List[GuardProfile] = field(default_factory=list)
    credit_levels: List[CreditLevel] = field(default_factory=list)
    vip_definitions: List[VipDefinition] = field(default_factory=list)
    sponsor_image_name: str = "ai.png"
    data_dir: Path = field(default_factory=_data_dir)
    backups_to_keep: int = 10
    red_packet_fee_rate: float = 0.05
    loot_share_ratio: float = 0.1
    default_auto_tasks: Dict[str, bool] = field(
        default_factory=lambda: {"打工": False, "收获": False, "存款": False}
    )
    jail_term_seconds: int = 900
    jail_work_cooldown_seconds: int = 300
    auto_task_interval_seconds: int = 600
    training_base_cost: int = 800
    training_cost_growth: int = 150
    training_cooldown_seconds: int = 900
    duel_reward_ratio: float = 0.15
    training_gain_min: int = 1
    training_gain_max: int = 4
    shop_items: List[ShopItem] = field(default_factory=list)
    welfare_interval_seconds: int = 7200
    welfare_base_amount: int = 800
    welfare_threshold: int = 15000
    welfare_growth: int = 200
    lottery_cost: int = 500
    lottery_rewards: List[LotteryReward] = field(default_factory=list)
    gambling_min_bet: int = 100
    gambling_max_bet: int = 5000
    allowed_groups: List[str] = field(default_factory=list)
    blocked_groups: List[str] = field(default_factory=list)
    allowed_users: List[str] = field(default_factory=list)
    blocked_users: List[str] = field(default_factory=list)
    initial_admins: List[str] = field(default_factory=list)


DEFAULT_CONFIG = GameConfig(
    rob_strategies=[
        RobberyStrategy("steady", "稳健", 0.8, 0.6, 0.4),
        RobberyStrategy("balanced", "均衡", 0.6, 1.0, 0.8),
        RobberyStrategy("risky", "冒险", 0.35, 1.6, 1.2),
    ],
    crops=[
        CropProfile("小麦", "🌾", 2, 300, 700),
        CropProfile("西瓜", "🍉", 4, 600, 1100),
        CropProfile("咖啡豆", "☕", 3, 500, 900),
        CropProfile("胡萝卜", "🥕", 2, 250, 600),
    ],
    guards=[
        GuardProfile("巡逻保镖", 400, 6, 0.1),
        GuardProfile("精英保镖", 800, 12, 0.25),
        GuardProfile("影卫", 1200, 24, 0.4),
    ],
    credit_levels=[
        CreditLevel(1, 0, 10000, 8000),
        CreditLevel(2, 4000, 20000, 16000),
        CreditLevel(3, 9000, 40000, 30000),
        CreditLevel(4, 15000, 80000, 60000),
    ],
    vip_definitions=[
        VipDefinition("日卡", 24, "24 小时 VIP"),
        VipDefinition("周卡", 24 * 7, "7 天 VIP"),
        VipDefinition("月卡", 24 * 30, "30 天 VIP"),
        VipDefinition("小时卡", 1, "自定义小时卡"),
    ],
    shop_items=[
        ShopItem(
            item_id="str_potion",
            name="力量药剂",
            price=2400,
            description="永久 +3 力量",
            effect_type="stat",
            effect_value=3,
            target_stat="力量",
        ),
        ShopItem(
            item_id="agi_boots",
            name="敏捷长靴",
            price=2200,
            description="永久 +3 敏捷",
            effect_type="stat",
            effect_value=3,
            target_stat="敏捷",
        ),
        ShopItem(
            item_id="vit_shield",
            name="体魄护符",
            price=2600,
            description="永久 +3 体魄",
            effect_type="stat",
            effect_value=3,
            target_stat="体魄",
        ),
    ],
    lottery_rewards=[
        LotteryReward("空手而归", 0, 0, 10),
        LotteryReward("小额奖金", 200, 400, 30),
        LotteryReward("普通奖金", 500, 900, 20),
        LotteryReward("大奖", 1200, 2400, 8),
        LotteryReward("惊喜大奖", 3000, 5000, 2),
    ],
)

__all__ = [
    "GameConfig",
    "DEFAULT_CONFIG",
    "RobberyStrategy",
    "CropProfile",
    "GuardProfile",
    "CreditLevel",
    "VipDefinition",
    "ShopItem",
    "LotteryReward",
    "load_game_config",
]


def _normalize_list(value) -> List[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        if "," in value:
            candidates = value.split(",")
        else:
            candidates = value.splitlines()
        return [item.strip() for item in candidates if item.strip()]
    return []


def load_game_config(overrides: dict | None = None) -> GameConfig:
    """Create a GameConfig instance merged with overrides from dashboard config."""

    config = deepcopy(DEFAULT_CONFIG)
    if not overrides:
        return config

    list_fields = {
        "allowed_groups",
        "blocked_groups",
        "allowed_users",
        "blocked_users",
        "initial_admins",
    }

    for key, value in overrides.items():
        if value is None:
            continue
        if key in list_fields:
            setattr(config, key, _normalize_list(value))
            continue
        if hasattr(config, key):
            setattr(config, key, value)

    return config
