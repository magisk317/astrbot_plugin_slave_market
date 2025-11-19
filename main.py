"""AstrBot entry point for the slave market plugin."""

from __future__ import annotations

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from slave_market import SlaveMarketEngine, load_game_config


@register("slave-market", "magisk317", "群聊牛马市场游戏（Python 版）", "1.0.0")
class SlaveMarketPlugin(Star):
    def __init__(self, context: Context, config: dict | None = None, **_):
        super().__init__(context)
        game_config = load_game_config(config)
        self.engine = SlaveMarketEngine(game_config)

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


# Backward compatibility
SlaveMarketStar = SlaveMarketPlugin
