from enum import StrEnum
from os import getenv, _exit
from requests import get, post, patch
from requests.exceptions import ConnectionError
from datetime import date, datetime
from time import sleep
from utils.generic import httperror
from utils.wt import normalizeUsername
from collections.abc import Iterator

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
	class User:
		__base_url:str
		__token:str
		__data:dict[str, int|str|None]
		def __init__(self, base_url:str, token:str, **data:int|str):
			self.__base_url = base_url
			self.__token = token
			self.__data = data
		def pull(self) -> bool:
			r = get(self.__base_url+f"users/{self.gaijin_id}")
			if not r.ok:
				logger.error(f"Endpoint threw an error: {r.status_code} ({httperror(r)})")
				return False
			self.__data:dict[str, int|str] = r.json()["data"]
			return True
		def push(self) -> bool:
			r = get(self.__base_url+f"users/{self.gaijin_id}")
			if not r.ok:
				logger.error(f"An error occurred when getting the current data of user {self.gaijin_id} returned {r.status_code} ({httperror(r)})")
				return False
			currentData:dict[str, int|str] = r.json()["data"]
			editedValues:dict[str, str|int] = {}
			for k, i in currentData.items():
				_ = self.__data.get(k)
				if i != _:
					editedValues[k] = _
			del currentData
			r = get(self.__base_url+f"users/{self.gaijin_id}/leave_info")
			if not r.ok:
				logger.error(f"Leave info returned {r.status_code} ({httperror(r)})")
				return False
			if (None if self.leave_info is None else self.leave_info.value) != r.json()["data"]:
				if self.leave_info is not None:
					r = patch(self.__base_url+f"users/{self.gaijin_id}/leave_info", json={"type":self.leave_info.value, "token": self.__token})
					if not r.ok:
						logger.error(f"Failed to update the following member's leave info: {self.gaijin_id} returned {r.status_code} ({httperror(r)})")
						return False	
			if editedValues:
				editedValues["token"] = self.__token
				r = patch(self.__base_url+f"users/{self.gaijin_id}", json=editedValues)
				if not r.ok:
					logger.error(f"Failed to update the following member: {self.gaijin_id} returned {r.status_code} ({httperror(r)})")
					return False
			return True
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
		#region discord ID
		@property
		def discord_id(self) -> int:
			return self.__data["discord_id"]
		@discord_id.setter
		def discord_id(self, value:int) -> None:
			self.__data["discord_id"] = value
		#endregion
		#region Status
		@property
		def status(self) -> "UserRepository.Status":
			return UserRepository.Status(self.__data["status"])
		@status.setter
		def status(self, value:"UserRepository.Status") -> None:
			self.__data["status"] = value.value
		#endregion
		#region Timezone
		@property
		def timezone(self) -> int|None:
			return self.__data["tz"]
		@timezone.setter
		def timezone(self, value:int|None) -> None:
			self.__data["tz"] = value
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
		self.refresh()
	def __required_env(self, key:str) -> str:
		value = getenv(key)
		if value is None:
			raise EnvironmentError(f"Missing required environment variable '{key}'")
		return value.strip().strip('"').strip("'")
	def __iter__(self) -> Iterator["UserRepository.User"]:
		return super().__iter__()
	def refresh(self):
		self.clear()
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
			if r.json()["data"] == []:
				break
			if not r.ok:
				logger.error(f"Endpoint threw an error: {r.status_code} ({httperror(r)})")
				return
			self.extend(self.User(self.__base_url, self.__api_token, **item) for item in r.json()["data"])
			i += 1
		logger.info("Refreshed user cache")
	def add_user(self, gaijin_id:int, username:str, status:Status=Status.UNVERIFIED, discord_id:int|None=None, timezone:int|None=None, joindate:date|None=None, initiator:int|None=None):
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
					"token":self.__api_token
				}
			)
			if not r.ok:
				raise ValueError(f"User '{username}' could not be added to the database ({r.status_code}, {httperror(r)}): {r.text}")
		elif not r.ok:
			raise LookupError(f"Endpoint threw an error while querying {r.status_code} ({httperror(r)})")
		self.append(self.User(self.__base_url, self.__api_token, gaijin_id=gaijin_id, username=username, status=status, discord_id=discord_id, tz=timezone, joindate=joindate.strftime("%Y-%m-%d") if joindate is not None else None, initiator=initiator))
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
