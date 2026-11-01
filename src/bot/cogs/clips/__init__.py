import logging

import discord
from discord.ext import commands

#import utils.time as timeUtil
import bot.client as Client
import bot.config as Config
from . import modals as Modals

# "utils.generic", "utils.media",
# "utils.memory", "utils.network", "utils.newsAPI",
# "utils.resources", "utils.thunderapi", "utils.time"
# "bot.views", "bot.client", "bot.config"
__reload_deps__ = ("bot.client", "bot.config")

class ClipsCog(commands.GroupCog, group_name="clips"):
	def __init__(self):
		self.logger = logging.getLogger(__name__)
		self.logger.debug(f"{self.__class__.__name__} initialized")

	@discord.app_commands.command(name="upload")
	async def upload_clip(self, interaction:discord.Interaction):
		await interaction.response.send_modal(Modals.CreateClip())

	@discord.app_commands.command(name="add_alias")
	async def add_alias(self, interaction:discord.Interaction):
		await interaction.response.send_modal(Modals.CreateAlias())

	@discord.app_commands.command(name="remove_alias")
	@discord.app_commands.default_permissions(manage_channels=True)
	@Client.admin_only()
	async def remove_alias(self, interaction:discord.Interaction, alias:str, user:discord.User):
		await interaction.response.defer(thinking=True, ephemeral=True)

		config =await Config.get(interaction.guild.id)
		if config is None:
			await interaction.edit_original_response(content="An error occurred while loading server data")
			return
		category = config.get(Config.Channels.CLIPS)
		if category is None:
			raise LookupError(f"Could not find clips category in guild {interaction.guild_id}")

		userClipCh = None
		for ch in category.channels:
			if ch.name != str(user.id):
				continue
			userClipCh = ch
			break
		else:
			await interaction.edit_original_response(content=f"No clips channel could be found for user {user.name}")
			return
		aliases = userClipCh.topic.split("\n")
		for ind, _alias in enumerate(aliases):
			if _alias.lower() != alias.lower():
				continue
			aliases.pop(ind)
			userClipCh.topic = "\n".join(aliases)
			await interaction.edit_original_response(content=f"Alias '{alias}' has been removed from user {user.name}")
			break
		else:
			await interaction.edit_original_response(content=f"No such alias found. The following aliases are connected to the given user: {"; ".join(aliases)}")
			return

async def setup(bot: Client._Bot):
	await bot.add_cog(ClipsCog())
