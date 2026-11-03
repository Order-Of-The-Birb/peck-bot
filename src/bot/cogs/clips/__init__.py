import logging

import discord
from discord.ext import commands

import bot.client as Client
import bot.extensions as ext

from . import modals as Modals


class ClipsCog(commands.GroupCog, group_name="clips"):
	def __init__(self):
		self.logger = logging.getLogger(__name__)
		self.logger.debug(f"{self.__class__.__name__} initialized")

	@discord.app_commands.command(name="upload")
	@Client.guild_only()
	async def upload_clip(self, interaction:ext.Interaction):
		await interaction.response.send_modal(Modals.CreateClip())

	@discord.app_commands.command(name="add_alias")
	@Client.guild_only()
	async def add_alias(self, interaction:ext.Interaction):
		await interaction.response.send_modal(Modals.CreateAlias())

	@discord.app_commands.command(name="remove_alias")
	@Client.guild_only()
	async def remove_alias(self, interaction:ext.Interaction):
		await interaction.response.send_modal(Modals.RemoveAlias())

async def setup(bot: Client._Bot):
	await bot.add_cog(ClipsCog())
