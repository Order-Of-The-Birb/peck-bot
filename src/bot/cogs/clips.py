if __name__ == "__main__":
	raise Exception("Start the program from the main process")
import discord, logging
from discord.ext import commands
# owner_only, officer_only, members_only, debug_only
from bot.client import admin_only
from bot.modals import CreateClipCh, AddAlias
#import utils.time as timeUtil
#import utils.wt as wtUtil
import bot.client as Client
import bot.config as Config

# "utils.generic", "utils.helper", "utils.management",
# "utils.memory", "utils.network", "utils.newsAPI",
# "utils.resources", "utils.thunderapi", "utils.time", "utils.wt"
# "bot.modals", "bot.client", "bot.config"
__reload_deps__ = ("bot.client", "bot.config", "bot.modals")

class ClipsCog(commands.GroupCog, group_name="clips"):
	def __init__(self):
		self.logger = logging.getLogger(__name__)
		self.logger.debug(f"{self.__class__.__name__} initialized")

	@discord.app_commands.command(name="upload")
	async def upload_clip(self, interaction:discord.Interaction):
		await interaction.response.send_modal(CreateClipCh(Client.BOT))

	@discord.app_commands.command(name="add_alias")
	@admin_only()
	async def add_alias(self, interaction:discord.Interaction):
		await interaction.response.send_modal(AddAlias(Client.BOT))

	@discord.app_commands.command(name="remove_alias")
	@discord.app_commands.default_permissions(manage_channels=True)
	@admin_only()
	async def remove_alias(self, interaction:discord.Interaction, alias:str, user:discord.User):
		await interaction.response.defer(thinking=True, ephemeral=True)

		config = Config.get(interaction.guild.id)
		if config is None:
			await interaction.edit_original_response(content=f"An error occurred while loading server data")
			return
		category = config.get_category(Config.GuildConfig.Categories.CLIPS)

		if category is None:
			raise LookupError(f"Could not find clips category in guild {interaction.guild_id}")
		userClipCh = None
		for ch in category.channels:
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

async def setup():
	await Client.BOT.add_cog(ClipsCog())
