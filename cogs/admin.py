if __name__ == "__main__":
	raise Exception("Start the program from the main process")
import discord, logging
from discord.ext import commands
from typing import TYPE_CHECKING
if TYPE_CHECKING:
	from utils.bot import Bot
# ChannelIDs, RoleIDs, CategoryIDs
# owner_only, officer_only, members_only, debug_only
#from utils.bot import 
import utils.generic as genericUtil
#import utils.time as timeUtil
import utils.wt as wtUtil

# "utils.generic", "utils.time", "utils.wt"
__reload_deps__ = ("utils.wt", "utils.generic")

class AdminCog(commands.Cog):
	bot:'Bot'
	def __init__(self, bot:'Bot'):
		self.bot = bot
		self.logger = logging.getLogger(__name__)
		self.logger.setLevel(bot.logLevel)
		self.exclude_file = "userlist_exclude.txt"
		self.logger.debug(f"{self.__class__.__name__} initialized")
	async def interaction_check(self, interaction:discord.Interaction):
		if isinstance(interaction.channel, discord.DMChannel):
			self.logger.warning(f"Unauthorized request\n\tCommand:{interaction.command.name}\t\nUser:{interaction.user.name}({interaction.user.id})\n\tReason: Admin command in DMs")
			await interaction.response.send_message("You need to execute this command in a server (Required to check for permissions)")
			return False
		if any(i.id in self.bot.authorityRoleIDs for i in interaction.user.roles):
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
		user = await self.bot.fetch_user(userid)
		await user.send(content=f"{content}\n-# From the PECK administration")
		await interaction.response.send_message(f"{user} has recieved your message")

	@discord.app_commands.command()
	@discord.app_commands.guild_only()
	@discord.app_commands.default_permissions(administrator=True)
	@discord.app_commands.checks.has_permissions(administrator=True)
	async def say(self, interaction:discord.Interaction, content:str, file:discord.Attachment):
		"""Says the content as the bot, Only usable as the owner of the bot"""
		await interaction.response.defer(ephemeral=True)
		await interaction.channel.send(content.replace("\\n", "\n"), file=await file.to_file())
		await interaction.delete_original_response()
	
	@discord.app_commands.command()
	@discord.app_commands.guild_only()
	@discord.app_commands.default_permissions(manage_roles=True)
	@discord.app_commands.checks.has_permissions(manage_roles=True)
	async def verify_user(self, interaction:discord.Interaction, username:str, user:discord.Member):
		await interaction.response.defer(thinking=True)
		await self.bot.squadron.updateMembers()
		dbuser = self.bot.db.getByName(username)
		member = self.bot.squadron.getMember(username)
		if dbuser is None and member is None:
			await interaction.edit_original_response(content="User doesn't yet exist in database, nor on the War Thunder page")
			return
		elif dbuser is not None and dbuser.status != self.bot.db.Status.MEMBER:
			dbuser.status = self.bot.db.Status.MEMBER
			dbuser.discord_id = user.id
			dbuser.push()
			await interaction.edit_original_response(content=f"Successfully verified user '{username}'")
		elif dbuser is None and member is not None:
			_ = wtUtil.get_user_ids(username)[username]
			if _ is not None:
				self.bot.db.add_user(_, username=username, discord_id=user.id, joindate=member.joindate.date(), status=self.bot.db.Status.MEMBER)
				await interaction.edit_original_response(content=f"Successfully verified user '{username}'")
			else:
				await interaction.edit_original_response(content="Could not retrieve user's gaijin ID")

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
async def setup(bot: 'Bot'):
	await bot.add_cog(AdminCog(bot))