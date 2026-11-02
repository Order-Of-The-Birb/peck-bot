import ast
import inspect
import logging
from datetime import UTC, datetime
from importlib import reload
from sys import modules as sysmodules
from types import ModuleType
from typing import Protocol, TypedDict

import discord
from discord.ext import commands

import bot.config as Config
import paths
from bot.cogs import EXTENSIONS

_logger = logging.getLogger(__name__)

BOT: '_Bot' = globals().get("BOT")
PECK_SERVER_ICON = "https://cdn.discordapp.com/icons/917850361019125820/325129a273dac84e31f9aa5de51f1936.png?size=128"
_LOCAL_ROOTS = {"bot", "utils", "paths"}

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

	@staticmethod
	def local_deps(module: ModuleType) -> set[str]:
		try:
			src = inspect.getsource(module)
		except (OSError, TypeError):
			return set()
		deps: set[str] = set()
		for node in ast.walk(ast.parse(src)):
			if isinstance(node, ast.Import):
				for alias in node.names:
					deps.add(alias.name)
			elif isinstance(node, ast.ImportFrom) and node.module:
				deps.add(node.module)
		return {d for d in deps if d.split(".", 1)[0] in _LOCAL_ROOTS}

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
			deps = _Bot.local_deps(module)
			for dep in deps:
				for name, submodule in tuple(sysmodules.items()):
					if submodule is None or not name.startswith(dep) or name in reloaded:
						continue
					if name in EXTENSIONS:          # cogs are reloaded via reload_extension
						continue
					reloaded.add(name)
					await reload_deps(name)
					try:
						reload(submodule)
						_logger.debug(f"Reloaded module: {name}")
					except Exception:
						_logger.exception(f"Failed to reload module: {name}")

		await reload_deps(extension)
		try:
			await self.reload_extension(extension)
		except commands.errors.ExtensionNotLoaded:
			pass

	async def setup_hook(self):
		_logger.info("Bot is getting ready...")
		self.status = discord.Status.do_not_disturb
		for extension in EXTENSIONS:
			try:
				await self.load_extension(extension)
			except Exception:
				_logger.exception(f"Failed to load extension '{extension}'")
				raise
		try:
			synced = await self.tree.sync()
			_logger.info(f"Synced {len(synced)} command(s)")
		except Exception:
			_logger.exception("An error occured while syncing")
		_logger.info("Startup complete")

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

class genericButtons(discord.ui.View):
	class _callbackProtocol(Protocol):
		async def __call__(
			self,
			interaction: Interaction,
			**kwargs
		) -> bool|None: ...
	def __init__(self, *, acceptFunc:_callbackProtocol, denyFunc:_callbackProtocol|None=None, timeout:int|None = 180, acceptLabel:str = "Yes", denyLabel:str="No", deny:bool=True, removeButtonsAfter:bool=False, requiredPerms:discord.Permissions|None=None, id: str | None = None, **kwargs):
		if deny and denyFunc is None:
			raise ValueError("deny=True requires denyFunc to be provided")
		self.requiredPerms = requiredPerms
		super().__init__(timeout=timeout)
		yes = discord.ui.Button(
			label=acceptLabel,
			style=discord.ButtonStyle.green,
			custom_id="accept"
		)
		no = discord.ui.Button(
			label=denyLabel,
			style=discord.ButtonStyle.red,
			custom_id="deny"
		)
		async def yes_callback(interaction: Interaction):
			await interaction.response.edit_message(view=self)
			if self.requiredPerms is not None and not all(getattr(interaction.user.guild_permissions, p[0], False) for p in self.requiredPerms if p[1]):
				_logger.warning(f"Accept attempt by: {interaction.user.name} ({interaction.user.id})")
				await interaction.followup.send("You do not have the required permission to use this!", ephemeral=True)
				return
			result = await acceptFunc(interaction, **kwargs)
			if result:
				yes.disabled = True
				if deny:
					no.disabled = True
				self.stop()
				if removeButtonsAfter:
					try:
						await interaction.edit_original_response(view=None)
					except discord.NotFound:
						pass # The callback may already have deleted the message.
		async def no_callback(interaction: Interaction):
			await interaction.response.edit_message(view=self)
			if self.requiredPerms is not None and not all(getattr(interaction.user.guild_permissions, p[0], False) for p in self.requiredPerms if p[1]):
				_logger.warning(f"Deny attempt by: {interaction.user.name} ({interaction.user.id})")
				await interaction.followup.send("You do not have the required permission to use this!", ephemeral=True)
				return
			result = await denyFunc(interaction, **kwargs)
			if result:
				yes.disabled = True
				no.disabled = True
				self.stop()
				if removeButtonsAfter:
					try:
						await interaction.edit_original_response(view=None)
					except discord.NotFound:
						pass # The callback may already have deleted the message.
		yes.callback = yes_callback
		no.callback = no_callback
		self.add_item(yes)
		if deny and denyFunc is not None:
			self.add_item(no)

async def setup(token: str):
	global BOT
	BOT = _Bot(command_prefix='.pt ')
	await BOT.start(token)
