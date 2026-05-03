if __name__ == "__main__":
	raise Exception("Start the program from the main process")
import discord, logging
from discord.ext import commands
from pathlib import Path
from datetime import datetime, UTC, timedelta, time, date
from typing import TYPE_CHECKING
if __name__ == "__main__":
	from os import path
	from sys import path as sys_path
	sys_path.append(path.abspath(path.join(path.dirname(__file__), '..')))
if TYPE_CHECKING:
	from utils.bot import Bot
# ChannelIDs, RoleIDs, CategoryIDs
# owner_only, officer_only, members_only, debug_only
from utils.bot import members_only, officer_only, ChannelIDs
import utils.generic as genericUtil
import utils.time as timeUtil
import utils.wt as wtUtil

# "utils.generic", "utils.time", "utils.wt"
__reload_deps__ = ("utils.generic", "utils.time", "utils.wt")

class SQBCog(commands.GroupCog, group_name="sqb"):
	announcement_delay = 30
	announcements = 0
	use_sqb_ping_role:bool = False
	def __init__(self, bot:'Bot'):
		self.bot = bot
		self.logger = logging.getLogger(__name__)
		self.logger.setLevel(bot.logLevel)
		self.logger.debug(f"{self.__class__.__name__} initialized")
	@discord.app_commands.command(name="announce")
	@members_only()
	@discord.app_commands.guild_only()
	@discord.app_commands.checks.cooldown(1, 30*60)
	async def announce_sqb(self, interaction:discord.Interaction):
		"""[Member] Announces SQB by pinging members in the announcements channel"""
		await interaction.response.defer(ephemeral=True)
		voice_channel = interaction.user.voice.channel if interaction.user.voice else None
		if not timeUtil.isInTimebracket() and not self.bot.debug:
			await interaction.edit_original_response(content="Error: Outside of SQB time frame.")
			return
		if not (voice_channel is not None and voice_channel.id == self.bot.channelIDs[ChannelIDs.SQB]) and not self.bot.debug:
			await interaction.edit_original_response(content=f"You have to be in <#{self.bot.channelIDs[ChannelIDs.SQB]}> to announce SQB.")
			return
		await interaction.edit_original_response(content="Announcing SQB...")
		channel = self.bot.get_channel(self.bot.channelIDs[ChannelIDs.ANNOUNCEMENTS])
		if self.use_sqb_ping_role:
			self.announcements += 1
			role_id = 1065769588849115248
			if self.announcements >= 3:
				role_id = 919803983286128661
		else:
			role_id = 919803983286128661
		br_data = wtUtil.get_sqb_br()
		await channel.send(f"<@&{role_id}> an SQB ping was requested by {interaction.user.mention}. You can join <#{self.bot.channelIDs[ChannelIDs.SQB]}> to play SQB.\nCurrent BR:\n# {br_data[0] if br_data else "Could not find BR data"}\n\tTimeframe ends {timeUtil.discord_timestamp(timeUtil.get_sqb_timebracket()[1], timeUtil.timestampTypes.RELATIVE)}\n\n{await self.bot.random_propaganda()}")
		await interaction.edit_original_response(content="SQB announced.")
		embed = discord.Embed(title="SQB Announcement", color=0x0000FF, timestamp=datetime.now(UTC), description="A member just announced SQB")
		embed.add_field(name="Username", value=f"{interaction.user.name}")
		embed.add_field(name="User ID", value=f"{interaction.user.id}")
		embed.add_field(name="User mention", value=interaction.user.mention)
		await (self.bot.get_channel(self.bot.channelIDs[ChannelIDs.SPAM]).send(embed=embed))

	@discord.app_commands.command(name="plan")
	@members_only()
	@discord.app_commands.guild_only()
	@discord.app_commands.describe(
		date="Date in YYYY-MM-DD format (omit both date and time to use next bracket)",
		time="Time in HH:MM 24-hour UTC format",
	)
	async def plan_sqb(self, interaction:discord.Interaction, date:str|None=None, time:str|None=None):
		"""[Member] Announces an SQB session by using events"""
		await interaction.response.defer(thinking=True, ephemeral=True)
		# region Time parse
		if date is None and time is None:
			_date = datetime.now(UTC).date()
			rn = datetime.now(UTC).time()
			rn_since_midnight = rn.hour * 60 + rn.minute
			closest = None
			smallest_diff = float("inf")
			for _start, end in wtUtil.sqb_brackets:
				start_since_midnight = _start.hour*60
				diff = start_since_midnight-rn_since_midnight
				if diff >= 0 and diff < smallest_diff:
					smallest_diff = diff
					closest = (_start, end)
			if closest is None:
				closest = wtUtil.sqb_brackets[0]
			_time = closest[0]
			if _time < rn: _date += timedelta(days=1)
		else:
			if date is None or time is None:
				await interaction.edit_original_response(content="Please provide both `date` and `time`, or omit both.")
				return
			try:
				_date = datetime.strptime(date, "%Y-%m-%d").date()
			except ValueError:
				await interaction.edit_original_response(content="Invalid date format. Use `YYYY-MM-DD`.")
				return
			try:
				_time = datetime.strptime(time, "%H:%M").time()
			except ValueError:
				await interaction.edit_original_response(content="Invalid time format. Use `HH:MM` in UTC.")
				return
		planned_end_date = _date
		bracket_end_time = None
		for bracket_start, bracket_end in wtUtil.sqb_brackets:
			if bracket_start <= _time < bracket_end:
				bracket_end_time = bracket_end
				break
		if bracket_end_time is None:
			next_bracket = next((i for i in wtUtil.sqb_brackets if _time < i[0]), None)
			if next_bracket is None:
				bracket_end_time = wtUtil.sqb_brackets[0][1]
				planned_end_date = _date + timedelta(days=1)
			else:
				bracket_end_time = next_bracket[1]
		# endregion
		guild = self.bot.get_guild(self.bot.peckServer)
		planned_start = datetime.combine(_date, _time, UTC)
		planned_end = datetime.combine(planned_end_date, bracket_end_time, UTC)
		now = datetime.now(UTC)
		try:
			scheduled_events = await guild.fetch_scheduled_events()
		except discord.HTTPException:
			self.logger.exception("Could not fetch scheduled events, falling back to cache")
			scheduled_events = guild.scheduled_events
		for event in scheduled_events:
			if not event.name.lower().startswith("[sqb]"): continue
			if event.end_time is not None and event.end_time <= now: continue
			if event.description and f"({interaction.user.id})" in event.description: 
				await interaction.edit_original_response(content="You have already created an existing SQB event. Wait until that one is over to schedule another one.")
				return
			if event.end_time is None:
				if event.start_time <= planned_start:
					await interaction.edit_original_response(content=f"Another session is already scheduled for the given time. Please just apply for that one.\n{event.url}")
					return
			elif planned_start < event.end_time and event.start_time < planned_end:
				await interaction.edit_original_response(content=f"Another session is already scheduled for the given time. Please just apply for that one.\n{event.url}")
				return
		class dataCheckView(discord.ui.LayoutView):
			current_br = wtUtil.get_sqb_br(datetime.combine(_date, _time, UTC))
			_1 = discord.ui.TextDisplay("The following data have been given, and the event will be created according to them. Are these correct?")
			_2 = discord.ui.Section(
				discord.ui.TextDisplay(f"Start time: <t:{round(planned_start.timestamp())}:s>"),
				discord.ui.TextDisplay(f"End time: <t:{round(planned_end.timestamp())}:s>"),
				discord.ui.TextDisplay(f"Current BR: {current_br[0] if current_br else "Could not retrieve BR data for the given date"}"),
				accessory=discord.ui.Button(
					style=discord.ButtonStyle.green,
					label="Yes"
				)
			)
			def __init__(self, bot:'Bot'):
				self.bot = bot
				self._2.accessory.callback = self.acceptButton
				super().__init__(timeout=180)
			async def acceptButton(self, interaction:discord.Interaction):
				event = await guild.create_scheduled_event(
					name="[SQB] Scheduled session",
					description=f"Current BR: {self.current_br}\nCreated by: {interaction.user.name} ({interaction.user.id})",
					channel=guild.get_channel(self.bot.channelIDs[ChannelIDs.SQB]),
					entity_type=discord.EntityType.voice,
					privacy_level=discord.PrivacyLevel.guild_only,
					start_time=planned_start,
					end_time=planned_end
				)
				await interaction.response.send_message(f"The event can be found at the following place: {event.url}", ephemeral=True)
		await interaction.edit_original_response(view=dataCheckView(self.bot))
	@discord.app_commands.command(name="recruit")
	@officer_only()
	@discord.app_commands.guild_only()
	@discord.app_commands.default_permissions(manage_channels=True)
	@discord.app_commands.describe(username="Enter War Thunder username, who the message gets sent to",dc_user="Ping a user to send a message to")
	async def sqbrecruit(self, interaction: discord.Interaction, username:str|None=None, dc_user:discord.Member|None=None):
		"""[Officer] Recruits a given person for SQB"""
		await interaction.response.defer(thinking=True)
		if username is not None:	identifier = username
		elif dc_user is not None:	identifier = dc_user.id
		else: return await interaction.edit_original_response(content="You must give me any user identifier.")
		if isinstance(identifier, int):
			user = self.bot.db.getByDID(identifier)
			user = user[0] if user else None
		elif isinstance(identifier, str):
			user = self.bot.db.getByName(identifier)
		else:
			raise ValueError(f"Invalid type given for identifier '{type(identifier)}'")
		if user is None:
			self.logger.debug(f"Could not find user '{identifier}' in the database")
			await interaction.edit_original_response(content=f"Could not find user '{identifier}' in the database")
			return
		current_br = wtUtil.get_sqb_br()
		message = f"Hello {user.username}!\nYou have been drafted for SQB.\nThe current BR is {current_br[0] if current_br else "Could not get BR data"}\n{await self.bot.random_propaganda()}"
		dc_user2 = self.bot.get_user(user.discord_id)
		async def accept(interaction2:discord.Interaction):
			await interaction2.followup.send(f"Splendid, please join <#{self.bot.channelIDs[ChannelIDs.SQB]}> to start participating!")
			await interaction.edit_original_response(content=f"User '{interaction2.user.name}' has accepted participating.")
			return True
		async def deny(interaction2:discord.Interaction):
			await interaction2.followup.send("Understood.")
			await interaction.edit_original_response(content=f"User '{interaction2.user.name}' has denied participating this time.")
			return True
		try:
			await dc_user2.send(message, view=genericUtil.genericButtons(acceptFunc=accept, denyFunc=deny, acceptLabel="Accept Invitation", denyLabel="Deny Invitation", removeButtonsAfter=True))
			await interaction.edit_original_response(content=f"Message sent to {dc_user2.name} (War Thunder username: {user.username})")
		except discord.Forbidden:
			await interaction.edit_original_response(content=f"Could not send DM to {dc_user2.name} (War Thunder username: {user.username}).")

	@discord.app_commands.command(name="brackets")
	@officer_only()
	@discord.app_commands.default_permissions(manage_channels=True)
	@discord.app_commands.guild_only()
	async def sqb_brackets(self, interaction:discord.Interaction):
		"""[Officer] Posts the seasonal schedule for SQB"""
		await interaction.response.defer(thinking=True)
		for i in (await interaction.channel.pins()):
			if i.content.startswith("1st week:") and i.author.id == self.bot.user.id:
				await i.delete()
				self.logger.debug("Pinned message found and deleted")
				break
		await interaction.edit_original_response(content=wtUtil.get_sqb_season())
		await (await interaction.original_response()).pin(reason="Pinning SQB BR message")
		def is_me(m:discord.Message):
			return m.author == interaction.client.user
		await interaction.channel.purge(limit=1, reason="Removing pin message", check=is_me)

	@discord.app_commands.command(name="current_br")
	async def current_br(self, interaction:discord.Interaction):
		"""[Public] Posts the current active BR"""
		await interaction.response.defer()
		tmp = wtUtil.get_sqb_br()
		if not tmp:
			await interaction.edit_original_response(content=f"Could not get current BR data. Please try again later...")
			self.logger.error(f"sqb_br returned '{tmp}'")
			return
		await interaction.edit_original_response(content=f"Current BR:\n# {tmp[0]}\nCurrent BR started {timeUtil.discord_timestamp(tmp[1][0], timeUtil.timestampTypes.RELATIVE)} and ends {timeUtil.discord_timestamp(tmp[1][1], timeUtil.timestampTypes.RELATIVE)}")

async def setup(bot:'Bot'):
	await bot.add_cog(SQBCog(bot))
