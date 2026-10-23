from aiohttp import ClientSession
from aiohttp.cookiejar import DummyCookieJar
from fastapi.concurrency import asynccontextmanager 
from fastapi import HTTPException
from asyncio import Lock, Event

class NetworkError(HTTPException): pass

_session: ClientSession | None = None
_closing = False
_active_ops = 0
_active_ops_done = Event()
_active_ops_done.set()
_lock = Lock()

@asynccontextmanager
async def post(url:str, **kwargs):
	async with request("POST", url, **kwargs) as resp:
		yield resp
@asynccontextmanager
async def get(url:str, **kwargs):
	async with request("GET", url, **kwargs) as resp:
		yield resp
@asynccontextmanager
async def request(method:str, url:str, **kwargs):
	async with operation() as session:
		async with session.request(method, url, **kwargs) as resp:
			resp.raise_for_status()
			yield resp

@asynccontextmanager
async def operation():
	session = await _enter_op()
	try:
		yield session
	finally:
		await _exit_op()

async def start():
	"""Initializes the NetworkManager library"""
	global _closing, _session
	async with _lock:
		if _session is not None and not _session.closed:
			return
		_closing = False
		_session = ClientSession(headers={"User-Agent": "ThunderAPI/1.0"}, cookie_jar=DummyCookieJar())

async def close():
	"""Prepares the NetworkManager library for shutdown"""
	global _closing, _session
	async with _lock:
		_closing = True

	await _active_ops_done.wait()

	async with _lock:
		if _session is not None and not _session.closed:
			await _session.close()
		_session = None

async def _enter_op():
	global _active_ops
	async with _lock:
		if _closing:
			raise RuntimeError("NetworkManager is shutting down")

		if _session is None or _session.closed:
			raise RuntimeError("NetworkManager is not started")

		_active_ops += 1
		_active_ops_done.clear()

		return _session

async def _exit_op():
	global _active_ops
	async with _lock:
		_active_ops -= 1

		if _active_ops <= 0:
			_active_ops = 0
			_active_ops_done.set()