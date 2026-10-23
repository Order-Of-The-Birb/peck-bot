if __name__ == "__main__":
	raise Exception("Start the program from the main process")
import discord, logging
from discord.ext import commands
import bot.config as Config
import bot.client as Client

# "utils.generic", "utils.helper", "utils.management",
# "utils.memory", "utils.network", "utils.newsAPI",
# "utils.resources", "utils.thunderapi", "utils.time", "utils.wt"
# "bot.modals", "bot.client", "bot.config"
__reload_deps__ = ("bot.client", "bot.config")

class AdminCog(commands.Cog):
	def __init__(self):
		self.logger = logging.getLogger(__name__)
		self.logger.debug(f"{self.__class__.__name__} initialized")
	async def interaction_check(self, interaction:discord.Interaction):
		if isinstance(interaction.channel, discord.DMChannel):
			self.logger.warning(f"Unauthorized request\n\tCommand:{interaction.command.name}\t\nUser:{interaction.user.name}({interaction.user.id})\n\tReason: Admin command in DMs")
			await interaction.response.send_message("You need to execute this command in a server (Required to check for permissions)")
			return False
		if interaction.user.guild_permissions.administrator:
			return True
		self.logger.warning(f"User {interaction.user.name} ({interaction.user.id}) tried using an admin command without the needed permissions")
		return False

	@discord.app_commands.command()
	@discord.app_commands.guild_only()
	@discord.app_commands.default_permissions(manage_messages=True)
	@discord.app_commands.checks.has_permissions(manage_messages=True)
	@discord.app_commands.describe(count="The amount of messages to purge")
	async def purge(self, interaction:discord.Interaction, count:int):
		if count < 1:
			await interaction.response.send_message(content="Count too low.", ephemeral=True)
			return
		await interaction.response.send_message(f"Purging {count} messages", ephemeral=True)
		await interaction.channel.purge(limit=count)
		await interaction.edit_original_response(content="Messages purged.")

	@discord.app_commands.command()
	@discord.app_commands.guild_only()
	@discord.app_commands.default_permissions(administrator=True)
	@discord.app_commands.checks.has_permissions(administrator=True)
	@discord.app_commands.describe(userid="The user's id to send the DM to", content="What will be sent")
	async def senddm(self, interaction: discord.Interaction, userid:str, content:str):
		"""Sends a DM to a specified user, used with an ID, Only usable by the bot owner"""
		userid = int(userid)
		user = await Client.BOT.fetch_user(userid)
		await user.send(content=f"{content}\n-# From the PECK administration")
		await interaction.response.send_message(f"{user} has recieved your message")

	@discord.app_commands.command()
	@discord.app_commands.guild_only()
	@discord.app_commands.default_permissions(administrator=True)
	@discord.app_commands.checks.has_permissions(administrator=True)
	async def say(self, interaction:discord.Interaction, content:str, file:discord.Attachment = None, respond_to_id:str = None):
		"""Says the content as the bot, Only usable as the owner of the bot"""
		await interaction.response.defer(ephemeral=True)
		if "-" in respond_to_id: # copy message ID returns <channelID>-<messageID> when holding shift
			parts = respond_to_id.split("-")
			if parts[0] != str(interaction.channel_id):
				await interaction.edit_original_response(content="Channel ID for message doesn't match the current channel")
				return
			respond_to_id = parts[1]
		await interaction.channel.send(
			content=content.replace("\\n", "\n"),
			file=(await file.to_file()) if file else None,
			reference=interaction.channel.get_partial_message(int(respond_to_id)) if respond_to_id else None
		)
		await interaction.delete_original_response()

	@discord.app_commands.command()
	@discord.app_commands.guild_only()
	@discord.app_commands.default_permissions(ban_members=True)
	@discord.app_commands.checks.has_permissions(ban_members=True)
	@discord.app_commands.choices(
		delete_messages = [
			discord.app_commands.Choice(name="None", value=0),
			discord.app_commands.Choice(name="5m", value=5*60),
			discord.app_commands.Choice(name="15m", value=15*60),
			discord.app_commands.Choice(name="30m", value=30*60),
			discord.app_commands.Choice(name="1h", value=60*60),
			discord.app_commands.Choice(name="6h", value=6*60*60),
			discord.app_commands.Choice(name="12h", value=12*60*60),
			discord.app_commands.Choice(name="1d", value=24*60*60),
			discord.app_commands.Choice(name="2d", value=2*24*60*60),
			discord.app_commands.Choice(name="3d", value=3*24*60*60),
			discord.app_commands.Choice(name="4d", value=4*24*60*60),
			discord.app_commands.Choice(name="5d", value=5*24*60*60),
			discord.app_commands.Choice(name="6d", value=6*24*60*60),
			discord.app_commands.Choice(name="7d", value=7*24*60*60),
		]
	)
	async def softban(self, interaction:discord.Interaction, user:discord.Member, reason:str, delete_messages:int):
		await interaction.response.defer(thinking=True, ephemeral=True)
		if delete_messages > 24*60*60:
			await user.ban(delete_message_days=delete_messages//24//60//60, reason=reason)
		else:
			await user.ban(delete_message_seconds=delete_messages, reason=reason)
		await interaction.guild.unban(user, reason="softban")
		await interaction.edit_original_response(content="User has been softbanned.")

async def setup():
	await Client.BOT.add_cog(AdminCog())
