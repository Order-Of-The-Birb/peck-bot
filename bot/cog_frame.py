if __name__ == "__main__":
	raise Exception("Start the program from the main process")
import discord, logging
from discord.ext import commands
from typing import TYPE_CHECKING
if TYPE_CHECKING:
	from bot.client import Bot
# ChannelIDs, RoleIDs, CategoryIDs
# owner_only, officer_only, members_only, debug_only
#from utils.bot import 
#import utils.generic as genericUtil
#import utils.time as timeUtil
#import utils.wt as wtUtil
import shared

# "utils.generic", "utils.time", "utils.wt"
# "bot.modals", "bot.client"
__reload_deps__ = ()

class className(commands.GroupCog, group_name=""):
	def __init__(self):
		self.logger = logging.getLogger(__name__)
		self.logger.debug(f"{self.__class__.__name__} initialized")

async def setup(bot:'Bot'):
	await bot.add_cog(className())