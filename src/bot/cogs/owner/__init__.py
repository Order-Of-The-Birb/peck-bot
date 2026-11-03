import asyncio
import logging

import discord
from aiohttp import ClientSession
from discord.ext import commands
from psutil._common import bytes2human

import bot.client as Client
import bot.extensions as ext
import utils.newsAPI as NewsAPI
import utils.thunderapi as ThunderAPI
from bot.cogs import EXTENSIONS
from utils.memory import cache_counts, process_memory


async def reload_autocomplete(interaction: ext.Interaction, current: str):
	options = [
		discord.app_commands.Choice(name=i, value=i)
		for i in [i.removeprefix("bot.cogs.") for i in EXTENSIONS] if current.lower() in i.lower()
	]
	if "all".startswith(current.lower()):
		options.append(discord.app_commands.Choice(name="all", value="all"))
	return options
class OwnerCog(commands.Cog):
	def __init__(self):
		self.logger = logging.getLogger(__name__)
		self.logger.debug(f"{self.__class__.__name__} initialized")

	async def interaction_check(self, interaction:ext.Interaction):
		return interaction.user.id in [332030423913725953, 709449854371364895]

	@discord.app_commands.command(name="memory", description="Inspect bot RAM and cache counts")
	@Client.owner_only()
	async def memory(self, interaction: ext.Interaction):
		await interaction.response.defer(ephemeral=True)
		memory = await asyncio.to_thread(process_memory)
		counts = cache_counts(Client.BOT)
		lines = [f"Python RSS: {bytes2human(memory['rss'])}"]
		for key, label in (("uss", "Python private RAM (USS)"), ("pss", "Python proportional RAM (PSS)"),
			("cgroup_current", "Cgroup RAM (includes file cache)"), ("cgroup_peak", "Cgroup peak")):
			if memory[key] is not None:
				lines.append(f"{label}: {bytes2human(memory[key])}")
		lines.append(f"Child processes: {memory['children']} / {bytes2human(memory['children_rss'])} summed RSS")
		if memory["children_pss"] is not None:
			lines.append(f"Child proportional RAM (PSS): {bytes2human(memory['children_pss'])}")
		lines.append(f"Cached messages: {counts['messages']} / {counts['message_limit']}")
		lines.append(f"Cached members: {counts['cached_members']} / {counts['members']}")
		lines.append(f"Open forms: {counts['modals']}; view message keys: {counts['view_message_keys']}")
		lines.append(f"Async tasks: {len(asyncio.all_tasks())}")
		lines.append("RSS includes shared pages; child RSS totals can double-count shared memory.")
		await interaction.edit_original_response(content="\n".join(lines))

	@discord.app_commands.command()
	@Client.owner_only()
	@discord.app_commands.autocomplete(extension=reload_autocomplete)
	async def reload(self, interaction:ext.Interaction, extension:str):
		await interaction.response.defer(ephemeral=True)
		try:
			if extension.lower() == "all":
				await Client.BOT.reload_module(extension)
				await interaction.edit_original_response(content="Reloaded all cogs")
			else:
				full = f"bot.cogs.{extension}"
				await Client.BOT.reload_module(full)
				await interaction.edit_original_response(content=f"Reloaded cog '{extension}'")
		except Exception:
			self.logger.exception(f"An error occured while reloading cog '{extension}'")
			await interaction.edit_original_response(content=f"Failed to reload '{extension}'")

	@discord.app_commands.command()
	@Client.owner_only()
	async def force_sync(self, interaction:ext.Interaction):
		await interaction.response.defer(thinking=True)
		try:
			synced = await Client.BOT.tree.sync()
			self.logger.info(f"Synced {len(synced)} command(s)")
			await interaction.edit_original_response(content=f"Synced {len(synced)} command(s)")
		except Exception:
			self.logger.exception("An error occured while syncing")
			await interaction.edit_original_response(content="An error occurred while syncing")

	@discord.app_commands.command()
	@Client.debug_only()
	async def test_news(self, interaction: ext.Interaction):
		await interaction.response.defer(thinking=True)
		async with ClientSession(ThunderAPI._api_url) as session, session.get("/v1/news") as r:
			r.raise_for_status()
			for item in await r.json():
				news = NewsAPI.News(ThunderAPI.NewsModel.model_validate(item))
				Client.BOT.dispatch("newsapi_post", news)
		await interaction.edit_original_response(content="News posted")

async def setup(bot: Client._Bot):
	await bot.add_cog(OwnerCog())
