import logging

from discord.ext import commands

import bot.client as Client

# "utils.generic", "utils.media",
# "utils.memory", "utils.network", "utils.newsAPI",
# "utils.resources", "utils.thunderapi", "utils.time"
# "bot.modals", "bot.client", "bot.config"
__reload_deps__ = ("bot.client", "bot.config")

class className(commands.GroupCog, group_name=""):
	def __init__(self):
		self.logger = logging.getLogger(__name__)
		self.logger.debug(f"{self.__class__.__name__} initialized")

async def setup(bot: Client._Bot):
	await bot.add_cog(className())
