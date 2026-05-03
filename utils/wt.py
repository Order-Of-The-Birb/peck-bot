from __future__ import annotations
import logging, requests, re, threading
from playwright.async_api import async_playwright, Page as aPage
from bs4 import BeautifulSoup
from urllib.parse import quote
from json import loads
from time import sleep
from datetime import datetime, UTC, date
from typing import TYPE_CHECKING
from contextlib import asynccontextmanager
if __name__ == "__main__":
	from os import path
	from sys import path as sys_path
	sys_path.append(path.abspath(path.join(path.dirname(__file__), '..')))
from utils.time import discord_timestamp, sqb_brackets, timestampTypes
from utils.generic import httperror
if TYPE_CHECKING:
	from utils.bot import Bot
logger = logging.getLogger(__name__)

headers = {
	"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 OPR/117.0.0.0"
}
class SQBData:
	class _astat:
		dr_era5:int
		deaths:int
		ftime:int
		gkills:int
		battles:int
		wins:int
		akills:int
		activity:int
		clan_activity_by_periods:int
		def __init__(self, astat:dict[str, int]):
			self.dr_era5 = astat.get("dr_era5_hist", 0)
			self.deaths = astat.get("deaths_hist", 0)
			self.ftime = astat.get("ftime_hist", 0)
			self.gkills = astat.get("gkills_hist", 0)
			self.battles = astat.get("battles_hist", 0)
			self.wins = astat.get("wins_hist", 0)
			self.akills = astat.get("akills_hist", 0)
			self.activity = astat.get("activity", 0)
			self.clan_activity_by_periods = astat.get("clan_activity_by_periods", 0)
	pos:int
	_id:int
	announcement:str
	autoaccept:bool
	cdate:datetime
	changed_by_uid:int
	changed_time:datetime
	creator_uid:int
	currentTagRegalia:str
	desc:str
	interlockid:int
	lastPaidTag:str
	members_cnt:int
	membership_req:list
	name:str
	namel:str
	region:str
	slogan:str
	tag:str
	tagl:str
	type:str
	astat:_astat
	def __init__(self, content:dict, page_num:int):
		self.page_num = page_num
		self.pos = content.get("pos")
		self._id = content.get("_id")
		self.announcement = content.get("announcement")
		self.autoaccept = content.get("autoaccept")
		self.cdate = content.get("cdate")
		self.changed_by_uid = content.get("changed_by_uid")
		self.changed_time = content.get("changed_time")
		self.creator_uid = content.get("creator_uid")
		self.currentTagRegalia = content.get("currentTagRegalia")
		self.desc = content.get("desc")
		self.interlockid = content.get("interlockid")
		self.lastPaidTag = content.get("lastPaidTag")
		self.members_cnt = content.get("members_cnt")
		self.membership_req = content.get("membership_req")
		self.name = content.get("name")
		self.namel = content.get("namel")
		self.region = content.get("region")
		self.slogan = content.get("slogan")
		self.tag = content.get("tag")
		self.tagl = content.get("tagl")
		self.type = content.get("type")
		self.astat = self._astat(content.get("astat"))
	@classmethod
	def fetch_data(cls) -> SQBData | None:
		obj = None
		def checkPage(pagenum:int):
			while True:
				response = requests.get(f"https://warthunder.com/en/community/getclansleaderboard/dif/_hist/page/{pagenum}/sort/dr_era5")
				if response.status_code == 429: sleep(1)
				else: break
			if not response.ok:
				logger.error(f"page number {pagenum} returned HTTP error {response.status_code} ({httperror(response)})")
				return
			data = loads(response.text)
			if data["status"] != "ok":
				logger.error(f"Page status returned {data["status"]}, with message '{data["msg"]}'")
				return None
			for squadron in data["data"]:
				if isinstance(squadron, dict) and squadron.get("_id") == 1061551:
					nonlocal obj
					if obj is None:
						obj = cls(squadron, pagenum)
						return
		pagenum = 1
		while True: # 20 places per page
			if pagenum > 50:
				return None # Not found in first 20*50=1000 places
			threads = [threading.Thread(None, checkPage, args=(i,)) for i in range(pagenum, pagenum+5)] # 5 pages per thread batch, 20*5=100 places per check
			[i.start() for i in threads]
			while any(i.is_alive() for i in threads):
				sleep(0.1)
			if obj is not None:
				return obj
			pagenum += 5
			sleep(0.5)
class Squadron:
	class Member:
		def __init__(self, data:tuple):
			self.name:str = data[1]
			self.sqb_rating:int = int(data[2])
			self.activity:int = int(data[3])
			self.role:str = data[4]
			self.joindate:datetime = datetime.strptime(data[5], "%d.%m.%Y")
	def __init__(self, squadron_name:str):
		self.URL = f"https://warthunder.com/en/community/claninfo/{quote(squadron_name)}"
		self._logger = logging.getLogger(__name__)
	def __contains__(self, name:str): return name in self.GetNames()
	def __iter__(self): return iter(self.members)
	def __getitem__(self, index): return self.members[index]
	def __len__(self): return self.member_count
	def SortBySQBPoints(self, reverse:bool=True) -> list[Member]: return sorted([i for i in self.members if i.sqb_rating > 0], key=lambda x: x.sqb_rating, reverse=reverse)
	def GetNames(self): return tuple([normalizeUsername(i.name) for i in self.members])
	def UserInSquadron(self, name:str): return normalizeUsername(name) in self.GetNames()
	def getMember(self, name:str) -> Member|None:
		name = normalizeUsername(name)
		if not self.UserInSquadron(name): return
		for member in self.members:
			if member.name == name:
				return member
		return
	async def updateAll(self):
		async with self.openPage() as page:
			await self.updateMembers(page)
			await self.updateInfo(page)
			await self.updateStats(page)
	async def updateMembers(self, page:aPage|None=None):
		if page is None:
			async with self.openPage() as page:
				await page.wait_for_load_state("domcontentloaded")
				content = await page.content()
		else:
			content = await page.content()
		soup = BeautifulSoup(content, "html.parser")
		divs = [i.text.strip() for i in soup.find("div", {"class":"squadrons-members__table"}).find_all("div", {"class":"squadrons-members__grid-item"})[6:]]
		self.members = tuple(self.Member(divs[i:i+6]) for i in range(0, len(divs), 6))
	async def updateStats(self, page:aPage|None=None):
		if page is None:
			async with self.openPage() as page:
				await page.wait_for_load_state("domcontentloaded")
				content = await page.content()
		else:
			content = await page.content()
		soup = BeautifulSoup(content, "html.parser")
		top = soup.find("div", {"class":"squadrons-profile__header-wrapper"})
		_sqb_stats = top.find("div", {"class":"squadrons-profile__header-stat"}).find_all("ul")[1].find_all("li", {"class":"squadrons-stat__item-value"})[1:]
		class sqb_stats:
			def __init__(self):
				self.air_kills = int(_sqb_stats[0].text.strip())
				self.ground_kills = int(_sqb_stats[1].text.strip())
				self.deaths = int(_sqb_stats[2].text.strip())
				self.time = _sqb_stats[3].text.strip()
		self.sqb = sqb_stats()
		squadron_rating = top.find("div", {"class":"squadrons-profile__header-aside"}).find("div", {"class":"squadrons-counter__count-wrapper"}).find_all("div", {"class":"squadrons-counter__item"})
		if (sqb_rating := re.search(r"\d+", squadron_rating[0].text)) is None:
			logger.debug("Failed to obtain SQB rating")
		else:
			self.sqb_rating = int(sqb_rating.group(0).strip())
		if (activity := re.search(r"\d+", squadron_rating[1].text)) is None:
			logger.debug("Failed to obtain activity")
		else:
			self.activity = int(activity.group(0).strip())
	async def updateInfo(self, page:aPage|None=None):
		if page is None:
			async with self.openPage() as page:
				await page.wait_for_load_state("domcontentloaded")
				content = await page.content()
		else:
			content = await page.content()
		soup = BeautifulSoup(content, "html.parser")
		top = soup.find("div", {"class":"squadrons-profile__header-wrapper"})
		squadron_info = top.find("div", {"class":"squadrons-info__content-wrapper"})
		squadron_name_tag = squadron_info.find("div", {"class":"squadrons-info__title"}).text.strip().split(" ")
		self.squadron_name = " ".join(squadron_name_tag[1:])
		self.squadron_tag = squadron_name_tag[0]
		self.member_count = int(squadron_info.find("div", {"class":"squadrons-info__meta-item"}).text.strip().removeprefix("Number of players: "))
		self.squadron_description = squadron_info.find("div", {"class":"squadrons-info__description--full"}).text.strip()
		self.creation_date = datetime.strptime(squadron_info.find("div", {"class":"squadrons-info__meta-item--date"}).text.strip().removeprefix("date of creation: "), "%d.%m.%Y")
	@asynccontextmanager
	async def openPage(self):
		async with async_playwright() as p:
			try:
				browser = await p.firefox.launch(headless=True)
				context = await browser.new_context(ignore_https_errors=True)
				# Disable images (performance + CF friendliness)
				await context.route("**/*", lambda route: (route.abort() if route.request.resource_type == "image" else route.continue_()))
				page = await context.new_page()
				await page.goto(self.URL, wait_until="domcontentloaded")
				yield page
			except Exception:
				self._logger.exception("An error occurred in the page")
				raise
			finally:
				await context.close()
				await browser.close()
def _get_raw_sqb_post():
	logger.debug("Retrieving SQB BR data")
	URL = "https://forum.warthunder.com/t/season-schedule-for-squadron-battles/4446"
	response = requests.get(URL, headers=headers)
	if response.status_code != 200:
		raise LookupError(f"WT Forums gave back an error: {response.status_code} ({httperror(response)})")
	post = str(BeautifulSoup(response.text, 'html.parser').find("div", class_="post").find_all("p")[1]).removeprefix("<p>").removesuffix("</p>").replace("<br/>","").split("\n")
	logger.debug("Retrieved data")
	return post
def _parse_sqb_weeks() -> list[dict[str, datetime|float]]:
	post = _get_raw_sqb_post()
	rn = datetime.now(UTC)
	weeks = []
	for num, week in enumerate(post):
		week_number = "Afterward"
		main_regex = re.search(r"(([0-9]+) *(st|nd|rd|th|) week|) мах (BR|БР) ([0-9.]+) \(([0-9.]+)\D+([0-9.]+)\)", week, re.IGNORECASE)
		if num != len(post)-1:
			week_number = main_regex.group(1)
			append_numbering = {"1":"st","2":"nd","3":"rd"}
			if not any(i in week_number for i in [*append_numbering.values(), "th"]) and main_regex.group(3) is not None:
				_ = main_regex.group(2)
				week_number = week_number.replace(_, f"{_}{append_numbering.get(_[-1], "th")}")
		br = float(main_regex.group(5))
		start_time = datetime.strptime(f"{main_regex.group(6)}.{rn.year}", "%d.%m.%Y").replace(hour=sqb_brackets[0][0].hour, minute=0, second=0, tzinfo=UTC)
		end_time = datetime.strptime(f"{main_regex.group(7)}.{rn.year}", "%d.%m.%Y").replace(hour=sqb_brackets[1][1].hour, minute=0, second=0, tzinfo=UTC)
		weeks.append({
			"week": week_number,
			"br": br,
			"start": start_time,
			"end": end_time
		})
	return weeks
def get_sqb_season() -> str:
	weeks = _parse_sqb_weeks()
	return "\n".join(f"{i["week"]}: {i["br"]}\n\t{discord_timestamp(i["start"], timestampTypes.SHORT_DATE)} ({discord_timestamp(i["start"], timestampTypes.RELATIVE)}) - {discord_timestamp(i["end"], timestampTypes.SHORT_DATE)} ({discord_timestamp(i["end"], timestampTypes.RELATIVE)})" for i in weeks)
def get_sqb_br(other_date:datetime|None = None) -> tuple[float, tuple[date, date]]|None:
	"""Gets the BR of a given day of SQB. Will get today if no date is given."""
	if not other_date: rn = datetime.now(UTC)
	else: rn = other_date.astimezone(UTC)
	weeks = _parse_sqb_weeks()
	for week in weeks:
		if week["start"] <= rn < week["end"]:
			return week["br"], (week["start"], week["end"])
	_ = weeks[-1]
	return None
def get_user_ids(*usernames:str) -> dict[str, int]:
	logger = logging.getLogger(__name__)
	result:dict[str, int] = {}
	session = requests.Session()
	for username in usernames:
		response = session.get(f"https://api.thunderinsights.dk/v1/users/direct/search/?nick={username}&limit=10")
		if not response.ok:
			if response.status_code == 500:
				logger.debug(f"User '{username}' doesn't seem to exist anymore")
				result[username] = None
				continue
			raise ValueError(f"Failed to look up gaijin ID of user '{username}' (HTTP {response.status_code}, \"{httperror(response)}\")")
		data:list[dict[str, int|str]] = response.json()
		normalizedUsername = normalizeUsername(username)
		for user in data:
			found_username = user.get("nick")
			if found_username is None: continue
			if found_username == username or normalizeUsername(found_username) == normalizedUsername: # Normalizing for database lookups (database doesn't store @psn and @live)
				result[username] = int(user["userid"])
				break
		else:
			result[username] = None
	return result
def normalizeUsername(name: str) -> str|None:
	match = re.fullmatch(r"([\w-](?:[\w -]{1,14}[\w-])?)(?:@(psn|live))?", name)
	if not match: return None
	return match.group(1)
async def userInReplay(username:str, replay_id:int|str, login:'Bot.GaijinLogin') -> bool:
	username = normalizeUsername(username)
	if isinstance(replay_id, str):
		replay_id = int(replay_id, 16 if any(c in "abcdefABCDEF" for c in replay_id) else 10) # convert from HEX to DEC
	async def login_and_prepare(page:aPage):
		await page.wait_for_selector("form#js-form", timeout=15000)
		await page.fill("input#email", login.email)
		await page.fill("input#password", login.password)
		await page.click("div.form__row > button[type='submit']")
	async def block_images(route):
		if route.request.resource_type == "image":
			await route.abort()
			return
		await route.continue_()
	async with async_playwright() as p:
		browser = await p.firefox.launch(headless=__name__ != "__main__")
		context = await browser.new_context(ignore_https_errors=True)
		try:
			await context.route("**/*", block_images)
			page = await context.new_page()
			await page.goto(f"https://warthunder.com/en/tournament/replay/{replay_id}", wait_until="domcontentloaded")
			await login_and_prepare(page)
			await page.wait_for_function(
				"location.hostname.includes('warthunder.com')",
				timeout=30000
			)
			await page.wait_for_selector("div#wtVueApp", timeout=15000)
			await page.wait_for_load_state("networkidle")
			html = await page.content()
		finally:
			await context.close()
			await browser.close()
	soup = BeautifulSoup(html, 'html.parser')
	teams = soup.select("div[class*='_resultItemNames_1umbu_']", limit=2)
	if len(teams) < 2:
		raise ValueError("Somehow the provided replay URL has less than 2 teams")
	for team in teams:
		_ = team.select("ul>li")
		for userEntry in _:
			_2 = userEntry.select_one("div[class*='_resultItemNames__name_1umbu_']")
			if normalizeUsername(_2.text) == username:
				return True
	return False