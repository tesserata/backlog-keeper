from typing import Awaitable, Callable

import discord

ALL_CHANNELS = "all"

OnSelectCallback = Callable[
    [discord.Interaction, list[discord.TextChannel]],
    Awaitable[None],
]


class BacklogChannelSelectorView(discord.ui.View):
    def __init__(
        self,
        channels: list[discord.TextChannel],
        user_id: int,
        on_select: OnSelectCallback,
        timeout: float = 60 * 60,
    ):
        super().__init__(timeout=timeout)
        self.user_id = user_id
        self.add_item(BacklogChannelSelect(channels, on_select=on_select))


class BacklogChannelSelect(discord.ui.Select):
    def __init__(
        self,
        channels: list[discord.TextChannel],
        on_select: OnSelectCallback,
    ):
        self._channels_by_id = {channel.id: channel for channel in channels}
        self._on_select = on_select

        options = [discord.SelectOption(label="All channels", value=ALL_CHANNELS)]
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

    async def callback(self, interaction: discord.Interaction) -> None:
        selected = set(self.values)

        if ALL_CHANNELS in selected:
            channels = list(self._channels_by_id.values())
        else:
            channels = [
                self._channels_by_id[int(v)]
                for v in selected
                if int(v) in self._channels_by_id
            ]

        await self._on_select(interaction, channels)
