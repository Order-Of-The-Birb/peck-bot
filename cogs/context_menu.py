if __name__ == "__main__":
	raise Exception("Start the program from the main process")
import discord, logging
from discord.ext import commands
from typing import TYPE_CHECKING
if TYPE_CHECKING:
	from utils.bot import Bot
# ChannelIDs, RoleIDs, CategoryIDs
# owner_only, officer_only, members_only, debug_only
#from utils.bot import 
#import utils.generic as genericUtil
#import utils.time as timeUtil
#import utils.wt as wtUtil

# "utils.generic", "utils.time", "utils.wt"
__reload_deps__ = ()

class ContextMenuCog(commands.Cog):
	def __init__(self, bot:'Bot'):
		self.bot = bot
		self.logger = logging.getLogger(__name__)
		self.logger.setLevel(bot.logLevel)
		self.logger.debug(f"{self.__class__.__name__} initialized")
		self.menuItems = (
			discord.app_commands.ContextMenu(
				name="Get War Thunder username",
				callback=self.get_wt_name
			),
		)

	async def get_wt_name(self, interaction:discord.Interaction, user:discord.Member):
		associatedAccounts = self.bot.db.getByDID(user.id)
		if not associatedAccounts:
			await interaction.response.send_message("Could not find any accounts associated with the user.", ephemeral=True)
			return
		accounts_string = "\n".join(f'- {i.username}' for i in associatedAccounts)
		await interaction.response.send_message(
			f"The following accounts are connected to the user:\n{accounts_string}",
			ephemeral=True
		)
	async def cog_load(self) -> None:
		for item in self.menuItems:
			self.bot.tree.add_command(item)

	def cog_unload(self) -> None:
		for item in self.menuItems:
			self.bot.tree.remove_command(item.name, type=item.type)

async def setup(bot:'Bot'):
	await bot.add_cog(ContextMenuCog(bot))
