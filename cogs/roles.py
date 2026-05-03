if __name__ == "__main__":
	raise Exception("Start the program from the main process")
import discord, logging
from discord.ext import commands
from datetime import datetime, UTC
from dateutil.relativedelta import relativedelta
from typing import TYPE_CHECKING
if __name__ == "__main__":
	from os import path
	from sys import path as sys_path
	sys_path.append(path.abspath(path.join(path.dirname(__file__), '..')))
if TYPE_CHECKING:
	from utils.bot import Bot
# ChannelIDs, RoleIDs, CategoryIDs
# owner_only, officer_only, members_only, debug_only
from utils.bot import RoleIDs, ChannelIDs
#import utils.generic as genericUtil
#import utils.time as timeUtil
#import utils.wt as wtUtil

# "utils.generic", "utils.time", "utils.wt"
__reload_deps__ = ()

old_timer_interval = relativedelta(years=1)
class RolesCog(commands.GroupCog, group_name="role"):
	def __init__(self, bot:'Bot'):
		self.bot = bot
		self.logger = logging.getLogger(__name__)
		self.logger.setLevel(bot.logLevel)
		self.logger.debug(f"{self.__class__.__name__} initialized")

	@discord.app_commands.command(name="get")
	@discord.app_commands.guild_only()
	@discord.app_commands.choices(role=[
		discord.app_commands.Choice(name="sqb ping",value=1),
		discord.app_commands.Choice(name="old timer",value=2)
	])
	async def get_role(self, interaction:discord.Interaction, role:int):
		await interaction.response.defer(thinking=True)
		if role == 1:
			pingrole = interaction.guild.get_role(self.bot.roleIDs[RoleIDs.PING])
			if pingrole in interaction.user.roles:
				await interaction.edit_original_response(content=f"You already have the role. If you wish to remove it use the `/role remove` command!")
				return
			await interaction.user.add_roles(pingrole)
			await interaction.edit_original_response(content=f"You have been given the {pingrole.mention} role.")
		elif role == 2:
			main_profile = self.bot.db.getByDID(interaction.user.id)
			if not main_profile:
				await interaction.edit_original_response(content="You aren't registered in the squadron member list.")
				return
			main_profile = min(main_profile, key=lambda u: (u.joindate is None, u.joindate))
			x_time_ago = (datetime.now(UTC) - old_timer_interval).date()
			old_timer = interaction.guild.get_role(self.bot.roleIDs[RoleIDs.OLD_TIMER])
			if main_profile.joindate is None:
				await interaction.edit_original_response(content=f"You seem to not have a join date saved in the database. Please contact <@{self.bot.yoshinoID}> about this.")
			elif interaction.user.get_role(old_timer.id) is not None:
				await interaction.edit_original_response(content="You already seem to have the role.")
			elif main_profile.joindate > x_time_ago:
				await interaction.edit_original_response(content="You haven't been in the squadron for a year yet!")
			elif main_profile.joindate <= x_time_ago:
				await interaction.user.add_roles(old_timer, reason="User is an old timer")
				await interaction.edit_original_response(content="Role given.")
				embed = discord.Embed(title="Old timer role promotion")
				embed.add_field(name="Discord user", value=interaction.user.mention)
				tmp = self.bot.get_channel(self.bot.channelIDs[ChannelIDs.SPAM])
				await tmp.send(embed=embed)

	@discord.app_commands.command(name="remove")
	@discord.app_commands.guild_only()
	@discord.app_commands.choices(role=[
		discord.app_commands.Choice(name="sqb ping", value=1)
	])
	async def rm_role(self, interaction:discord.Interaction, role:int):
		await interaction.response.defer(thinking=True, ephemeral=True)
		if role == 1:
			pingrole = interaction.guild.get_role(self.bot.roleIDs[RoleIDs.PING])
			if pingrole not in interaction.user.roles:
				await interaction.edit_original_response(content=f"You don't have the role. If you wish to get it use the `/role get` command!")
				return
			await interaction.user.remove_roles(pingrole)
			await interaction.edit_original_response(content=f"Your {pingrole.mention} role has been removed.")

async def setup(bot:'Bot'):
	await bot.add_cog(RolesCog(bot))