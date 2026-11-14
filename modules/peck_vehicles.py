"""Read vehicle battle ratings from the official War Thunder Wiki."""

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from time import monotonic
from unicodedata import normalize

import aiohttp
from bs4 import BeautifulSoup, SoupStrainer

WIKI_URL = "https://wiki.warthunder.com"
_TIMEOUT = aiohttp.ClientTimeout(total=5)
_MAX_BODY = 3 * 1024 * 1024
_CATALOG_TTL = 15 * 60
_CATALOG_PATHS = ("/aviation", "/ground", "/helicopters", "/ships", "/boats")
_UNIT_LIST = re.compile(r"\s*window\.WT_UnitList\s*=\s*'(\[.*\])';\s*", re.DOTALL)
_UNIT_ID = re.compile(r"[a-zA-Z0-9_-]{1,100}")
_RATING = re.compile(r"[0-9]{1,2}\.[037]")
_BATTLE_TYPES = {"air": "air", "tank": "ground", "ship": "naval"}
_VEHICLE_TYPES = {
	"Aviation": "air",
	"Ground Vehicles": "ground",
	"Helicopters": "helicopter",
	"Bluewater Fleet": "naval",
	"Coastal Fleet": "naval",
}
_COUNTRIES = {
	"usa": ("USA", "US", "United States", "American"),
	"germany": ("Germany", "German"),
	"ussr": ("USSR", "Soviet", "Russia", "Russian"),
	"britain": ("Great Britain", "Britain", "UK", "United Kingdom", "British"),
	"japan": ("Japan", "Japanese"),
	"china": ("China", "Chinese"),
	"italy": ("Italy", "Italian"),
	"france": ("France", "French"),
	"sweden": ("Sweden", "Swedish"),
	"israel": ("Israel", "Israeli"),
}
_COUNTRY_IDS = {alias.casefold(): country for country, aliases in _COUNTRIES.items() for alias in aliases}
_COUNTRY_NAMES = "|".join(map(re.escape, _COUNTRY_IDS))
_COUNTRY_PREFIX = re.compile(rf"^({_COUNTRY_NAMES})(?:['’]s)?\s+(.+)$", re.IGNORECASE)
_COUNTRY_SUFFIX = re.compile(rf"^(.+?)(?:\s+(?:(?:from|in)\s+)?|\s*\()({_COUNTRY_NAMES})\)?$", re.IGNORECASE)
_PREMIUM = re.compile(r"\bpremium\b", re.IGNORECASE)
_HYPHENS = str.maketrans("‐‑‒–—−", "------")
_RANKS = ("", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X")
_logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _Vehicle:
	vehicle_id: str
	name: str
	country: str
	rank: int
	premium: bool

	def as_result(self) -> dict[str, str]:
		country = _COUNTRIES.get(self.country, (self.country.title(),))[0]
		rank = _RANKS[self.rank] if 0 < self.rank < len(_RANKS) else str(self.rank)
		description = f"{country} · Rank {rank}"
		if self.premium:
			description += " · Premium"
		return {"vehicle": self.name, "vehicle_id": self.vehicle_id, "description": description}


_catalog_cache: dict[str, tuple[float, tuple[_Vehicle, ...]]] = {}
_catalog_lock = asyncio.Lock()


class _WikiError(Exception):
	pass


async def _fetch(session: aiohttp.ClientSession, path: str) -> str:
	async with session.get(f"{WIKI_URL}{path}", timeout=_TIMEOUT, allow_redirects=False) as response:
		if response.status != 200:
			raise _WikiError(f"{path} returned HTTP {response.status}")
		body = bytearray()
		async for chunk in response.content.iter_chunked(16 * 1024):
			body.extend(chunk)
			if len(body) > _MAX_BODY:
				raise _WikiError(f"{path} exceeded the response size limit")
		return body.decode("utf-8")


def _catalog_rows(html: str) -> tuple[_Vehicle, ...]:
	# The Wiki embeds the vehicle list as JSON in the same script its filters use.
	page = BeautifulSoup(html, "html.parser", parse_only=SoupStrainer("script"))
	for script in page.find_all("script"):
		if script.string and (match := _UNIT_LIST.fullmatch(script.string)):
			break
	else:
		raise _WikiError("Vehicle catalog script is missing")
	try:
		rows = json.loads(match.group(1))
	except (ValueError, RecursionError) as error:
		raise _WikiError("Vehicle catalog JSON is invalid") from error
	if not isinstance(rows, list) or not rows:
		raise _WikiError("Vehicle catalog is empty")
	vehicles = []
	for row in rows:
		if not isinstance(row, list) or len(row) < 6:
			raise _WikiError("Vehicle catalog has an invalid row")
		unit_id, name, country, rank, _, status = row[:6]
		if (not isinstance(unit_id, str) or not _UNIT_ID.fullmatch(unit_id)
				or not isinstance(name, str) or not 0 < len(name.strip()) <= 100
				or not isinstance(country, str) or not country.isalpha()
				or type(rank) is not int or type(status) is not int):
			raise _WikiError("Vehicle catalog has invalid vehicle details")
		# The official catalog marks premium vehicles with status 1.
		vehicles.append(_Vehicle(unit_id, " ".join(name.split()), country, rank, premium=status == 1))
	return tuple(vehicles)


async def _load_catalog(session: aiohttp.ClientSession, path: str) -> None:
	html = await _fetch(session, path)
	rows = await asyncio.to_thread(_catalog_rows, html)
	_catalog_cache[path] = (monotonic() + _CATALOG_TTL, rows)


async def _get_catalog(session: aiohttp.ClientSession, query: str) -> tuple[_Vehicle, ...]:
	async with _catalog_lock:
		now = monotonic()
		expired = [path for path in _CATALOG_PATHS if _catalog_cache.get(path, (0, ()))[0] <= now]
		results = await asyncio.gather(*(_load_catalog(session, path) for path in expired), return_exceptions=True)
		catalog = tuple(vehicle for path in _CATALOG_PATHS if path in _catalog_cache for vehicle in _catalog_cache[path][1])
		for path, result in zip(expired, results):
			if isinstance(result, BaseException):
				# A partial catalog can establish a known internal ID, but cannot disambiguate a name.
				if any(vehicle.vehicle_id.casefold() == query.casefold() for vehicle in catalog):
					return catalog
				raise _WikiError(f"Could not load the vehicle catalog at {path}: {result}") from result
		return catalog


def _formal_name(value: str) -> str:
	value = normalize("NFKC", value).translate(_HYPHENS).casefold()
	return "".join(char for char in value if char.isalnum() or char in " .-_").strip()


def _compact_name(value: str) -> str:
	return "".join(char for char in value if char.isalnum())


def _vehicle_query(value: str) -> tuple[str, str | None, bool]:
	value, substitutions = _PREMIUM.subn(" ", value)
	value = " ".join(re.sub(r"\(\s*\)", " ", value).split())
	if match := _COUNTRY_SUFFIX.fullmatch(value):
		name, country = match.groups()
	elif match := _COUNTRY_PREFIX.fullmatch(value):
		country, name = match.groups()
	else:
		return value, None, bool(substitutions)
	return name, _COUNTRY_IDS[country.casefold()], bool(substitutions)


def _candidates(vehicle: str, catalog: tuple[_Vehicle, ...]) -> list[_Vehicle]:
	identifier = [entry for entry in catalog if entry.vehicle_id.casefold() == vehicle.casefold()]
	if identifier:
		return identifier
	query, country, premium = _vehicle_query(vehicle)
	formal = _formal_name(query)
	key = _compact_name(formal)
	if not key:
		return []
	# A numeric suffix is part of the model number, so F-2 must not match F-20A.
	continuation = r"(?!\d)" if key[-1].isdigit() else ""
	formal_prefix = re.compile(rf"{re.escape(formal)}{continuation}")
	compact_prefix = re.compile(rf"{re.escape(key)}{continuation}")
	word = re.compile(rf"(?<!\w){re.escape(formal)}{continuation}")
	by_score: dict[int, dict[str, _Vehicle]] = {}
	for entry in catalog:
		if (country and entry.country != country) or (premium and not entry.premium):
			continue
		name = _formal_name(entry.name)
		compact = _compact_name(name)
		if name == formal:
			score = 0
		elif compact == key:
			score = 1
		elif formal_prefix.match(name):
			score = 2
		elif compact_prefix.match(compact):
			score = 3
		elif word.search(name):
			score = 4
		else:
			continue
		by_score.setdefault(score, {})[entry.vehicle_id] = entry
	return list(by_score[min(by_score)].values()) if by_score else []


def _battle_ratings(page: BeautifulSoup) -> dict[str, dict[str, str]]:
	card = page.select_one(".game-unit_card-info .game-unit_br")
	if card is None:
		raise _WikiError("Vehicle page is missing the BR card")
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
		raise _WikiError("Vehicle BR card does not contain any ratings")
	return ratings


async def get_vehicle_br(session: aiohttp.ClientSession, vehicle: str) -> dict:
	"""Resolve a vehicle name or internal ID and return its published battle ratings."""
	if not isinstance(vehicle, str) or not 2 <= len(vehicle.strip()) <= 80:
		return {"status": "invalid_query"}
	vehicle = " ".join(vehicle.split())
	if not _compact_name(_formal_name(vehicle)):
		return {"status": "invalid_query"}

	try:
		candidates = _candidates(vehicle, await _get_catalog(session, vehicle))
		if not candidates:
			return {"status": "not_found"}
		if len(candidates) != 1:
			return {"status": "ambiguous", "candidates": [candidate.as_result() for candidate in candidates[:5]]}

		selected = candidates[0]
		path = f"/unit/{selected.vehicle_id}"
		html = await _fetch(session, path)
		stat_card = await asyncio.to_thread(BeautifulSoup, html, "html.parser")
		return {
			"status": "ok",
			**selected.as_result(),
			"battle_ratings": _battle_ratings(stat_card),
			"source_url": f"{WIKI_URL}{path}",
		}
	except (aiohttp.ClientError, TimeoutError, UnicodeError, _WikiError) as error:
		_logger.warning("Could not read War Thunder Wiki vehicle data: %s", error)
		return {"status": "unavailable"}
