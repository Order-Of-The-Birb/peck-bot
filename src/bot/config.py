from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import Enum, StrEnum
from json import loads as load_json
from os import getenv
from random import choice
from typing import Annotated, Literal, overload
from urllib.parse import quote_plus

import discord
from aiohttp import ClientResponseError
from typing_extensions import Doc

import bot.client as Client
import bot.extensions as ext
import utils.network as Network
from paths import GUILDS

_MANAGEMENT_URL: str = getenv("management_api_url", "http://127.0.0.1:8000/").strip().removesuffix("/")

class Channels(StrEnum):
	ANNOUNCEMENTS = "ANNOUNCEMENTS"
	AUDIT_LOG = "AUDIT_LOG"
	LOGS = "LOGS"
	SCORE = "SCORE"
	SQB = "SQB"
	PROPAGANDA = "PROPAGANDA"
	WTNEWS = "WTNEWS"
	CLIPS = "CLIPS"
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
	SQUAD_VC = "SQUAD_VC"

class GuildConfig:
	class _Management:
		squadron_id: int

		@classmethod
		async def login(cls, squadron_id: int | None):
			if squadron_id is None:
				return None

			self = cls()
			self.squadron_id=squadron_id
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

			async def context(self) -> tuple["ContextModels.AbsenceOnce | ContextModels.AbsenceRecurring | ContextModels.Miscellaneous", ...]:
				async with Network.get(f"{_MANAGEMENT_URL}/api/v1/users/{self.gaijin_id}/context") as r:
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
		async def get(self, *, username:str, discord_id: int | None = None, gaijin_id: int | None = None) -> tuple["Entry", ...]: ...
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
						async with Network.get(f"{_MANAGEMENT_URL}/api/v1/users?search={user}&page={i}") as r:
							r.raise_for_status()
							data = (await r.json())["data"]
						if data == []:
							return tuple(users)
						for _user in data:
							if (username and user in _user["username"]) or (discord_id and _user["discord_id"] == user):
								users.append(self.Entry.from_dict(_user))
						i += 1
				except ClientResponseError:
					return None

			elif gaijin_id:
				async with Network.get(f"{_MANAGEMENT_URL}/api/v1/users/{gaijin_id}") as r:
					data = (await r.json())["data"]
				if not data:
					return
				return self.Entry.from_dict(data)


		class SortFields(Enum):
			NAME = "username"
			GAIJIN = "gaijin_id"
			STATUS = "status"
			DISCORD = "discord_id"
			TZ = "tz"
			SQB = "sqb_part"
			JOINDATE = "joined_at"
		async def query(
			self,
			page:int = 1,
			/, *,
			per_page: int = 50,
			search: Annotated[int | str | None, Doc("Search for a specific user")] = None,
			status: Annotated[Entry.Status | None, Doc("Filter by a specific status\nString searches by username, int searches both Gaijin and Discord IDs")] = None,
			tz: Annotated[int | None, Doc("Filter by a specific timezone")] = None,
			sort_direction: Literal["asc", "desc"] = "asc",
			sort_by: SortFields | None = None
		) -> tuple["GuildConfig._Management.Entry", ...]:
			if page < 1:
				raise ValueError("Page value must be above 0")
			if not 1 <= per_page <= 100:
				raise ValueError("per_page must be between 1 and 100")
			if tz is not None and not -11 <= tz <= 12:
				raise ValueError(f"timezone value '{tz}' is invalid")
			if sort_direction not in ["asc", "desc"]:
				raise ValueError(f"Invalid sort direction '{sort_direction}' given")

			queries = {
				"page": page,
				"per_page": per_page
			}
			if sort_by is not None:
				queries["sort_direction"] = sort_direction
				queries["sort_by"] = sort_by.value
			if tz is not None:
				queries["tz"] = tz
			if search is not None:
				queries["search"] = search
			if status is not None:
				queries["status"] = status.value

			link = f"{_MANAGEMENT_URL}/api/v1/users?{"&".join(f"{k}={quote_plus(str(v))}" for k, v in queries.items())}"

			async with Network.get(link) as r:
				data = (await r.json())["data"]
			for i, user in enumerate(data):
				data[i] = GuildConfig._Management.Entry.from_dict(user)
			return tuple(data)

	__ID: int
	__CHANNELS: dict[Channels, int]
	__ROLES: dict[Roles, int|list[int]]
	__CATEGORIES: dict[Categories, int]
	__SQUADRON_ID: int | None
	__MANAGEMENT: _Management | None

	def __init__(self,
		id: int,
		channels: dict[Channels, int],
		roles: dict[Roles, int|list[int]],
		categories: dict[Categories, int],
		squadron_id: int | None,
		management: _Management | None
	):
		self.__ID = id
		self.__CHANNELS = channels
		self.__ROLES = roles
		self.__CATEGORIES = categories
		self.__SQUADRON_ID = squadron_id
		self.__MANAGEMENT = management

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
			id=guild_id,
			channels= config.get("channels", {}),
			roles= config.get("roles", {}),
			categories= config.get("categories", {}),
			squadron_id= config.get("squadron"),
			management=await cls._Management.login(config.get("squadron"))
		)

	@overload
	def get(self, value: Literal[Roles.COMMON]) -> tuple[discord.Role, ...]: ...
	@overload
	def get(self, value: Roles) -> discord.Role | None: ...
	@overload
	def get(self, value: Categories) -> discord.CategoryChannel | None: ...
	@overload
	def get(self, value: Literal[Channels.ANNOUNCEMENTS, Channels.AUDIT_LOG, Channels.LOGS, Channels.SCORE, Channels.PROPAGANDA]) -> discord.TextChannel | None: ...
	@overload
	def get(self, value: Literal[Channels.WTNEWS, Channels.CLIPS]) -> ext.ForumChannel | None: ...
	def get(self, value: Roles|Channels|Categories):
		if isinstance(value, Channels):
			if value not in self.__CHANNELS:
				return None

			channel = Client.BOT.get_channel(self.__CHANNELS[value])
			if channel is None:
				return None

			if isinstance(channel, discord.ForumChannel):
				channel.__class__ = ext.ForumChannel
			return channel
		elif isinstance(value, Categories):
			if value not in self.__CATEGORIES:
				return

			for categ in self.guild.categories:
				if categ.id != self.__CATEGORIES[value]:
					continue
				return categ
		elif isinstance(value, Roles):
			if value not in self.__ROLES:
				return None

			if value == Roles.COMMON:
				if Roles.COMMON in self.__ROLES:
					guild = self.guild
					return tuple([guild.get_role(role) for role in self.__ROLES[Roles.COMMON]])
				return ()
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

	async def create_missing_tags_wtnews(self):
		ch = self.get(Channels.WTNEWS)
		available_tags = []
		required = ["Event", "Development", "Video", "Shop", "Fixed", "eSport", "Market", "Special", "Warbonds", "Fair Play", "Update"]
		for tag in ch.available_tags:
			if tag in required:
				available_tags.append(tag.name)

		for tag in required:
			if tag not in available_tags:
				ch.create_tag(
					name=tag,
					moderated=True,
					reason="Missing News channel tag"
				)

	async def random_propaganda(self):
		channel = self.get(Channels.PROPAGANDA)
		if channel is None:
			raise ext.MissingConfigError("Propaganda channel not set up")

		attachments = []
		async for msg in channel.history(limit=None):
			if not msg.attachments:
				await msg.delete(reason="No propaganda attachment given")
			else:
				attachments.extend(msg.attachments)
		if attachments:
			return choice(attachments)
		return None

	async def setup(self, channel: Channels):
		pass # TODO: Implement

__CACHE: dict[int, GuildConfig] = {}

async def get(guild_id: int | ext.Interaction) -> GuildConfig | None:
	if isinstance(guild_id, ext.Interaction):
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
		if path.name in ["example.json",".gitignore"]:
			continue
		config = await GuildConfig.from_id(int(path.name.removesuffix(".json")))
		if config is None:
			continue
		yield config
