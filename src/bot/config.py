from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import Enum, StrEnum
from json import load as load_json
from os import getenv
from random import choice
from typing import Literal, overload

import discord
from aiohttp import ClientResponseError

import bot.client as Client
import utils.network as Network
from paths import GUILDS

__MANAGEMENT_URL: str = getenv("management_api_url", "http://127.0.0.1:8000/").strip().removesuffix("/")

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
@dataclass(slots=True)
class GuildConfig:
	class _Management:
		squadron_id: int

		@classmethod
		async def login(cls, squadron_id: int | None):
			if squadron_id is None:
				return None

			self = cls(
				squadron_id=squadron_id
			)
			return self

		@dataclass(slots=True, frozen=True)
		class Entry:
			class ContextModels:
				@dataclass(slots=True)
				class AbsenceOnce:
					id: int
					from_: date
					to: date
					type: Literal["onceAbsence"] = "onceAbsence"

				@dataclass(slots=True)
				class AbsenceRecurring:
					id: int
					weekdays: list[int] | None = None
					monthDay: int | None = None
					type: Literal["recurringAbsence"] = "recurringAbsence"

				@dataclass(slots=True)
				class Miscellaneous:
					id: int
					comment: str
					type: Literal["misc"] = "misc"

			class Status(Enum):
				MEMBER = "member"
				EX_MEMBER = "ex_member"
			gaijin_id: int
			username: str
			discord_id: int | None
			status: Status
			joined_at: datetime | None
			timezone: int | None
			sqb_part: bool | None

			@classmethod
			def from_dict(cls, obj:dict[str, str|int]):
				return cls(
					obj["gaijin_id"],
					obj["username"],
					obj["discord_id"],
					GuildConfig._Management.Entry.Status(obj["status"]),
					datetime.fromtimestamp(obj["joined_at"], UTC) if obj["joined_at"] is not None else None,
					obj["tz"],
					obj["sqb_part"]
				)

			@staticmethod
			async def list_users(page:int = 1) -> tuple["GuildConfig._Management.Entry", ...]:
				if page < 1:
					raise ValueError("Page value must be above 0")
				async with Network.get(f"{__MANAGEMENT_URL}/api/v1/users?page={page}&per_page=50") as r:
					data = (await r.json())["data"]
				for i, user in enumerate(data):
					data[i] = GuildConfig._Management.Entry.from_dict(user)
				return tuple(data)

			async def context(self) -> tuple["ContextModels.AbsenceOnce | ContextModels.AbsenceRecurring | ContextModels.Miscellaneous", ...]:
				async with Network.get(f"{__MANAGEMENT_URL}/api/v1/users/{self.gaijin_id}/context") as r:
					data: list[dict[str, int|str|list[str]]] = await r.json()
				parsed = []
				for item in data:
					match item.get("type"):
						case "recurringAbsence":
							parsed.append(self.ContextModels.AbsenceRecurring(
								id=item["id"],
								weekdays=item.get("weekdays"),
								monthDay=item.get("monthDay")
							))
						case "onceAbsence":
							parsed.append(self.ContextModels.AbsenceOnce(
								id=item["id"],
								from_=datetime.strptime(item["from"], "%Y-%m-%d"),
								to=datetime.strptime(item["from"], "%Y-%m-%d")
							))
						case "misc":
							parsed.append(self.ContextModels.Miscellaneous(
								id=item["id"],
								comment=item["comment"]
							))
						case _:
							raise RuntimeError(f"Invalid type {item.get("type")} given")
				return tuple(parsed)

		@overload
		async def get(self, *, username:str, discord_id: int | None = None, gaijin_id: int | None = None) -> "Entry | None": ...
		@overload
		async def get(self, *, username:str | None = None, discord_id: int, gaijin_id: int | None = None) -> tuple["Entry", ...]: ...
		@overload
		async def get(self, *, username:str | None = None, discord_id: int | None = None, gaijin_id: int) -> "Entry| None": ...
		async def get(self, *, username:str | None = None, discord_id: int | None = None, gaijin_id: int | None = None):
			if not (username or discord_id or gaijin_id):
				raise RuntimeError("You must provide either `username`, `discord_id` or `gaijin_id`")
			if len([i for i in [username, discord_id, gaijin_id] if i is not None]) != 1:
				raise RuntimeError("You must provide only one of `username`, `discord_id` or `gaijin_id`")

			if username or discord_id:
				user = username or discord_id
				i = 1
				users = []
				try:
					while True:
						async with Network.get(
							f"{__MANAGEMENT_URL}/api/v1/users?search={user}&page={i}",
							headers={
								"Authorization": f"Bearer {self.token}"
							}
						) as r:
							r.raise_for_status()
							data = (await r.json())["data"]
						if data == []:
							if username:
								return None
							if discord_id:
								return tuple(users)
						for _user in data:
							if username and _user["username"] == user:
								return self.Entry.from_dict(_user)
							elif discord_id and _user["discord_id"] == user:
								users.append(self.Entry.from_dict(_user))
						i += 1
				except ClientResponseError:
					return None

			elif gaijin_id:
				async with Network.get(f"{__MANAGEMENT_URL}/api/v1/users/{gaijin_id}") as r:
					data = (await r.json())["data"]
				if not data:
					return
				return self.Entry.from_dict(data)

	__ID: int
	__CHANNELS: dict[Channels, int]
	__ROLES: dict[Roles, int|list[int]]
	__CATEGORIES: dict[Categories, int]
	__SQUADRON_ID: int | None
	__MANAGEMENT: _Management | None

	@classmethod
	async def from_id(cls, guild_id: int | None) -> "GuildConfig | None":
		if guild_id is None:
			return None

		path = GUILDS / f"{guild_id}.json"
		if not path.exists():
			return None
		if Client.BOT.get_guild(guild_id) is None:
			path.unlink()
			return None # Bot is no longer in the given guild

		config:dict[str, dict] = load_json(path.read_text())

		return cls(
			__ID=guild_id,
			__CHANNELS=config.get("channels", {}),
			__ROLES=config.get("roles", {}),
			__CATEGORIES=config.get("categories", {}),
			__MANAGEMENT=await cls._Management.login(config.get("squadron"))
		)

	@overload
	def get(self, value: Literal[Roles.COMMON]) -> tuple[discord.Role, ...]: ...
	@overload
	def get(self, value: Roles) -> discord.Role | None: ...
	@overload
	def get(self, value: Categories) -> discord.CategoryChannel | None: ...
	@overload
	def get(self, value: Literal[Channels.ANNOUNCEMENTS, Channels.AUDIT_LOG, Channels.LOGS, Channels.SCORE]) -> discord.TextChannel | None: ...
	@overload
	def get(self, value: Literal[Channels.WTNEWS, Channels.PROPAGANDA]) -> discord.ForumChannel | None: ...
	def get(self, value: Roles|Channels|Categories):
		if isinstance(value, Channels):
			if value in self.__CHANNELS:
				return Client.BOT.get_channel(self.__CHANNELS[value])
		elif isinstance(value, Categories):
			if value not in self.__CATEGORIES:
				return
			for categ in self.guild.categories:
				if categ.id != self.__CATEGORIES[value]:
					continue
				return categ
		elif isinstance(value, Roles):
			if value == Roles.COMMON:
				if Roles.COMMON in self.__ROLES:
					guild = self.guild
					return tuple([guild.get_role(role) for role in self.__ROLES[Roles.COMMON]])
				return ()
			elif value in self.__ROLES:
				return self.guild.get_role(self.__ROLES[value])
		return None

	@property
	def guild(self)	-> discord.Guild:
		return Client.BOT.get_guild(self.__ID)
	@property
	def squadron(self) -> int | None:
		return self.__SQUADRON_ID
	@property
	def management(self) -> _Management:
		return self.__MANAGEMENT

	async def random_propaganda(self):
		channel = self.get(Channels.PROPAGANDA)

		threads: list[discord.Thread] = []
		for post in channel.threads:
			if post.starter_message.content.startswith("[Unverified]"):
				continue
			threads.append(post)
		async for post in channel.archived_threads(limit=None):
			threads.append(post)

		attachments = []
		for post in threads:
			if not post.starter_message.attachments:
				await post.delete(reason="No propaganda attachment given")
			else:
				attachments.extend(post.starter_message.attachments)

		return choice(attachments) if attachments else None

__CACHE: dict[int, GuildConfig] = {}

async def get(guild_id: int | discord.Interaction) -> GuildConfig | None:
	if isinstance(guild_id, discord.Interaction):
		guild_id = guild_id.guild_id
	if guild_id in __CACHE:
		return __CACHE[guild_id]
	config = await GuildConfig.from_id(guild_id)
	if config is None:
		return
	__CACHE[guild_id] = config
	return config

async def guilds() -> AsyncIterator[GuildConfig]:
	for path in GUILDS.iterdir():
		if path.name == "example.json":
			continue
		config = await GuildConfig.from_id(int(path.name.removesuffix(".json")))
		if config is None:
			continue
		yield config
