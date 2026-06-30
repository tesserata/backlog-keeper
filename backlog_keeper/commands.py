import discord
from discord import app_commands

from backlog_keeper.ui import BacklogChannelSelectorView
from backlog_keeper.discord_utility import resolve_channels, get_custom_emoji

BACKLOG_EMOJI = "backlog"
IN_PROGRESS_EMOJI = "having_a_think"
ALL_CHANNELS = "all"


def get_backlog_commands() -> list[app_commands.Command]:
    return [
        app_commands.Command(
            name="backlog_by_channel",
            description="Get a list of unanswered messages for select channels",
            callback=_get_backlog_selector,
        ),
        app_commands.Command(
            name="backlog",
            description="Get a list of unanswered messages",
            callback=_get_backlog_all,
        ),
    ]


async def _get_backlog_all(interaction: discord.Interaction) -> None:
    channels = await resolve_channels(interaction)
    if channels is None:
        return

    await interaction.response.send_message("Checking backlog...", ephemeral=True)
    result = await _build_backlog_message(channels, interaction.user)
    await interaction.edit_original_response(
        content=result
        or f"Everything covered {get_custom_emoji(interaction.guild, "tay_wow")}"
    )


async def _get_backlog_selector(interaction: discord.Interaction) -> None:
    channels = await resolve_channels(interaction)
    if channels is None:
        return

    if len(channels) > 24:
        await interaction.response.send_message(
            "Too many channels for one selector.", ephemeral=True
        )
        return

    view = BacklogChannelSelectorView(
        channels=channels,
        user_id=interaction.user.id,
        on_select=_on_channels_selected,
    )
    await interaction.response.send_message(
        "What channels should I check?", view=view, ephemeral=True
    )


async def _on_channels_selected(
    interaction: discord.Interaction,
    channels: list[discord.TextChannel],
) -> None:
    await interaction.response.edit_message(content="Checking backlog...", view=None)
    result = await _build_backlog_message(channels, interaction.user)
    await interaction.edit_original_response(
        content=result
        or f"Everything covered {get_custom_emoji(interaction.guild, "tay_wow")}",
        view=None,
    )


async def _build_backlog_message(
    channels: list[discord.TextChannel],
    user: discord.User | discord.Member,
) -> str:
    messages: list[str] = []

    for channel in channels:
        backlog = await _get_channel_backlog(channel, user)
        if backlog:
            messages.append("---\n")
            urls = "\n".join(m.jump_url for m in backlog)
            messages.append(f"{urls}\n")

    return "\n".join(messages)


def _reaction_name(emoji: discord.Emoji | discord.PartialEmoji | str) -> str:
    if isinstance(emoji, str):
        return emoji
    return emoji.name or ""


async def _get_channel_backlog(
    channel: discord.TextChannel,
    user: discord.User | discord.Member,
) -> list[discord.Message]:
    backlog: list[discord.Message] = []

    async for message in channel.history(limit=2000):
        names = [_reaction_name(r.emoji) for r in message.reactions]
        if BACKLOG_EMOJI in names and message.author != user:
            backlog.append(message)

    return backlog
