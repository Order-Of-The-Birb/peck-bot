if __name__ == "__main__":
	raise Exception("Start the program from the main process")
import asyncio, logging, discord
from discord.ext import commands
from typing import TYPE_CHECKING
from sys import modules as sysmodules
if TYPE_CHECKING:
	from utils.bot import Bot
from cogs import EXTENSIONS
# ChannelIDs, RoleIDs, CategoryIDs
# owner_only, officer_only, members_only, debug_only
from utils.bot import owner_only
from utils.memory import process_memory, cache_counts
from psutil._common import bytes2human
#import utils.generic as genericUtil
#import utils.time as timeUtil
#import utils.wt as wtUtil

# "utils.generic", "utils.time", "utils.wt"
__reload_deps__ = ()

async def reload_autocomplete(interaction: discord.Interaction, current: str):
	options = [
		discord.app_commands.Choice(name=i, value=i)
		for i in [i.removeprefix("cogs.") for i in EXTENSIONS] if current.lower() in i.lower()
	]
	if current.lower() in "all":
		options.append(discord.app_commands.Choice(name="all", value="all"))
	return options
class OwnerCog(commands.Cog):
	def __init__(self, bot:'Bot'):
		self.bot = bot
		self.logger = logging.getLogger(__name__)
		self.logger.setLevel(bot.logLevel)
		self.logger.debug(f"{self.__class__.__name__} initialized")

	@discord.app_commands.command(name="memory", description="Inspect bot RAM and cache counts")
	@owner_only()
	async def memory(self, interaction: discord.Interaction):
		await interaction.response.defer(ephemeral=True)
		memory = await asyncio.to_thread(process_memory)
		counts = cache_counts(self.bot)
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
		lines.append(f"Repository users: {counts['repository_users']}; async tasks: {len(asyncio.all_tasks())}")
		lines.append("RSS includes shared pages; child RSS totals can double-count shared memory.")
		await interaction.edit_original_response(content="\n".join(lines))

	@discord.app_commands.command()
	@owner_only()
	@discord.app_commands.autocomplete(extension=reload_autocomplete)
	async def reload(self, interaction:discord.Interaction, extension:str):
		await interaction.response.defer(ephemeral=True)
		try:
			if extension.lower() == "all":
				for ext in EXTENSIONS:
					module = sysmodules.get(ext)
					deps = getattr(module, "__reload_deps__", ())
					await self.bot.reload_extension_with_deps(ext, *deps)
				await interaction.edit_original_response(content="Reloaded all cogs")
			else:
				full = f"cogs.{extension}"
				module = sysmodules.get(full)
				deps = getattr(module, "__reload_deps__", ()) if module else ()
				await self.bot.reload_extension_with_deps(full, *deps)
				await interaction.edit_original_response(content=f"Reloaded cog '{extension}'")
				self.logger.info(f"Reloaded cog '{extension}'")
		except:
			self.logger.exception(f"An error occured while reloading cog '{extension}'")
			await interaction.edit_original_response(content=f"Failed to reload '{extension}'")
	
	@discord.app_commands.command()
	@owner_only()
	async def force_sync(self, interaction:discord.Interaction):
		await interaction.response.defer(thinking=True)
		try:
			synced = await self.bot.tree.sync()
			self.logger.info(f"Synced {len(synced)} command(s)")
			await interaction.edit_original_response(content=f"Synced {len(synced)} command(s)")
		except Exception:
			self.logger.exception("An error occured while syncing")
			await interaction.edit_original_response(content="An error occurred while syncing")

async def setup(bot: 'Bot'):
	await bot.add_cog(OwnerCog(bot))