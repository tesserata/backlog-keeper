import discord
from discord.ext.commands import Bot
from discord import app_commands
from loguru import logger

from backlog_keeper.config import Config
from backlog_keeper.commands import get_backlog_commands


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
