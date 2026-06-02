import discord
from discord import app_commands

ALL_CHANNELS = "all"
BACKLOG_EMOJI = "backlog"
IN_PROGRESS_EMOJI = "having_a_think"


def get_backlog_commands() -> list[app_commands.Command]:
    return [
        app_commands.Command(
            name="backlog",
            description="Get a list of unanswered messages",
            callback=_get_backlog_selector,
        ),
    ]


async def _get_backlog_selector(interaction: discord.Interaction):
    if interaction.guild is None:
        await interaction.response.send_message(
            "This command only works inside a server.",
            ephemeral=True,
        )
        return

    channels = _get_available_text_channels(interaction)

    if not channels:
        await interaction.response.send_message(
            "I cannot see any text channels here.",
            ephemeral=True,
        )
        return

    if len(channels) > 24:
        await interaction.response.send_message(
            "Too many channels for one selector. For now, use a channel-specific command "
            "or add pagination later.",
            ephemeral=True,
        )
        return

    view = BacklogChannelSelectorView(channels, user_id=interaction.user.id)

    await interaction.response.send_message(
        "Which channels should I check?",
        view=view,
        ephemeral=True,
    )


def _get_available_text_channels(
        interaction: discord.Interaction,
) -> list[discord.TextChannel]:
    assert interaction.guild is not None

    bot_member = interaction.guild.me
    user = interaction.user

    channels: list[discord.TextChannel] = []

    for channel in interaction.guild.text_channels:
        bot_perms = channel.permissions_for(bot_member)
        user_perms = channel.permissions_for(user)

        if not bot_perms.view_channel:
            continue

        if not bot_perms.read_message_history:
            continue

        if not user_perms.view_channel:
            continue

        channels.append(channel)

    return channels


class BacklogChannelSelectorView(discord.ui.View):
    def __init__(
            self,
            channels: list[discord.TextChannel],
            user_id: int,
            timeout: float = 60 * 60,
    ):
        super().__init__(timeout=timeout)
        self.user_id = user_id
        self.add_item(BacklogChannelSelect(channels))


class BacklogChannelSelect(discord.ui.Select):
    def __init__(self, channels: list[discord.TextChannel]):
        self.channels_by_id = {channel.id: channel for channel in channels}

        options = [
            discord.SelectOption(
                label="All channels",
                value=ALL_CHANNELS,
            )
        ]

        options.extend(
            discord.SelectOption(
                label=f"#{channel.name}",
                value=str(channel.id),
                description=(
                    f"In {channel.category.name}"
                    if channel.category is not None
                    else "No category"
                ),
            )
            for channel in channels
        )

        super().__init__(
            placeholder="Select channels to check",
            min_values=1,
            max_values=len(options),
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        selected_values = set(self.values)

        if ALL_CHANNELS in selected_values:
            selected_channels = list(self.channels_by_id.values())
        else:
            selected_channels = [
                self.channels_by_id[int(value)]
                for value in selected_values
                if int(value) in self.channels_by_id
            ]

        await interaction.response.edit_message(
            content="Checking backlog...",
            view=None,
        )

        backlog_message = await _get_backlog(
            channels=selected_channels,
            user=interaction.user,
        )

        await interaction.edit_original_response(
            content=backlog_message,
            view=None,
        )


async def _get_backlog(
        channels: list[discord.TextChannel],
        user: discord.User | discord.Member,
) -> str:
    summary = ""
    for channel in channels:
        channel_backlog = await _get_channel_backlog(channel, user)
        summary += f"{channel.mention}:\n"
        summary += "\n".join([f"\t{message.jump_url}" for message in channel_backlog])

    return summary


async def _get_channel_backlog(
        channel: discord.TextChannel,
        user: discord.User | discord.Member
) -> list[discord.Message]:
    backlog = []
    messages = channel.history(limit=200)
    async for message in messages:
        if BACKLOG_EMOJI in message.reactions:
            backlog.append(message)
    return backlog
