if __name__ == "__main__":
	raise Exception("Start the program from the main process")
import logging, discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta, UTC, time
from typing import TYPE_CHECKING
if TYPE_CHECKING:
	from utils.bot import Bot
# ChannelIDs, RoleIDs, CategoryIDs
# owner_only, officer_only, members_only, debug_only
from utils.bot import ChannelIDs, RoleIDs, debug_only
#import utils.generic as genericUtil
import utils.time as timeUtil
import utils.wt as wtUtil

# "utils.generic", "utils.time", "utils.wt"
__reload_deps__ = ("utils.wt", "utils.time")

vc_check_delay = 30
class Tasks(commands.Cog):
	def __init__(self, bot:'Bot'):
		self.bot = bot
		self.logger = logging.getLogger(__name__)
		self.logger.setLevel(bot.logLevel)
		self.lastPing = datetime.now(UTC)-timedelta(hours=1)
		self.bot.squadVC.checkDelay = vc_check_delay
		autostartFunctions:tuple[tasks.Loop] = (
			self.planner_check_loop,
			self.vc_check_user,
			self.sqb_post,
			self.ping_users_task
		)
		for func in autostartFunctions:
			_ = func.start()
		self.logger.debug(f"{self.__class__.__name__} initialized")
	@commands.Cog.listener()
	async def on_error(self, ctx, error: Exception) -> None:
		self.logger.error(f"An error occured in a task", exc_info=True, stacklevel=2)
	
	pings_cnt:int = 0
	@tasks.loop(seconds=30)
	async def planner_check_loop(self):
		self.logger.debug("Running planner_check_loop")
		await self.bot.wait_until_ready()
		guild = self.bot.get_guild(self.bot.peckServer)
		sqb_vc = guild.get_channel(self.bot.channelIDs[ChannelIDs.SQB])
		currently_sqb_event = any(i.start_time <= datetime.now(UTC) and ((i.end_time and datetime.now(UTC) < i.end_time) or (not i.end_time)) for i in guild.scheduled_events if i.name.lower().startswith("[sqb]"))
		if not (currently_sqb_event): return
		if len(sqb_vc.members) >= 8: return
		elif len(sqb_vc.members) >= 6: _ = timedelta(minutes=15 if not self.bot.debug else 1)
		else: _ = timedelta(minutes=30 if not self.bot.debug else 3)
		if (self.lastPing < (datetime.now(UTC) - _)):
			self.logger.debug("Sending SQB reminder ghost ping")
			announcements = guild.get_channel(self.bot.channelIDs[ChannelIDs.ANNOUNCEMENTS])
			role = guild.get_role(self.bot.roleIDs[RoleIDs.MEMBER])
			if self.pings_cnt < 3:
				role = guild.get_role(self.bot.roleIDs[RoleIDs.PING])
			await announcements.send(content=f"{role.mention} {8-len(sqb_vc.members)} needed", delete_after=0.1)
			self.pings_cnt += 1
			self.lastPing = datetime.now(UTC)

	@tasks.loop(minutes=vc_check_delay)
	async def vc_check_user(self):
		self.logger.debug("Running vc_check_user")
		await self.bot.wait_until_ready()
		if len(self.bot.squadVC.channels) == 0:
			return
		_30min_ago = (datetime.now(UTC)-timedelta(minutes=vc_check_delay)).timestamp()
		for channel in list(self.bot.squadVC.channels):
			vc = self.bot.get_channel(channel._id)
			if not vc:
				raise ValueError(f"Error fetching voice channel {vc} (id: {channel._id})")
			if len(vc.members) == 0 and channel.last_seen_person_time <= _30min_ago:
				await vc.delete(reason=f"Autocreated channel has been empty for {vc_check_delay} minutes")
				self.bot.squadVC.channels.remove(channel)
			elif len(vc.members) != 0:
				channel.last_seen_person_time=datetime.now(UTC).timestamp()
		self.logger.debug("VC check complete")
	
	@tasks.loop(time=(time(hour=wtUtil.sqb_brackets[0][1].hour, minute=30, tzinfo=UTC), time(hour=wtUtil.sqb_brackets[1][1].hour, minute=30, tzinfo=UTC))) # 30 minute delay to account for last-second matches
	async def sqb_post(self):
		self.logger.debug("Running sqb_post")
		await self.bot.wait_until_ready()
		self.pings_cnt = 0
		data = wtUtil.SQBData.fetch_data()
		if data is None: return
		embed = discord.Embed(title=f"SQB Stats of {data.tag} {data.name}", color=0xFF0000)
		embed.add_field(name="Leaderboard ranking", value=data.pos+1)
		embed.add_field(name="Squadron rating", value=data.astat.dr_era5)
		embed.add_field(name="Battles", value=data.astat.battles, inline=False)
		embed.add_field(name="Ground kills", value=data.astat.gkills)
		embed.add_field(name="Air kills", value=data.astat.akills)
		embed.add_field(name="Deaths", value=data.astat.deaths)
		embed.set_footer(text=f"{datetime.now(UTC).strftime("%Y.%m.%d")}", icon_url=self.bot.iconURL)
		ch = self.bot.get_channel(self.bot.channelIDs[ChannelIDs.SCORE])
		await ch.send(embed=embed)
	
	@tasks.loop(time=time(hour=11, minute=0, second=0, tzinfo=UTC))
	async def ping_users_task(self):
		self.logger.debug("Running ping_users_task")
		peckServer = self.bot.get_guild(self.bot.peckServer)
		today = datetime.now(UTC)
		for event in peckServer.scheduled_events:
			if event.start_time > today: continue
			if not event.name.lower().startswith("[event]"): continue
			days_since_start = (today-event.start_time+timedelta(seconds=30)).days 
			if days_since_start % 2 != 0: continue
			blocked_dms_users:list[int] = []
			async for user in event.users():
				try:
					await user.send(f"{event.name}: A new stage ({days_since_start//2+1}) has started!", delete_after=2*24*60*60) # 2 days
				except discord.HTTPException:
					blocked_dms_users.append(user.id)
				except Exception:
					self.logger.exception(f"Unexpected error occurred while trying to DM user {user.name} ({user.id})")
					blocked_dms_users.append(user.id)
			if blocked_dms_users:
				await (self.bot.get_channel(self.bot.channelIDs[ChannelIDs.ANNOUNCEMENTS])).send(f"{event.name}[\u200B]({event.url}): A new stage ({days_since_start//2+1}) has started!\nThe following users could not be pinged through DMs, and are interested\n\n{", ".join(f"<@{i}>" for i in blocked_dms_users)}", delete_after=2*24*60*60) # 2 days

	@discord.app_commands.command()
	@debug_only()
	async def test_task(self, interaction:discord.Interaction):
		await interaction.response.send_message("Trying to run task...", ephemeral=True)
		await self.ping_users_task()
		await interaction.edit_original_response(content="Task ran successfully")

async def setup(bot:'Bot'):
	await bot.add_cog(Tasks(bot))