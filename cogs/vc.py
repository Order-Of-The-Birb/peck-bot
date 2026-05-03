if __name__ == "__main__":
	raise Exception("Start the program from the main process")
import discord, logging, re
from discord.ext import commands
from datetime import datetime, timedelta, UTC
from typing import TYPE_CHECKING
if TYPE_CHECKING:
	from utils.bot import Bot
# ChannelIDs, RoleIDs, CategoryIDs
# owner_only, officer_only, members_only, debug_only
from utils.bot import CategoryIDs
#import utils.generic as genericUtil
#import utils.time as timeUtil
#import utils.wt as wtUtil

# "utils.generic", "utils.time", "utils.wt"
__reload_deps__ = ()

class VcCog(commands.GroupCog, group_name="squad"):
	bot:'Bot'
	def __init__(self, bot:'Bot'):
		self.bot = bot
		self.logger = logging.getLogger(__name__)
		self.SQUADVC_RE = re.compile(r"squad (\d+)", re.IGNORECASE)
		async def vcInit():
			await self.bot.wait_until_ready()
			self.logger.debug("VCInit running")
			if len(self.bot.squadVC.channels)!=0:
				self.logger.critical("Channels list is not empty")
				return
			category = next((i for i in bot.get_guild(self.bot.peckServer).categories if i.id == self.bot.categoryIDs[CategoryIDs.SQUAD_VC]), None)
			if category is None: raise ValueError("Could not find the squad VC category")
			self.bot.squadVC.channels=[self.bot.squadVC.SquadVCData(i.id, datetime.now(UTC).timestamp(), None, datetime.now(UTC).timestamp()) 
				for i in category.voice_channels 
				if self.SQUADVC_RE.fullmatch(i.name) is not None and i.name.lower() not in ["squad 1", "squad 2"]
			]
			self.logger.debug("VCInit over")
		self.bot.runtime.create_task(vcInit())
		self.logger.debug(f"{self.__class__.__name__} initialized")
	
	@discord.app_commands.command(name="create")
	@discord.app_commands.guild_only()
	@discord.app_commands.choices(size=[
		discord.app_commands.Choice(name="4 users", value=4),
		discord.app_commands.Choice(name="8 users", value=8),
		discord.app_commands.Choice(name="10 users", value=10),
		discord.app_commands.Choice(name="No limit", value=-1)
	])
	async def create_vc(self, interaction:discord.Interaction, size:int):
		"""Creates a new squad VC with a set size (4,8 or 10). Will not create one if you already have one active"""
		await interaction.response.defer(thinking=True)
		_30min_ago = (datetime.now(UTC)-timedelta(minutes=self.bot.squadVC.checkDelay)).timestamp()
		empty_voices = [i for i in interaction.guild.voice_channels if self.SQUADVC_RE.fullmatch(i.name) is not None and len(i.members)==0]
		if empty_voices and not self.bot.debug:
			await interaction.edit_original_response(content=f"The following channels are empty: {', '.join([i.mention for i in empty_voices])}, use those!")
			return
		for channel in self.bot.squadVC.channels:
			if channel.creator == interaction.user.id and channel.created >= _30min_ago:
				await interaction.edit_original_response(content="You created a channel recently, chill out dude...")
				return
		category = next((category for category in self.bot.get_guild(self.bot.peckServer).categories if category.id == self.bot.categoryIDs[CategoryIDs.SQUAD_VC]), None)
		if category is None: raise ValueError("Category not found... Does the server still exist?")
		squad_voice_channels = [i for i in interaction.guild.voice_channels if self.SQUADVC_RE.fullmatch(i.name) is not None and i in category.voice_channels]
		squad_numbers = sorted([int(i.name.split()[-1]) for i in squad_voice_channels], reverse=True)
		num = len(category.channels)
		for i in range(len(squad_voice_channels)+1,0,-1):
			if i in squad_numbers:
				num-=1
				continue
			break
		thing = sorted([int(squad_channel.name.split()[-1]) for squad_channel in [i for i in interaction.guild.voice_channels if self.SQUADVC_RE.fullmatch(i.name) is not None]])
		lowest = 1
		while lowest in thing:
			lowest += 1
		new_ch = await interaction.guild.create_voice_channel(name=f"Squad {lowest}", reason=f"Command, ran by {interaction.user.name}({interaction.user.id})",position=num,user_limit=size, category=category)
		await interaction.edit_original_response(content=f"Channel created, {new_ch.mention}")
		self.bot.squadVC.channels.append(self.bot.squadVC.SquadVCData(new_ch.id, last_seen_person_time=datetime.now(UTC).timestamp(), creator=interaction.user.id, created=datetime.now(UTC).timestamp()))

	@discord.app_commands.command(name="delete")
	@discord.app_commands.guild_only()
	@discord.app_commands.describe(channel="The squad channel number")
	async def delete_vc(self, interaction:discord.Interaction, channel:int):
		"""Deletes the squad VC that you created. Will refuse to delete if people are in the channel or you didn't create it."""
		await interaction.response.defer(thinking=True)
		_channel = next((i for i in interaction.guild.voice_channels if self.SQUADVC_RE.fullmatch(i.name) and i.name.lower() == f"squad {channel}"), None)
		if _channel is None:
			await interaction.edit_original_response(content=f"There is no channel named 'Squad {channel}'")
			return
		if len(_channel.members) != 0:
			await interaction.edit_original_response(content=f"There are users in {_channel.mention} ({", ".join([i.name for i in _channel.members])})")
			return
		for channel_stored in self.bot.squadVC.channels:
			if channel_stored._id == _channel.id and (channel_stored.creator is None or (channel_stored.creator is not None and channel_stored.creator == interaction.user.id)):
				_ = []
				for ch in self.bot.squadVC.channels:
					if ch._id != channel_stored._id:
						_.append(ch)
				self.bot.squadVC.channels = _
				await _channel.delete()
				await interaction.edit_original_response(content="Removed channel.")
				return
			elif channel_stored._id == _channel.id and channel_stored.creator != interaction.user.id:
				await interaction.edit_original_response(content="Given channel wasn't created by you.")
				return

async def setup(bot: 'Bot'):
	await bot.add_cog(VcCog(bot))