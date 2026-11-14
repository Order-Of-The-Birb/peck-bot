"""Read vehicle battle ratings from the official War Thunder Wiki."""

import json
import re
from unicodedata import normalize

import aiohttp
from bs4 import BeautifulSoup

WIKI_URL = "https://wiki.warthunder.com"
_TIMEOUT = aiohttp.ClientTimeout(total=5)
_MAX_BODY = 2 * 1024 * 1024
_UNIT_PATH = re.compile(r"/unit/([a-zA-Z0-9_-]{1,100})")
_RATING = re.compile(r"[0-9]{1,2}\.[037]")
_BATTLE_TYPES = {"air": "air", "tank": "ground", "ship": "naval"}
_VEHICLE_TYPES = {
	"Aviation": "air",
	"Ground Vehicles": "ground",
	"Helicopters": "helicopter",
	"Bluewater Fleet": "naval",
	"Coastal Fleet": "naval",
}


class _WikiError(Exception):
	pass


async def _fetch(session: aiohttp.ClientSession, method: str, path: str, **kwargs) -> str:
	async with session.request(method, f"{WIKI_URL}{path}", timeout=_TIMEOUT, allow_redirects=False, **kwargs) as response:
		if response.status != 200:
			raise _WikiError
		body = bytearray()
		async for chunk in response.content.iter_chunked(16 * 1024):
			body.extend(chunk)
			if len(body) > _MAX_BODY:
				raise _WikiError
		return body.decode("utf-8")


def _match_key(value: str) -> str:
	return "".join(char for char in normalize("NFKC", value).casefold() if char.isalnum())


def _matches(search: str) -> list[dict[str, str]]:
	try:
		payload = json.loads(search)
		groups = payload.get("result") if isinstance(payload, dict) and payload.get("success") is True else None
	except (ValueError, RecursionError) as error:
		raise _WikiError from error
	if not isinstance(groups, list):
		raise _WikiError

	matches = {}
	for group in groups:
		if not isinstance(group, dict) or group.get("title") != "Vehicles":
			continue
		items = group.get("items")
		if not isinstance(items, list):
			raise _WikiError
		for item in items:
			if not isinstance(item, dict):
				continue
			path = item.get("link")
			name = item.get("title")
			match = _UNIT_PATH.fullmatch(path) if isinstance(path, str) else None
			if match is None or not isinstance(name, str) or not 0 < len(name) <= 100:
				continue
			unit_id = match.group(1)
			candidate = {"vehicle": " ".join(name.split()), "vehicle_id": unit_id}
			subtitle = item.get("subtitle")
			if isinstance(subtitle, str) and len(subtitle) <= 100:
				candidate["description"] = " ".join(subtitle.split())
			matches[unit_id] = candidate
	return list(matches.values())


def _battle_ratings(page: BeautifulSoup) -> dict[str, dict[str, str]]:
	card = page.select_one(".game-unit_card-info .game-unit_br")
	if card is None:
		raise _WikiError
	category = page.select_one(".game-unit_title .game-unit_nation")
	default_type = _VEHICLE_TYPES.get(category.get_text(strip=True), "standard") if category else "standard"
	ratings = {}
	for row in card.select(".game-unit_br-item"):
		mode = row.select_one(".mode")
		value = row.select_one(".value")
		if mode is None or value is None:
			continue
		mode, value = mode.get_text(strip=True), value.get_text(strip=True)
		if mode not in ("AB", "RB", "SB") or not _RATING.fullmatch(value):
			continue
		panel = row.find_parent(id=re.compile(r"^unit-br-(air|tank|ship)$"))
		battle_type = _BATTLE_TYPES[panel["id"].removeprefix("unit-br-")] if panel else default_type
		ratings.setdefault(battle_type, {})[mode] = value
	if not ratings:
		raise _WikiError
	return ratings


async def get_vehicle_br(session: aiohttp.ClientSession, vehicle: str) -> dict:
	"""Resolve a vehicle name or internal ID and return its published battle ratings."""
	if not isinstance(vehicle, str) or not 2 <= len(vehicle.strip()) <= 80:
		return {"status": "invalid_query"}
	vehicle = " ".join(vehicle.split())
	key = _match_key(vehicle)
	if not key:
		return {"status": "invalid_query"}

	try:
		# Wiki search uses the landing page's CSRF token and public session cookie.
		page = BeautifulSoup(await _fetch(session, "GET", "/"), "html.parser")
		param = page.select_one('meta[name="csrf-param"]')
		token = page.select_one('meta[name="csrf-token"]')
		if param is None or token is None or param.get("content") != "_csrf" or not token.get("content"):
			raise _WikiError
		search = await _fetch(
			session, "POST", "/api/search",
			data={"q": vehicle, "_csrf": token["content"]},
			headers={"X-Requested-With": "XMLHttpRequest", "Origin": WIKI_URL, "Referer": f"{WIKI_URL}/"},
		)
		matches = _matches(search)
		identifiers = [entry for entry in matches if entry["vehicle_id"].casefold() == vehicle.casefold()]
		exact = [entry for entry in matches if _match_key(entry["vehicle"]) == key]
		candidates = identifiers or exact or matches
		if not candidates:
			return {"status": "not_found"}
		if len(candidates) != 1:
			return {"status": "ambiguous", "candidates": candidates[:5]}

		selected = candidates[0]
		path = f"/unit/{selected['vehicle_id']}"
		stat_card = BeautifulSoup(await _fetch(session, "GET", path), "html.parser")
		return {
			"status": "ok",
			**selected,
			"battle_ratings": _battle_ratings(stat_card),
			"source_url": f"{WIKI_URL}{path}",
		}
	except (aiohttp.ClientError, TimeoutError, UnicodeError, _WikiError):
		return {"status": "unavailable"}
