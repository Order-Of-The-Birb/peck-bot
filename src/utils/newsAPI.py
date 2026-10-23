from __future__ import annotations
from asyncio import get_running_loop
from datetime import datetime
from typing import Literal, TYPE_CHECKING, Any, NoReturn, Coroutine
from discord import Embed
from enum import Enum
if __name__ == "__main__":
	from os import path
	from sys import path as sys_path
	sys_path.append(path.abspath(path.join(path.dirname(__file__), '..')))

from utils.thunderapi import news_ws
if TYPE_CHECKING:
	from asyncio import Task
import bot.client as Client

class News:
	id:int
	anons:str # Short description
	title:str # Title
	link:str # URL
	pinned:bool
	images:tuple['Image'] # Attached images
	tags:tuple[Literal["Event", "Development", "Video", "Shop", "Fixed", "eSport", "Market", "Special", "Warbonds", "Fair Play", "Update"]] # Attached tags
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
		self.images = tuple([self.Image(i) for i in item['images']])
		self.tags = tuple(item.get('tags', []))
		self.platforms = item.get('platforms', [])
		self.project = item.get('project', "warthunder_en")
		self.type = item['type']
		self.created = datetime.strptime(item['created'], "%Y-%m-%dT%H:%M:%S%z")
		self.importance = item["importance"]
	def buildEmbed(self) -> 'Embed':
		embed = Embed(
			title=self.title,
			description=self.anons,
			color=0xFF0000,
			url=self.link
		)
		embed.set_author(name="War Thunder News")
		embed.add_field(
			name="",
			value="",
			inline=False
		)
		if len(self.tags) > 0:
			embed.add_field(
				name="**Tags**",
				value=", ".join(self.tags),
				inline=False
			)
		embed.set_image(url=self.images[0].src)
		embed.set_footer(
			text=f"News provided by PECK bot • {self.created.strftime("%A, %B %d, %Y")}",
			icon_url="https://cdn.discordapp.com/icons/917850361019125820/325129a273dac84e31f9aa5de51f1936.png?size=128" # Hardcoded PECK Server URL
		)
		return embed

_runtime: Task
async def runtime() -> Coroutine[Any, Any, NoReturn]:
	async for news in news_ws():
		Client.BOT.dispatch("newsapi_post", News(news))

def setup():
	global _runtime
	_runtime = Client.BOT.loop.create_task(runtime, name="NewsAPI")
