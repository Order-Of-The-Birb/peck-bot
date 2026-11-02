import logging
from datetime import UTC, datetime

import discord
from dateutil.relativedelta import relativedelta
from discord.ext import commands

import bot.client as Client
import bot.config as Config

old_timer_interval = relativedelta(years=1)
class RolesCog(commands.GroupCog, group_name="role"):
	def __init__(self):
		self.logger = logging.getLogger(__name__)
		self.logger.debug(f"{self.__class__.__name__} initialized")

	async def interaction_check(self, interaction: Client.Interaction):
		if isinstance(interaction.channel, discord.DMChannel):
			await interaction.response.send_message("This command can only be run in servers.")
			return False
		return True

	@discord.app_commands.command(name="get")
	@Client.guild_only()
	@discord.app_commands.choices(role=[
		discord.app_commands.Choice(name="sqb ping",value=1),
		discord.app_commands.Choice(name="old timer",value=2)
	])
	async def get_role(self, interaction:Client.Interaction, role:int):
		await interaction.response.defer(thinking=True)
		config =await Config.get(interaction.guild_id)
		if config is None:
			await interaction.edit_original_response(content="This server is not yet configured")
			return
		if role in [2]:
			management = config.management
			if management is None:
				await interaction.edit_original_response(content="This server's management token is not yet configured.")
				return

		if role == 1:
			pingrole = config.get(Config.Roles.PING)
			if pingrole in interaction.user.roles:
				await interaction.edit_original_response(content="You already have the role. If you wish to remove it use the `/role remove` command!")
				return
			await interaction.user.add_roles(pingrole)
			await interaction.edit_original_response(content=f"You have been given the {pingrole.mention} role.")
		elif role == 2:
			main_profile = await management.get(discord_id=interaction.user.id)
			if not main_profile:
				await interaction.edit_original_response(content="You aren't registered in the squadron member list.")
				return
			main_profile = min(main_profile, key=lambda u: (u.joined_at is None, u.joined_at))
			x_time_ago = (datetime.now(UTC) - old_timer_interval).date()
			old_timer = config.get(Config.Roles.OLD_TIMER)
			if main_profile.joined_at is None:
				await interaction.edit_original_response(content="You seem to not have a join date saved in the database. Please contact an admin about this.")
			elif interaction.user.get_role(old_timer.id) is not None:
				await interaction.edit_original_response(content="You already seem to have the role.")
			elif main_profile.joined_at > x_time_ago:
				await interaction.edit_original_response(content="You haven't been in the squadron for a year yet!")
			elif main_profile.joined_at <= x_time_ago:
				await interaction.user.add_roles(old_timer, reason="User is an old timer")
				await interaction.edit_original_response(content="Role given.")
				embed = discord.Embed(title="Old timer role promotion")
				embed.add_field(name="Discord user", value=interaction.user.mention)
				tmp = config.get(Config.Channels.LOGS)
				await tmp.send(embed=embed)

	@discord.app_commands.command(name="remove")
	@Client.guild_only()
	@discord.app_commands.choices(role=[
		discord.app_commands.Choice(name="sqb ping", value=1)
	])
	async def rm_role(self, interaction:Client.Interaction, role:int):
		await interaction.response.defer(thinking=True, ephemeral=True)
		if role == 1:
			pingrole = interaction.extras["config"].get(Config.Roles.PING)
			if pingrole not in interaction.user.roles:
				await interaction.edit_original_response(content="You don't have the role. If you wish to get it use the `/role get` command!")
				return
			await interaction.user.remove_roles(pingrole)
			await interaction.edit_original_response(content=f"Your {pingrole.mention} role has been removed.")

async def setup(bot: Client._Bot):
	await bot.add_cog(RolesCog())
