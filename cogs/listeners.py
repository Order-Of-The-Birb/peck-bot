if __name__ == "__main__":
	raise Exception("Start the program from the main process")
import discord, logging, re, aiohttp, asyncio
from discord.ext import commands
from datetime import datetime, timedelta, UTC
from enum import IntEnum
from typing import TYPE_CHECKING
if TYPE_CHECKING:
	from modules.newsAPI import NewsAPI
	from utils.bot import Bot
# ChannelIDs, RoleIDs, CategoryIDs
# owner_only, officer_only, members_only, debug_only
from utils.bot import ChannelIDs, RoleIDs
import utils.generic as genericUtil
import utils.time as timeUtil
#import utils.wt as wtUtil

# "utils.generic", "utils.time", "utils.wt"
__reload_deps__ = ("utils.generic", "utils.time")

sqb_member_last_seen = datetime.now(UTC)-timedelta(minutes=30)

class Listeners(commands.Cog):
	def __init__(self, bot:'Bot'):
		self.bot = bot
		self.logger = logging.getLogger(__name__)
		self.logger.setLevel(bot.logLevel)
		self.last_disconnect: datetime | None = None
		self.logger.debug(f"{self.__class__.__name__} initialized")
	# region DEFAULT LISTENERS
	# region Bot
	@commands.Cog.listener()
	async def on_disconnect(self):
		self.last_disconnect = datetime.now(UTC)
		self.logger.debug(f"Bot disconnected as of {self.last_disconnect.isoformat()}")

	@commands.Cog.listener()
	async def on_connect(self):
		activity = discord.Game("SQB with PECK")
		await self.bot.change_presence(activity=activity,status=discord.Status.do_not_disturb)
		now = datetime.now(UTC)
		if self.last_disconnect is not None:
			delta = now - self.last_disconnect
			if delta > timedelta(minutes=5):
				self.logger.warning(f"Bot reconnected after {delta.total_seconds():.1f}s ")
			else:
				self.logger.debug(f"Bot reconnected after {delta.total_seconds():.1f}s")
		else:
			self.logger.debug(f"Bot connected at {now.isoformat()}")

	@commands.Cog.listener()
	async def on_error(self, event:str, *args, **kwargs):
		self.logger.error(f"An error occurred in '{event}'", exc_info=True)
		# If the event had a message, reply there
		if args and hasattr(args[0], "channel"):
			try:
				await args[0].channel.send("An unexpected error occurred.")
			except Exception:
				pass

	@commands.Cog.listener()
	async def on_ready(self):
		await self.bot.change_presence(activity=discord.Game("SQB with PECK"), status=discord.Status.online)

	@commands.Cog.listener()
	async def on_resumed(self):
		self.logger.debug("Bot resumed session")
	# endregion
	# region Member
	@commands.Cog.listener()
	async def on_member_remove(self, member:discord.Member):
		user = self.bot.db.getByDID(member.id)
		if user:
			user.sort(key=lambda x: x.joindate)
			channel = self.bot.get_channel(self.bot.channelIDs[ChannelIDs.LOGS])
			embed = discord.Embed(title="User left", description="A Squadron member left the server!", color=0xb7a287)
			embed.add_field(name="Discord name", value=f"{member.name}", inline=False)
			embed.add_field(name="UID", value=f"{member.id}", inline=False)
			embed.add_field(name="WT username", value=f"{genericUtil.demarkdownify(user[0].username)}", inline=False)
			embed.add_field(name="Length of stay", value=f"{member.joined_at.strftime("%Y.%m.%d")}-{datetime.now(UTC).strftime("%Y.%m.%d")}")
			await channel.send(embed=embed)
			await self.bot.squadron.updateMembers()
			for user in user:
				user.status = self.bot.db.Status.EX_MEMBER
				if self.bot.squadron.getMember(user.username) is None:
					user.leave_info = self.bot.db.LeaveInfo.LEFT
				else:
					user.leave_info = self.bot.db.LeaveInfo.SERVER
				user.push()
	# endregion
	# region Message
	trevortimes:int = 0
	@commands.Cog.listener()
	async def on_message(self, message:discord.Message):
		if message.author.id in self.bot.botIDs: return
		if isinstance(message.channel, discord.DMChannel):
			embed = discord.Embed(title=f"DM sent to PECK bot")
			embed.add_field(name="", value=message.content, inline=True)
			embed.set_footer(text=f"{message.author.name} ({message.author.id})")
			await self.bot.get_channel(self.bot.channelIDs[ChannelIDs.SPAM]).send(embed=embed)
		elif "clip" in message.content.lower():
			temp = self.bot.get_guild(self.bot.peckServer)
			if temp is None:
				return self.logger.error("get_guild returned 'None'")
			temp = temp.categories
			CLIPS_CATEGORY = next((c for c in temp if c.name == "user-clips"), None)
			subjects = CLIPS_CATEGORY.text_channels
			subject = next((
				s for s in subjects
				if (
					s.name in message.content.lower()
					or (
						s.topic
						and any(i in message.content.lower() for i in s.topic.split("\n"))
					)
				)
			), None)
			if subject is None:
				return
			subject_clips_links:list[discord.Attachment] = []
			async for _message in subject.history(limit=None, oldest_first=True):
				subject_clips_links.extend(_message.attachments)
			if (expire_time := self.bot.timeouts["clip"].getExpireTime(message.author.id)) and self.bot.timeouts["clip"].isTimedOut(message.author.id):
				await message.reply(f"You are under cooldown. It will expire {timeUtil.discord_timestamp(expire_time, "R")}", delete_after=5)
				return
			else:
				self.bot.timeouts["clip"].add(message.author.id)
			if len(subject_clips_links) > 10:
				for num, i in enumerate(range(0, len(subject_clips_links), 10)):
					await message.reply(f"Part {num+1}:\n{"\n".join([i.url for i in subject_clips_links[i-10:i]])}", mention_author=False)
			else:
				await message.reply(f"Here you go\n{"\n".join([i.url for i in subject_clips_links])}", mention_author=False)
			return
		elif any(i in message.content.lower() for i in ["updoot", "downdoot", "upvote", "downvote"]):
			updoot_msg = message.reference if message.reference else message
			await updoot_msg.add_reaction(self.bot.get_emoji(1277999470038220902))
			await asyncio.sleep(0.2)
			await updoot_msg.add_reaction(self.bot.get_emoji(1277999500262244362))
		elif (match := re.match(r"peckbot[,:\s]+(.*)", message.content, flags=re.IGNORECASE)) is not None:
			prompt:str = match.group(1)
			if not prompt:
				await message.reply(f"You need to provide a prompt if you want to ask Peckbot something.", delete_after=5)
				return
			if self.bot.timeouts["ai"].isTimedOut(message.author.id):
				await message.reply(f"You are under cooldown. It will expire {timeUtil.discord_timestamp(self.bot.timeouts["ai"].getOldest(message.author.id)+timedelta(minutes=5), "R")}", delete_after=5)
				return
			else:
				self.bot.timeouts["ai"].add(message.author.id)
			async with aiohttp.ClientSession(base_url="http://127.0.0.1") as session:
				try:
					payload = {
						"model": "gemma4",
						"messages": [{"role": "user", "content": prompt}],
						"temperature": 0.7,
					}
					async with session.post(
						"/v1/chat/completions",
						json=payload,
						timeout=aiohttp.ClientTimeout(total=45),
					) as response:
						if response.status != 200:
							err_text = (await response.text()).strip()
							await message.reply(
								f"Peckbot error {response.status}: {err_text[:200]}",
								delete_after=5,
							)
							return
						data = await response.json()
				except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
					self.logger.exception("Peckbot request failed")
					await message.reply("Peckbot is unavailable right now.", delete_after=5)
					return
				reply_text = (
					data.get("choices", [{}])[0]
					.get("message", {})
					.get("content", "")
					.strip()
				)
				if not reply_text:
					await message.reply("Peckbot returned an empty response.", delete_after=5)
					return
				for i in range(0, len(reply_text), 2000):
					await message.reply(reply_text[i:i+2000], mention_author=False)
		elif ("trevor" in message.content.lower()):
			await message.channel.send("https://tenor.com/view/trevor-moment-discord-swag-meme-gif-20463477") 
			self.trevortimes += 1
			self.logger.info(f"Trevor has been sent {self.trevortimes} times")
	# endregion
	# region Scheduled Event
	@commands.Cog.listener()
	async def on_scheduled_event_create(self, event:discord.ScheduledEvent):
		if event.name.startswith("["):
			announcementsCh = self.bot.get_channel(self.bot.channelIDs[ChannelIDs.ANNOUNCEMENTS])
			if event.name.lower().startswith("[event]"):
				await announcementsCh.send(f"A new event is starting soon:tm:!\n{event.url}")
			if event.name.lower().startswith("[sqb]"):
				await announcementsCh.send(f"An SQB session has been scheduled by a member!\n{event.url}")
	# endregion
	# endregion
	# region CUSTOM LISTENERS
	@commands.Cog.listener()
	async def on_newsapi_post(self, data:'NewsAPI.News'):
		self.logger.debug("Dispatch for NewsAPI post received")
		news_ch = self.bot.get_channel(self.bot.channelIDs[ChannelIDs.WTNEWS])
		ImportanceEnum = self.bot.newsAPI.News.ImportanceLevel
		match data.importance:
			case ImportanceEnum.EVENT:
				ping_role = self.bot.roleIDs[RoleIDs.EVENT_NEWS]
			case ImportanceEnum.MAJOR:
				ping_role = self.bot.roleIDs[RoleIDs.MAJOR_NEWS]
			case _:
				ping_role = None
		await news_ch.send(content="" if ping_role is None else f"<@&{ping_role}>", embed=data.buildEmbed(self.bot.iconURL))
		self.logger.debug("Dispatch for NewsAPI Post complete")
	# endregion

async def setup(bot:'Bot'):
	await bot.add_cog(Listeners(bot))