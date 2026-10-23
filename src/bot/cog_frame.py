if __name__ == "__main__":
	raise Exception("Start the program from the main process")
import discord, logging
from discord.ext import commands
import bot.client as Client
import bot.config as Config
import paths

# "utils.generic", "utils.helper", "utils.management",
# "utils.memory", "utils.network", "utils.newsAPI",
# "utils.resources", "utils.thunderapi", "utils.time", "utils.wt"
# "bot.modals", "bot.client", "bot.config"
__reload_deps__ = ("bot.client", "bot.config")

class className(commands.GroupCog, group_name=""):
	def __init__(self):
		self.logger = logging.getLogger(__name__)
		self.logger.debug(f"{self.__class__.__name__} initialized")

async def setup():
	await Client.BOT.add_cog(className())
