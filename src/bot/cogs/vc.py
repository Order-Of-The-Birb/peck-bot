if __name__ == "__main__":
	raise Exception("Start the program from the main process")
import asyncio, discord, logging, re
from discord.ext import commands, tasks
from datetime import datetime, timedelta, UTC
from typing import TYPE_CHECKING
if TYPE_CHECKING:
	from bot.client import _Bot
from dataclasses import dataclass
#import utils.generic as genericUtil
#import utils.time as timeUtil
#import utils.wt as wtUtil
import bot.client as Client

# "utils.generic", "utils.time", "utils.wt"
__reload_deps__ = ()

@dataclass(slots=True)
class SquadVC:
	def __init__(self):
		self.channels:list['SquadVC.SquadVCData'] = []
		self.checkDelay:int = 0

	class SquadVCData:
		_id:int
		last_seen_person_time:float
		owner:int|None
		created:float

	def add(self, channel:discord.VoiceChannel, owner: int|discord.Member):
		if any(i._id == channel.id for i in self.channels):
			return None
		owner = owner if isinstance(owner, int) else owner.id
		self.channels.append(
			self.SquadVCData(
				channel.id,
				datetime.now(UTC).timestamp(),
				owner,
				channel.created_at
			)
		)

class VcCog(commands.GroupCog, group_name="squad"):
	def __init__(self):
		self.logger = logging.getLogger(__name__)
		self.SQUADVC_RE = re.compile(r"squad (\d+)", re.IGNORECASE)
		self.logger.debug(f"{self.__class__.__name__} initialized")

	@tasks.loop(minutes=30)
	async def channels_check():
		pass

	@discord.app_commands.command(name="create")
	@Client.guild_only()
	@discord.app_commands.choices(size=[
		discord.app_commands.Choice(name="4 users", value=4),
		discord.app_commands.Choice(name="8 users", value=8),
		discord.app_commands.Choice(name="10 users", value=10),
		discord.app_commands.Choice(name="No limit", value=-1)
	])
	async def create_vc(self, interaction:discord.Interaction, size:int, private:bool = False):
		"""Creates a new squad VC with a set size (4,8 or 10). Will not create one if you already have one active."""
		await interaction.response.defer(thinking=True)
		_30min_ago = (datetime.now(UTC)-timedelta(minutes=Client.BOT.squadVC.checkDelay)).timestamp()
		empty_voices = [i for i in interaction.guild.voice_channels if self.SQUADVC_RE.fullmatch(i.name) is not None and len(i.members)==0]
		if empty_voices and not private:
			await interaction.edit_original_response(content=f"The following channels are empty: {', '.join([i.mention for i in empty_voices])}, use those!")
			return
		for channel in Client.BOT.squadVC.channels:
			if channel.creator == interaction.user.id and channel.created >= _30min_ago:
				await interaction.edit_original_response(content="You created a channel recently, chill out dude...")
				return
		category = next((category for category in Client.BOT.get_guild(Client.BOT.peckServer).categories if category.id == Client.BOT.categoryIDs[Client.CategoryIDs.SQUAD_VC]), None)
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
		Client.BOT.squadVC.channels.append(Client.BOT.squadVC.SquadVCData(new_ch.id, last_seen_person_time=datetime.now(UTC).timestamp(), creator=interaction.user.id, created=datetime.now(UTC).timestamp()))

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
		for channel_stored in Client.BOT.squadVC.channels:
			if channel_stored._id == _channel.id and (channel_stored.creator is None or (channel_stored.creator is not None and channel_stored.creator == interaction.user.id)):
				_ = []
				for ch in Client.BOT.squadVC.channels:
					if ch._id != channel_stored._id:
						_.append(ch)
				Client.BOT.squadVC.channels = _
				await _channel.delete()
				await interaction.edit_original_response(content="Removed channel.")
				return
			elif channel_stored._id == _channel.id and channel_stored.creator != interaction.user.id:
				await interaction.edit_original_response(content="Given channel wasn't created by you.")
				return

	@discord.app_commands.command(name="forfeit")
	@discord.app_commands.guild_only()
	@discord.app_commands.describe(new_owner="The member to transfer the squad channel to")
	async def forfeit_vc(self, interaction:discord.Interaction, new_owner: discord.Member):
		"""Forfeit your ownership over a squad channel. Will only let you pick a member, who is in the channel currently."""
		await interaction.response.defer(thinking=True)
		#TODO: Finish

async def setup(bot: '_Bot'):
	await bot.add_cog(VcCog())
