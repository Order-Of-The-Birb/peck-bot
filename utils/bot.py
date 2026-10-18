if __name__ == "__main__":
	raise Exception("Start the program from the main process")
import logging, discord
from sys import modules as sysmodules
from threading import Lock
from importlib import reload
from discord.ext import commands, tasks
from datetime import datetime, UTC, timedelta
from typing import Literal, TypedDict
from os import getenv
from dataclasses import dataclass
from cogs import EXTENSIONS
import shared
logger = logging.getLogger(__name__)

class Bot(commands.Bot):
	ltsLock = Lock()
	class Timeouts(TypedDict):
		clip: 'Bot.GenericTimeout'
		ai: 'Bot.GenericTimeout'
	
	class GenericTimeout:
		cleanupTask:tasks.Loop
		expiry:timedelta
		def __init__(self, bot:'Bot', timeout_after:int=3, expires_after:timedelta = timedelta(minutes=5)):
			self._wait_until_ready = bot.wait_until_ready
			self.timeoutCount:int = timeout_after
			self.cooldowns:dict[int, list[datetime]] = {}
			self.expiry	= expires_after

			self.cleanupTask = self.cleanup
		def isTimedOut(self, user_id:int) -> bool:
			return len(self.cooldowns.get(user_id, [])) >= self.timeoutCount
		def getOldest(self, user_id:int) -> datetime|None:
			tmp = self.cooldowns.get(user_id)
			return min(tmp) if tmp else None
		def add(self, user_id:int):
			now = datetime.now(UTC)
			self.cooldowns.setdefault(user_id, []).append(now)
		def getExpireTime(self, user_id: int) -> datetime | None:
			oldest = self.getOldest(user_id)
			if oldest is None:
				return None

			expire_time = oldest + self.expiry

			next_iter = self.cleanupTask.next_iteration
			if next_iter is not None:
				expire_time = max(expire_time, next_iter)

			return expire_time
		# region Integrated Loop
		@tasks.loop(minutes=1)
		async def cleanup(self):
			rn = datetime.now(UTC)
			for user, entries in list(self.cooldowns.items()):
				new = [e for e in entries if rn - e < self.expiry]
				if new:
					self.cooldowns[user] = new
				else:
					self.cooldowns.pop(user, None)
		@cleanup.before_loop
		async def _beforeCleanup(self):
			await self._wait_until_ready()
		def stop(self):
			if self.cleanupTask:
				self.cleanupTask.cancel()
		def run(self):
			if self.cleanupTask:
				self.cleanupTask.start()
		# endregion
	def __init__(self, *args,**kwargs):
		self.timeouts:Bot.Timeouts = {
			"clip": self.GenericTimeout(self),
			"ai": self.GenericTimeout(self)
		}
		self.squadVC: dict[int, 'Bot._SquadVC'] = {}
		super().__init__(tree_cls=_Tree, *args, **kwargs)
	def _reload_prefix(self, prefix: str):
		to_reload = [
			(name, module)
			for name, module in sysmodules.items()
			if module and name.startswith(prefix)
		]
		for name, module in to_reload:
			try:
				reload(module)
				logger.debug(f"Reloaded module: {name}")
			except Exception:
				logger.exception(f"Failed to reload module: {name}")
	async def reload_extension_with_deps(self,extension: str,*module_prefixes: str):
		"""Reload helper modules, then reload the extension."""
		if isinstance(module_prefixes, str):
			raise TypeError(f"__reload_deps__ must be a tuple, not str")
		for prefix in module_prefixes:
			self._reload_prefix(prefix)
		try:
			await self.reload_extension(extension)
		except commands.errors.ExtensionNotLoaded: pass
	async def memberHasRole(self, guild: int, role_id:shared.RoleIDs, member_id:int):
		config = shared.GUILD_CONFIGS.get(guild)
		if config is None:
			return False
		return (self.get_guild(config.peck_server).get_member(member_id).get_role(config.role_ids[role_id])) is not None
	async def generateAuditLog(
			self,
			guild: int,
			/,
			*,
			description:str = None,
			author:discord.User|discord.Member|discord.Guild=None,
			title:str = None,
			url:str=None,
			color:int=None,
			footer_text:str=None,
			footer_icon_url:str=None,
			items:list[dict[Literal["name", "value"], str]|None] = [],
			override_channel:int=None,
			timestamp:datetime=None,
			author_name_override:str = None,
			author_avatar_thumbnail:bool = False
		) -> None:
		embed = discord.Embed(title=title, description=description, timestamp=datetime.now(UTC) if not timestamp else timestamp, color=color, url=url)
		if author_avatar_thumbnail: embed.set_thumbnail(url=(author.display_avatar.url if isinstance(author, (discord.Member, discord.User)) else (author.icon.url if isinstance(author, discord.Guild) else None)))
		if isinstance(author, (discord.Member, discord.User)): embed.set_author(name=author.name, icon_url=author.display_avatar.url)
		elif isinstance(author, discord.Guild): embed.set_author(name=author.name, icon_url=author.icon.url)
		if author_name_override: embed.set_author(name=author_name_override, icon_url=author.icon.url if isinstance(author, discord.Guild) else (author.display_avatar.url if isinstance(author, (discord.Member, discord.User)) else None))
		for item in items:
			if item is None: continue
			embed.add_field(name=item["name"], value=item["value"], inline=False)
		embed.set_footer(text=footer_text if footer_text else (f"ID: {author.id}" if author else ""), icon_url=footer_icon_url)
		
		config = shared.GUILD_CONFIGS.get(guild)
		if config is None:
			return
		
		if override_channel: channelID = override_channel
		else: channelID = config.channel_ids[shared.ChannelIDs.AUDIT_LOG]
		await (self.get_channel(channelID)).send(embed=embed)

	async def setup_hook(self):
		logger.info("Bot is getting ready...")
		self.status = discord.Status.do_not_disturb
		for i in self.timeouts.values(): i.run()
		for extension in EXTENSIONS:
			try:
				await self.load_extension(extension)
			except Exception:
				logger.exception(f"Failed to load extension '{extension}'")
				raise
		try:
			synced = await self.tree.sync()
			logger.info(f"Synced {len(synced)} command(s)")
		except Exception:
			logging.exception("An error occured while syncing")
		logger.info("Startup complete")

class _Tree(discord.app_commands.CommandTree):
	async def on_error(self, interaction: discord.Interaction, error: Exception):
		if isinstance(error, discord.app_commands.CheckFailure):
			logger.warning(f"User {interaction.user.name} ({interaction.user.id}) tried running {interaction.command.name} without the required permissions")
			await interaction.response.send_message("You don't have the required Permissions", ephemeral=True, delete_after=5)
			return
		if not interaction.response.is_done():
			await interaction.response.send_message("Oops! Something went wrong.", ephemeral=True)
		raise error  # still log real bugs

#region Decorators
def debug_only():
	return discord.app_commands.check(lambda x: shared.DEBUG)
def owner_only():
	async def predicate(interaction: discord.Interaction) -> bool:
		return interaction.user.id in [332030423913725953, 709449854371364895, shared.YOSHINO_ID]
	return discord.app_commands.check(predicate)
def officer_only():
	async def predicate(interaction: discord.Interaction) -> bool:
		if not interaction.guild: return False
		config = shared.GUILD_CONFIGS.get(interaction.guild.id)
		if config is None:
			return False
		return any(
			i.id in config.authority_role_ids
			for i in interaction.user.roles
		)
	return discord.app_commands.check(predicate)
def members_only():
	async def predicate(interaction: discord.Interaction) -> bool:
		if not interaction.guild: return False
		config = shared.GUILD_CONFIGS.get(interaction.guild.id)
		if config is None:
			return False
		return any(role.id == config.role_ids[shared.RoleIDs.MEMBER] for role in interaction.user.roles)
	return discord.app_commands.check(predicate)
#endregion