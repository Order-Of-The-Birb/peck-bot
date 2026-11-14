import asyncio
import logging
from os import getenv
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from modules.peck_ai import PeckAI, PeckAIError
from utils.bot import ChannelIDs

if TYPE_CHECKING:
	from utils.bot import Bot


logger = logging.getLogger(__name__)
MAX_PROMPT_LENGTH = 2000
MAX_REPLY_LENGTH = 2000


class PeckAICog(commands.Cog):
	def __init__(self, bot: 'Bot', ai: PeckAI):
		self.bot = bot
		self.ai = ai
		self.inference = asyncio.Lock()

	def mention_prompt(self, message: discord.Message) -> str | None:
		bot_user = self.bot.user
		if (
			bot_user is None or message.author.bot or message.webhook_id is not None
			or message.guild is None or message.guild.id != self.bot.peckServer
			or message.channel.id == self.bot.channelIDs[ChannelIDs.WTNEWS]
		):
			return None
		content = message.content.lstrip()
		for mention in (f"<@{bot_user.id}>", f"<@!{bot_user.id}>"):
			if content.startswith(mention):
				return content[len(mention):].lstrip().removeprefix(",").strip()
		return None

	def _stored_timezone(self, author_id: int) -> int | None:
		offsets = set()
		for account in self.bot.db.getByDID(author_id):
			try:
				offset = account.timezone
			except KeyError:
				continue
			if type(offset) is int and -12 <= offset <= 14:
				offsets.add(offset)
		return offsets.pop() if len(offsets) == 1 else None

	async def _reply(self, message: discord.Message, text: str) -> None:
		if len(text) > MAX_REPLY_LENGTH:
			text = text[:MAX_REPLY_LENGTH - 1].rstrip() + "…"
		try:
			await message.reply(text, allowed_mentions=discord.AllowedMentions.none(), mention_author=False)
		except discord.HTTPException:
			logger.warning("Could not send the Peck AI response to Discord")

	@commands.Cog.listener()
	async def on_message(self, message: discord.Message):
		prompt = self.mention_prompt(message)
		if prompt is None:
			return
		if not prompt:
			await self._reply(message, "Add your question after the mention.")
			return
		if len(prompt) > MAX_PROMPT_LENGTH:
			await self._reply(message, f"Please keep your question to {MAX_PROMPT_LENGTH:,} characters.")
			return

		author_id = message.author.id
		cooldown = self.bot.timeouts["ai"]
		if cooldown.isTimedOut(author_id):
			expires = cooldown.getExpireTime(author_id)
			when = f" {discord.utils.format_dt(expires, style='R')}" if expires is not None else " later"
			await self._reply(message, f"You’ve reached your Peck Bot limit. Try again{when}.")
			return
		if self.inference.locked():
			await self._reply(message, "Peck Bot is answering another question. Try again in a moment.")
			return

		async with self.inference:
			cooldown.add(author_id)
			try:
				answer = await self.ai.answer(prompt, default_timezone=self._stored_timezone(author_id))
			except PeckAIError:
				logger.warning("Airbot could not answer a Peck AI request")
				answer = "Peck Bot couldn’t answer right now. Try again in a moment."
		await self._reply(message, answer)


async def setup(bot: 'Bot'):
	base_url = getenv("PECK_AI_BASE_URL", "").strip()
	if not base_url:
		return
	model = getenv("PECK_AI_MODEL", "gemma-4-heretic").strip() or "gemma-4-heretic"
	try:
		ai = PeckAI(base_url, model)
	except ValueError:
		logger.warning("Invalid Peck AI configuration. Discord AI replies are disabled.")
		return
	await bot.add_cog(PeckAICog(bot, ai))
