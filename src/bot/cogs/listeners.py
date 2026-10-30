import asyncio
import logging
from datetime import UTC, datetime, timedelta
from re import sub as re_sub

import discord
from discord.ext import commands

import bot.client as Client
import bot.config as Config
import utils.generic as genericUtil
import utils.newsAPI as NewsAPI
import utils.time as timeUtil

# "utils.generic", "utils.helper",
# "utils.memory", "utils.network", "utils.newsAPI",
# "utils.resources", "utils.thunderapi", "utils.time"
# "bot.modals", "bot.client", "bot.config"
__reload_deps__ = ("bot.client", "bot.config", "utils.generic", "utils.time",  "utils.newsAPI")

sqb_member_last_seen = datetime.now(UTC)-timedelta(minutes=30)

class Listeners(commands.Cog):
	last_disconnect: datetime | None
	clip_timeouts: timeUtil.GenericTimeout
	def __init__(self):
		self.logger = logging.getLogger(__name__)

		self.last_disconnect = None
		self.clip_timeouts = timeUtil.GenericTimeout()
		self.clip_timeouts.run()
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
		await Client.BOT.change_presence(activity=activity,status=discord.Status.do_not_disturb)
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
		self.logger.exception(f"An error occurred in '{event}'")
		# If the event had a message, reply there
		if args and hasattr(args[0], "channel"):
			try:
				await args[0].channel.send("An unexpected error occurred.")
			except Exception:
				self.logger.exception("Could not send exception message")

	@commands.Cog.listener()
	async def on_ready(self):
		await Client.BOT.change_presence(activity=discord.Game("SQB with PECK"), status=discord.Status.online)

	@commands.Cog.listener()
	async def on_resumed(self):
		self.logger.debug("Bot resumed session")
	# endregion
	# region Member
	@commands.Cog.listener()
	async def on_member_remove(self, member:discord.Member):
		config = await Config.get(member.guild.id)
		if config is None:
			return

		user = await config.management.get(discord_id=member.id)
		if user:
			logs_channel = config.get(Config.Channels.LOGS)
			if logs_channel is None:
				return

			embed = discord.Embed(title="User left", description="A Squadron member left the server!", color=0xb7a287)
			embed.add_field(name="Discord name", value=f"{member.name}", inline=False)
			embed.add_field(name="UID", value=f"{member.id}", inline=False)
			embed.add_field(name="WT username", value=f"{genericUtil.demarkdownify(user[0].username)}", inline=False)
			embed.add_field(name="Length of stay", value=f"{member.joined_at.strftime("%Y.%m.%d")}-{datetime.now(UTC).strftime("%Y.%m.%d")}")
			await logs_channel.send(embed=embed)

	# endregion
	# region Message
	trevortimes:int = 0
	@commands.Cog.listener()
	async def on_message(self, message:discord.Message):

		if message.author.bot:
			return

		config = await Config.get(message.guild.id)
		if config is None:
			return
		if message.channel ==config.get(Config.Channels.WTNEWS):
			if "warthunder.com" not in message.content.lower():
				await message.delete()
		elif "clip" in message.content.lower():
			CLIPS_CATEGORY =config.get(Config.Categories.CLIPS)
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
			if self.clip_timeouts.isTimedOut(message.author.id):
				expire_time = self.clip_timeouts.getExpireTime(message.author.id)
				if expire_time is None:
					cooldown_reply = "You are under cooldown. Please try again later."
				else:
					cooldown_reply = f"You are under cooldown. It will expire {timeUtil.discord_timestamp(expire_time, "R")}"
				try:
					await message.reply(cooldown_reply, delete_after=5)
				except discord.HTTPException:
					self.logger.exception(f"Could not send clip cooldown reply to user {message.author.id}")
				return
			self.clip_timeouts.add(message.author.id)
			clip_urls:list[str] = []
			part = 0
			try:
				async for clip_message in subject.history(limit=None, oldest_first=True):
					for attachment in clip_message.attachments:
						# The next attachment proves this is a multipart reply.
						if len(clip_urls) == 10:
							await message.reply(f"Part {part+1}:\n{"\n".join(clip_urls)}", mention_author=False)
							part += 1
							clip_urls.clear()
						clip_urls.append(attachment.url)
				if part:
					await message.reply(f"Part {part+1}:\n{"\n".join(clip_urls)}", mention_author=False)
				elif clip_urls:
					await message.reply(f"Here you go\n{"\n".join(clip_urls)}", mention_author=False)
				else:
					await message.reply("No clips found.", mention_author=False)
			except discord.HTTPException:
				self.logger.exception(f"Clip request failed for user {message.author.id} in source channel {subject.id} after {part} completed batches")
				failure = "I couldn't complete this clip request."
				if part:
					failure += " The results above are incomplete."
				failure += " Please try again later. This attempt counts toward your cooldown."
				try:
					await message.reply(failure, mention_author=False)
				except discord.HTTPException:
					self.logger.exception(f"Could not send clip failure reply to user {message.author.id}")
			return
		elif any(i in message.content.lower() for i in ["updoot", "downdoot", "upvote", "downvote"]):
			updoot_msg = message.reference if message.reference else message
			await updoot_msg.add_reaction(Client.BOT.get_emoji(1277999470038220902))
			await asyncio.sleep(0.2)
			await updoot_msg.add_reaction(Client.BOT.get_emoji(1277999500262244362))
		elif ("trevor" in message.content.lower()):
			await message.channel.send("https://cdn.discordapp.com/attachments/917952050883596309/1560956360349454426/trevor-moment.gif")
			self.trevortimes += 1
			self.logger.info(f"Trevor has been sent {self.trevortimes} times")
	# endregion
	# region Scheduled Event
	@commands.Cog.listener()
	async def on_scheduled_event_create(self, event:discord.ScheduledEvent):
		config = await Config.get(event.guild_id)
		if config is None:
			return

		if event.name.startswith("["):
			announcementsCh =config.get(Config.Channels.ANNOUNCEMENTS)
			if event.name.lower().startswith("[event]"):
				await announcementsCh.send(f"A new event is starting soon:tm:!\n{event.url}")
			if event.name.lower().startswith("[sqb]"):
				await announcementsCh.send(f"An SQB session has been scheduled by a member!\n{event.url}")
	# endregion
	# endregion
	# region CUSTOM LISTENERS
	@commands.Cog.listener()
	async def on_newsapi_post(self, data:NewsAPI.News):
		self.logger.debug("Dispatch for NewsAPI post received")
		_ = re_sub(r"\[[a-zA-Z0-9]+\]", "", data.title).strip()
		title_truncated = _ if len(_) <= 100 else _[:97] + "..."
		del _

		embed = data.buildEmbed()

		async for guild in Config.guilds():
			news_ch = guild.get(Config.Channels.WTNEWS)

			match data.importance:
				case NewsAPI.NewsModel.ImportanceLevel.EVENT:
					content = guild.get(Config.Roles.EVENT_NEWS).mention
				case NewsAPI.NewsModel.ImportanceLevel.MAJOR:
					content = guild.get(Config.Roles.MAJOR_NEWS).mention
				case _:
					content = ""

			await guild.create_missing_tags_wtnews()

			applied_tags = [tag for tag in news_ch.available_tags if tag.name in data.tags]

			await news_ch.create_thread(
				name=title_truncated,
				reason="Autogenerated thread under news post",
				content=content,
				embed=embed,
				applied_tags=applied_tags
			)
			await asyncio.sleep(0.1)
		self.logger.debug("Dispatch for NewsAPI Post complete")
	# endregion

async def setup(bot: Client._Bot):
	 await bot.add_cog(Listeners())
