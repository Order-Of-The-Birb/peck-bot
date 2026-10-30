from asyncio import sleep
from collections.abc import AsyncGenerator
from logging import getLogger
from os import getenv
from typing import Any, NoReturn

from aiohttp import ClientResponseError, ClientSession

from utils import network
from utils.models.thunderapi.clan import (
	ApplicantModel,
	ClanLeaderboardModel,
	ClanModel,
	ClanSearchModel,
	CurrentSQBBracket,
	SQBTimeBracket,
)
from utils.models.thunderapi.generic import NewsModel, ReplayResultsModel
from utils.models.thunderapi.market import ItemModel, OrderHistoryModel, OrdersModel
from utils.models.thunderapi.user import GetModel, TerseModel

_logger = getLogger(__name__)

_api_url: str = getenv("thunderapi_url", "http://127.0.0.1:8008/")

async def replay(replay_id:str|int) -> ReplayResultsModel:
	if isinstance(replay_id, str):
		replay_id = int(replay_id, 16)
	return ReplayResultsModel.model_validate(await _get_json(f"/v1/replay/{replay_id:X16}"))

async def news_ws() -> AsyncGenerator[NewsModel, NoReturn]:
	while True:
		try: # On failure, restart
			async with ClientSession(_api_url) as session, session.ws_connect("/v1/news_ws") as ws:
				while True:
					yield NewsModel.model_validate(await ws.receive_json())
		except Exception:
			_logger.exception("An exception occured during news websocket runtime")
			await sleep(3)

class user:
	@staticmethod
	async def get(userid:int) -> GetModel:
		return GetModel.model_validate(await _get_json(f"/v1/users/{userid}/meta"))
	@staticmethod
	async def src(username:str) -> dict[str, TerseModel]:
		data = await _get_json(f"/v1/users/search/{username}")
		for k, v in dict(data).items():
			data[k] = TerseModel.model_validate(v)
		return data
	@staticmethod
	async def terse(*userids:int) -> dict[str, TerseModel]:
		data = await _get_json(f"/v1/users/terse?{"&".join(f"id={i}" for i in userids)}")
		for k, v in dict(data).items():
			data[k] = TerseModel.model_validate(v)
		return data
class clan:
	@staticmethod
	async def search(src: str, page: int = 0) -> list[ClanSearchModel]:
		return tuple([ClanSearchModel.model_validate(i) for i in await _get_json(f"/v1/clans/search?clanName={src}&clanTag={src}&page={page}")])
	@staticmethod
	async def clanLeaderboard(limit:int = 20, page: int = 0) -> list[ClanLeaderboardModel]:
		return tuple([ClanLeaderboardModel.model_validate(i) for i in await _get_json(f"/v1/clans/leaderboard?limit={limit}&page={page}")])
	@staticmethod
	async def leaderboardPos(clan:int) -> ClanLeaderboardModel:
		return ClanLeaderboardModel.model_validate(await _get_json(f"/v1/clans/leaderboard/{clan}"))
	@staticmethod
	async def get(clan:int) -> ClanModel:
		return ClanModel.model_validate(await _get_json(f"/v1/clans/{clan}"))
	@staticmethod
	async def applicants(clan:int) -> list[ApplicantModel]:
		return tuple([ApplicantModel.model_validate(i) for i in await _get_json(f"/v1/clans/applicants/{clan}/")])
	@staticmethod
	async def sqb_brackets() -> tuple[SQBTimeBracket, ...]:
		return tuple([SQBTimeBracket.model_validate(i) for i in await _get_json("/v1/clans/sqb")])
	@staticmethod
	async def current_bracket() -> CurrentSQBBracket:
		return CurrentSQBBracket.model_validate(await _get_json("/v1/clans/sqb/current"))
class market:
	@staticmethod
	async def get(item_hash:str) -> ItemModel:
		return ItemModel.model_validate(await _get_json(f"/v1/market/{item_hash}"))
	@staticmethod
	async def src(name: str | None = None) -> tuple[ItemModel]:
		return tuple([ItemModel.model_validate(i) for i in await _get_json(f"/v1/market/search{f"?name={name}" if name is not None else ""}")])
	@staticmethod
	async def orders(item_hash: str) -> OrdersModel:
		return OrdersModel.model_validate(await _get_json(f"/v1/market/{item_hash}/orders"))
	@staticmethod
	async def orders_history(item_hash:str) -> OrderHistoryModel:
		return OrderHistoryModel.model_validate(await _get_json(f"/v1/market/{item_hash}/history"))

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


		await network.close()
	loop = asyncio.new_event_loop()
	result = loop.run_until_complete(main())
