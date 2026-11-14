"""War Thunder's published Squadron Battles BR schedule."""

import re
from datetime import UTC, date, datetime

from bs4 import BeautifulSoup

from utils.time import sqb_brackets


SQB_SCHEDULE_HEADERS = {
	"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 OPR/117.0.0.0"
}
SQB_SCHEDULE_URL = "https://forum.warthunder.com/t/season-schedule-for-squadron-battles/4446"
SQB_SCHEDULE_TTL = 300


class sqbBracket:
	name: str
	start: datetime
	end: datetime
	br: float
	def __init__(self, week:dict[str, datetime|float]):
		self.name = week.get("week")
		self.start = week.get("start")
		self.end = week.get("end")
		self.br = week.get("br")

def parse_sqb_season(html:str) -> list[sqbBracket]:
	"""Parse the official forum schedule, using its published season year."""
	page = BeautifulSoup(html, "html.parser")
	post = page.select_one("div.post")
	if page.title is None or post is None:
		raise LookupError("War Thunder season schedule was missing its title or announcement")
	season = re.search(
		r"\((\d{1,2}\.\d{1,2})(?:\.(\d{4}))?\s*[-–—−]\s*(\d{1,2}\.\d{1,2})\.(\d{4})\)",
		page.title.get_text(" ", strip=True),
	)
	if season is None:
		raise LookupError("War Thunder season schedule was missing its published date range")

	start_text, start_year, end_text, end_year = season.groups()
	end = datetime.strptime(f"{end_text}.{end_year}", "%d.%m.%Y").date()
	start = datetime.strptime(f"{start_text}.{start_year or end_year}", "%d.%m.%Y").date()
	if start_year is None and start > end:
		start = start.replace(year=start.year - 1)

	def published_date(value:str) -> date:
		day, month = map(int, value.split("."))
		year = start.year if (month, day) >= (start.month, start.day) else start.year + 1
		return date(year, month, day)

	weeks = []
	for match in re.finditer(
		r"(?:(\d+)(?:st|nd|rd|th)?\s+week\s+)?[mм][aа][xх]\s+(?:BR|БР)\s+(\d+(?:\.\d+)?)\s*"
		r"\(\s*(\d{1,2}\.\d{1,2})\s*[-–—−]\s*(\d{1,2}\.\d{1,2})\s*\)",
		post.get_text(" ", strip=True),
		re.IGNORECASE,
	):
		week, br, week_start, week_end = match.groups()
		first_day = published_date(week_start)
		last_day = published_date(week_end)
		if not start <= first_day <= last_day <= end:
			raise LookupError("War Thunder BR dates were outside the published season")
		if week is None:
			name = "Afterward"
		else:
			suffix = "th" if int(week) % 100 in (11, 12, 13) else {"1": "st", "2": "nd", "3": "rd"}.get(week[-1], "th")
			name = f"{week}{suffix} week"
		weeks.append(sqbBracket({
			"week": name,
			"br": float(br),
			"start": datetime.combine(first_day, sqb_brackets[0][0], UTC),
			"end": datetime.combine(last_day, sqb_brackets[-1][1], UTC),
		}))
	if not weeks:
		raise LookupError("War Thunder season schedule contained no BR windows")
	return weeks
