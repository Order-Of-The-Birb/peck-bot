from __future__ import annotations
import logging
from asyncio import sleep as asleep
from aiohttp import ClientSession
from json import load, dump
from datetime import datetime, time, UTC
from typing import Literal, TYPE_CHECKING, Any
from bs4 import BeautifulSoup, Tag
from pathlib import Path
from discord import Embed
from enum import Enum
from re import search as re_search, IGNORECASE
if __name__ == "__main__":
	from os import path
	from sys import path as sys_path
	sys_path.append(path.abspath(path.join(path.dirname(__file__), '..')))
if TYPE_CHECKING:
	from utils.bot import Bot
	from asyncio import Task

fasterUpdate = (
	time(hour=12, minute=0), # Start
	time(hour=21, minute=30) # End
)
excludeFastWeekdays = (5,6) # Zero-indexed number of weekday 
fastCheck = 5*60 # Every 5 mins
slowCheck = 30*60 # Every 30 mins
class NewsAPI:
	"""
# Website documentation  
Development news API endpoint: 'http://newslist.gaijin.net:8080/news/warthunder/en/js'  
	Available query parameters: Offset  
Changelogs news (webscraping): 'https://warthunder.com/en/game/changelog/'  
"""
	API_URL = "http://newslist.gaijin.net:8080/news/warthunder/en/js"
	Changelog_URL = "https://warthunder.com/en/game/changelog/"
	class News:
		"""
		# Example Input dictionary with required elements
```
{
		   "id": 9862,
		   "anons": "...",
		   "title": "...",
		   "link": "https://warthunder.com/en/news/9862-planned-technical-works-on-16122025-en",
		   "images": [
			   {
				   "src": "https://staticfiles.warthunder.com/upload/image/0_2022_Anons/Ground/tank13_TW_Anons_831ad679a7237ed6886bfc1267b44e51.png",
				   "width": 0,
				   "height": 0
			   }
		   ],
		   "type": "news",
		   "created": "2025-12-15T17:21:00+0000"
	   }
```
		"""
		id:int
		anons:str # Short description
		title:str # Title
		link:str # URL
		pinned:bool
		images:list['Image'] # Attached images
		tags:list[Literal["Event", "Development", "Video", "Shop", "Fixed", "eSport", "Market", "Special", "Warbonds", "Fair Play", "Update"]] # Attached tags
		platforms:list[str] # Affected platforms
		project:str # Game (100% of the time War Thunder with different version numbers) 
		type:Literal["news", "changelog"] # Article Type
		created:datetime # Article Creation Time
		importance:ImportanceLevel
		class ImportanceLevel(Enum):
			REGULAR = 0
			MINOR = 1
			EVENT = 2
			MAJOR = 3
		class Image:
			def __init__(self, item:dict):
				self.src:str = item['src']
				self.width:int = int(item['width'])
				self.height:int = int(item['height'])
		def __init__(self, item:dict[str, Any]):
			self.id = int(item['id'])
			self.anons = item['anons'] 
			self.title = item['title']
			self.link = item['link']
			self.pinned = item.get('pinned', False)
			self.images = [self.Image(i) for i in item['images']]
			self.tags = item.get('tags', [])
			self.platforms = item.get('platforms', [])
			self.project = item.get('project', "warthunder_en")
			self.type = item['type']
			self.created = datetime.strptime(item['created'], "%Y-%m-%dT%H:%M:%S%z")
			self.importance = self._getImportant()
		def buildEmbed(self, footerIconURL:str) -> 'Embed':
			embed = Embed(title=self.title, description=self.anons, color=0xFF0000, url=self.link)
			embed.set_author(name="War Thunder News")
			embed.add_field(name="", value="", inline=False)
			if len(self.tags) > 0:
				embed.add_field(name="**Tags**", value=", ".join(self.tags), inline=False)
			embed.set_image(url=self.images[0].src)
			embed.set_footer(text=f"News provided by PECK bot • {self.created.strftime("%A, %B %d, %Y")}", icon_url=footerIconURL)
			return embed
		def _getImportant(self) -> ImportanceLevel:
			title = self.title.lower()
			if (
					(
						"Video" in self.tags and 
						(
							"trailer" in title or 
							"teaser" in title
						) 
					) or 
					(
						("Shop" in self.tags or "Event" in self.tags) and
						(
							(
								(
									any(i in title for i in ["winter", "summer", "may", "holiday"]) or 
									("war thunder" in title and "birthday" in title)
								) and
								any(i in title for i in ["sale", "discount", "celebrate"])  
							) or
							"black friday" in title
						)
					) or (
						re_search("Meet the “[A-z0-9 ]+” Major Update!", title, IGNORECASE) is not None and self.pinned 
					)
				):
				return self.ImportanceLevel.MAJOR
			if ("Event" in self.tags and "pages" not in title):
				return self.ImportanceLevel.EVENT
			if ("discount" in title and ("Shop" in self.tags or "Special" in self.tags)):
				return self.ImportanceLevel.MINOR
			return self.ImportanceLevel.REGULAR
	periodicTask:'Task'|None = None
	periodicChLogTask:'Task'|None = None
	def __init__(self, bot:'Bot', startTasks:bool=True):
		self._logger = logging.getLogger(__name__)
		self.session = ClientSession(headers={"User-Agent": "PECK_bot/1.0 (War Thunder squadron bot; contact: https://discord.gg/wsn9Wcqqym)", "Accept": "application/json"})
		self.bot = bot
		self.lock = bot.ltsLock
		if not Path.exists(Path("modules/news.json")):
			with open("modules/news.json", "x") as file:
				dump({}, file, indent=4)
		with open("modules/news.json", "r") as file:
			savedValues:dict[str, Any] = load(file)
		self.lastPostedNewsID = savedValues.get("lastPostedID", 0)
		self.lastPostedChLogsID = savedValues.get("lastPostedChLogID", 0)
		self.lastPostedMajorChLogsID = savedValues.get("lastMajorChLogID", 0)
		if startTasks:
			try:
				self.periodicTask = self.bot.runtime.create_task(self.periodicNewsPing())
				self.periodicChLogTask = self.bot.runtime.create_task(self.periodicChLogPing())
			except Exception:
				self._logger.exception("An error occurred while running the autochecking loops")
		self._logger.debug("NewsAPI initialized")
	lastPostedNewsID:int
	lastPostedChLogsID:int
	async def setID(self, ID:int|News=None, _type:Literal["News", "Changelogs"] = "News"):
		self._logger.debug(f"Writing value {ID} for {_type}")
		if _type == "News":			keyValue = "lastPostedID"
		elif _type == "Changelogs":	keyValue = "lastPostedChLogID"
		else:
			return self._logger.error(f"keyValue given is neither 'News' or 'Changelogs'. Instead it is '{_type}'")
		with self.lock:
			with open("modules/news.json", "r") as _:content = load(_)
			if isinstance(ID, int):			content[keyValue] = ID
			elif isinstance(ID, self.News): content[keyValue] = ID.id
			else: return self._logger.error(f"ID given is neither type 'int' or 'News'. Instead it is '{type(ID)}'")
			with open("modules/news.json", "w") as file: dump(content, file, indent=4)
			if _type == "News":	self.lastPostedNewsID		 = content[keyValue]
			else:				self.lastPostedChLogsID 	 = content[keyValue]
		self._logger.debug("Data written.")
	async def fetchNews(self) -> list[News]:
		"""Fetches the latest news from the News API."""
		if self.session.closed:
			raise RuntimeError("Session has already been closed.")
		latestNews = []
		async with self.session.get(self.API_URL) as response:
			response.raise_for_status()
			data = await response.json()
			for item in data["items"]:
				latestNews.append(self.News(item))
		return latestNews
	async def fetchLatestChLog(self) -> News:
		async with self.session.get(self.Changelog_URL) as response:
			response.raise_for_status()
			parsed = BeautifulSoup(await response.text(), 'html.parser')
			changelogs = parsed.select("div.showcase__content-wrapper>div.showcase__item.widget")
			if len(changelogs) < 2:
				raise RuntimeError("An error occured when parsing changelogs")
			async def processChangelog(chlog:Tag) -> 'NewsAPI.News':
				ChLogURL:str = chlog.select_one("a.widget__link")["href"]
				content = chlog.select_one("div.widget__content")
				title = content.select_one("div.widget__title").get_text(strip=True)
				anons = content.select_one("div.widget__comment").get_text(strip=True)
				datetext = content.select_one("ul.widget__meta.widget-meta").select_one("li.widget-meta__item.widget-meta__item--right").get_text(strip=True)
				date = datetime.strptime(datetext, "%d %B %Y").replace(tzinfo=UTC).strftime("%Y-%m-%dT%H:%M:%S%z")
				del datetext
				src = chlog.select_one("div.widget__poster>img").attrs["data-src"]
				return self.News({
					"id":int(ChLogURL.split("/")[-1]),
					"anons":anons,
					"title":title,
					"link":f"https://warthunder.com{ChLogURL}",
					"tags":["Update"],
					"images":[{
						"src":src,
			   			"width": 0,
			   			"height": 0
					}],
					"type":"Changelog",
					"created":date
				})
			latestMajor:'NewsAPI.News' = await processChangelog(changelogs[0]) # 0 is the always pinned major update changelogs
			latest:'NewsAPI.News' = await processChangelog(changelogs[1]) # 1 should be the newest
			if latestMajor.created > latest.created:
				return latestMajor
			return latest
	async def newsSincePost(self, lastID:int) -> list[News]:
		news = await self.fetchNews()
		for i, item in enumerate(news):
			if item.id == lastID: 
				return news[:i]
		self.lastPostedNewsID = news[0].id
		await self.setID(self.lastPostedNewsID)
		return []
	async def periodicNewsPing(self, return_after:bool = False):
		await self.bot.wait_until_ready()
		while True:
			latest:list['NewsAPI.News'] = (await self.newsSincePost(self.lastPostedNewsID))[::-1]
			if latest and latest[-1].id != self.lastPostedNewsID:
				self._logger.debug("News have been posted since last post")
				for news in latest:
					self.bot.dispatch("newsapi_post", news) 
					self._logger.debug(f"Dispatched news id {news.id} to listener")
				await self.setID(latest[-1])
			if return_after: return
			await asleep(self.__calcDelay__())
	async def periodicChLogPing(self, return_after:bool = False):
		await self.bot.wait_until_ready()
		while True:
			latest = await self.fetchLatestChLog()
			if latest.id != self.lastPostedChLogsID and latest.id != self.lastPostedMajorChLogsID:
				self._logger.debug("Changelogs have been posted since last post")
				self.bot.dispatch("newsapi_post", latest) 
				self._logger.debug(f"Dispatched changelog id {latest.id} to listener")
				await self.setID(latest, _type="Changelogs")
			if return_after: return
			await asleep(self.__calcDelay__(True))
	def __calcDelay__(self, isChangelogs:bool=False) -> int:
		rn = datetime.now(UTC)
		weekday = rn.weekday()
		rn = rn.time()
		if self.bot.debug: return 30
		if not isChangelogs:
			start, end = fasterUpdate
			if start <= rn <= end and weekday not in excludeFastWeekdays:
				return fastCheck
			return slowCheck
		else:
			return slowCheck
