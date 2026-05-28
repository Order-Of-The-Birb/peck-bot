from enum import StrEnum
from os import getenv
from typing import Any, TypeVar
from requests import get, post, patch
from requests.exceptions import ConnectionError
from datetime import date, datetime
from time import sleep
from collections.abc import Hashable, Iterator, Callable, Iterable

from utils.generic import httperror
from utils.wt import normalizeUsername

__reload_deps__ = ("utils.generic", "utils.wt")

from logging import getLogger
logger = getLogger(__name__)

class UserRepository(list["UserRepository.User"]):
	"""User repository for stored users"""
	class LeaveInfo(StrEnum):
		NONE = "null"
		LEFT = "Left"
		SERVER = "LeftServer"
		SQUADRON = "LeftSquadron"
	class Status(StrEnum):
		EX_MEMBER = "ex_member"
		MEMBER = "member"
		UNVERIFIED = "unverified"
		APPLICANT = "applicant"

	class DiscordData:
		"""Shared per-discord-user data. Multiple peck_users rows referencing the
		same discord_id share a single DiscordData instance, so updating sqb_part
		or timezone on one User immediately reflects on all others."""
		def __init__(self, discord_id: int, sqb_part: bool|None = None, timezone: int|None = None):
			self.discord_id: int = discord_id
			self.sqb_part: bool|None = sqb_part
			self.timezone: int|None = timezone

	class User:
		class Editor:
			def __init__(self, user: "UserRepository.User"):
				self.user = user

			def __enter__(self):
				return self.user

			def __exit__(self, exc_type, exc, tb):
				if exc_type is not None:
					self.user.rollback()
					return False
				if not self.user.commit():
					logger.error(f"Failed to commit changes for user {self.user.gaijin_id}")
					self.user.rollback()
					raise RuntimeError(f"Failed to commit changes for user {self.user.gaijin_id}")
				return False

		__base_url:str
		__token:str
		__data:dict[str, int|str|None]
		__saved_data:dict[str, int|str|None]
		_discord_data: "UserRepository.DiscordData|None"
		def __init__(self, base_url:str, token:str, discord_data:"UserRepository.DiscordData|None"=None, **data:int|str):
			self.__base_url = base_url
			self.__token = token
			self.__data = data
			self.__saved_data = data.copy()
			self._discord_data = discord_data
		def pull(self) -> bool:
			r = get(self.__base_url+f"users/{self.gaijin_id}")
			if not r.ok:
				logger.error(f"Endpoint threw an error: {r.status_code} ({httperror(r)})")
				return False
			data: dict[str, int|str] = r.json()["data"]
			self.__data = data
			self.__saved_data = data.copy()
			# Sync shared DiscordData
			if self._discord_data:
				self._discord_data.discord_id = data.get("discord_id")
				self._discord_data.sqb_part = data.get("sqb_part")
				self._discord_data.timezone = data.get("tz")
			return True
		def push(self) -> bool:
			editedValues:dict[str, str|int|None] = {
			    key: value
			    for key, value in self.__data.items()
			    if key != "leave_info" and self.__saved_data.get(key) != value
			}

			if self.__data.get("leave_info") != self.__saved_data.get("leave_info"):
				if self.leave_info is not None:
					r = patch(
						self.__base_url+f"users/{self.gaijin_id}/leave_info", 
						json={"type":self.leave_info.value, "token": self.__token},
						headers={"X-Api-Key": self.__token},
					)
					if not r.ok:
						logger.error(f"Failed to update the following member's leave info: {self.gaijin_id} returned {r.status_code} ({httperror(r)})")
						return False	
			if editedValues:
				editedValues["token"] = self.__token
				r = patch(self.__base_url+f"users/{self.gaijin_id}", json=editedValues, headers={"X-Api-Key": self.__token})
				if not r.ok:
					logger.error(f"Failed to update the following member: {self.gaijin_id} returned {r.status_code} ({httperror(r)})")
					return False
			return True
		
		def rollback(self) -> None:
			self.__data = self.__saved_data.copy()
		def commit(self) -> bool:
			if self.push():
				self.__saved_data = self.__data.copy()
				return True
			return False
	
		def edit(self):
			return self.Editor(self)
		#region Gaijin ID
		@property
		def gaijin_id(self) -> int:
			return self.__data["gaijin_id"]
		#endregion
		#region Username
		@property
		def username(self) -> str:
			return self.__data["username"]
		@username.setter
		def username(self, value:str) -> None:
			self.__data["username"] = value
		#endregion
		#region discord ID — delegates to shared DiscordData
		@property
		def discord_id(self) -> int|None:
			return self._discord_data.discord_id if self._discord_data else self.__data["discord_id"]
		@discord_id.setter
		def discord_id(self, value:int) -> None:
			self.__data["discord_id"] = value
			if self._discord_data:
				self._discord_data.discord_id = value
		#endregion
		#region Status
		@property
		def status(self) -> "UserRepository.Status":
			return UserRepository.Status(self.__data["status"])
		@status.setter
		def status(self, value:"UserRepository.Status") -> None:
			self.__data["status"] = value.value
		#endregion
		#region Timezone — delegates to shared DiscordData
		@property
		def timezone(self) -> int|None:
			return self._discord_data.timezone if self._discord_data else self.__data.get("tz")
		@timezone.setter
		def timezone(self, value:int|None) -> None:
			self.__data["tz"] = value
			if self._discord_data:
				self._discord_data.timezone = value
		#endregion
		#region Joindate
		@property
		def joindate(self) -> date|None:
			if self.__data.get("joindate") is None: return None
			return datetime.strptime(self.__data["joindate"], "%Y-%m-%d").date()
		@joindate.setter
		def joindate(self, value:date) -> None:
			self.__data["joindate"] = value.strftime("%Y-%m-%d")
		#endregion
		#region Initiator
		@property
		def initiator(self) -> int:
			return self.__data["initiator"]
		@initiator.setter
		def initiator(self, value:int) -> None:
			self.__data["initiator"] = value
		#endregion
		#region SQB Participation — delegates to shared DiscordData
		@property
		def sqb_part(self) -> bool|None:
			if self._discord_data:
				return self._discord_data.sqb_part
			return None
		@sqb_part.setter
		def sqb_part(self, value:bool|None) -> None:
			self.__data["sqb_part"] = value
			if self._discord_data:
				self._discord_data.sqb_part = value
				return
		#endregion
		#region Leave Info
		@property
		def leave_info(self) -> "UserRepository.LeaveInfo"|None:
			value = self.__data.get("leave_info")
			return None if value is None else UserRepository.LeaveInfo(value)
		@leave_info.setter
		def leave_info(self, value:"UserRepository.LeaveInfo") -> None:
			self.__data["leave_info"] = None if value is None else value.value
		#endregion
	def __init__(self):
		super().__init__()
		self.__api_token = self.__required_env("management_token")
		base_url = self.__required_env("api_url")
		self.__base_url = (base_url if base_url.endswith("/") else base_url + "/") + "api/v1/"
		self._discord_data_cache: dict[int, UserRepository.DiscordData] = {}
		self.refresh()

	def _get_or_create_discord_data(self, discord_id: int|None, sqb_part: bool|None, timezone: int|None) -> "UserRepository.DiscordData|None":
		"""Return a shared DiscordData instance for the given discord_id, creating one if needed."""
		if discord_id is None:
			return None
		if discord_id not in self._discord_data_cache:
			self._discord_data_cache[discord_id] = UserRepository.DiscordData(
				discord_id=discord_id,
				sqb_part=sqb_part,
				timezone=timezone,
			)
		return self._discord_data_cache[discord_id]
	def __required_env(self, key:str) -> str:
		value = getenv(key)
		if value is None:
			raise EnvironmentError(f"Missing required environment variable '{key}'")
		return value.strip().strip('"').strip("'")
	def __iter__(self) -> Iterator["UserRepository.User"]:
		return super().__iter__()
	def refresh(self):
		self.clear()
		self._discord_data_cache.clear()
		i = 1
		while True:
			connection_attempts = 2
			while True:
				try:
					r = get(self.__base_url+f"users?page={i}&per_page=100", headers={"accepts": "application/json"})
					break
				except ConnectionError:
					logger.warning(f"Database API could not be reached. Retrying in {f"{connection_attempts//60} minutes" if connection_attempts > 60 else ""}{connection_attempts%60} seconds")
					sleep(connection_attempts)
					connection_attempts = connection_attempts*2
					if connection_attempts >= 10*60:
						raise ConnectionRefusedError("Establishing connection to database timed out.")
			if not r.ok:
				logger.error(f"Endpoint threw an error: {r.status_code} ({httperror(r)})")
				return
			if r.json()["data"] == []:
				break
			for item in r.json()["data"]:
				sqb_raw = item.get("sqb_part")
				sqb_part: bool|None = None if sqb_raw is None else sqb_raw == 1
				dd = self._get_or_create_discord_data(item.get("discord_id"), sqb_part, item.get("tz"))
				self.append(self.User(self.__base_url, self.__api_token, discord_data=dd, **item))
			i += 1
		logger.info("Refreshed user cache")
	def add_user(self, gaijin_id:int, username:str, status:Status=Status.UNVERIFIED, discord_id:int|None=None, timezone:int|None=None, joindate:date|None=None, initiator:int|None=None, sqb_part:bool|None=None):
		if gaijin_id is None: raise ValueError("Invalid gaijin ID given: Cannot be `null`")
		if gaijin_id in [i.gaijin_id for i in self]: return
		r = get(self.__base_url+f"users/{gaijin_id}")
		if r.status_code == 404:
			r = post(
				self.__base_url+"users",
				headers={"X-Api-Key": self.__api_token},
				json={
					"gaijin_id":gaijin_id, 
					"username":username, 
					"status":status.value, 
					"discord_id":discord_id, 
					"tz":timezone, 
					"joindate":joindate.strftime("%Y-%m-%d") if joindate is not None else None, 
					"initiator":initiator,
					"sqb_part": sqb_part,
					"token":self.__api_token
				}
			)
			if not r.ok:
				raise ValueError(f"User '{username}' could not be added to the database ({r.status_code}, {httperror(r)}): {r.text}")
		elif not r.ok:
			raise LookupError(f"Endpoint threw an error while querying {r.status_code} ({httperror(r)})")
		dd = self._get_or_create_discord_data(discord_id, sqb_part, timezone)
		self.append(self.User(self.__base_url, self.__api_token, discord_data=dd, gaijin_id=gaijin_id, username=username, status=status, discord_id=discord_id, tz=timezone, joindate=joindate.strftime("%Y-%m-%d") if joindate is not None else None, initiator=initiator, sqb_part=sqb_part))
	def getByGID(self, gaijin_id:int) -> User|None:
		for user in self:
			if user.gaijin_id == gaijin_id:
				return user
	def getByName(self, username:str) -> User|None:
		username = normalizeUsername(username)
		for user in self:
			if user.username == username:
				return user
	def getByDID(self, discord_id:int) -> list[User]:
		tmp = []
		for user in self:
			if user.discord_id == discord_id:
				tmp.append(user)
		return tmp

	#region LINQ quick-querying 
	def where(self, key: Callable[[User], bool]) -> Query[User]:
		query = Query(self)
		return query.where(key)
	def orderBy(self, key: Callable[[User], Any], desc: bool = False) -> Query[User]:
		query = Query(self)
		return query.orderBy(key, desc)
	def distinct(self, key: Callable[[User], Hashable]) -> Query[User]:
		query = Query(self)
		return query.distinct(key)
	def any(self, key: Callable[[User], bool]) -> bool:
		return any(key(item) for item in self)

	def query(self) -> "Query[UserRepository.User]":
		return Query(self)

# C# LINQ esque querying system
T = TypeVar("T")
class Query(list[T]):
    def __init__(self, items: Iterable[T]):
        super().__init__(items)

    def where(self, key: Callable[[T], bool]) -> "Query[T]":
        return Query(item for item in self if key(item))

    def orderBy(self, key: Callable[[T], Any], desc: bool = False) -> "Query[T]":
        return Query(sorted(self, key=key, reverse=desc))

    def distinct(self, key: Callable[[T], Hashable]) -> "Query[T]":
        seen = set()
        result = []

        for item in self:
            value = key(item)
            if value not in seen:
                seen.add(value)
                result.append(item)

        return Query(result)

    def any(self, key: Callable[[T], bool]) -> bool:
        return any(key(item) for item in self)

    def first(self) -> T | None:
        return self[0] if self else None
