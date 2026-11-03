import asyncio
import logging

import discord

import bot.client as Client
import bot.extensions as Shared

logger = logging.getLogger(__name__)

def demarkdownify(text:str):
	replace_list = ["_", "*", "#", "~", "`", "|"]
	for i in replace_list:
		text = text.replace(i, "\\"+i)
	return text

async def get_clip_threads(channel: Shared.ForumChannel, user_id: int) -> tuple[discord.Thread | None, discord.Thread | None]:
	user_thread: discord.Thread | None = None
	vote_thread: discord.Thread | None = None

	name = str(user_id)

	async for thread in channel.get_threads():
		if thread.flags.pinned:
			vote_thread = thread
		elif user_thread is None and thread.name == name:
			user_thread = thread
		if vote_thread is not None and user_thread is not None:
			break
	return vote_thread, user_thread

async def count_votes(message: discord.Message) -> tuple[int, int]:
	for_votes = 0
	against_votes = 0
	for_vote_emoji = await asyncio.to_thread(Client.BOT.get_emoji, 1277999470038220902)
	against_vote_emoji = await asyncio.to_thread(Client.BOT.get_emoji, 1277999500262244362)
	for vote in message.reactions:
		if not vote.me:
			continue
		if vote.emoji == for_vote_emoji:
			for_votes = vote.count-1
		elif vote.emoji == against_vote_emoji:
			against_votes = vote.count-1

	return for_votes, against_votes
