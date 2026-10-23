if __name__ == "__main__":
	raise Exception("Start the program from the main process")
import logging, discord
from sys import modules as sysmodules
from importlib import reload
from discord.ext import commands
from datetime import datetime, UTC
from bot.cogs import EXTENSIONS
import bot.config as Config
import paths
logger = logging.getLogger(__name__)

BOT: '_Bot' = None

class _Bot(commands.Bot):
	RUNNING_SINCE: datetime = datetime.now(UTC)
	def __init__(self, *args,**kwargs):
		intents = discord.Intents.all()
		# No features consume member presence or typing updates. Keep member and
		# message caches for role lookups and edit/delete audit logs.
		intents.presences = False
		intents.typing = False
		self.intents = intents
		del intents

		super().__init__(tree_cls=_Tree, *args, **kwargs)

	def _reload_prefix(self, prefix: str):
		to_reload = [
			(name, module)
			for name, module in sysmodules.items()
			if module and name.startswith(prefix)
		]
		for name, module in to_reload:
			try:
				reload(module)
				logger.debug(f"Reloaded module: {name}")
			except Exception:
				logger.exception(f"Failed to reload module: {name}")
	async def reload_extension_with_deps(self,extension: str,*module_prefixes: str):
		"""Reload helper modules, then reload the extension."""
		if isinstance(module_prefixes, str):
			raise TypeError(f"__reload_deps__ must be a tuple, not str")
		for prefix in module_prefixes:
			self._reload_prefix(prefix)
		try:
			await self.reload_extension(extension)
		except commands.errors.ExtensionNotLoaded: pass

	async def memberHasRole(self, guild_id: int, role_id:Config.GuildConfig.Roles, member_id:int):
		config = Config.get(guild_id)
		if config is None:
			logger.warning(f"Server {guild_id} not configured, returning False for 'memberHasRole'")
			return False
		guild = self.get_guild(guild_id)
		if not guild:
			raise RuntimeError(f"Guild {guild} could not be retrieved")
		member = guild.get_member(member_id)
		if not member:
			raise RuntimeError(f"Member {member} of guild {guild} could not be retrieved")
		return member.get_role(config.get_role(role_id)) is not None

	async def setup_hook(self):
		logger.info("Bot is getting ready...")
		self.status = discord.Status.do_not_disturb
		for i in self.timeouts.values(): i.run()
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
			logging.exception("An error occured while syncing")
		logger.info("Startup complete")

class _Tree(discord.app_commands.CommandTree):
	async def on_error(self, interaction: discord.Interaction, error: Exception):
		if isinstance(error, discord.app_commands.CheckFailure):
			logger.warning(f"User {interaction.user.name} ({interaction.user.id}) tried running {interaction.command.name} without the required permissions")
			await interaction.response.send_message("You don't have the required Permissions", ephemeral=True, delete_after=5)
			return
		if not interaction.response.is_done():
			await interaction.response.send_message("Oops! Something went wrong.", ephemeral=True)
		raise error  # still log real bugs

#region Decorators
def guild_config():
	async def predicate(interaction: discord.Interaction) -> bool:
		config = Config.get(interaction.guild_id)
		if config is None:
			return True
		interaction.extras["config"] = config
		return True
	return discord.app_commands.check(predicate)
def guild_only():
	async def predicate(interaction: discord.Interaction) -> bool:
		config = Config.get(interaction.guild_id)
		if config is None:
			return False
		interaction.extras["config"] = config
		return True
	return discord.app_commands.check(predicate)

def debug_only():
	return discord.app_commands.check(lambda x: paths.DEBUG)
def owner_only():
	async def predicate(interaction: discord.Interaction) -> bool:
		return interaction.user.id in [332030423913725953, 709449854371364895]
	return discord.app_commands.check(predicate)
def admin_only():
	async def predicate(interaction: discord.Interaction) -> bool:
		if interaction.guild is None: return False
		return interaction.user.guild_permissions.administrator
	return discord.app_commands.check(predicate)
def members_only():
	async def predicate(interaction: discord.Interaction) -> bool:
		if interaction.guild_id is None: return False
		config = Config.get(interaction.guild_id)
		if config is None:
			return False
		member_role = config.get_role(Config.GuildConfig.Roles.MEMBER)
		if member_role is None:
			raise RuntimeError(f"Could not find the member role of server {interaction.guild_id}")
		return any(role.id == member_role.id for role in interaction.user.roles)
	return discord.app_commands.check(predicate)
#endregion

async def setup(token: str):
	global BOT
	BOT = _Bot(command_prefix='.pt ')
	await BOT.start(token)
