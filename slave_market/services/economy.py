"""Banking, robbery and red packet logic."""

from __future__ import annotations

import random
import time
from typing import Tuple

from ..config import GameConfig
from ..errors import GameError, NotFound
from ..models import Player, RedPacket, Loan
from ..repository import GameRepository
from ..utils import clamp, format_currency, now_ts
from .ledger import LedgerService


class EconomyService:
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

    async def work(self, actor: Player) -> str:
        now = now_ts()
        if now - actor.last_work_time < self.config.work_cooldown_seconds:
            wait = int(self.config.work_cooldown_seconds - (now - actor.last_work_time))
            raise GameError(f"打工冷却中，{wait} 秒后再来。")
        reward = random.randint(
            self.config.work_reward_min, self.config.work_reward_max
        )
        actor.balance += reward
        actor.last_work_time = now
        actor.updated_at = now
        await self.repo.save_player(actor)
        await self._log(actor, "打工", reward, "income", "打工收益")
        share_note = ""
        if actor.owner_id:
            owner = await self.repo.get_player(actor.owner_id)
            if owner:
                share = max(1, int(reward * self.config.loot_share_ratio))
                owner.balance += share
                owner.updated_at = now
                await self.repo.save_player(owner)
                await self._log(owner, "贡金", share, "income", "牛马打工分成")
                share_note = f"\n向雇主进贡 {format_currency(share)}。"
        return f"打工成功，获得 {format_currency(reward)}。{share_note}".strip()

    async def rob(self, attacker: Player, target: Player, strategy_key: str) -> str:
        if attacker.player_id == target.player_id:
            raise GameError("不要自抢。")
        now = now_ts()
        if now - attacker.last_rob_time < self.config.rob_cooldown_seconds:
            wait = int(
                self.config.rob_cooldown_seconds - (now - attacker.last_rob_time)
            )
            raise GameError(f"抢劫冷却中，{wait} 秒后再来。")
        strategy = next(
            (s for s in self.config.rob_strategies if s.key == strategy_key), None
        )
        if not strategy:
            raise GameError(
                "未知策略，可用策略："
                + ",".join(s.key for s in self.config.rob_strategies)
            )
        guard_bonus = (
            target.guard.protection_bonus
            if target.guard and target.guard.active()
            else 0
        )
        success_rate = clamp(strategy.success_rate - guard_bonus, 0.05, 0.95)
        attacker.last_rob_time = now
        roll = random.random()
        if roll <= success_rate and target.balance > 0:
            loot = int(
                target.balance * strategy.reward_multiplier * random.uniform(0.2, 0.6)
            )
            loot = max(1, min(loot, target.balance))
            target.balance -= loot
            attacker.balance += loot
            await self.repo.save_player(target)
            await self.repo.save_player(attacker)
            await self._log(attacker, "抢劫", loot, "income", f"抢劫 {target.nickname}")
            await self._log(
                target, "被抢", loot, "expense", f"被 {attacker.nickname} 抢劫"
            )
            return f"抢劫成功！掠夺 {format_currency(loot)} (成功率 {success_rate * 100:.0f}%)"
        else:
            loss = int(
                attacker.balance
                * strategy.penalty_multiplier
                * random.uniform(0.1, 0.4)
            )
            loss = max(1, min(loss, attacker.balance))
            attacker.balance -= loss
            await self.repo.save_player(attacker)
            await self._log(attacker, "抢劫失败", loss, "expense", "抢劫罚款")
            if target.guard and target.guard.active():
                target.balance += loss
                await self.repo.save_player(target)
                await self._log(target, "保镖赔付", loss, "income", "保镖赔付")
            return f"抢劫失败，被罚款 {format_currency(loss)}"

    async def deposit(self, player: Player, amount: int) -> str:
        if amount <= 0:
            raise GameError("金额必须大于 0。")
        if amount > player.balance:
            raise GameError("余额不足。")
        if player.bank_balance + amount > player.deposit_limit:
            raise GameError("超过存款上限。")
        player.balance -= amount
        player.bank_balance += amount
        player.updated_at = now_ts()
        await self.repo.save_player(player)
        await self._log(player, "存款", amount, "expense", "存入银行")
        return f"已存入 {format_currency(amount)}"

    async def withdraw(self, player: Player, amount: int) -> str:
        if amount <= 0:
            raise GameError("金额必须大于 0。")
        if amount > player.bank_balance:
            raise GameError("存款不足。")
        player.bank_balance -= amount
        player.balance += amount
        player.updated_at = now_ts()
        await self.repo.save_player(player)
        await self._log(player, "取款", amount, "income", "取出存款")
        return f"已取出 {format_currency(amount)}"

    async def collect_interest(self, player: Player) -> str:
        now = now_ts()
        if now < player.interest_ready_at:
            remain = int(player.interest_ready_at - now)
            raise GameError(f"利息冷却中，{remain} 秒后可领取。")
        interest = int(player.bank_balance * self.config.deposit_interest_rate)
        if interest <= 0:
            raise GameError("没有可领取的利息。")
        player.bank_balance += interest
        player.interest_ready_at = now + self.config.interest_cooldown_seconds
        player.updated_at = now
        await self.repo.save_player(player)
        await self.repo.adjust_system_balance(-interest)
        await self._log(player, "利息", interest, "income", "领取利息")
        return f"领取利息 {format_currency(interest)}"

    async def bank_info(self, player: Player) -> str:
        lines = [
            f"存款：{format_currency(player.bank_balance)} / 上限 {format_currency(player.deposit_limit)}",
            f"利率：{self.config.deposit_interest_rate * 100:.1f}%",
        ]
        if player.interest_ready_at > now_ts():
            lines.append(f"利息冷却：{int(player.interest_ready_at - now_ts())} 秒")
        return "\n".join(lines)

    async def upgrade_credit(self, player: Player) -> str:
        current_idx = player.credit_level - 1
        if current_idx >= len(self.config.credit_levels) - 1:
            raise GameError("已达到最高等级。")
        next_level = self.config.credit_levels[current_idx + 1]
        if player.balance < next_level.upgrade_cost:
            raise GameError(
                "余额不足，升级需 " + format_currency(next_level.upgrade_cost)
            )
        player.balance -= next_level.upgrade_cost
        player.credit_level = next_level.level
        player.deposit_limit = next_level.deposit_limit
        player.updated_at = now_ts()
        await self.repo.save_player(player)
        await self.repo.adjust_system_balance(next_level.upgrade_cost)
        await self._log(
            player,
            "信用升级",
            next_level.upgrade_cost,
            "expense",
            "信用升级",
        )
        return f"信用升级成功，新的存款上限 {format_currency(next_level.deposit_limit)}"

    async def transfer(
        self, sender: Player, target: Player, amount: int, fee_rate: float = 0.03
    ) -> str:
        if amount <= 0:
            raise GameError("金额必须大于 0。")
        if amount > sender.balance:
            raise GameError("余额不足。")
        fee = int(amount * fee_rate)
        sender.balance -= amount
        target.balance += amount - fee
        sender.updated_at = now_ts()
        target.updated_at = now_ts()
        await self.repo.save_player(sender)
        await self.repo.save_player(target)
        await self.repo.adjust_system_balance(fee)
        await self.repo.adjust_tax_pool(fee)
        await self._log(sender, "转账", amount, "expense", f"转给 {target.nickname}")
        await self._log(
            target, "转账收入", amount - fee, "income", f"来自 {sender.nickname}"
        )
        return f"转账成功，实收 {format_currency(amount - fee)}，手续费 {format_currency(fee)}"

    async def request_loan(self, player: Player, amount: int) -> str:
        if player.loan and not player.loan.repaid:
            raise GameError("请先偿还现有贷款。")
        tier = self.config.credit_levels[player.credit_level - 1]
        if amount <= 0 or amount > tier.loan_limit:
            raise GameError(f"额度需在 1~{tier.loan_limit} 之间。")
        player.loan = Loan(
            amount=amount, rate=self.config.deposit_interest_rate, issued_at=now_ts()
        )
        player.balance += amount
        await self.repo.save_player(player)
        await self.repo.adjust_system_balance(-amount)
        await self._log(player, "贷款", amount, "income", "贷款到账")
        return f"贷款到账 {format_currency(amount)}"

    async def repay_loan(self, player: Player, amount: int) -> str:
        if not player.loan or player.loan.repaid:
            raise GameError("暂无贷款。")
        interest = int(player.loan.amount * 0.05)
        total = player.loan.amount + interest
        if amount < total:
            raise GameError(f"至少需要偿还 {format_currency(total)}")
        if player.balance < amount:
            raise GameError("余额不足。")
        player.balance -= amount
        player.loan.repaid = True
        await self.repo.save_player(player)
        await self.repo.adjust_system_balance(amount)
        await self._log(player, "还款", amount, "expense", "偿还贷款")
        return f"已偿还贷款，支付 {format_currency(amount)}"

    async def send_red_packet(
        self, sender: Player, total: int, parts: int
    ) -> Tuple[str, RedPacket]:
        if total <= 0 or parts <= 0:
            raise GameError("金额与份数必须大于 0。")
        admins = await self.repo.list_admins()
        fee = (
            0
            if sender.player_id in admins
            else int(total * self.config.red_packet_fee_rate)
        )
        if total + fee > sender.balance:
            raise GameError("余额不足以发红包。")
        sender.balance -= total + fee
        packet = RedPacket(
            packet_id=f"P{int(time.time() * 1000)}",
            sender_id=sender.player_id,
            total_amount=total,
            parts=parts,
            created_at=now_ts(),
            fee_rate=self.config.red_packet_fee_rate,
        )
        await self.repo.save_player(sender)
        await self.repo.add_red_packet(packet)
        await self.repo.adjust_system_balance(fee)
        await self.repo.adjust_tax_pool(fee)
        await self._log(sender, "发红包", total + fee, "expense", "发红包")
        return (
            f"红包 ID：{packet.packet_id}，共 {parts} 份，手续费 {format_currency(fee)}",
            packet,
        )

    async def grab_red_packet(self, player: Player, packet_id: str) -> str:
        packet = await self.repo.get_red_packet(packet_id)
        if not packet:
            raise NotFound("红包不存在或已过期。")
        if player.player_id == packet.sender_id:
            raise GameError("不能抢自己的红包。")
        if packet.finished():
            await self.repo.purge_red_packet(packet_id)
            raise GameError("来晚了，红包已经被抢光。")
        if player.player_id in packet.claimed_by:
            raise GameError("您已经抢过该红包。")
        remaining_parts = max(1, packet.parts - len(packet.claimed_by))
        remaining_amount = packet.total_amount - packet.claimed_amount
        max_claim = max(1, remaining_amount // remaining_parts)
        claim = random.randint(1, max_claim)
        packet.claimed_by[player.player_id] = claim
        packet.claimed_amount += claim
        if packet.finished():
            await self.repo.purge_red_packet(packet.packet_id)
        else:
            await self.repo.update_red_packet(packet)
        player.balance += claim
        await self.repo.save_player(player)
        await self._log(player, "抢红包", claim, "income", "红包收益")
        return f"抢到 {format_currency(claim)}"


__all__ = ["EconomyService"]
