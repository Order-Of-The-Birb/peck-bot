from os import getenv
from typing import Any, overload
from aiohttp import ClientResponseError
from modules import network
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, UTC

_url: str = getenv("management_api_url", "http://127.0.0.1:8000/").strip().removesuffix("/")
_token: str = getenv("management_token")
SQUADRON_ID = None

@dataclass(slots=True, frozen=True)
class Entry:
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
			Entry.Status(obj["status"]),
			datetime.fromtimestamp(obj["joined_at"], UTC) if obj["joined_at"] is not None else None,
			obj["tz"],
			obj["sqb_part"]
		)

async def list_users(page:int = 1) -> tuple[Entry]:
	if page < 1:
		raise ValueError("Page value must be above 0")
	async with network.get(f"{_url}/api/v1/users?page={page}&per_page=50") as r:
		data = (await r.json())["data"]
	for i, user in enumerate(data):
		data[i] = Entry.from_dict(user)
	return tuple(data)

@overload
async def get(*, username:str, discord_id: int = None, gaijin_id: int = None) -> Entry | None: ...
@overload
async def get(*, username:str = None, discord_id: int, gaijin_id: int = None) -> tuple[Entry]: ...
@overload
async def get(*, username:str = None, discord_id: int = None, gaijin_id: int) -> Entry | None: ...
async def get(*, username:str = None, discord_id: int = None, gaijin_id: int = None):
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
				async with network.get(f"{_url}/api/v1/users?search={user}&page={i}") as r:
					r.raise_for_status()
					data = (await r.json())["data"]
				if data == []:
					if username:
						return None
					if discord_id:
						return tuple(users)
				for _user in data:
					if username and _user["username"] == user:
						return Entry.from_dict(_user)
					elif discord_id and _user["discord_id"] == user:
						users.append(Entry.from_dict(_user))	
				i += 1
		except ClientResponseError:
			return None
		
	elif gaijin_id:
		async with network.get(f"{_url}/api/v1/users/{gaijin_id}") as r:
			data = (await r.json())["data"]
		if not data:
			return
		return Entry.from_dict(data)

async def context(user:int) -> tuple[dict[str, Any]]:
	async with network.get(f"{_url}/api/v1/users/{user}/context") as r:
		return tuple(await r.json())

async def thunderapi_token() -> str:
	async with network.get(f"{_url}/api/v1/server-token", headers={"Authorization": f"Bearer {_token}"}) as r:
		data = await r.json()
	return data["token"]

async def upd_squadron_id():
	global SQUADRON_ID
	if SQUADRON_ID:
		return

	try:
		async with network.get(f"{_url}/api/v1/clan-id") as r:
			r.raise_for_status()
			SQUADRON_ID = int((await r.json())["clan_id"])
	except ClientResponseError:
		return

if __name__ == '__main__':
	import asyncio
	async def main():
		await network.start()

		results = (

		)
		pass
		
		await network.close()
	loop = asyncio.new_event_loop()
	result = loop.run_until_complete(main())