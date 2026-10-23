from asyncio import sleep
from logging import getLogger
from aiohttp import ClientSession, ClientResponseError
from datetime import datetime, UTC
from os import getenv
from typing import Any, AsyncGenerator, NoReturn
from utils import network

_logger = getLogger(__name__)

_api_url: str = getenv("thunderapi_url", "http://127.0.0.1:8008/")

async def replay(replay_id:str|int) -> dict[str, Any]:
	if isinstance(replay_id, str):
		replay_id = int(replay_id, 16)
	return await _get_json(f"/v1/replay/{replay_id:X16}")

async def news_ws() -> AsyncGenerator[dict[str, Any], NoReturn]:
	while True:
		try: # On failure, restart
			async with ClientSession(_api_url) as session:
				async with session.ws_connect("/v1/news_ws") as ws:
					while True:
						yield await ws.receive_json()
		except Exception:
			_logger.exception("An exception occured during news websocket runtime")
			await sleep(3)

class user:
	@staticmethod
	async def get(userid:int) -> dict[str, Any]:
		return await _get_json(f"/v1/users/{userid}")
	@staticmethod
	async def src(username:str) -> dict[str, Any]:
		return await _get_json(f"/v1/users/search/{username}")
	@staticmethod
	async def terse(*userids:int) -> dict[str, Any]:
		return await _get_json(f"/v1/users/terse?{"&".join(f"id={i}" for i in userids)}")
class clan:
	@staticmethod
	async def search(src: str, page: int = 0) -> list[dict[str, Any]]:
		return await _get_json(f"/v1/clans/search?clanName={src}&clanTag={src}&page={page}")
	@staticmethod
	async def clanLeaderboard(limit:int = 20, page: int = 0) -> list[dict[str, Any]]:
		return await _get_json(f"/v1/clans/leaderboard?limit={limit}&page={page}")
	@staticmethod
	async def leaderboardPos(clan:int) -> dict[str, Any]:
		return await _get_json(f"/v1/clans/leaderboard/{clan}")
	@staticmethod
	async def get(clan:int) -> dict[str, Any]:
		return await _get_json(f"/v1/clans/{clan}")
	@staticmethod
	async def applicants(clan:int) -> list[dict[str, Any]]:
		return await _get_json(f"/v1/clans/applicants/{clan}/")
class market:
	@staticmethod
	async def get(item_hash:str) -> dict[str, Any]:
		return await _get_json(f"/v1/market/{item_hash}")
	@staticmethod
	async def src(name: str | None = None) -> list[dict[str, Any]]:
		return await _get_json(f"/v1/market/search{f"?name={name}" if name is not None else ""}")
	@staticmethod
	async def orders(item_hash: str) -> dict[str, Any]:
		return await _get_json(f"/v1/market/{item_hash}/orders")
	@staticmethod
	async def orders_history(item_hash:str) -> dict[str, Any]:
		return await _get_json(f"/v1/market/{item_hash}/orders/history")

#region Helpers
async def _get_json(path: str, **kwargs) -> Any:
	try:
		return await _fetch_json(path, **kwargs)
	except ClientResponseError as e:
		if e.status != 401:
			raise
	return await _fetch_json(path, **kwargs)

async def _fetch_json(path: str, **kwargs) -> Any:
	async with network.get(
		_create_url(path),
		**kwargs
	) as r:
		return await r.json()

def _create_url(path: str) -> str:
	return f"{_api_url.strip().removesuffix("/")}/{path.strip().removeprefix("/")}"
#endregion

if __name__ == '__main__':
	import asyncio
	async def main():
		await network.start()

		pass

		await network.close()
	loop = asyncio.new_event_loop()
	result = loop.run_until_complete(main())
