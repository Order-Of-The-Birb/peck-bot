"""Read-only Squadron Battles schedule for the Peck tool endpoints."""

import asyncio
import logging
import re
from datetime import UTC, datetime, timedelta, timezone as fixed_timezone, tzinfo
from time import monotonic
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import aiohttp

from utils.sqb import SQB_SCHEDULE_HEADERS, SQB_SCHEDULE_TTL, SQB_SCHEDULE_URL, parse_sqb_season, sqbBracket
from utils.time import discord_timestamp, sqb_brackets, timestampTypes


logger = logging.getLogger(__name__)
_season_lock = asyncio.Lock()
_season: tuple[sqbBracket, ...] = ()
_season_expires = 0.0


def _resolve_timezone(value: str) -> tzinfo:
    if len(value) > 128:
        raise ValueError("Use an IANA timezone or a UTC offset such as UTC+01:00.")
    if value.upper() == "UTC":
        return UTC
    offset = re.fullmatch(r"UTC([+-])([0-9]{1,2})(?::([0-9]{2}))?", value, re.IGNORECASE)
    if offset:
        sign, hour, minute = offset.groups()
        hours = int(hour)
        minutes = int(minute or "0")
        if minutes < 60 and (hours < 14 or (hours == 14 and minutes == 0)):
            delta = timedelta(hours=hours, minutes=minutes)
            return fixed_timezone(-delta if sign == "-" else delta)
    else:
        try:
            return ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            pass
    raise ValueError("Use an IANA timezone or a UTC offset such as UTC+01:00.")


async def _get_season() -> tuple[sqbBracket, ...]:
    global _season, _season_expires

    async with _season_lock:
        if monotonic() < _season_expires:
            return _season
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=6)) as session:
                async with session.get(SQB_SCHEDULE_URL, headers=SQB_SCHEDULE_HEADERS, max_redirects=3) as response:
                    response.raise_for_status()
                    body = bytearray()
                    async for chunk in response.content.iter_chunked(64 * 1024):
                        body.extend(chunk)
                        if len(body) > 2 * 1024 * 1024:
                            raise LookupError("War Thunder season schedule exceeded its size limit")
            brackets = await asyncio.to_thread(parse_sqb_season, body.decode("utf-8"))
        except (aiohttp.ClientError, TimeoutError, LookupError, ValueError) as error:
            logger.warning("Could not refresh the Squadron Battles BR schedule (%s)", type(error).__name__)
            _season = ()
            _season_expires = monotonic() + 30
        else:
            _season = tuple(brackets)
            _season_expires = monotonic() + SQB_SCHEDULE_TTL
        return _season


def _describe_day(now: datetime, zone: tzinfo, season: tuple[sqbBracket, ...]) -> dict:
    day = now.astimezone(zone).date()
    day_start = datetime.combine(day, datetime.min.time(), zone).astimezone(UTC)
    day_end = datetime.combine(day + timedelta(days=1), datetime.min.time(), zone).astimezone(UTC)

    def describe_window(start: datetime, end: datetime) -> dict:
        ratings = {week.br for week in season if week.start <= start and end <= week.end}
        status = "scheduled" if now < start else "active" if now < end else "ended"
        return {
            "starts_at": start.astimezone(zone).isoformat(),
            "ends_at": end.astimezone(zone).isoformat(),
            "starts_at_utc": start.isoformat().replace("+00:00", "Z"),
            "ends_at_utc": end.isoformat().replace("+00:00", "Z"),
            "discord_start": discord_timestamp(start, timestampTypes.DATE_WEEKDAY_TIME),
            "discord_end": discord_timestamp(end, timestampTypes.DATE_WEEKDAY_TIME),
            "status": status,
            "max_br": ratings.pop() if len(ratings) == 1 else None,
        }

    windows = []
    next_window = None
    utc_day = day_start.date() - timedelta(days=1)
    last_day = max(day_end.date(), now.date() + timedelta(days=1))
    while utc_day <= last_day:
        for start_time, end_time in sqb_brackets:
            start = datetime.combine(utc_day, start_time, UTC)
            end = datetime.combine(utc_day, end_time, UTC)
            if start < day_end and end > day_start:
                window = describe_window(start, end)
                windows.append(window)
            else:
                window = None
            if next_window is None and start > now:
                next_window = window if window is not None else describe_window(start, end)
        utc_day += timedelta(days=1)

    known_ratings = [window["max_br"] for window in windows if window["max_br"] is not None]
    if not known_ratings:
        br_status = "unavailable"
    elif len(known_ratings) != len(windows):
        br_status = "partial"
    else:
        br_status = "available"
    shared_rating = known_ratings[0] if br_status == "available" and len(set(known_ratings)) == 1 else None
    return {
        "on_date": day.isoformat(),
        "timezone": str(zone),
        "as_of_utc": now.isoformat().replace("+00:00", "Z"),
        "windows": windows,
        "next_window": next_window,
        "max_br": shared_rating,
        "br_status": br_status,
        "br_source": SQB_SCHEDULE_URL,
    }


async def get_sqb_today(timezone: str = "UTC") -> dict:
    """Return recurring play windows and published max BR for the requested local date."""
    zone = _resolve_timezone(timezone.strip())
    now = datetime.now(UTC)
    return _describe_day(now, zone, await _get_season())
