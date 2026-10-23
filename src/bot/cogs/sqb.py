if __name__ == "__main__":
	raise Exception("Start the program from the main process")
import discord, logging
from random import randrange
from discord.ext import commands
from datetime import datetime, UTC, timedelta
# ChannelIDs, RoleIDs, CategoryIDs
# owner_only, officer_only, members_only, debug_only
import utils.generic as genericUtil
import utils.time as timeUtil
import utils.wt as wtUtil
import utils.management as management
import bot.client as Client
import bot.config as Config

# "utils.generic", "utils.helper", "utils.management",
# "utils.memory", "utils.network", "utils.newsAPI",
# "utils.resources", "utils.thunderapi", "utils.time", "utils.wt"
# "bot.modals", "bot.client", "bot.config"
__reload_deps__ = ("bot.client", "bot.config", "utils.generic", "utils.time", "utils.wt", "utils.management")

class SQBCog(commands.GroupCog, group_name="sqb"):
	announcement_delay = 30
	announcements = 0
	use_sqb_ping_role:bool = False
	def __init__(self):
		self.logger = logging.getLogger(__name__)
		self.logger.debug(f"{self.__class__.__name__} initialized")
	@discord.app_commands.command(name="announce")
	@discord.app_commands.guild_only()
	@Client.members_only()
	#@discord.app_commands.checks.cooldown(1, 30*60)
	async def announce_sqb(self, interaction:discord.Interaction):
		"""[Member] Announces SQB by pinging members in the announcements channel"""
		await interaction.response.defer(ephemeral=True)

		config = shared.GuildConfig.from_id(interaction.guild_id)
		if config is None:
			await interaction.edit_original_response(content="You must be in a guild to perform this")
			return

		voice_channel = interaction.user.voice.channel if interaction.user.voice else None
		if not timeUtil.isInTimebracket() and not Client.BOT.debug:
			await interaction.edit_original_response(content="Error: Outside of SQB time frame.")
			return
		if not (voice_channel is not None and voice_channel.id == Client.BOT.channelIDs[ChannelIDs.SQB]) and not Client.BOT.debug:
			await interaction.edit_original_response(content=f"You have to be in <#{Client.BOT.channelIDs[ChannelIDs.SQB]}> to announce SQB.")
			return
		await interaction.edit_original_response(content="Announcing SQB...")
		pingUser = interaction.user
		if interaction.user.id == 364119745571848192 or interaction.user.id == 709449854371364895: # Alex or my Alt
			postAsFraud:bool = False
			async def acceptFunc(interaction2:discord.Interaction):
				nonlocal postAsFraud
				postAsFraud = True
				await interaction2.edit_original_response(content="Posting as eevee")
				return True
			async def denyFunc(interaction2:discord.Interaction):
				nonlocal postAsFraud
				postAsFraud = False
				await interaction2.edit_original_response(content="Posting as self")
				return True
			view = genericUtil.genericButtons(acceptFunc=acceptFunc, denyFunc=denyFunc, acceptLabel="Post as eevee", denyLabel="Post as self", removeButtonsAfter=True, timeout=2*60)
			await interaction.edit_original_response(content="Announcing SQB...\n\nYou have the option to post as eevee or as yourself. You have 2 minutes to make your choice.\nIf you don't make a choice, it will default to posting as yourself.", view=view)
			await view.wait()
			if postAsFraud is None:
				await interaction.edit_original_response(content="No option selected, posting as self", ephemeral=True, view=None)
			elif postAsFraud:
				pingUser = Client.BOT.get_user(311555617032765451 if not Client.BOT.debug else 332030423913725953) # eevee
		channel = Client.BOT.get_channel(Client.BOT.channelIDs[ChannelIDs.ANNOUNCEMENTS])
		self.announcements += 1
		if self.use_sqb_ping_role and self.announcements >= 3:
			role_id = 1065769588849115248
		else:
			role_id = 919803983286128661
		role = Client.BOT.get_guild(Client.BOT.peckServer).get_role(role_id)
		sqbChannel = Client.BOT.get_channel(Client.BOT.channelIDs[ChannelIDs.SQB])
		await channel.send(f"{role.mention} an SQB ping was requested by {pingUser.mention}. You can join {sqbChannel.mention} to play SQB.\nCurrent BR:\n# {br_data.br if (br_data := wtUtil.get_sqb_br()) else "Could not find BR data"}\n\tTimeframe ends {timeUtil.discord_timestamp(timeUtil.get_sqb_timebracket()[1], timeUtil.timestampTypes.RELATIVE)}\n\n{await Client.BOT.random_propaganda()}")
		await interaction.edit_original_response(content="SQB announced.")
		embed = discord.Embed(title="SQB Announcement", color=0x0000FF, timestamp=datetime.now(UTC), description="A member just announced SQB")
		embed.add_field(name="Username", value=f"{interaction.user.name}")
		embed.add_field(name="User ID", value=f"{interaction.user.id}")
		embed.add_field(name="User mention", value=interaction.user.mention)
		if pingUser != interaction.user:
			embed.add_field(name="Pinged as", value=f"{pingUser.name} ({pingUser.id})")
		await (Client.BOT.get_channel(Client.BOT.channelIDs[ChannelIDs.SPAM]).send(embed=embed))

	@discord.app_commands.command(name="plan") # Removed temporarily, while we implement a better solution
	@discord.app_commands.guild_only()
	@Client.members_only()
	@Client.debug_only()
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
		guild = Client.BOT.get_guild(Client.BOT.peckServer)
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
		await interaction.edit_original_response(view=dataCheckView(Client.BOT))
	@discord.app_commands.command(name="recruit")
	@admin_only()
	@guild_only()
	@discord.app_commands.default_permissions(manage_channels=True)
	@discord.app_commands.describe(username="Enter War Thunder username, who the message gets sent to",dc_user="Ping a user to send a message to")
	async def sqbrecruit(self, interaction: discord.Interaction, username:str|None=None, dc_user:discord.Member|None=None):
		"""[Officer] Recruits a given person for SQB"""
		await interaction.response.defer(thinking=True)
		if username is not None:	identifier = username
		elif dc_user is not None:	identifier = dc_user.id
		else: return await interaction.edit_original_response(content="You must give me any user identifier.")
		if isinstance(identifier, int):
			user = await management.get(discord_id=identifier)
			user = user[0] if user else None
		elif isinstance(identifier, str):
			user = await management.get(username=identifier)
		else:
			raise ValueError(f"Invalid type given for identifier '{type(identifier)}'")
		if user is None:
			self.logger.debug(f"Could not find user '{identifier}' in the database")
			await interaction.edit_original_response(content=f"Could not find user '{identifier}' in the database")
			return
		current_br = wtUtil.get_sqb_br()
		message = f"Hello {user.username}!\nYou have been drafted for SQB.\nThe current BR is {current_br.br if current_br else "Could not get BR data"}\n{await genericUtil.random_propaganda(interaction.guild_id)}"
		dc_user2 = Client.BOT.get_user(user.discord_id)
		async def accept(interaction2:discord.Interaction):
			await interaction2.followup.send(f"Splendid, please join <#{Client.BOT.channelIDs[ChannelIDs.SQB]}> to start participating!")
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
	@guild_only()
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
		sqbSeason = wtUtil.get_sqb_season()
		messageContent = f"Seasonal schedule for SQB:\nSchedule from {sqbSeason[0].start.strftime('%Y-%m-%d')} to {sqbSeason[-1].end.strftime('%Y-%m-%d')}\n\n"
		for bracket in sqbSeason:
			messageContent += f"{bracket.name}: BR {bracket.br}\n\t{timeUtil.discord_timestamp(bracket.start, timeUtil.timestampTypes.SHORT_DATE)} ({timeUtil.discord_timestamp(bracket.start, timeUtil.timestampTypes.RELATIVE)}) - {timeUtil.discord_timestamp(bracket.end, timeUtil.timestampTypes.SHORT_DATE)} ({timeUtil.discord_timestamp(bracket.end, timeUtil.timestampTypes.RELATIVE)})\n\n"
		await interaction.edit_original_response(content=messageContent)
		if interaction.user.guild_permissions.pin_messages and pin:
			await (await interaction.original_response()).pin(reason="Pinning SQB BR message")
			await interaction.channel.purge(limit=1, reason="Removing pin message", check=lambda m: m.author == interaction.client.user)
		elif not interaction.user.guild_permissions.pin_messages and pin:
			await interaction.followup.send("You don't have permissions to pin messages, the message will be posted without pinning.", ephemeral=True)

	@discord.app_commands.command(name="current_br")
	async def current_br(self, interaction:discord.Interaction):
		"""[Public] Posts the current active BR"""
		await interaction.response.defer()
		brackets = wtUtil.get_sqb_season()
		if not brackets:
			await interaction.edit_original_response(content=f"Could not get current BR data. Please try again later...")
			return
		for ind, bracket in enumerate(brackets):
			if bracket.start <= datetime.now(UTC) < bracket.end:
				break
		else:
			await interaction.edit_original_response(content=f"Could not find the current BR data. Please try again later...")
			return
		await interaction.edit_original_response(content=f"Current BR:\n# {brackets[ind].br}\nCurrent BR started {timeUtil.discord_timestamp(brackets[ind].start, timeUtil.timestampTypes.RELATIVE)} and ends {timeUtil.discord_timestamp(brackets[ind].end, timeUtil.timestampTypes.RELATIVE)}{f" (After: {brackets[ind+1].br})" if ind+1 < len(brackets) else ''}")

	@staticmethod
	async def random_propaganda(guild:int) -> str:
		"""Selects a random propaganda post and returns with its URL"""
		config = Config.get(guild)
		if config is None:
			return
		propaganda_ch = shared.BOT.get_channel(config.channels[shared.ChannelIDs.PROPAGANDA])
		selected_url = None
		attachment_count = 0
		async for message in propaganda_ch.history(limit=None):
			for attachment in message.attachments:
				attachment_count += 1
				# Each attachment has the same chance without retaining the history.
				if randrange(attachment_count) == 0:
					selected_url = attachment.url
		if selected_url is None:
			raise LookupError("No propaganda posts found")
		return selected_url

async def setup():
	await Client.BOT.add_cog(SQBCog())
