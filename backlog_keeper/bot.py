import asyncio

import discord
from discord.ext.commands import Bot
from discord import app_commands
from loguru import logger

from backlog_keeper.config import Config
from backlog_keeper.commands import get_backlog_commands
from backlog_keeper.index import BacklogIndex, _reaction_name


def setup_intents() -> discord.Intents:
    intents = discord.Intents.default()
    intents.guild_messages = True
    intents.guild_reactions = True
    intents.webhooks = True
    return intents


class BacklogBot(Bot):
    def __init__(self, config: Config):
        super().__init__(command_prefix="/", intents=setup_intents())
        self.remove_command("help")
        self.config = config
        self.backlog_index = BacklogIndex()
        self._warmup_task: asyncio.Task | None = None

    async def setup_hook(self) -> None:
        guild = discord.Object(id=self.config.GUILD_ID)

        self.tree.clear_commands(guild=guild)
        self.tree.on_error = self.on_app_command_error

        commands = get_backlog_commands()
        for command in commands:
            self.tree.add_command(command, guild=guild)

        synced = await self.tree.sync(guild=guild)
        logger.info(
            "Synced {} guild commands: {}",
            len(synced),
            [cmd.name for cmd in synced],
        )

    async def on_ready(self) -> None:
        logger.info(f"{self.user} has connected to Discord!")
        activity = discord.Activity(
            type=discord.ActivityType.listening,
            name="Thinking about them",
        )
        await self.change_presence(activity=activity)
        logger.info(f"Presence set")

        if self._warmup_task is None:
            self._warmup_task = asyncio.create_task(self._warm_all_channels())

    async def _warm_all_channels(self) -> None:
        guild = self.get_guild(self.config.GUILD_ID)
        if guild is None:
            logger.warning("Warm-up skipped: guild {} not found", self.config.GUILD_ID)
            return

        me = guild.me
        channels = [
            channel
            for channel in guild.text_channels
            if channel.permissions_for(me).view_channel
            and channel.permissions_for(me).read_message_history
        ]
        logger.info("Warming backlog index for {} channel(s)", len(channels))

        for channel in channels:
            try:
                await self.backlog_index.ensure_warm(channel)
            except discord.HTTPException as error:
                logger.warning("Warm-up failed for #{}: {}", channel.name, error)

        logger.info("Backlog index warm-up complete")

    async def on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        logger.exception("App command failed: {}", error)
        try:
            if interaction.response.is_done():
                await interaction.followup.send(
                    f"Command failed: {error}", ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"Command failed: {error}", ephemeral=True
                )
        except Exception:
            logger.exception("Failed to send interaction error response")

    async def _reaction_event(self, payload: discord.RawReactionActionEvent) -> None:
        channel = self.get_channel(payload.channel_id)
        if not isinstance(channel, discord.TextChannel):
            return
        await self.backlog_index.handle_reaction_change(
            channel, payload.message_id, _reaction_name(payload.emoji)
        )

    async def on_raw_reaction_add(
        self, payload: discord.RawReactionActionEvent
    ) -> None:
        await self._reaction_event(payload)

    async def on_raw_reaction_remove(
        self, payload: discord.RawReactionActionEvent
    ) -> None:
        await self._reaction_event(payload)

    async def on_raw_reaction_clear_emoji(
        self, payload: discord.RawReactionClearEmojiEvent
    ) -> None:
        channel = self.get_channel(payload.channel_id)
        if not isinstance(channel, discord.TextChannel):
            return
        await self.backlog_index.handle_reaction_change(
            channel, payload.message_id, _reaction_name(payload.emoji)
        )

    async def on_raw_reaction_clear(
        self, payload: discord.RawReactionClearEvent
    ) -> None:
        channel = self.get_channel(payload.channel_id)
        if not isinstance(channel, discord.TextChannel):
            return
        await self.backlog_index.handle_reaction_clear(channel, payload.message_id)

    async def on_raw_message_delete(
        self, payload: discord.RawMessageDeleteEvent
    ) -> None:
        self.backlog_index.handle_message_delete(payload.channel_id, payload.message_id)
