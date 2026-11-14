"""Read the published War Thunder squadron member table."""

from urllib.parse import quote

from bs4 import BeautifulSoup

PECK_SQUADRON_NAME = "Order Of The Birb"
_MEMBER_COLUMNS = 6


def squadron_url(name: str) -> str:
	return f"https://warthunder.com/en/community/claninfo/{quote(name)}"


def squadron_member_rows(content: str) -> list[tuple[str, ...]]:
	soup = BeautifulSoup(content, "html.parser")
	try:
		table = soup.find("div", class_="squadrons-members__table")
		if table is None:
			raise ValueError("The squadron member table is missing.")
		cells = table.find_all("div", class_="squadrons-members__grid-item")
		if len(cells) < _MEMBER_COLUMNS or len(cells) % _MEMBER_COLUMNS:
			raise ValueError("The squadron member table contains incomplete rows.")
		return [
			tuple(cell.get_text().strip() for cell in cells[start : start + _MEMBER_COLUMNS])
			for start in range(_MEMBER_COLUMNS, len(cells), _MEMBER_COLUMNS)
		]
	finally:
		soup.decompose()
