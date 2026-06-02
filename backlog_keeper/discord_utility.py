import discord

def get_available_text_channels(
    interaction: discord.Interaction,
) -> list[discord.TextChannel]:
    assert interaction.guild is not None

    bot_member = interaction.guild.me
    user = interaction.user
    channels: list[discord.TextChannel] = []

    for channel in interaction.guild.text_channels:
        bot_perms = channel.permissions_for(bot_member)
        user_perms = channel.permissions_for(user)

        if bot_perms.view_channel and bot_perms.read_message_history and user_perms.view_channel:
            channels.append(channel)

    return channels


async def resolve_channels(
    interaction: discord.Interaction,
) -> list[discord.TextChannel] | None:
    if interaction.guild is None:
        await interaction.response.send_message(
            "This command only works inside a server.", ephemeral=True
        )
        return None

    channels = get_available_text_channels(interaction)

    if not channels:
        await interaction.response.send_message(
            "I cannot see any text channels here.", ephemeral=True
        )
        return None

    return channels

def get_custom_emoji(guild: discord.Guild | None, name: str) -> str:
    emoji = discord.utils.get(guild.emojis, name=name)
    return str(emoji) if emoji else ":white_check_mark:"