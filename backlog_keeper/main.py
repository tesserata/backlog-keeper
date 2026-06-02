#!/usr/bin/env python3
import asyncio

from backlog_keeper.bot import BacklogBot
from backlog_keeper.config import get_config


async def main() -> None:
    config = get_config()
    print(config.DISCORD_TOKEN)
    bot = BacklogBot(config)

    async with bot:
        await bot.start(config.DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())