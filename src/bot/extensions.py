from typing import TYPE_CHECKING, TypedDict

import discord

if TYPE_CHECKING:
	import bot.config as Config


class ForumChannel(discord.ForumChannel):
	def __init__(self, *, state, guild, data):
		super().__init__(state=state, guild=guild, data=data)

	async def get_threads(self):
		for thread in self.threads:
			yield thread
		async for thread in self.archived_threads(limit=None):
			yield thread

	async def get_by_name(self, channel_name: str) -> discord.Thread | None:
		async for thread in self.get_threads():
			if thread.name == channel_name:
				return thread
		return None

	async def get_pinned_thread(self) -> discord.Thread | None:
		async for thread in self.get_threads():
			if thread.flags.pinned:
				return thread
		return None

class MissingConfigError(BaseException):
    pass
class NoConfigError(BaseException):
    pass

class Interaction(discord.Interaction):
	class _InteractionExtras(TypedDict):
		config: "Config.GuildConfig | None"
	extras: _InteractionExtras
