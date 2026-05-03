if __name__ == "__main__":
	raise Exception("Start the program from the main process")
import logging, discord
from random import choice
from sys import modules as sysmodules
from threading import Lock
from importlib import reload
from dataclasses import dataclass
from discord.ext import commands, tasks
from datetime import datetime, UTC, timedelta
from typing import TYPE_CHECKING, Literal, TypedDict
from enum import StrEnum
from os import getenv
from modules.db import UserRepository
from utils.wt import Squadron
if TYPE_CHECKING:
	from modules.newsAPI import NewsAPI
	from asyncio import AbstractEventLoop
logger = logging.getLogger(__name__)

# region ID Enums
class ChannelIDs(StrEnum):
	LOGS = "logs"
	SPAM = "spam"
	ANNOUNCEMENTS = "announcements"
	SQB = "sqb"
	WTNEWS = "wtNews"
	SCORE = "score"
	PROPAGANDA = "propaganda"
	AUDIT_LOG = "auditLog"
class RoleIDs(StrEnum):
	MEMBER = "member"
	PING = "ping"
	OLD_TIMER = "oldTimer"
	RETIRED = "retired"
	MAJOR_NEWS = "majorNews"
	EVENT_NEWS = "eventNews"
	APPLICANT = "applicant"
class CategoryIDs(StrEnum):
	CLIPS = "clips"
	SQUAD_VC = "squadVC"
# endregion
# region Bot ID Config
@dataclass(frozen=True)
class _GuildConfig:
	channel_ids: dict[ChannelIDs, int]
	role_ids: dict[RoleIDs, int]
	category_ids: dict[CategoryIDs, int]
	common_roles: tuple[int, ...]
	peck_server: int
	sqb_plan_check_limit: timedelta
_LIVE_GUILD_CONFIG = _GuildConfig(
	channel_ids={
		ChannelIDs.LOGS: 1229136570498682900,
		ChannelIDs.SPAM: 1229136570498682900,
		ChannelIDs.ANNOUNCEMENTS: 931263111992848395,
		ChannelIDs.SQB: 1353122797504827422,
		ChannelIDs.WTNEWS: 920311640161943552,
		ChannelIDs.SCORE: 1125129523499896974,
		ChannelIDs.PROPAGANDA: 1066119609914232842,
		ChannelIDs.AUDIT_LOG: 1490460729994641408,
	},
	role_ids={
		RoleIDs.MEMBER: 919803983286128661,
		RoleIDs.PING: 1065769588849115248,
		RoleIDs.OLD_TIMER: 917946204736860190,
		RoleIDs.RETIRED: 983021494739292250,
		RoleIDs.MAJOR_NEWS: 1476690321051222119,
		RoleIDs.EVENT_NEWS: 1489360745039921222,
		RoleIDs.APPLICANT: 1184950087873466438,
	},
	category_ids={
		CategoryIDs.CLIPS: 1428798448102277263,
		CategoryIDs.SQUAD_VC: 917850361019125821,
	},
	common_roles=(917852847482232852, 923683349611053106),
	peck_server=917850361019125820,
	sqb_plan_check_limit=timedelta(minutes=30),
)
_DEBUG_GUILD_CONFIG = _GuildConfig(
	channel_ids={
		ChannelIDs.LOGS: 1453040931703095550,
		ChannelIDs.SPAM: 1453040954343821513,
		ChannelIDs.ANNOUNCEMENTS: 1453040983934767277,
		ChannelIDs.SQB: 1453041059746676837,
		ChannelIDs.WTNEWS: 1453041016969101458,
		ChannelIDs.SCORE: 1456770254972784780,
		ChannelIDs.PROPAGANDA: 1456788537755045931,
		ChannelIDs.AUDIT_LOG: 1490460729994641408,
	},
	role_ids={
		RoleIDs.MEMBER: 1073297853587398696,
		RoleIDs.PING: 1456660597616803956,
		RoleIDs.OLD_TIMER: 1454228913742938112,
		RoleIDs.RETIRED: 1456971952165093467,
		RoleIDs.MAJOR_NEWS: 1476690625612222647,
		RoleIDs.EVENT_NEWS: 1489360453233541170,
		RoleIDs.APPLICANT: 1477308945759735900,
	},
	category_ids={
		CategoryIDs.CLIPS: 1454228135280119982,
		CategoryIDs.SQUAD_VC: 1453040903626293338,
	},
	common_roles=(1124647932696743948,),
	peck_server=685948316541779974,
	sqb_plan_check_limit=timedelta(minutes=2),
)
# endregion

class Bot(commands.Bot):
	ltsLock = Lock()
	class Timeouts(TypedDict):
		clip: 'Bot.GenericTimeout'
		ai: 'Bot.GenericTimeout'
	class GaijinLogin:
		email:str
		password:str
		def __init__(self):
			self.email = getenv("WT_LOGIN_EMAIL")
			self.password = getenv("WT_LOGIN_PASS")
	class _SquadVC:
		channels:list['SquadVCData'] = []
		checkDelay:int = 0
		class SquadVCData:
			_id:int
			last_seen_person_time:float
			creator:int|None
			created:float
			def __init__(self, _id:int, last_seen_person_time:float, creator:int|None, created:float):
				self._id = _id
				self.last_seen_person_time = last_seen_person_time
				self.creator = creator
				self.created = created
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
		self.debug:bool = kwargs.pop("debug")
		guild_config = _DEBUG_GUILD_CONFIG if self.debug else _LIVE_GUILD_CONFIG
		self.channelIDs:dict[ChannelIDs, int] = guild_config.channel_ids.copy()
		self.roleIDs:dict[RoleIDs, int] = guild_config.role_ids.copy()
		self.categoryIDs:dict[CategoryIDs, int] = guild_config.category_ids.copy()
		self.commonRoles = list(guild_config.common_roles)
		self.peckServer = guild_config.peck_server
		self.sqbPlanCheckLimit = guild_config.sqb_plan_check_limit
		self.botIDs = [
			1005502691713237035, # Main Bot
			1007702877264941127 # Testing Bot
		]
		self.authorityRoleIDs = [
			917852215014727742,  # The Birbman
			917944202015408189, # Deputy
			917945129921302599, # Officer
			918571367027322890, # Administr8ors
			1185637328446816299, # Emergency Admin
			1477307536305557516 # Testing server Officer
		]
		self.yoshinoID = 332030423913725953
		self.sqb_season_length = 2
		self.db = UserRepository()
		self.runningSince:datetime = datetime.now(UTC)
		self.iconURL ='https://cdn.discordapp.com/icons/917850361019125820/325129a273dac84e31f9aa5de51f1936.png?size=128'
		self.logLevel:int = kwargs.pop("logLevel")
		self.timeouts:Bot.Timeouts = {
			"clip": self.GenericTimeout(self),
			"ai": self.GenericTimeout(self)
		}
		self.squadVC = self._SquadVC()
		self.runtime:AbstractEventLoop = kwargs.pop("runtime")
		self.newsAPI:'NewsAPI' = kwargs.pop("newsAPI", None)
		self.SQUADRON_TAG = "PECK"
		self.squadron = Squadron("Order Of The Birb")
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
	async def memberHasRole(self, role_id:RoleIDs, member_id:int):
		return (self.get_guild(self.peckServer).get_member(member_id).get_role(self.roleIDs[role_id])) is not None
	async def generateAuditLog(
			self,
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
		if override_channel: channelID = override_channel
		else: channelID = self.channelIDs[ChannelIDs.AUDIT_LOG]
		await (self.get_channel(channelID)).send(embed=embed)
	async def random_propaganda(self) -> str:
		"""Selects a random propaganda post and returns with its URL"""
		propaganda_ch = self.get_channel(self.channelIDs[ChannelIDs.PROPAGANDA])
		messages = [
			j.url 
			async for i in propaganda_ch.history(limit=None) 
			for j in i.attachments
		]
		if not messages: 
			raise LookupError("No propaganda posts found")
		return choice(messages)
	@staticmethod
	def toDiscordTimestamp(dt_obj:datetime) -> discord.app_commands.Timestamp:
		return discord.app_commands.Timestamp(year=dt_obj.year, month=dt_obj.month, day=dt_obj.day, hour=dt_obj.hour, minute=dt_obj.minute, second=dt_obj.second, tzinfo=dt_obj.tzinfo)
class _Tree(discord.app_commands.CommandTree):
	async def on_error(self, interaction: discord.Interaction, error: Exception):
		if isinstance(error, discord.app_commands.CheckFailure):
			logger.warning(f"User {interaction.user.name} ({interaction.user.id}) tried running {interaction.command.name} without the required permissions")
			await interaction.response.send_message("You don't have the required Permissions", ephemeral=True, delete_after=5)
			return
		if not interaction.response.is_done():
			await interaction.response.send_message("Oops! Something went wrong.", ephemeral=True)
		raise error  # still log real bugs
def debug_only():
	async def predicate(interaction: discord.Interaction) -> bool:
		return interaction.client.debug
	return discord.app_commands.check(predicate)
def owner_only():
	async def predicate(interaction: discord.Interaction) -> bool:
		return interaction.user.id in [332030423913725953, 709449854371364895, interaction.client.yoshinoID]
	return discord.app_commands.check(predicate)
def officer_only():
	async def predicate(interaction: discord.Interaction) -> bool:
		if not interaction.guild: return False
		return (
			(interaction.user.guild_permissions.administrator and interaction.guild_id == 917850361019125820) or # PECK admin 
			interaction.user.id in [
				332030423913725953, # Maho Yoshino
				171971803625816075, # Tzatziki
				311555617032765451, # eevee
			]
		)
	return discord.app_commands.check(predicate)
def members_only():
	async def predicate(interaction: discord.Interaction) -> bool:
		if not interaction.guild: return False
		return any(role.id == interaction.client.roleIDs[RoleIDs.MEMBER] for role in interaction.user.roles)
	return discord.app_commands.check(predicate)
