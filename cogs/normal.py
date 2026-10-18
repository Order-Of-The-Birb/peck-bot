if __name__ == "__main__":
	raise Exception("Start the program from the main process")
import discord, logging, re
from discord.ext import commands
from typing import TYPE_CHECKING
from datetime import datetime, UTC, time, timedelta
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
from utils.modals import ReportModal
import utils.generic as genericUtil
import utils.time as timeUtil
import shared
from modules import management

# "utils.generic", "utils.time", "utils.wt"
__reload_deps__ = ("utils.generic", "utils.time")

def toSelectList(names:list[str]) -> list[discord.SelectOption]: return [discord.SelectOption(label=name) for name in names]
class NormalCog(commands.Cog):
	def __init__(self, bot:'Bot'):
		self.bot = bot
		self.logger = logging.getLogger(__name__)
		self.logger.debug(f"{self.__class__.__name__} initialized")

	@discord.app_commands.command(description="Command to report a squadron member")
	@discord.app_commands.guild_only()
	async def report(self, interaction: discord.Interaction):
		
		await interaction.response.send_modal(ReportModal(self.bot))

	@discord.app_commands.command()
	async def info(self, interaction:discord.Interaction):
		embed = discord.Embed(title="Bot info", color=0xFF0000)
		embed.add_field(name="Ping", value=f"{round(self.bot.latency*1000, 2)} ms", inline=False)
		uptime = datetime.now(UTC)-shared.RUNNING_SINCE
		embed.add_field(name="Uptime", value=f"{uptime.days}d {uptime.seconds//60//60}h {uptime.seconds//60%60}m {uptime.seconds%60}s", inline=False)
		memstat = virtual_memory()
		embed.add_field(name="Bot RAM usage", value=bytes2human(psutilProcess().memory_info().rss))
		embed.add_field(name="System RAM usage", value=f"{bytes2human(memstat.used)}/{bytes2human(memstat.total)}", inline=False)
		embed.add_field(name="System RAM available", value=bytes2human(memstat.available), inline=False)
		embed.set_author(name="PECK bot", icon_url=shared.ICON_URL)
		await interaction.response.send_message(embed=embed)

	@discord.app_commands.command()
	async def convert_to_gif(self, interaction:discord.Interaction, image:discord.Attachment):
		await interaction.response.defer(thinking=True)
		try:
			file = await genericUtil.convertImageToGif(image)
		except ValueError as e:
			await interaction.edit_original_response(content=str(e))
			return
		await interaction.edit_original_response(content="Here you go", attachments=[file,])

	@discord.app_commands.command()
	async def ge_to_gjn(self, interaction:discord.Interaction, value:int):
		msg_content = ""
		if value % 10 != 0: # Gaijin limitation: Only sold in steps of 10
			value = round(value, -1)
			msg_content += "An invalid value was given for the value (Not divisible by 10), so the value is calculated using a rounded value\n"
		msg_content += f"{value} GE is worth {round(0.0066*value, 2)} GJN/EUR\n"
		if value < 150: # Gaijin limitation: Minimum buy value is 150 
			msg_content += "-# Due to gaijin's limitations, this amount cannot be bought\n"
		elif value > 75000: # Gaijin limitation: Maximum buy value at once is 75000
			msg_content += "-# Due to gaijin's limitations, this amount can't be bought in one purchase, so the amount cannot be calculated precisely\n"
			msg_content += f"-# This amount can be bought by purchasing {value//75000}x 75000 GE and then {value%75000} GE separately"
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
		if not (db_user := management.get(discord_id=user.id)):
			await interaction.edit_original_response(content="User not found")
			return
		await interaction.edit_original_response(content=f"User(s) found: {", ".join(f"{i.username}" for i in db_user)}")

	@group_requests.command(name="discord")
	@discord.app_commands.describe(user="The War Thunder username to search for")
	async def request_dc(self, interaction: discord.Interaction, user:str):
		"""Requests a user's ID based on the WT username in the database"""
		await interaction.response.defer(thinking=True)
		if (db_user := await management.get(username=user)) is not None:
			dcuser = interaction.guild.get_member(db_user.discord_id)
			if dcuser is None:
				await interaction.edit_original_response(content=f"User can no longer be found in the server (User ID was {db_user.discord_id})")
			else:
				await interaction.edit_original_response(content=f"User found: {dcuser.name} ({dcuser.id})")
		else:
			await interaction.edit_original_response(content="User not found")
	# endregion

	@discord.app_commands.command()
	async def deepseek_peak(self, interaction: discord.Interaction):
		"""Determines whether currently it is on- or off-peak for Deepseek:tm: API token usage"""
		peak_times = (
			( time(hour=1, tzinfo=UTC), time(hour=4, tzinfo=UTC) ),
			( time(hour=6, tzinfo=UTC), time(hour=10, tzinfo=UTC) )
		)
		rn = datetime.now(UTC)
		next_peak_start = datetime.combine(rn.date(), peak_times[0][0])

		for peak_start, peak_end in peak_times:
			if peak_start <= rn.timetz() <= peak_end:
				await interaction.response.send_message(
					content=f"We are currently in peak time\nPeak time ends {timeUtil.discord_timestamp(datetime.combine(rn.date(), peak_end), type=timeUtil.timestampTypes.RELATIVE)}", 
					ephemeral=True
				)
				return
			if rn.timetz() < peak_start and next_peak_start.timetz() < rn.timetz():
				next_peak_start = datetime.combine(rn.date(), peak_start)

		if next_peak_start.timetz() < rn.timetz():
			next_peak_start = datetime.combine((rn + timedelta(days=1)).date(), peak_times[0][0])

		await interaction.response.send_message(
			content=f"We are currently in off-peak time\nPeak time starts {timeUtil.discord_timestamp(next_peak_start, type=timeUtil.timestampTypes.RELATIVE)}", 
			ephemeral=True
		)

async def setup(bot:'Bot'):
	await bot.add_cog(NormalCog(bot))