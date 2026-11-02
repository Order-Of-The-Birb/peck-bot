import logging
from datetime import UTC, datetime
from importlib import reload
from sys import modules as sysmodules
from typing import TypedDict

import discord
from discord.ext import commands

import bot.config as Config
import paths
from bot.cogs import EXTENSIONS

logger = logging.getLogger(__name__)

BOT: '_Bot' = globals().get("BOT")
PECK_SERVER_ICON = "https://cdn.discordapp.com/icons/917850361019125820/325129a273dac84e31f9aa5de51f1936.png?size=128"

class _Bot(commands.Bot):
	class _Tree(discord.app_commands.CommandTree):
		async def on_error(self, interaction: discord.Interaction, error: Exception):
			if isinstance(error, discord.app_commands.CheckFailure):
				return
			if isinstance(error, discord.app_commands.CommandOnCooldown):
				await interaction.response.send_message("This command is on cooldown")
			if not interaction.response.is_done():
				await interaction.response.send_message("Oops! Something went wrong.", ephemeral=True)
			raise error  # still log real bugs
	RUNNING_SINCE: datetime = datetime.now(UTC)
	def __init__(self, *args,**kwargs):
		intents = discord.Intents.all()
		# No features consume member presence or typing updates. Keep member and
		# message caches for role lookups and edit/delete audit logs.
		intents.presences = False
		intents.typing = False

		super().__init__(*args, tree_cls=_Bot._Tree, intents=intents, **kwargs)

	async def reload_module(self, extension: str):
		if extension == "all":
			for ext in EXTENSIONS:
				await self.reload_module(ext)
			return

		reloaded: set[str] = set()

		async def reload_deps(mod: str):
			module = sysmodules.get(mod)
			if module is None:
				return
			deps = getattr(module, "__reload_deps__", ())
			if isinstance(deps, str): # Protection against missing commas
				deps = (deps,)
			for dep in deps:
				for name, submodule in tuple(sysmodules.items()):
					if submodule is None or not name.startswith(dep) or name in reloaded:
						continue
					reloaded.add(name)
					await reload_deps(name)
					try:
						reload(submodule)
						logger.debug(f"Reloaded module: {name}")
					except Exception:
						logger.exception(f"Failed to reload module: {name}")

		await reload_deps(extension)
		try:
			await self.reload_extension(extension)
		except commands.errors.ExtensionNotLoaded:
			pass

	async def setup_hook(self):
		logger.info("Bot is getting ready...")
		self.status = discord.Status.do_not_disturb
		for extension in EXTENSIONS:
			try:
				await self.load_extension(extension)
			except Exception:
				logger.exception(f"Failed to load extension '{extension}'")
				raise
		try:
			synced = await self.tree.sync()
			logger.info(f"Synced {len(synced)} command(s)")
		except Exception:
			logger.exception("An error occured while syncing")
		logger.info("Startup complete")

class _InteractionExtras(TypedDict):
	config: Config.GuildConfig | None
class Interaction(discord.Interaction):
	extras: _InteractionExtras

#region Decorators
def guild_config():
	async def predicate(interaction: discord.Interaction) -> bool:
		config = await Config.get(interaction.guild_id)
		if config is None:
			return True
		interaction.extras["config"] = config
		return True
	return discord.app_commands.check(predicate)
def guild_only():
	async def predicate(interaction: discord.Interaction) -> bool:
		config = await Config.get(interaction.guild_id)
		if config is None:
			await interaction.response.send_message("This server is not configured")
			return False
		interaction.extras["config"] = config
		return True
	def decorator(func):
		return discord.app_commands.check(predicate)(discord.app_commands.guild_only()(func))
	return decorator

def debug_only():
	return discord.app_commands.check(lambda x: paths.DEBUG)
def owner_only():
	async def predicate(interaction: discord.Interaction) -> bool:
		return interaction.user.id in [332030423913725953, 709449854371364895]
	return discord.app_commands.check(predicate)
def admin_only():
	async def predicate(interaction: discord.Interaction) -> bool:
		if interaction.guild is None:
			return False
		return interaction.user.guild_permissions.administrator
	return discord.app_commands.check(predicate)
def members_only():
	async def predicate(interaction: discord.Interaction) -> bool:
		if interaction.guild_id is None:
			return False
		config = await Config.get(interaction.guild_id)
		if config is None:
			return False
		member_role = config.get(Config.Roles.MEMBER)
		if member_role is None:
			raise RuntimeError(f"Could not find the member role of server {interaction.guild_id}")
		return any(role.id == member_role.id for role in interaction.user.roles)
	return discord.app_commands.check(predicate)
#endregion

async def setup(token: str):
	global BOT
	BOT = _Bot(command_prefix='.pt ')
	await BOT.start(token)
