from __future__ import annotations

from collections.abc import Coroutine
from datetime import datetime
from typing import Any, Literal, NoReturn

from discord import Embed

if __name__ == "__main__":
	from os import path
	from sys import path as sys_path
	sys_path.append(path.abspath(path.join(path.dirname(__file__), '..')))

from asyncio import Task

import bot.client as Client
from utils.models.thunderapi.generic import NewsModel
from utils.thunderapi import news_ws


class News:
	id:int
	anons:str # Short description
	title:str # Title
	link:str # URL
	pinned:bool
	images:tuple[Image] # Attached images
	tags:set[Literal["Event", "Development", "Video", "Shop", "Fixed", "eSport", "Market", "Special", "Warbonds", "Fair Play", "Update"]] # Attached tags
	platforms:list[str] # Affected platforms
	project:str # Game (100% of the time War Thunder with different version numbers)
	type:Literal["news", "changelog"] # Article Type
	created:datetime # Article Creation Time
	importance:NewsModel.ImportanceLevel
	class Image:
		def __init__(self, item:NewsModel.Image):
			self.src:str = item.src
			self.width:int = int(item.width)
			self.height:int = int(item.height)
	def __init__(self, item:NewsModel):
		self.id = int(item.id)
		self.anons = item.anons
		self.title = item.title
		self.link = item.link
		self.pinned = item.pinned
		self.images = tuple([self.Image(i) for i in item.images])
		self.tags = set(item.tags)
		self.platforms = item.platforms
		self.project = item.project
		self.type = item.type
		self.created = item.created
		self.importance = item.importance
	def buildEmbed(self) -> Embed:
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
			icon_url=Client.PECK_SERVER_ICON
		)
		return embed

_runtime: Task
async def runtime() -> Coroutine[Any, Any, NoReturn]:
	async for news in news_ws():
		Client.BOT.dispatch("newsapi_post", News(news))

def setup():
	global _runtime
	_runtime = Client.BOT.loop.create_task(runtime, name="NewsAPI")
