import logging

import discord
from discord.ext import commands

import bot.client as Client
import bot.config as Config

# "utils.generic", "utils.media",
# "utils.memory", "utils.network", "utils.newsAPI",
# "utils.resources", "utils.thunderapi", "utils.time"
# "bot.views", "bot.client", "bot.config"
__reload_deps__ = ("bot.client", "bot.config", )

class ContextMenuCog(commands.Cog):
	def __init__(self):
		self.logger = logging.getLogger(__name__)
		self.menuItems = (
			discord.app_commands.ContextMenu(
				name="Get War Thunder username",
				callback=self.get_wt_name
			),
		)
		self.logger.debug(f"{self.__class__.__name__} initialized")

	async def get_wt_name(self, interaction:discord.Interaction, user:discord.Member):
		await interaction.response.defer(ephemeral=True, thinking=True)
		config =await Config.get(interaction.guild_id)
		if config is None:
			await interaction.response.send_message("This server is not configured.", ephemeral=True)
			return
		associatedAccounts = await config.management.get(discord_id=user.id)
		if not associatedAccounts:
			await interaction.response.send_message("Could not find any accounts associated with the user.", ephemeral=True)
			return
		accounts_string = "\n".join(f'- {i.username}' for i in associatedAccounts)
		await interaction.edit_original_response(content=f"The following accounts are connected to the user:\n{accounts_string}")
	async def cog_load(self) -> None:
		for item in self.menuItems:
			Client.BOT.tree.add_command(item)

	def cog_unload(self) -> None:
		for item in self.menuItems:
			Client.BOT.tree.remove_command(item.name, type=item.type)

async def setup(bot: Client._Bot):
	await bot.add_cog(ContextMenuCog())
