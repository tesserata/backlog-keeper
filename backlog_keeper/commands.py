import io
from typing import TYPE_CHECKING, cast

import discord
from discord import TextChannel, app_commands

from backlog_keeper.ui import BacklogChannelSelectorView, ConfirmView
from backlog_keeper.discord_utility import resolve_channels, get_custom_emoji
from backlog_keeper.index import BacklogEntry, BacklogIndex

if TYPE_CHECKING:
    from backlog_keeper.bot import BacklogBot

MESSAGE_LIMIT = 1900
IN_PROGRESS_MARK = " ✅"

_CleanTarget = tuple[
    discord.TextChannel, list[tuple[discord.Message, list[discord.Reaction]]]
]


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
        app_commands.Command(
            name="clean",
            description="Clear backlog + in-progress markers from selected channels",
            callback=_clean,
        ),
        app_commands.Command(
            name="download_backlog",
            description="Download backlog as a text file",
            callback=_download_backlog,
        )
    ]


def _index(interaction: discord.Interaction) -> BacklogIndex:
    return cast("BacklogBot", interaction.client).backlog_index


async def _get_backlog_all(interaction: discord.Interaction) -> None:
    channels = await resolve_channels(interaction)
    if channels is None:
        return

    await interaction.response.send_message("Checking backlog...", ephemeral=True)
    chunks = await _build_backlog_chunks(
        _index(interaction), channels, interaction.user
    )
    await _send_chunks(interaction, chunks)


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
    chunks = await _build_backlog_chunks(
        _index(interaction), channels, interaction.user
    )
    await _send_chunks(interaction, chunks)


async def _build_backlog_chunks(
        index: BacklogIndex,
        channels: list[discord.TextChannel],
        user: discord.User | discord.Member,
) -> list[str]:
    lines: list[str] = []

    for channel in channels:
        entries = await index.get_backlog(channel, user)
        if not entries:
            continue
        lines.append("---")
        lines.extend(_format_entry(entry) for entry in entries)

    return _pack_lines(lines, MESSAGE_LIMIT)


def _format_entry(entry: BacklogEntry) -> str:
    postfix = IN_PROGRESS_MARK if entry.has_in_progress else ""
    return f"{entry.jump_url}{postfix}"

async def _get_entry_text(entry: BacklogEntry, channel: TextChannel) -> str:
    try:
        msg = await channel.fetch_message(entry.message_id)
        content = msg.content
    except discord.NotFound:
        content = f"couldnt find message {entry.jump_url}"

    return f"{entry.jump_url}\n{content}\n----"


def _pack_lines(lines: list[str], limit: int) -> list[str]:
    chunks: list[str] = []
    current = ""

    for line in lines:
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit and current:
            chunks.append(current)
            current = line
        else:
            current = candidate

    if current:
        chunks.append(current)

    return chunks


async def _send_chunks(interaction: discord.Interaction, chunks: list[str]) -> None:
    if not chunks:
        await interaction.edit_original_response(
            content=f"Everything covered {get_custom_emoji(interaction.guild, 'tay_wow')}"
        )
        return

    await interaction.edit_original_response(content=chunks[0])
    for chunk in chunks[1:]:
        await interaction.followup.send(chunk, ephemeral=True)


async def _clean(interaction: discord.Interaction) -> None:
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
        on_select=_on_clean_channels_selected,
    )
    await interaction.response.send_message(
        "What channels should I clean?", view=view, ephemeral=True
    )


async def _on_clean_channels_selected(
        interaction: discord.Interaction,
        channels: list[discord.TextChannel],
) -> None:
    await interaction.response.edit_message(content="Scanning channels...", view=None)

    index = _index(interaction)
    targets: list[_CleanTarget] = []
    total = 0
    for channel in channels:
        messages = await index.collect_user_marked_messages(channel, interaction.user)
        if messages:
            targets.append((channel, messages))
            total += len(messages)

    if total == 0:
        await interaction.edit_original_response(
            content="You have no backlog or in-progress markers to clean here.",
            view=None,
        )
        return

    async def _confirm(confirm_interaction: discord.Interaction) -> None:
        await _perform_clean(confirm_interaction, index, targets)

    view = ConfirmView(user_id=interaction.user.id, on_confirm=_confirm)
    await interaction.edit_original_response(
        content=(
            f"This will remove your backlog + in-progress reactions from {total} "
            f"message(s) across {len(targets)} channel(s). Continue?"
        ),
        view=view,
    )


async def _perform_clean(
        interaction: discord.Interaction,
        index: BacklogIndex,
        targets: list[_CleanTarget],
) -> None:
    await interaction.response.edit_message(content="Cleaning...", view=None)

    user = interaction.user
    cleared = 0
    failed: list[discord.TextChannel] = []
    for channel, messages in targets:
        for message, reactions in messages:
            try:
                for reaction in reactions:
                    await message.remove_reaction(reaction.emoji, user)
            except discord.NotFound:
                continue
            except (discord.Forbidden, discord.HTTPException):
                failed.append(channel)
                break
            cleared += 1
        index.drop_channel(channel.id)

    summary = f"Removed your markers from {cleared} message(s)."
    if failed:
        names = ", ".join(f"#{channel.name}" for channel in failed)
        summary += f" Couldn't finish in {names} (missing Manage Messages?)."
    await interaction.edit_original_response(content=summary, view=None)

async def _download_backlog(interaction: discord.Interaction) -> None:
    channels = await resolve_channels(interaction)
    if channels is None:
        return

    await interaction.response.send_message("Checking backlog...", ephemeral=True)
    lines: list[str] = []

    index = _index(interaction)
    for channel in channels:
        entries = await index.get_backlog(channel, interaction.user)
        if not entries:
            continue
        lines.append("*"*10)
        for entry in entries:
            lines.append(await _get_entry_text(entry, channel))
    buffer = io.BytesIO("\n\n".join(lines).encode("utf-8"))
    await interaction.edit_original_response(content="Gathered the backlog, please see the file", view=None)
    await interaction.followup.send(file=discord.File(buffer, filename="backlog.txt"), ephemeral=True)