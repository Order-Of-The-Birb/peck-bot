from __future__ import annotations
from asyncio import get_running_loop
from datetime import datetime
from typing import Literal, TYPE_CHECKING, Any, NoReturn, Coroutine
from bot.cogs import Embed
from enum import Enum
if __name__ == "__main__":
	from os import path
	from sys import path as sys_path
	sys_path.append(path.abspath(path.join(path.dirname(__file__), '..')))

from utils.thunderapi import news_ws
if TYPE_CHECKING:
	from bot.client import Bot
	from asyncio import Task

class News:
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
		self.importance = item["importance"]
	def buildEmbed(self, footerIconURL:str) -> 'Embed':
		embed = Embed(title=self.title, description=self.anons, color=0xFF0000, url=self.link)
		embed.set_author(name="War Thunder News")
		embed.add_field(name="", value="", inline=False)
		if len(self.tags) > 0:
			embed.add_field(name="**Tags**", value=", ".join(self.tags), inline=False)
		embed.set_image(url=self.images[0].src)
		embed.set_footer(text=f"News provided by PECK bot • {self.created.strftime("%A, %B %d, %Y")}", icon_url=footerIconURL)
		return embed

async def runtime(bot: 'Bot') -> Coroutine[Any, Any, NoReturn]:
	async for news in news_ws():
		bot.dispatch("newsapi_post", News(news))

_runtime: Task

def main(bot: 'Bot'):
	global _runtime

	loop = get_running_loop()

	_runtime = loop.create_task(runtime(bot), name="NewsAPI")