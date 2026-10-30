import logging
from datetime import UTC, datetime, time, timedelta

import discord
from discord.ext import commands, tasks

import bot.client as Client
import bot.config as Config
import bot.modals as Modals
import utils.thunderapi as ThunderAPI

# ChannelIDs, RoleIDs, CategoryIDs
# owner_only, officer_only, members_only, debug_only
import utils.time as timeUtil

# "utils.generic", "utils.helper",
# "utils.memory", "utils.network", "utils.newsAPI",
# "utils.resources", "utils.thunderapi", "utils.time"
# "bot.modals", "bot.client", "bot.config"
__reload_deps__ = ("bot.client", "bot.config", "bot.modals", "utils.time")

class SQBCog(commands.GroupCog, group_name="sqb"):
	posting_task: tasks.Loop
	def __init__(self):
		self.asked_users = {}
		self.logger = logging.getLogger(__name__)
		self.logger.debug(f"{self.__class__.__name__} initialized")

	async def interaction_check(self, interaction: discord.Interaction):
		if isinstance(interaction.channel, discord.DMChannel):
			await interaction.response.send_message("This command can only be run in servers.")
			return False

		config =await Config.get(interaction.guild_id)
		if config is None:
			await interaction.response.send_message(content="This server is not yet configured.")
			return False

		member_role =config.get(Config.Roles.MEMBER)
		return member_role in interaction.user.roles

	asked_users: dict[int, dict[int, datetime]] # guild: {userid: asked_at}
	@discord.app_commands.command(name="recruit")
	@Client.admin_only()
	@discord.app_commands.guild_only()
	@discord.app_commands.default_permissions(manage_channels=True)
	@discord.app_commands.describe(username="Enter War Thunder username, who the message gets sent to",dc_user="Ping a user to send a message to")
	async def sqbrecruit(self, interaction: discord.Interaction, username:str|None=None, dc_user:discord.Member|None=None):
		"""Recruits a given person for SQB"""
		await interaction.response.defer(thinking=True)
		self.asked_users = {k:{key:value for key, value in v.items() if value < (datetime.now(UTC) - timedelta(minutes=30))} for k, v in self.asked_users.items()}
		if interaction.user.id in self.asked_users.get(interaction.guild_id, {}):
			await interaction.edit_original_response(content="This user recently rejected recruitment. No message was sent.")

		config =await Config.get(interaction.guild_id)
		if config is None:
			await interaction.edit_original_response(content="This server is not configured.")
			return
		management = config.management
		if management is None:
			await interaction.edit_original_response(content="This server's management token is not yet configured.")
			return

		if username is not None:
			identifier = username
		elif dc_user is not None:
			identifier = dc_user.id
		else:
			await interaction.edit_original_response(content="You must give me any user identifier.")
			return
		if isinstance(identifier, int):
			user = await management.get(discord_id=identifier)
			user = user[0] if user else None
		elif isinstance(identifier, str):
			user = await management.get(username=identifier)
		else:
			raise TypeError(f"Invalid type given for identifier '{type(identifier)}'")
		if user is None:
			self.logger.debug(f"Could not find user '{identifier}' in the database")
			await interaction.edit_original_response(content=f"Could not find user '{identifier}' in the database")
			return
		current_br = await ThunderAPI.clan.current_bracket()
		message = f"Hello {user.username}!\nYou have been drafted for SQB.\nThe current BR is {current_br.bracket.br}\n{await config.random_propaganda(interaction.guild_id)}"
		dc_user2 = Client.BOT.get_user(user.discord_id)
		async def accept(interaction2:discord.Interaction):
			await interaction2.followup.send(f"Splendid, please join <#{config.get(Config.Channels.SQB)}> to start participating!")
			await interaction.followup.send(content=f"User '{interaction2.user.name}' has accepted participating.")
			return True
		async def deny(interaction2:discord.Interaction):
			await interaction2.followup.send("Understood.")
			await interaction.followup.send(content=f"User '{interaction2.user.name}' has denied participating this time.")
			self.asked_users.setdefault(interaction.guild_id, {})
			self.asked_users[interaction.guild_id][interaction2.user.id] = datetime.now(UTC)
			return True
		try:
			await dc_user2.send(message, view=Modals.genericButtons(acceptFunc=accept, denyFunc=deny, acceptLabel="Accept Invitation", denyLabel="Deny Invitation", removeButtonsAfter=True))
			await interaction.edit_original_response(content=f"Message sent to {dc_user2.name} (War Thunder username: {user.username})")
		except discord.Forbidden:
			await interaction.edit_original_response(content=f"Could not send DM to {dc_user2.name} (War Thunder username: {user.username}).")

	@discord.app_commands.command(name="brackets")
	@discord.app_commands.guild_only()
	async def sqb_brackets(self, interaction:discord.Interaction, pin:bool=False):
		"""Posts the seasonal schedule for SQB"""
		await interaction.response.defer(thinking=True)
		if interaction.user.guild_permissions.pin_messages and pin:
			for i in (await interaction.channel.pins(limit=None)):
				if i.content.startswith("Seasonal schedule for SQB:") and i.author.id == Client.BOT.user.id:
					await i.delete()
					self.logger.debug("Pinned message found and deleted")
					break
		elif (not interaction.user.guild_permissions.pin_messages and pin):
			await interaction.edit_original_response(content="You do not have the permission to pin messages")
			return
		sqbSeason = await ThunderAPI.clan.sqb_brackets()
		messageContent = f"# Seasonal schedule for SQB:\nSchedule from {sqbSeason[0].start.strftime('%Y-%m-%d')} to {sqbSeason[-1].end.strftime('%Y-%m-%d')}\n\n"
		i = 1
		for bracket in sqbSeason:
			messageContent += f"## Bracket {i}\n- BR: **{bracket.br:.1f}**\n- Start: {timeUtil.discord_timestamp(bracket.start, timeUtil.timestampTypes.SHORT_DATE)} ({timeUtil.discord_timestamp(bracket.start, timeUtil.timestampTypes.RELATIVE)})\n- End: {timeUtil.discord_timestamp(bracket.end, timeUtil.timestampTypes.SHORT_DATE)} ({timeUtil.discord_timestamp(bracket.end, timeUtil.timestampTypes.RELATIVE)})\n\n"
			i += 1
		await interaction.edit_original_response(content=messageContent)
		if interaction.user.guild_permissions.pin_messages and pin:
			await (await interaction.original_response()).pin(reason="Pinning SQB BR message")
			await interaction.channel.purge(limit=1, reason="Removing pin message", check=lambda m: m.author == interaction.client.user)
		elif not interaction.user.guild_permissions.pin_messages and pin:
			await interaction.followup.send("You don't have permissions to pin messages, therefore the message wasn't pinned.", ephemeral=True)

	@discord.app_commands.command(name="current_br")
	async def current_br(self, interaction:discord.Interaction):
		"""Posts the current active BR"""
		await interaction.response.defer(thinking=True, ephemeral=True)
		bracket = await ThunderAPI.clan.current_bracket()
		if not bracket:
			await interaction.edit_original_response(content="Could not get current BR data. Please try again later.")
			return
		await interaction.edit_original_response(content=f"Current BR:\n# {bracket.bracket.br:.1f}\nCurrent bracket started {timeUtil.discord_timestamp(bracket.bracket.start, timeUtil.timestampTypes.RELATIVE)} and ends {timeUtil.discord_timestamp(bracket.bracket.end, timeUtil.timestampTypes.RELATIVE)}")

	#region Tasks
	@tasks.loop(
		time=(
			time(hour=timeUtil.sqb_brackets[0][1].hour, minute=30, tzinfo=UTC),
			time(hour=timeUtil.sqb_brackets[1][1].hour, minute=30, tzinfo=UTC)
		) # 30 minute delay to account for last-second matches
	)
	async def sqb_post(self):
		self.logger.debug("Running sqb_post")
		await Client.BOT.wait_until_ready()
		async for guild in Config.guilds():
			self.pings_cnt = 0
			data = await ThunderAPI.clan.leaderboardPos(guild.management.squadron_id)
			if data is None:
				return
			embed = discord.Embed(title=f"SQB Stats of {data.tag} {data.name}", color=0xFF0000)
			embed.add_field(name="Leaderboard ranking", value=data.pos)
			embed.add_field(name="Squadron rating", value=data.stats.rating)
			embed.add_field(name="Battles", value=data.stats.battles, inline=False)
			embed.add_field(name="Ground kills", value=data.stats.ground_kills)
			embed.add_field(name="Air kills", value=data.stats.air_kills)
			embed.add_field(name="Deaths", value=data.stats.deaths)
			embed.set_footer(text=f"{datetime.now(UTC).strftime("%Y.%m.%d")}", icon_url=Client.PECK_SERVER_ICON)
			ch = guild.get(Config.Channels.SCORE)
			if ch is None:
				continue
			await ch.send(embed=embed)

	async def cog_load(self):
		self.posting_task = self.sqb_post.start()
		return await super().cog_load()
	async def cog_unload(self):
		self.posting_task.cancel()
		await self.posting_task
		return await super().cog_unload()
	#endregion

async def setup(bot: Client._Bot):
	 await bot.add_cog(SQBCog())
