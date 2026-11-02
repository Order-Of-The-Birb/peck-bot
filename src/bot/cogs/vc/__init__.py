import asyncio
import logging
import re
from datetime import UTC, datetime, timedelta

import discord
from discord.ext import commands, tasks

import bot.client as Client
import bot.config as Config


class SquadVC:
	def __init__(self):
		self.channels:dict[int, datetime|None] = {}
		self.checkDelay:int = 0

	async def add(self, channel:discord.VoiceChannel):
		if channel.id in self.channels:
			return
		if SQUADVC_RE.match(channel.name) is None:
			return
		if len(channel.members) > 0:
			self.channels[channel.id] = None
		else:
			self.channels[channel.id] = datetime.now(UTC)

	async def remove(self, channel:discord.VoiceChannel, reason: str = "Empty for too long") -> bool:
		if channel.id not in self.channels:
			return False
		try:
			await channel.delete(reason=reason)
			self.channels.pop(channel.id, None)
			return True
		except (discord.Forbidden, discord.HTTPException, discord.NotFound):
			return False

	async def update(self):
		for channel, last_seen in self.channels.items():
			ch = Client.BOT.get_channel(channel)
			if len(ch.members) > 0:
				self.channels[channel] = None
			elif last_seen is None:
				self.channels[channel] = datetime.now(UTC)
			elif (datetime.now(UTC) - last_seen) < vc_check_frequency*2:
				await self.remove(ch)

vc_check_frequency = timedelta(minutes=30)
SQUADVC_RE = re.compile(r"squad (\d+)", re.IGNORECASE)
class VcCog(commands.GroupCog, group_name="squad"):
	voice_channels: dict[int, SquadVC]
	check_task: asyncio.Task
	def __init__(self):
		self.logger = logging.getLogger(__name__)
		self.logger.debug(f"{self.__class__.__name__} initialized")
		self.voice_channels = {}

	@discord.app_commands.command(name="create")
	@Client.guild_only()
	@discord.app_commands.choices(size=[
		discord.app_commands.Choice(name="4 users", value=4),
		discord.app_commands.Choice(name="8 users", value=8),
		discord.app_commands.Choice(name="10 users", value=10),
		discord.app_commands.Choice(name="No limit", value=-1)
	])
	@discord.app_commands.checks.cooldown(1, 30*60)
	async def create_vc(self, interaction:Client.Interaction, size:int, private:bool = False):
		"""Creates a new squad VC with a set size (4,8 or 10). Will not create one if you already have one active."""
		await interaction.response.defer(thinking=True)
		config = await Config.get(interaction)
		if config is None:
			await interaction.edit_original_response(content="This server is not yet configured.")
			return

		category = config.get(Config.Categories.SQUAD_VC)
		if category is None:
			await interaction.edit_original_response(content="This server is not configured for this.")
			return

		squad_voice_channels = [
			i
			for i in category.voice_channels
			if SQUADVC_RE.fullmatch(i.name) is not None
		]
		squad_voice_channels.sort(key=lambda x: int(x.name.split(" ")[-1]))
		squad_numbers = [int(i.name.split()[-1]) for i in squad_voice_channels]

		pos = squad_voice_channels[-1].position+1
		lowest = len(squad_voice_channels)+1
		for i in range(1, lowest):
			if i in squad_numbers:
				continue
			pos = squad_voice_channels[i].position+1
			lowest = i
			break

		new_ch = await interaction.guild.create_voice_channel(
			name=f"Squad {lowest}",
			reason=f"Command, ran by {interaction.user.name}({interaction.user.id})",
			position=pos,
			user_limit=size,
			category=category
		)
		self.voice_channels.setdefault(interaction.guild_id, SquadVC())
		await self.voice_channels[interaction.guild_id].add(new_ch)
		await interaction.edit_original_response(content=f"Channel created, {new_ch.mention}")

	#region Tasks
	@tasks.loop(seconds=vc_check_frequency.total_seconds())
	async def channels_check(self):
		await Client.BOT.wait_until_ready()
		async for guild in Config.guilds():
			dc_guild = guild.guild
			if dc_guild.id not in self.voice_channels:
				self.logger.debug(f"Initializing voice channels for guild {dc_guild.id}")
				categ = guild.get(Config.Categories.SQUAD_VC)
				if categ is None:
					continue
				self.voice_channels[dc_guild.id] = SquadVC()
				for channel in categ.voice_channels:
					if not channel.name.lower().startswith("squad "):
						continue
					await self.voice_channels[dc_guild.id].add(channel)
				continue
			await self.voice_channels[dc_guild.id].update()

	async def cog_load(self):
		self.check_task = self.channels_check.start()
		return await super().cog_load()
	async def cog_unload(self):
		self.check_task.cancel()
		return await super().cog_unload()
	#endregion

async def setup(bot: 'Client._Bot'):
	await bot.add_cog(VcCog())
