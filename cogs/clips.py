if __name__ == "__main__":
	raise Exception("Start the program from the main process")
import discord, logging
from discord.ext import commands
from typing import TYPE_CHECKING
if TYPE_CHECKING:
	from utils.bot import Bot
# ChannelIDs, RoleIDs, CategoryIDs
# owner_only, officer_only, members_only, debug_only
from utils.bot import officer_only, CategoryIDs
from utils.modals import CreateClipCh, AddAlias
#import utils.time as timeUtil
#import utils.wt as wtUtil
import shared

# "utils.generic", "utils.time", "utils.wt"
__reload_deps__ = ()

class ClipsCog(commands.GroupCog, group_name="clips"):
	def __init__(self, bot:'Bot'):
		self.bot = bot
		self.logger = logging.getLogger(__name__)
		self.logger.setLevel(bot.logLevel)
		self.logger.debug(f"{self.__class__.__name__} initialized")

	@discord.app_commands.command(name="upload")
	async def upload_clip(self, interaction:discord.Interaction):
		await interaction.response.send_modal(CreateClipCh(self.bot))

	@discord.app_commands.command(name="add_alias")
	@officer_only()
	async def add_alias(self, interaction:discord.Interaction):
		await interaction.response.send_modal(AddAlias(self.bot))
	
	@discord.app_commands.command(name="remove_alias")
	@discord.app_commands.default_permissions(manage_channels=True)
	@officer_only()
	async def remove_alias(self, interaction:discord.Interaction, alias:str, user:discord.User):
		await interaction.response.defer(thinking=True, ephemeral=True)

		config = shared.GUILD_CONFIGS.get(interaction.guild.id)
		if config is None:
			await interaction.edit_original_response(content=f"An error occurred while loading server data")
			return

		for categ in interaction.guild.categories:
			if categ.id != config.category_ids[shared.CategoryIDs.CLIPS]: continue
			clipCateg = categ
			break
		else:
			raise LookupError(f"Could not find clips category in guild {interaction.guild_id}")
		userClipCh = None
		for ch in clipCateg.channels:
			if ch.name != str(user.id): continue
			userClipCh = ch
			break
		else:
			await interaction.edit_original_response(content=f"No clips channel could be found for user {user.name}")
			return
		aliases = userClipCh.topic.split("\n")
		for ind, _alias in enumerate(aliases):
			if _alias.lower() != alias.lower(): continue
			aliases.pop(ind)
			userClipCh.topic = "\n".join(aliases)
			await interaction.edit_original_response(content=f"Alias '{alias}' has been removed from user {user.name}")
			break
		else:
			await interaction.edit_original_response(content=f"No such alias found. The following aliases are connected to the given user: {"; ".join(aliases)}")
			return

async def setup(bot:'Bot'):
	await bot.add_cog(ClipsCog(bot))