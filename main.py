"""AstrBot entry point for the slave market plugin."""

from __future__ import annotations

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

from slave_market import SlaveMarketEngine


@register("slave-market", "magisk317", "群聊牛马市场游戏（Python 版）", "1.0.0")
class SlaveMarketStar(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.engine = SlaveMarketEngine()

    async def initialize(self):
        await self.engine.initialize()
        logger.info(
            "Slave market plugin initialized with %s commands.",
            len(self.engine.COMMAND_ALIASES),
        )

    @filter.regex(SlaveMarketEngine.build_pattern())
    async def handle_game_command(self, event: AstrMessageEvent):
        """Routes所有牛马指令到 Python 版引擎。"""

        result = await self.engine.dispatch(event)
        if not result:
            return
        if result.image:
            yield event.image_result(result.image)
        elif result.message:
            yield event.plain_result(result.message)

    async def terminate(self):
        await self.engine.shutdown()
        logger.info("Slave market plugin terminated.")
