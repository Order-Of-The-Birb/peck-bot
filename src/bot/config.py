import discord
from dataclasses import dataclass
from pathlib import Path
from enum import StrEnum
from collections.abc import Iterator
from json import load as load_json
import bot.client as Client

__CONFIGS_PATH = Path(__file__).parent.parent / "guilds"

@dataclass(slots=True)
class GuildConfig:
	class Channels(StrEnum):
		ANNOUNCEMENTS = "ANNOUNCEMENTS"
		AUDIT_LOG = "AUDIT_LOG"
		LOGS = "LOGS"
		SCORE = "SCORE"
		SQB = "SQB"
		PROPAGANDA = "PROPAGANDA"
		WTNEWS = "WTNEWS"
	class Roles(StrEnum):
		MEMBER = "MEMBER"
		EX_MEMBER = "EX_MEMBER"
		PING = "PING"
		OLD_TIMER = "OLD_TIMER"
		MAJOR_NEWS = "MAJOR_NEWS"
		EVENT_NEWS = "EVENT_NEWS"
		APPLICANT = "APPLICANT"
		COMMON = "COMMON"
	class Categories(StrEnum):
		CLIPS = "CLIPS"
		SQUAD_VC = "SQUAD_VC"

	__ID: int
	__CHANNELS: dict[Channels, int]
	__ROLES: dict[Roles, int|list[int]]
	__CATEGORIES: dict[Categories, int]
	__SQUADRON_ID: int | None

	@classmethod
	def from_id(cls, guild_id: int | None)	-> GuildConfig | None:
		if guild_id is None:
			return
		path = Path(__file__).parent / "guilds" / f"{guild_id}.json"
		if not path.exists():
			return None

		config:dict[str, dict] = load_json(path.read_text())

		return cls(
			__ID=guild_id,
			__CHANNELS=config.get("channels", {}),
			__ROLES=config.get("roles", {}),
			__CATEGORIES=config.get("categories", {}),
			__SQUADRON_ID=config.get("squadron", None)
		)

	def get_channel(self, channel: Channels) -> discord.TextChannel | None:
		if channel in self.__CHANNELS:
			return Client.BOT.get_channel(self.__CHANNELS[channel])
	def get_role(self, role: Roles) -> discord.Role | None:
		if role != GuildConfig.Roles.COMMON and role in self.__ROLES:
			return Client.BOT.get_guild(self.__ID).get_role(self.__ROLES[role])
		elif role == GuildConfig.Roles.COMMON:
			raise RuntimeError(f"Can not call 'get_role' with role '{GuildConfig.Roles.COMMON}'")
	def get_category(self, category: Categories) -> discord.CategoryChannel | None:
		if category not in self.__CATEGORIES:
			return
		for categ in Client.BOT.get_guild(self.__ID).categories:
			if categ.id != self.__CATEGORIES[category]:
				continue
			return categ
	@property
	def common_roles(self) -> tuple[discord.Role, ...]:
		if self.Roles.COMMON in self.__ROLES:
			guild = self.guild
			return tuple([guild.get_role(role) for role in self.__ROLES[self.Roles.COMMON]])
		return tuple()
	@property
	def guild(self)	-> discord.Guild:
		return Client.BOT.get_guild(self.__ID)
	@property
	def squadron(self) -> int | None:
		return self.__SQUADRON_ID

__CACHE: dict[int, GuildConfig] = {}

def get(guild_id: int) -> GuildConfig | None:
	if guild_id in __CACHE:
		return __CACHE[guild_id]
	config = GuildConfig.from_id(guild_id)
	if config is None:
		return
	__CACHE[guild_id] = config
	return config

def guilds() -> Iterator[GuildConfig]:
	for path in __CONFIGS_PATH.iterdir():
		yield GuildConfig.from_id(int(path.name.removesuffix(".json")))
