"""Recognize straightforward War Thunder questions and render verified data for Discord."""

import re
from dataclasses import dataclass

from discord.utils import escape_markdown


DATA_API_ERROR = "I can’t reach Peck Bot’s War Thunder data service right now. Try again later."

_SQB = r"(?:realistic\s+)?(?:sqb|squadron battles)"
_SQB_QUESTIONS = (
    re.compile(_SQB, re.IGNORECASE),
    re.compile(
        rf"(?:what (?:br|battle rating|tier|br cap) is (?:the )?{_SQB}"
        rf"|what is (?:the )?(?:current )?{_SQB} (?:br|battle rating|tier|br cap)"
        rf"|what {_SQB} (?:br|battle rating|tier|br cap) is)"
        r"(?: at)?(?: (?:currently|right now|today))?(?: at)?",
        re.IGNORECASE,
    ),
    re.compile(rf"when does (?:the next )?{_SQB} start(?: (?:today|in my local time))?", re.IGNORECASE),
)
_SQB_TIMING = re.compile(rf"when does (?:it|{_SQB}) start(?: in my local time)?", re.IGNORECASE)
_MODE = r"(?:arcade|realistic|simulator)(?: battles)?|ab|rb|sb"
_VEHICLE_QUESTIONS = (
    re.compile(r"what(?:'s| is) (?:the )?(?:br|battle rating) (?:of|for) (?:the )?(?P<vehicle>.+)", re.IGNORECASE),
    re.compile(r"what (?:br|battle rating) is (?:the )?(?P<vehicle>.+)", re.IGNORECASE),
)
_MODE_SUFFIX = re.compile(rf" in (?P<mode>{_MODE})$", re.IGNORECASE)
_SCHEDULE_TIME = re.compile(r"<t:\d{1,12}:F>")
_RATING = re.compile(r"\d{1,2}(?:\.\d)?")


@dataclass(frozen=True)
class Lookup:
    tool: str
    vehicle: str | None = None
    mode: str | None = None


def match_lookup(prompt: str) -> Lookup | None:
    question = " ".join(prompt.replace("’", "'").split()).rstrip("?.!")
    first, _, rest = question.partition("?")
    if any(pattern.fullmatch(first) for pattern in _SQB_QUESTIONS) and (
        not rest or _SQB_TIMING.fullmatch(rest.strip())
    ):
        return Lookup("get_sqb_today")

    for pattern in _VEHICLE_QUESTIONS:
        match = pattern.fullmatch(question)
        if match is None:
            continue
        vehicle = match["vehicle"]
        if "?" in vehicle or re.match(rf"(?:the )?{_SQB}\b", vehicle, re.IGNORECASE):
            return None
        mode_match = _MODE_SUFFIX.search(vehicle)
        mode = None
        if mode_match:
            mode = {"arcade": "AB", "realistic": "RB", "simulator": "SB"}.get(
                mode_match["mode"].lower().split()[0], mode_match["mode"].upper(),
            )
            vehicle = vehicle[:mode_match.start()]
        if 2 <= len(vehicle) <= 80:
            return Lookup("get_vehicle_br", vehicle, mode)
    return None


def _rating(value: object) -> str | None:
    value = str(value)
    return value if _RATING.fullmatch(value) else None


def _window(result: dict, key: str) -> dict:
    value = result.get(key)
    return value if isinstance(value, dict) else {}


def _timestamp(window: dict, key: str) -> str | None:
    stamp = window.get(key)
    return stamp if isinstance(stamp, str) and _SCHEDULE_TIME.fullmatch(stamp) else None


def _format_sqb(result: dict) -> str:
    if result.get("status") == "invalid_timezone":
        return "Use a timezone such as `Europe/Zurich` or `UTC+01:00`."
    active = _window(result, "active_window")
    if "active_window" not in result:  # During rollout the separate data service can still be on the old version.
        active = next((w for w in result.get("windows", ()) if w.get("status") == "active"), {})
    upcoming = _window(result, "next_window")
    cap = _rating(active.get("max_br") if active else result.get("max_br"))
    next_cap = _rating(upcoming.get("max_br"))
    started = _timestamp(active, "discord_start")
    ends = _timestamp(active, "discord_end")
    next_start = _timestamp(upcoming, "discord_start")

    if cap:
        scope = "The current" if active else "Today’s"
        text = f"{scope} Squadron Battles BR cap is **{cap}**."
    elif not active and next_cap and next_start:
        text = "Squadron Battles is closed right now."
    else:
        text = "I couldn’t verify the Squadron Battles BR cap from War Thunder."
    if started and ends:
        text += f" The active window started {started} and ends {ends}."
    if not active and cap and next_start:
        text += " The queue is closed right now."
    if next_start:
        text += f" The next window starts {next_start}"
        text += f" (BR **{next_cap}**)." if next_cap and next_cap != cap else "."
    return text


def _format_vehicle(result: dict, mode: str | None) -> str:
    status = result.get("status")
    if status == "ambiguous":
        candidates = result.get("candidates", ())[:5]
        names = []
        for candidate in candidates:
            name = escape_markdown(candidate["vehicle"])
            if description := candidate.get("description"):
                name += f" ({escape_markdown(description)})"
            names.append(name)
        return f"Which vehicle did you mean: {'; '.join(names)}?" if names else "Which vehicle did you mean?"
    if status == "not_found":
        return "I couldn’t find that vehicle in the War Thunder Wiki. Try its full in-game name."
    if status != "ok":
        return "I couldn’t look up that vehicle’s BR on the War Thunder Wiki right now. Try again later."
    vehicle = escape_markdown(result["vehicle"])
    ratings = result["battle_ratings"]
    lines = []
    for battle_type, label_name in (
        ("air", "Air"), ("ground", "Ground"), ("naval", "Naval"),
        ("helicopter", "Helicopter"), ("standard", "BR"),
    ):
        battle_ratings = ratings.get(battle_type, {})
        entries = [f"{label} **{value}**" for label in ("AB", "RB", "SB") if (mode is None or mode == label)
                   and (value := _rating(battle_ratings.get(label))) is not None]
        if entries:
            lines.append(f"{label_name}: {' · '.join(entries)}")
    if not lines:
        return f"The War Thunder Wiki doesn’t list a {mode or 'battle'} rating for **{vehicle}**."
    source = result.get("source_url")
    if isinstance(source, str) and re.fullmatch(r"https://wiki\.warthunder\.com/unit/[a-zA-Z0-9_-]+", source):
        lines.append(f"[War Thunder Wiki](<{source}>)")
    return f"**{vehicle}**\n" + "\n".join(lines)


def format_lookup(lookup: Lookup, result: dict) -> str:
    if result.get("status") == "data_api_unavailable":
        return DATA_API_ERROR
    if lookup.tool == "get_sqb_today":
        return _format_sqb(result)
    return _format_vehicle(result, lookup.mode)
