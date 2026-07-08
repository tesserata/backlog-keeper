import asyncio

import discord

BACKLOG_EMOJI = "backlog"
IN_PROGRESS_EMOJI = "having_a_think"
MARKER_EMOJIS = (BACKLOG_EMOJI, IN_PROGRESS_EMOJI)

HISTORY_LIMIT = 2000


def _reaction_name(emoji: discord.Emoji | discord.PartialEmoji | str) -> str:
    if isinstance(emoji, str):
        return emoji
    return emoji.name or ""


def marker_reactions(message: discord.Message) -> list[discord.Reaction]:
    return [r for r in message.reactions if _reaction_name(r.emoji) in MARKER_EMOJIS]


async def _user_reacted(reaction: discord.Reaction, user_id: int) -> bool:
    async for user in reaction.users():
        if user.id == user_id:
            return True
    return False


class BacklogEntry:
    def __init__(
            self,
            message_id: int,
            channel_id: int,
            author_id: int,
            jump_url: str,
            has_backlog: bool,
            has_in_progress: bool,
    ) -> None:
        self.message_id = message_id
        self.channel_id = channel_id
        self.author_id = author_id
        self.jump_url = jump_url
        self.has_backlog = has_backlog
        self.has_in_progress = has_in_progress


class BacklogIndex:

    def __init__(self, history_limit: int = HISTORY_LIMIT) -> None:
        self._history_limit = history_limit
        self._channels: dict[int, dict[int, BacklogEntry]] = {}
        self._warmed: set[int] = set()
        self._locks: dict[int, asyncio.Lock] = {}

    def _lock(self, channel_id: int) -> asyncio.Lock:
        lock = self._locks.get(channel_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[channel_id] = lock
        return lock

    def _upsert(self, channel_id: int, message: discord.Message) -> None:
        names = {_reaction_name(r.emoji) for r in message.reactions}
        has_backlog = BACKLOG_EMOJI in names
        has_in_progress = IN_PROGRESS_EMOJI in names

        entries = self._channels.setdefault(channel_id, {})
        if has_backlog or has_in_progress:
            entries[message.id] = BacklogEntry(
                message_id=message.id,
                channel_id=channel_id,
                author_id=message.author.id,
                jump_url=message.jump_url,
                has_backlog=has_backlog,
                has_in_progress=has_in_progress,
            )
        else:
            entries.pop(message.id, None)

    async def ensure_warm(self, channel: discord.TextChannel) -> None:
        if channel.id in self._warmed:
            return
        async with self._lock(channel.id):
            if channel.id in self._warmed:
                return
            self._channels[channel.id] = {}
            async for message in channel.history(limit=self._history_limit):
                self._upsert(channel.id, message)
            self._warmed.add(channel.id)

    async def get_backlog(
            self,
            channel: discord.TextChannel,
            user: discord.User | discord.Member,
    ) -> list[BacklogEntry]:
        await self.ensure_warm(channel)
        entries = self._channels.get(channel.id, {})
        backlog = [
            entry
            for entry in entries.values()
            if entry.has_backlog and entry.author_id != user.id
        ]
        backlog.sort(key=lambda entry: entry.message_id)
        return backlog

    async def collect_user_marked_messages(
            self,
            channel: discord.TextChannel,
            user: discord.User | discord.Member,
    ) -> list[tuple[discord.Message, list[discord.Reaction]]]:
        marked: list[tuple[discord.Message, list[discord.Reaction]]] = []
        async for message in channel.history(limit=self._history_limit):
            reactions = [
                reaction
                for reaction in marker_reactions(message)
                if await _user_reacted(reaction, user.id)
            ]
            if reactions:
                marked.append((message, reactions))
        return marked

    def drop_channel(self, channel_id: int) -> None:
        self._warmed.discard(channel_id)
        self._channels.pop(channel_id, None)

    async def _refresh_message(
            self, channel: discord.TextChannel, message_id: int
    ) -> None:
        async with self._lock(channel.id):
            if channel.id not in self._warmed:
                return
            try:
                message = await channel.fetch_message(message_id)
            except discord.NotFound:
                entries = self._channels.get(channel.id)
                if entries is not None:
                    entries.pop(message_id, None)
                return
            except discord.HTTPException:
                return
            self._upsert(channel.id, message)

    async def handle_reaction_change(
            self, channel: discord.TextChannel, message_id: int, emoji_name: str
    ) -> None:
        if emoji_name not in MARKER_EMOJIS:
            return
        await self._refresh_message(channel, message_id)

    async def handle_reaction_clear(
            self, channel: discord.TextChannel, message_id: int
    ) -> None:
        await self._refresh_message(channel, message_id)

    def handle_message_delete(self, channel_id: int, message_id: int) -> None:
        entries = self._channels.get(channel_id)
        if entries is not None:
            entries.pop(message_id, None)
