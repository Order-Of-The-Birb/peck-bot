if __name__ == "__main__":
	raise Exception("Start the program from the main process")
import discord, logging, re
from discord.ext import commands
from typing import TYPE_CHECKING
from datetime import datetime, UTC, timedelta
from psutil import virtual_memory, Process as psutilProcess
from psutil._common import bytes2human
if __name__ == "__main__":
	from os import path
	from sys import path as sys_path
	sys_path.append(path.abspath(path.join(path.dirname(__file__), '..')))
if TYPE_CHECKING:
	from utils.bot import Bot
# ChannelIDs, RoleIDs, CategoryIDs
# owner_only, officer_only, members_only, debug_only
from utils.bot import ChannelIDs, RoleIDs
import utils.generic as genericUtil
#import utils.time as timeUtil
import utils.wt as wtUtil

# "utils.generic", "utils.time", "utils.wt"
__reload_deps__ = ("utils.wt", "utils.generic")

def toSelectList(names:list[str]) -> list[discord.SelectOption]: return [discord.SelectOption(label=name) for name in names]
class NormalCog(commands.Cog):
	def __init__(self, bot:'Bot'):
		self.bot = bot
		self.logger = logging.getLogger(__name__)
		self.logger.setLevel(bot.logLevel)
		self.logger.debug(f"{self.__class__.__name__} initialized")
	@discord.app_commands.command()
	@discord.app_commands.guild_only()
	async def apply(self, interaction: discord.Interaction):
		"""This Command is used for applying to the squadron"""
		class join_modal(discord.ui.Modal, title="Submit application"):
			username = discord.ui.Label(
				text = "War Thunder username",
				description = "Your War Thunder username",
				component = discord.ui.TextInput(
					style = discord.TextStyle.short,
					custom_id = "joinWTUsername",
					min_length = 2,
					max_length = 16,
					placeholder = "username"
				)
			)
			tz = discord.ui.Label(
				text = "Timezone", 
				description = "Please provide your timezone's UTC offset",
				component = discord.ui.Select(
					options = toSelectList([str(i) for i in range(-11, 13)]), 
					placeholder="I'd rather not provide",
					row = 1, 
					required = False,
					min_values = 1,
					max_values = 1
				)
			)
			def __init__(self, parent:'NormalCog'):
				self.parent = parent
				super().__init__()
			async def on_submit(self, interaction: discord.Interaction):
				await interaction.response.defer(thinking=True, ephemeral=True)
				await self.parent.bot.squadron.updateMembers()
				# region Username sanitation
				USERNAME_REGEX = re.compile(r"^([A-Za-z0-9_ ]{2,16})(?:@(live|psn))?$")
				username = USERNAME_REGEX.search(self.username.component.value.strip())
				if username: username = username.group(1)
				else:
					await interaction.edit_original_response(content=f"Given username is invalid. The usernames follow the following rules:\n- Between 2 and 16 characters\n- Can have latin letters, numbers\n- Can contain spaces in the middle")
					return
				# endregion
				# region User already applied/registered
				userInfo = self.parent.bot.db.getByName(username)
				if userInfo is not None:
					if userInfo.status == self.parent.bot.db.Status.MEMBER:
						if interaction.user.id != userInfo.discord_id:
							await self.parent.bot.get_channel(self.parent.bot.channelIDs[ChannelIDs.SPAM]).send(f"{interaction.user.name} ({interaction.user.id}) tried joining with the username \"{username}\", but this username is already registered as a member.")
							await interaction.edit_original_response(content="User is already registered in the squadron. Possible false name detected.")
							self.parent.logger.warning(f"User {interaction.user.name} ({interaction.user.id}) tried applying with an username already in the database")
						else:
							await interaction.edit_original_response(content="You are already registered!")
						return
					if userInfo.status == self.parent.bot.db.Status.APPLICANT:
						if userInfo.discord_id == interaction.user.id:
							await interaction.edit_original_response(content="You have already applied before! Please wait for an admin to accept you.")
						else:
							await interaction.edit_original_response(content="Someone else has already applied under that username.")
							self.parent.logger.warning(f"User '{interaction.user.name}' ({interaction.user.id}) tried applying after someone already applied with the same name ('{userInfo.username}')")
						return
				# endregion
				# region Add new user to the database
				joindate = None
				for member in self.parent.bot.squadron.members:
					if member.name == username:
						joindate = member.joindate.date()
						break
				gaijin_id = wtUtil.get_user_ids(username).get(username)
				if gaijin_id is None:
					await interaction.edit_original_response(content="You did not provide a valid War Thunder username")
					return
				try:
					self.parent.bot.db.add_user(gaijin_id=gaijin_id, username=username, discord_id=interaction.user.id, joindate=joindate, timezone=int(self.tz.component.values[0]) if len(self.tz.component.values) != 0 else None, status=self.parent.bot.db.Status.APPLICANT)
				except ValueError:
					self.parent.logger.exception("An exception occurred while adding applicant to the database")
					await interaction.edit_original_response(content="You could not be added to the database")
					return
				# endregion
				# region User already accepted
				embed = discord.Embed(color=0xFF0000, title="Application")
				if self.parent.bot.squadron.UserInSquadron(username):
					_ = self.parent.bot.db.getByName(username)
					_.status = self.parent.bot.db.Status.MEMBER
					_.push()
					try:
						embed.title = "User verified"
						guild = self.parent.bot.get_guild(self.parent.bot.peckServer)
						memberRole = guild.get_role(self.parent.bot.roleIDs[RoleIDs.MEMBER])
						await interaction.user.add_roles(memberRole)
						for roleID in self.parent.bot.commonRoles:
							commonRole = guild.get_role(roleID)
							await interaction.user.remove_roles(commonRole)
						await interaction.user.remove_roles(guild.get_role(self.parent.bot.roleIDs[RoleIDs.APPLICANT]))
						await interaction.edit_original_response(content="You have been successfully added to the database")
					except Exception:
						self.parent.logger.exception("An error occurred while giving roles to an applicant")
						await interaction.edit_original_response(content="You have been added to the database, however an error occurred while giving roles. Please contact an officer about this.")
				else:
					await interaction.edit_original_response(content="You have been successfully added to the database.")
				# endregion
				# region Logging
				try:
					channel = self.parent.bot.get_channel(self.parent.bot.channelIDs[ChannelIDs.SPAM])
					embed.set_author(name=f"{interaction.user.name} ({interaction.user.id})", icon_url=interaction.user.display_avatar.url)
					embed.add_field(name="DC Username", value=interaction.user.name)
					embed.add_field(name="Discord UID", value=interaction.user.id)
					embed.add_field(name="WT Username", value=username)
					await channel.send(embed=embed)
				except Exception:
					self.parent.logger.exception("An error occurred while trying to log user joining.")
				# endregion
			async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
				self.parent.logger.exception(f"An error occured in 'Apply'")
				if interaction.response.is_done():
					await interaction.edit_original_response(content='Oops! Something went wrong.')
				else:
					await interaction.response.send_message('Oops! Something went wrong.', ephemeral=True)
		associatedAccounts = self.bot.db.getByDID(interaction.user.id)
		if any(i.status == self.bot.db.Status.MEMBER for i in associatedAccounts):
			await interaction.response.send_message("You are already a registered member. If you wish to add an alt account, consult an officer.")
			return
		await interaction.response.send_modal(join_modal(self))

	@discord.app_commands.command(description="Command to report a squadron member")
	@discord.app_commands.guild_only()
	async def report(self, interaction: discord.Interaction):
		class ReportModal(discord.ui.Modal, title="Report user"):
			user = discord.ui.Label(
				text="War Thunder Username",
				component=discord.ui.TextInput(
					min_length=2,
					max_length=16,
					required=True,
					style=discord.TextStyle.short,
					custom_id="report_username",
					placeholder="username"
				),
				description="The War Thunder username of the player. If they are on console adding the @psn or @live tags is optional"
			)
			type = discord.ui.Label(
				text="Category",
				component=discord.ui.Select(
					min_values=1,
					max_values=1,
					options=[
						discord.SelectOption(label="Cheating", value="cheating", description="Aimbot, ESP/Wallhacks, Botted gameplay, etc."),
						discord.SelectOption(label="Toxicity", value="chat"),
						discord.SelectOption(label="Annoying", value="annoying", description="If your only problem is this user being annoying"),
						discord.SelectOption(label="Sabotage", value="sabotage", description="Teamkilling, stealing air slots, etc.")
					],
					required=True,
					custom_id="report_category",
					id=69
				),
				description="The category the user's infraction would fall under"
			)
			message = discord.ui.Label(
				text="Message",
				component=discord.ui.TextInput(
					min_length=1, 
					max_length=2048,
					custom_id="report_msg",
					style=discord.TextStyle.paragraph,
					placeholder="I would like to report...",
					required=False
				),
				description="The message you wish for us to see"
			)
			replayURL = discord.ui.Label( 
				text="Evidence replay URL",
				component=discord.ui.TextInput(
					min_length=44,
					max_length=70,
					placeholder="https://warthunder.com/en/tournament/replay/...",
					required=True,
					custom_id="evidence",
					style=discord.TextStyle.short
				)
			)
			def __init__(self, bot:'Bot'):
				self.bot = bot
				self._logger = logging.getLogger(__name__)
				super().__init__()
			async def on_submit(self, interaction: discord.Interaction):
				await interaction.response.defer(thinking=True, ephemeral=True)
				REPLAY_URL_REGEX = re.compile(r"^https://warthunder\.com/[a-z]{2}/tournament/replay/\d+$")
				url:str = self.replayURL.component.value.strip().rstrip("/")
				url = re.sub(r"/[a-z]{2}/", "/en/", url)
				report_category:discord.ui.Select = self.find_item(69)
				if not REPLAY_URL_REGEX.match(url):
					await interaction.edit_original_response(content="**Invalid replay URL format.** Please use a valid War Thunder replay link: `https://warthunder.com/en/tournament/replay/<id>`")
					return
				username:str = self.user.component.value.strip()
				report_msg:str = self.message.component.value.strip()
				if self.bot.db.getByName(username) is None:
					await interaction.edit_original_response(content="No such user exists in our database")
					return
				isInReplay = await wtUtil.userInReplay(username, url.split("/")[-1], self.bot.GaijinLogin())
				if not isInReplay:
					await interaction.edit_original_response(content=f"The match you provided a link to does not have the user '{username}' in it.")
					return
				embed = discord.Embed(title=f"Report")
				embed.set_author(name=f"{interaction.user.name} (ID: {interaction.user.id})", icon_url=interaction.user.display_avatar.url)
				embed.add_field(name="WT username", value=username, inline=False)
				if report_msg:
					embed.add_field(name="Report message", value=report_msg, inline=False)
				embed.add_field(name="Category", value=report_category.values[0])
				embed.add_field(name="Evidence URL", value=url, inline=False)
				self._logger.debug(f"Report from {interaction.user.name} ({interaction.user.id})\nWT username: {username}\nReport message: {report_msg}")
				await self.bot.get_channel(self.bot.channelIDs[ChannelIDs.SPAM]).send(embed=embed)
				await interaction.edit_original_response(content="Report submitted!")
			async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
				await interaction.edit_original_response(content='Oops! Something went wrong.')
				self._logger.exception("An error occured while reporting", exc_info=error)
		await interaction.response.send_modal(ReportModal(self.bot))

	@discord.app_commands.command()
	async def info(self, interaction:discord.Interaction):
		embed = discord.Embed(title="Bot info", color=0xFF0000)
		embed.add_field(name="Ping", value=f"{round(self.bot.latency*1000, 2)} ms", inline=False)
		uptime = datetime.now(UTC)-self.bot.runningSince
		embed.add_field(name="Uptime", value=f"{uptime.days}d {uptime.seconds//60//60}h {uptime.seconds//60%60}m {uptime.seconds%60}s", inline=False)
		memstat = virtual_memory()
		embed.add_field(name="Bot RAM usage", value=bytes2human(psutilProcess().memory_info().rss))
		embed.add_field(name="System RAM usage", value=f"{bytes2human(memstat.used)}/{bytes2human(memstat.total)}", inline=False)
		embed.set_author(name="PECK bot", icon_url=self.bot.iconURL)
		await interaction.response.send_message(embed=embed)

	@discord.app_commands.command()
	async def convert_to_gif(self, interaction:discord.Interaction, image:discord.Attachment):
		await interaction.response.defer(thinking=True)
		try:
			file = await genericUtil.convertImageToGif(image)
		except ValueError as e:
			await interaction.edit_original_response(content=e)
			return
		await interaction.edit_original_response(content="Here you go", attachments=[file,])

	@discord.app_commands.command()
	async def ge_to_gjn(self, interaction:discord.Interaction, value:int):
		inaccuracyDisclaimer = value < 150 or value > 75000 # Gaijin's limits
		invalidValueChanged = value % 10 != 0 # Gaijin limit: Increments of 10
		if invalidValueChanged: value = round(value, -1)
		msg_content = ""
		if invalidValueChanged: msg_content += "An invalid value was given for the value (Not divisible by 10), so the value is calculated using a rounded value\n"
		msg_content += f"{value} GE is worth {0.0066*value} GJN/EUR\n"
		if inaccuracyDisclaimer: msg_content += "-# Due to gaijin's limitations, we cannot make sure that the value given is the correct value\n"
		await interaction.response.send_message(msg_content)
	
	@discord.app_commands.command()
	async def top_members(self, interaction: discord.Interaction, number:int=8):
		"""Requests the top `number` highest SQB Activity people from the squadron"""
		await interaction.response.defer(thinking=True)
		await self.bot.squadron.updateMembers()
		topmembers = self.bot.squadron.SortBySQBPoints()
		if len(topmembers) == 0:
			await interaction.edit_original_response(content=f"There seems to be nobody in the squadron with any SQB points.")
			return
		if len(topmembers) > number: topmembers = topmembers[:number]
		top_10_message = f"Top {len(topmembers)} Users:\n"
		for i, user in enumerate(topmembers, 1):
			top_10_message += f"{i}. {genericUtil.demarkdownify(user.name)}: {user.sqb_rating}\n"
		await interaction.edit_original_response(content=top_10_message)
	
	# region Download Commands
	group_download = discord.app_commands.Group(name="download", description="Commands for downloading media from providers")

	@group_download.command(name="medal", description="Gives the raw .mp4 of the shared link")
	@discord.app_commands.describe(share_url="Medal share link to the clip")
	async def download_medal_clip(self, interaction:discord.Interaction, share_url:str):
		URL_REGEX = re.compile(r"https://medal.tv/games/(.*)/clips/(.*)")
		if URL_REGEX.fullmatch(share_url) is None:
			await interaction.response.send_message(content="You did not provide a valid medal.tv url.", ephemeral=True)
			return
		await interaction.response.defer(thinking=True, ephemeral=True)  
		try:
			clip = await genericUtil.medalDownload(share_url)
		except LookupError as e:
			await interaction.edit_original_response(content=f"An error occurred while downloading the clip: {e}")
			return
		await interaction.followup.send(f"Here you go.", file=clip)
	# endregion
	# region Request Commands
	group_requests = discord.app_commands.Group(name="request", description="For requesting user data from our database")

	@group_requests.command(name="warthunder")
	@discord.app_commands.describe(user="The user to search for")
	async def request_wt(self, interaction: discord.Interaction, user:discord.Member):
		"""Requests a user's War Thunder username(s) from the database"""
		await interaction.response.defer(thinking=True)
		if not (db_user := self.bot.db.getByDID(user.id)):
			await interaction.edit_original_response(content="User not found")
			return
		await interaction.edit_original_response(content=f"User(s) found: {", ".join(f"{i.username}" for i in db_user)}")

	@group_requests.command(name="discord")
	@discord.app_commands.describe(user="The War Thunder username to search for")
	async def request_dc(self, interaction: discord.Interaction, user:str):
		"""Requests a user's ID based on the WT username in the database"""
		await interaction.response.defer(thinking=True)
		if (db_user := self.bot.db.getByName(user)) is not None:
			dcuser = self.bot.get_guild(self.bot.peckServer).get_member(db_user.discord_id)
			if dcuser is None:
				await interaction.edit_original_response(content=f"User can no longer be found in the server (User ID was {db_user.discord_id})")
			else:
				await interaction.edit_original_response(content=f"User found: {dcuser.name} ({dcuser.id})")
		else:
			await interaction.edit_original_response(content="User not found")
	# endregion

async def setup(bot:'Bot'):
	await bot.add_cog(NormalCog(bot))