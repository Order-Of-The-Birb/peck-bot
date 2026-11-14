"""Read the public PECK squadron's top Squadron Battles ratings."""

import aiohttp

from utils.squadron import PECK_SQUADRON_NAME, squadron_member_rows, squadron_url

_SOURCE = squadron_url(PECK_SQUADRON_NAME)
_TIMEOUT = aiohttp.ClientTimeout(total=7, connect=4)
_MAX_BODY = 1024 * 1024


async def get_sqb_leaderboard(limit: int) -> dict:
	if type(limit) is not int or not 1 <= limit <= 10:
		return {"status": "invalid_query"}

	try:
		async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
			async with session.get(_SOURCE, allow_redirects=False) as response:
				if response.status != 200:
					return {"status": "unavailable"}
				body = bytearray()
				async for chunk in response.content.iter_chunked(16 * 1024):
					if len(body) + len(chunk) > _MAX_BODY:
						return {"status": "unavailable"}
					body.extend(chunk)
		with_ratings = []
		for row in squadron_member_rows(body.decode("utf-8")):
			name, rating = row[1], int(row[2])
			if 0 < len(name) <= 100 and rating > 0:
				with_ratings.append({"name": name, "sqb_rating": rating})
	except (aiohttp.ClientError, TimeoutError, ValueError):
		return {"status": "unavailable"}

	with_ratings.sort(key=lambda member: member["sqb_rating"], reverse=True)
	return {"status": "ok", "members": with_ratings[:limit], "source_url": _SOURCE}
