"""Central orchestrator for the AstrBot slave market."""

from __future__ import annotations

import random
import re
from datetime import datetime
import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Sequence

from astrbot.api.event import AstrMessageEvent
from astrbot.api import logger

from .config import DEFAULT_CONFIG, GameConfig
from .errors import GameError
from .models import Player
from .repository import GameRepository
from .services.players import PlayerService
from .services.economy import EconomyService
from .services.market import MarketService
from .services.farm import FarmService
from .services.vip import VipService
from .services.jail import JailService
from .services.security import GuardService
from .services.training import TrainingService
from .services.shop import ShopService
from .services.welfare import WelfareService
from .services.lottery import LotteryService
from .services.appearance import AppearanceService
from .services.automation import AutomationService
from .services.ledger import LedgerService
from .services.weather import WeatherService
from .services.achievements import AchievementService, Achievement
from .services.events import EventService
from .services.gamble import GamblingService
from .utils import extract_first_at, normalize_amount, now_ts, format_currency


@dataclass(slots=True)
class CommandResult:
    message: str | None = None
    image: str | None = None


class SlaveMarketEngine:
    COMMAND_ALIASES: Dict[str, str] = {
        "玩家帮助": "help",
        "我的信息": "info",
        "重开": "reset",
        "重开玩家": "reset_target",
        "牛马市场": "market",
        "牛马列表": "market",
        "购买玩家": "buy",
        "抢牛马": "snatch",
        "放生": "release",
        "赎身": "redeem",
        "牛马排行": "owner_rank",
        "我的牛马": "owned",
        "牛马状态": "status",
        "打工": "work",
        "抢劫": "rob",
        "存款": "deposit",
        "取款": "withdraw",
        "银行信息": "bank",
        "领取利息": "interest",
        "升级信用": "credit",
        "贷款": "loan",
        "还款": "repay",
        "转账": "transfer",
        "发红包": "red_packet",
        "抢红包": "grab_packet",
        "种地": "plant",
        "收获": "harvest",
        "作物状态": "crop_status",
        "保镖市场": "guards",
        "雇佣保镖": "hire_guard",
        "保镖状态": "guard_status",
        "身价排行": "value_rank",
        "资金排行": "wealth_rank",
        "天气": "weather",
        "踩缝纫机": "prison_work",
        "监狱状态": "prison_status",
        "监狱名单": "prison_list",
        "交保出狱": "bail",
        "训练": "train",
        "属性面板": "stats",
        "决斗": "duel",
        "道具商城": "shop",
        "购买道具": "buy_item",
        "我的道具": "inventory",
        "使用道具": "use_item",
        "抽奖": "lottery",
        "形象": "appearance",
        "设置称号": "set_title",
        "设置签名": "set_signature",
        "玩家统计": "player_stats",
        "玩家档案": "player_profile",
        "查找玩家": "search_players",
        "玩家指南": "guide",
        "游戏概览": "system_overview",
        "系统资金": "system_overview",
        "税收奖池": "tax_pool",
        "账单": "statement",
        "禁用牛马": "disable",
        "启用牛马": "enable",
        "成就": "achievement",
        "今日事件": "event_today",
        "黑市竞拍": "event_bid",
        "猜硬币": "coin",
        "掷骰": "dice",
        "重置游戏": "wipe",
        "添加管理员": "add_admin",
        "移除管理员": "remove_admin",
        "管理员列表": "admins",
        "赞助": "sponsor",
        "赞助权益": "sponsor_bonus",
        "生成vip卡": "vip_generate",
        "vip兑换": "vip_redeem",
        "vip状态": "vip_status",
        "自动任务": "auto_task",
        "备份列表": "backup_list",
        "立即备份": "backup_now",
        "恢复备份": "backup_restore",
        "领取补助": "welfare",
    }

    @classmethod
    def build_pattern(cls) -> str:
        return (
            r"^("
            + "|".join(map(re.escape, cls.COMMAND_ALIASES.keys()))
            + r")(?:\\s+.*)?$"
        )

    def __init__(self, config: GameConfig | None = None):
        self.config = config or DEFAULT_CONFIG
        self.repo = GameRepository(self.config)
        self.players = PlayerService(self.repo, self.config)
        self.ledger = LedgerService(self.repo)
        self.economy = EconomyService(self.repo, self.config, self.ledger)
        self.market = MarketService(self.repo, self.config, self.ledger)
        self.farm = FarmService(self.repo, self.config, self.ledger)
        self.vip = VipService(self.repo, self.config)
        self.jail = JailService(self.repo, self.config, self.market.evaluate_player)
        self.guard = GuardService(self.repo, self.config)
        self.training = TrainingService(self.repo, self.config, self.ledger)
        self.shop = ShopService(self.repo, self.config, self.training, self.ledger)
        self.welfare = WelfareService(self.repo, self.config, self.ledger)
        self.lottery = LotteryService(self.repo, self.config, self.ledger)
        self.appearance = AppearanceService(self.repo)
        self.achievements = AchievementService(
            self.repo,
            [
                Achievement(
                    "rich",
                    "高净值玩家",
                    "资产超过 10 万",
                    lambda p: p.balance + p.bank_balance >= 100000,
                ),
                Achievement(
                    "collector",
                    "牛马收集者",
                    "拥有 3 名以上牛马",
                    lambda p: len(p.owned_slaves) >= 3,
                ),
                Achievement(
                    "farmer",
                    "农场达人",
                    lambda p: p.stats.get("力量", 0) >= 5,
                ),
            ],
        )
        self.automation = AutomationService(
            self.repo, self.config, self.economy, self.farm
        )
        self.weather = WeatherService()
        self.events = EventService(self.repo, self.ledger)
        self.gamble = GamblingService(self.repo, self.config, self.ledger)
        self._command_pattern = re.compile(self.build_pattern())
        self._automation_task: asyncio.Task | None = None

    @property
    def command_regex(self) -> str:
        return self._command_pattern.pattern

    @staticmethod
    def _format_ts(timestamp: float) -> str:
        return datetime.fromtimestamp(timestamp).strftime("%m-%d %H:%M")

    async def initialize(self) -> None:
        await self.repo.load()
        if not self._automation_task:
            self._automation_task = asyncio.create_task(self._run_automation())

    async def dispatch(self, event: AstrMessageEvent) -> Optional[CommandResult]:
        text = event.get_message_str().strip()
        match = self._command_pattern.match(text)
        if not match:
            return None
        allowed, reason, silent = self._check_access(event)
        if not allowed:
            return None if silent else CommandResult(reason or "权限受限。")
        command = match.group(1)
        args = text[len(command) :].strip().split()
        handler_name = self.COMMAND_ALIASES[command]
        handler = getattr(self, f"cmd_{handler_name}", None)
        if not handler:
            logger.warning("missing handler for %s", handler_name)
            return CommandResult("指令暂未实现。")
        player = await self.players.ensure_player(event)
        is_admin = player.player_id in await self.repo.list_admins()
        if await self.repo.is_plugin_disabled() and handler_name != "enable":
            if not is_admin:
                return CommandResult("牛马系统维护中，请稍后再试。")
        try:
            result = await handler(player, event, args)
        except GameError as exc:
            return CommandResult(str(exc))
        except Exception as exc:
            logger.exception("command %s crashed", command)
            return CommandResult(f"执行失败：{exc}")
        return result

    async def cmd_help(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        lines = [
            "大牛马时代指令速查",
            "基础：我的信息 / 打工 / 抢劫",
            "经济：存款/取款/领取利息/转账/贷款",
            "市场：牛马市场/购买玩家/放生/赎身",
            "系统：种地/收获/保镖/红包/VIP",
            "管理：备份列表/立即备份/恢复备份",
        ]
        return CommandResult("\n".join(lines))

    async def cmd_guide(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        lines = [
            "=== 新手指南 ===",
            "1. 打工或领取补助快速获得启动资金。",
            "2. 存款提升利息与信用，升级后提高银行上限。",
            "3. 购买/训练牛马，雇佣保镖降低被抢风险。",
            "4. 使用商城道具与训练指令提升属性，参与决斗增身价。",
            "5. 管理员请定期备份或恢复，保障数据安全。",
        ]
        return CommandResult("\n".join(lines))

    async def cmd_info(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        snapshot = await self.players.snapshot(player)
        return CommandResult(snapshot)

    async def cmd_reset(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        await self.players.reset_player(player)
        return CommandResult("角色已重置，余额恢复至起始。")

    async def cmd_reset_target(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        await self.players.require_admin(player)
        target = await self._resolve_target(event, args)
        await self.players.reset_player(target)
        return CommandResult(f"已重置 {target.nickname} 的数据。")

    async def cmd_market(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        info = await self.market.list_market(exclude_owner=player.player_id)
        return CommandResult(info)

    async def cmd_owned(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        text = await self.market.list_owned(player)
        return CommandResult(text)

    async def cmd_status(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        if args:
            text = await self.market.slave_status(args[0])
            return CommandResult(text)
        target = await self._resolve_target(event, args)
        text = await self.market.slave_status(target.nickname)
        return CommandResult(text)

    async def cmd_buy(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        target = await self._resolve_target(event, args)
        text = await self.market.buy(player, target)
        return CommandResult(text)

    async def cmd_snatch(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        target = await self._resolve_target(event, args)
        text = await self.market.snatch(player, target)
        return CommandResult(text)

    async def cmd_release(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        target = await self._resolve_target(event, args)
        text = await self.market.release(player, target)
        return CommandResult(text)

    async def cmd_redeem(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        text = await self.market.redeem(player)
        return CommandResult(text)

    async def cmd_owner_rank(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        text = await self.players.ranking("owner")
        return CommandResult(text)

    async def cmd_value_rank(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        text = await self.players.ranking("value")
        return CommandResult(text)

    async def cmd_wealth_rank(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        text = await self.players.ranking("wealth")
        return CommandResult(text)

    async def cmd_work(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        text = await self.economy.work(player)
        return CommandResult(text)

    async def cmd_rob(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        target = await self._resolve_target(event, args)
        strategy = args[1] if len(args) > 1 else "balanced"
        text = await self.economy.rob(player, target, strategy)
        return CommandResult(text)

    async def cmd_deposit(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        amount = self._require_amount(args)
        text = await self.economy.deposit(player, amount)
        return CommandResult(text)

    async def cmd_withdraw(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        amount = self._require_amount(args)
        text = await self.economy.withdraw(player, amount)
        return CommandResult(text)

    async def cmd_interest(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        text = await self.economy.collect_interest(player)
        return CommandResult(text)

    async def cmd_bank(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        text = await self.economy.bank_info(player)
        return CommandResult(text)

    async def cmd_credit(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        text = await self.economy.upgrade_credit(player)
        return CommandResult(text)

    async def cmd_transfer(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        if len(args) < 2:
            raise GameError("用法：转账 [@对方] <金额>")
        target = await self._resolve_target(event, args)
        amount = self._require_amount(args[1:])
        text = await self.economy.transfer(player, target, amount)
        return CommandResult(text)

    async def cmd_loan(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        amount = self._require_amount(args)
        text = await self.economy.request_loan(player, amount)
        return CommandResult(text)

    async def cmd_repay(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        amount = self._require_amount(args)
        text = await self.economy.repay_loan(player, amount)
        return CommandResult(text)

    async def cmd_red_packet(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        if len(args) < 2:
            raise GameError("用法：发红包 <金额> <份数>")
        amount = self._require_amount([args[0]])
        try:
            parts = int(args[1])
        except ValueError:
            raise GameError("份数必须是整数。")
        text, _ = await self.economy.send_red_packet(player, amount, parts)
        return CommandResult(text)

    async def cmd_grab_packet(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        if not args:
            raise GameError("请提供红包 ID。")
        text = await self.economy.grab_red_packet(player, args[0])
        return CommandResult(text)

    async def cmd_plant(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        if not args:
            raise GameError("请指定作物。")
        text = await self.farm.plant(player, args[0])
        return CommandResult(text)

    async def cmd_crop_status(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        text = await self.farm.status(player)
        return CommandResult(text)

    async def cmd_harvest(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        text = await self.farm.harvest(player)
        return CommandResult(text)

    async def cmd_guards(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        return CommandResult(self.guard.catalog())

    async def cmd_hire_guard(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        if not args:
            raise GameError("请指定保镖名称。")
        text = await self.guard.hire(player, args[0])
        return CommandResult(text)

    async def cmd_guard_status(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        text = await self.guard.status(player)
        return CommandResult(text)

    async def cmd_weather(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        status = self.weather.get_status()
        weather = status["weather"]
        season = status["season"]
        lines = [
            f"天气：{weather.name} - {weather.description}",
            f"季节：{season.name} - {season.description}",
            f"气温：{status['temperature']}°C",
            f"作物成长倍率：{status['crop_rate'] * 100:.0f}%",
            f"打工收益倍率：{weather.work_income * 100:.0f}%",
        ]
        return CommandResult("\n".join(lines))

    async def cmd_train(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        if not args:
            raise GameError("请输入要训练的属性（力量/体魄/敏捷）。")
        text = await self.training.train(player, args[0])
        return CommandResult(text)

    async def cmd_stats(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        text = await self.training.stats_sheet(player)
        return CommandResult(text)

    async def cmd_duel(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        target = await self._resolve_target(event, args)
        text = await self.training.duel(player, target)
        return CommandResult(text)

    async def cmd_shop(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        return CommandResult(self.shop.list_items())

    async def cmd_buy_item(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        if not args:
            raise GameError("请输入道具 ID。")
        text = await self.shop.buy(player, args[0])
        return CommandResult(text)

    async def cmd_inventory(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        text = self.shop.inventory(player)
        return CommandResult(text)

    async def cmd_use_item(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        if not args:
            raise GameError("请输入要使用的道具 ID。")
        text = await self.shop.use(player, args[0])
        return CommandResult(text)

    async def cmd_welfare(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        text = await self.welfare.claim(player)
        return CommandResult(text)

    async def cmd_lottery(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        text = await self.lottery.draw(player)
        return CommandResult(text)

    async def cmd_appearance(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        return CommandResult(await self.appearance.profile(player))

    async def cmd_set_title(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        if not args:
            raise GameError("请输入新的称号。")
        title = await self.appearance.set_title(player, args[0])
        return CommandResult(f"称号已更新为：{title}")

    async def cmd_set_signature(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        if not args:
            raise GameError("请输入新的签名。")
        signature = await self.appearance.set_signature(player, args[0])
        return CommandResult(f"签名已更新：{signature}")

    async def cmd_player_stats(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        text = await self.players.stats_overview()
        return CommandResult(text)

    async def cmd_player_profile(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        target = player
        if args:
            target = await self._resolve_target(event, args)
        profile = await self.players.snapshot(target)
        appearance = await self.appearance.profile(target)
        return CommandResult(f"{profile}\n{appearance}")

    async def cmd_search_players(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        if not args:
            raise GameError("请输入关键字。")
        matches = await self.players.search(args[0])
        if not matches:
            return CommandResult("未找到匹配玩家。")
        lines = ["搜索结果："]
        for target in matches:
            lines.append(f"{target.nickname} ({target.player_id})")
        return CommandResult("\n".join(lines))

    async def cmd_statement(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        tokens = list(args)
        limit = 10
        if tokens and tokens[0].isdigit():
            limit = max(1, min(30, int(tokens.pop(0))))
        target = player
        if tokens:
            target = await self._resolve_target(event, tokens)
        history = await self.ledger.history(target, limit)
        if not history:
            return CommandResult("暂无账单记录。")
        lines = [f"=== {target.nickname} 最近账单 ==="]
        for entry in history:
            ts = self._format_ts(entry.get("ts", now_ts()))
            direction = "收入" if entry.get("direction") == "income" else "支出"
            amount = format_currency(entry.get("amount", 0))
            desc = entry.get("description", "")
            lines.append(f"[{ts}] {direction} {amount} - {desc}")
        return CommandResult("\n".join(lines))

    async def cmd_achievement(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        unlocked = await self.achievements.evaluate(player)
        details = self.achievements.progress(player)
        if unlocked:
            return CommandResult(f"解锁成就：{', '.join(unlocked)}\n{details}")
        return CommandResult(details)

    async def cmd_event_today(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        text = await self.events.describe()
        return CommandResult(text)

    async def cmd_event_bid(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        amount = self._require_amount(args)
        try:
            result = await self.events.bid_black_market(player, amount)
        except ValueError as exc:
            raise GameError(str(exc))
        return CommandResult(result)

    async def cmd_coin(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        amount = self._require_amount(args)
        try:
            text = await self.gamble.coin_toss(player, amount)
        except GameError:
            raise
        except Exception as exc:
            raise GameError(str(exc))
        return CommandResult(text)

    async def cmd_dice(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        amount = self._require_amount(args)
        try:
            text = await self.gamble.dice(player, amount)
        except GameError:
            raise
        except Exception as exc:
            raise GameError(str(exc))
        return CommandResult(text)

    async def cmd_system_overview(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        stats = await self.players.stats_overview()
        economy = await self.players.economy_overview()
        system_balance = await self.repo.get_system_balance()
        tax_pool = await self.repo.get_tax_pool()
        pool_time = self._format_ts(tax_pool.get("updated_at", now_ts()))
        lines = [
            stats,
            economy,
            f"系统资金：{format_currency(system_balance)}",
            f"税收奖池：{format_currency(tax_pool.get('amount', 0))}（更新：{pool_time}）",
        ]
        return CommandResult("\n".join(lines))

    async def cmd_tax_pool(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        pool = await self.repo.get_tax_pool()
        amount = format_currency(pool.get("amount", 0))
        updated = self._format_ts(pool.get("updated_at", now_ts()))
        return CommandResult(f"当前税收奖池：{amount}\n最后更新：{updated}")

    async def cmd_prison_work(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        text = await self.jail.work(player)
        return CommandResult(text)

    async def cmd_prison_status(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        text = await self.jail.status(player)
        return CommandResult(text)

    async def cmd_prison_list(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        text = await self.jail.inmates()
        return CommandResult(text)

    async def cmd_bail(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        text = await self.jail.bail(player)
        return CommandResult(text)

    async def cmd_vip_generate(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        await self.players.require_admin(player)
        if len(args) < 2:
            raise GameError("用法：生成vip卡 <类型> <数量> [时长]")
        card_type = args[0]
        amount = int(args[1])
        hint = args[2] if len(args) > 2 else None
        cards = await self.vip.generate(card_type, amount, hint)
        codes = ", ".join(card.code for card in cards)
        return CommandResult(f"生成成功：{codes}")

    async def cmd_vip_redeem(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        if not args:
            raise GameError("请输入卡密。")
        text = await self.vip.redeem(player, args[0])
        return CommandResult(text)

    async def cmd_vip_status(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        text = await self.vip.status(player)
        return CommandResult(text)

    async def cmd_auto_task(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        if not args:
            tasks = "\n".join(
                f"{name}: {'开启' if enabled else '关闭'}"
                for name, enabled in player.auto_tasks.items()
            )
            return CommandResult(tasks)
        task = args[0]
        state = args[1] if len(args) > 1 else "on"
        enabled = state in ("on", "开启", "开", "1")
        normalized = await self.players.toggle_auto_task(player, task, enabled)
        return CommandResult(
            f"已将 {normalized} 设置为 {'开启' if enabled else '关闭'}"
        )

    async def cmd_admins(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        admins = await self.players.list_admins()
        if not admins:
            return CommandResult("暂无管理员。")
        players = await self.repo.list_players()
        lookup = {p.player_id: p.nickname for p in players}
        text = "管理员：" + ", ".join(lookup.get(pid, pid) for pid in admins)
        return CommandResult(text)

    async def cmd_add_admin(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        await self.players.require_admin(player)
        target = await self._resolve_target(event, args)
        await self.players.add_admin(target.player_id)
        return CommandResult(f"已授予 {target.nickname} 管理权限。")

    async def cmd_remove_admin(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        await self.players.require_admin(player)
        target = await self._resolve_target(event, args)
        await self.players.remove_admin(target.player_id)
        return CommandResult(f"已移除 {target.nickname} 的管理权限。")

    async def cmd_backup_list(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        await self.players.require_admin(player)
        text = await self.players.list_backups()
        return CommandResult(text)

    async def cmd_backup_now(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        await self.players.require_admin(player)
        text = await self.players.backup()
        return CommandResult(text)

    async def cmd_backup_restore(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        await self.players.require_admin(player)
        if not args:
            raise GameError("请提供文件名。")
        text = await self.players.restore_backup(args[0])
        return CommandResult(text)

    async def cmd_wipe(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        await self.players.require_admin(player)
        await self.repo.reset()
        return CommandResult("数据已重置。")

    async def cmd_sponsor(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        image_path = (
            Path(__file__).resolve().parent.parent / self.config.sponsor_image_name
        )
        if image_path.exists():
            return CommandResult(image=str(image_path))
        return CommandResult("请在插件目录放置 ai.png 以提供赞助二维码。")

    async def cmd_sponsor_bonus(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        text = "VIP 特权：自动任务、手续费减免、尊贵称号等。"
        return CommandResult(text)

    def _require_amount(self, args: Sequence[str]) -> int:
        if not args:
            raise GameError("缺少金额参数。")
        try:
            return normalize_amount(args[0])
        except ValueError:
            raise GameError("金额格式无效。")

    async def _resolve_target(
        self, event: AstrMessageEvent, args: Sequence[str]
    ) -> Player:
        mention_id = extract_first_at(event)
        if mention_id:
            candidate = await self.repo.get_player(
                PlayerService.player_id(event.get_platform_id(), mention_id)
            )
            if candidate:
                return candidate
        if not args:
            raise GameError("请 @ 对方或提供昵称。")
        keyword = args[0]
        target = await self.players.find_by_keyword(keyword)
        if not target:
            raise GameError("未找到目标玩家。")
        return target

    async def _run_automation(self) -> None:
        interval = max(60, self.config.auto_task_interval_seconds)
        while True:
            try:
                await self.automation.run_cycle()
            except Exception:
                logger.exception("自动任务执行失败")
            await asyncio.sleep(interval)

    def _check_access(self, event: AstrMessageEvent) -> tuple[bool, str | None, bool]:
        cfg = self.config
        group_id = event.get_group_id() or ""
        user_id = event.get_sender_id()
        if cfg.blocked_users and user_id in cfg.blocked_users:
            return False, "您已被列入黑名单。", False
        if cfg.allowed_users and user_id not in cfg.allowed_users:
            return False, "仅限白名单用户使用。", False
        if group_id:
            if cfg.blocked_groups and group_id in cfg.blocked_groups:
                return False, None, True
            if cfg.allowed_groups and group_id not in cfg.allowed_groups:
                return False, "本群未被授权使用。", False
        elif cfg.allowed_groups:
            return False, "仅限指定群使用。", False
        return True, None, False

    async def shutdown(self) -> None:
        if self._automation_task:
            self._automation_task.cancel()
            try:
                await self._automation_task
            except asyncio.CancelledError:
                pass
            self._automation_task = None


__all__ = ["SlaveMarketEngine", "CommandResult"]
    async def cmd_disable(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        await self.players.require_admin(player)
        await self.repo.set_plugin_disabled(True)
        return CommandResult("已禁用牛马系统，普通玩家暂时无法使用指令。")

    async def cmd_enable(
        self, player: Player, event: AstrMessageEvent, args: Sequence[str]
    ):
        await self.players.require_admin(player)
        await self.repo.set_plugin_disabled(False)
        return CommandResult("牛马系统已恢复正常。")
