if __name__ == "__main__":
	raise Exception("Start the program from the main process")
import discord, logging, asyncio
from discord.ext import commands
from typing import TYPE_CHECKING
if TYPE_CHECKING:
	from utils.bot import Bot
# ChannelIDs, RoleIDs, CategoryIDs
# owner_only, officer_only, members_only, debug_only
from utils.bot import officer_only, CategoryIDs
import utils.generic as genericUtil
#import utils.time as timeUtil
#import utils.wt as wtUtil

# "utils.generic", "utils.time", "utils.wt"
__reload_deps__ = ("utils.generic", )

class ClipsCog(commands.GroupCog, group_name="clips"):
	def __init__(self, bot:'Bot'):
		self.bot = bot
		self.logger = logging.getLogger(__name__)
		self.logger.setLevel(bot.logLevel)
		self.logger.debug(f"{self.__class__.__name__} initialized")

	@discord.app_commands.command(name="upload")
	async def upload_clip(self, interaction:discord.Interaction):
		VIDEO_FORMATS = [".mp4", ".mov", ".webm"]
		class CreateClipCh(discord.ui.Modal, title="Upload Clip"):
			userCh = discord.ui.Label(
				text="User to upload for", 
				component=discord.ui.UserSelect(
					required=True,
					max_values=1,
					min_values=1,
					id=0
				)
			)
			_ = discord.ui.TextDisplay(content="Provide at least one of the items below")
			clips = discord.ui.Label(
				text="Clip",
				component=discord.ui.FileUpload(
					min_values=1,
					required=False,
					id=1
				)
			)
			medal_url = discord.ui.Label(
				text="Medal share link",
				component=discord.ui.TextInput(
					placeholder="https://medal.tv/games/war-thunder/clips/...",
					min_length=42,
					required=False,
					id=2
				)
			)
			def __init__(self, bot:'Bot'):
				super().__init__()
				self.bot = bot
				self._logger = logging.getLogger(__name__)
			async def on_submit(self, interaction:discord.Interaction):
				await interaction.response.defer(ephemeral=True, thinking=True)
				selected_user:discord.Member = self.find_item(0).values[0]
				clips:list[discord.Attachment] = self.find_item(1).values
				medal_url:str = self.find_item(2).value
				self._logger.debug(f"clips={clips}, selected_user={selected_user}, medal_url={medal_url}")	
				if not clips and not medal_url:
					await interaction.edit_original_response(content=f"You didn't provide a clip nor a medal url.")
					return
				for clip in clips:
					for ext in VIDEO_FORMATS: 
						if clip.filename.lower().endswith(ext): break
					else:
						await interaction.edit_original_response(content=f"One of the attachments were not an accepted video format. The following formats are accepted: {", ".join(VIDEO_FORMATS)}")
						return
				CLIPS_CATEGORY:discord.CategoryChannel|None = next((c for c in self.bot.get_guild(self.bot.peckServer).categories if c.id == self.bot.categoryIDs[CategoryIDs.CLIPS]), None)
				if CLIPS_CATEGORY is None: raise LookupError("Could not find the Clips category")
				subjects = CLIPS_CATEGORY.text_channels
				self._logger.debug(f"Subjects: {subjects}")
				self._logger.debug(f"Category: {CLIPS_CATEGORY}")
				async def accept(interaction:discord.Interaction):
					original_msg = await interaction.original_response()
					await original_msg.edit(content=original_msg.content.removesuffix("\nAwaiting confirmation..."))
					return True
				async def deny(interaction:discord.Interaction):
					await interaction.message.delete()
					if len([i async for i in interaction.message.channel.history(limit=1)]) == 0:
						await interaction.message.channel.delete("Clips channel became empty")
					return True
				if not any([int(i.name) == selected_user.id for i in subjects]):
					channel = await CLIPS_CATEGORY.create_text_channel(str(selected_user.id), reason="User clip channel request")
				else:
					channel = [i for i in subjects if int(i.name) == selected_user.id][0]
				for clip in clips:
					await channel.send(f"Sent by: {interaction.user.name} ({interaction.user.id})\nAwaiting confirmation...", view=genericUtil.genericButtons(acceptFunc=accept, denyFunc=deny, removeButtonsAfter=True, acceptLabel="Accept", denyLabel="Delete", timeout=None), file=await clip.to_file())
				if medal_url:
					try:
						file = await genericUtil.medalDownload(medal_url)
					except LookupError as e:
						await interaction.edit_original_response(content=f"Something went wrong when trying to download the clip: {e}")
						return
					while self.bot.is_ws_ratelimited():
						await asyncio.sleep(0.5)
					try:
						await channel.send(f"Sent by: {interaction.user.name} ({interaction.user.id})\nAwaiting confirmation...", view=genericUtil.genericButtons(acceptFunc=accept, denyFunc=deny, removeButtonsAfter=True, acceptLabel="Accept", denyLabel="Delete", timeout=None), file=file)
					except discord.HTTPException as e:
						if e.status == 413:
							await interaction.edit_original_response(content=f"The medal file appears to be too big")
							return
						raise
				await interaction.edit_original_response(content=f"Uploaded clip for {selected_user}.")
		await interaction.response.send_modal(CreateClipCh(self.bot))

	@discord.app_commands.command(name="add_alias")
	@officer_only()
	async def add_alias(self, interaction:discord.Interaction):
		class AddAlias(discord.ui.Modal, title="Add alias to user"):
			userCh = discord.ui.Label(
				text="User to upload for", 
				component=discord.ui.UserSelect(
					required=True,
					max_values=1,
					min_values=1,
					id=0
				)
			)
			userAlias = discord.ui.Label(
				text="Alias of user",
				component=discord.ui.TextInput(
					required=True,
					min_length=1,
					max_length=64,
					style=discord.TextStyle.short
				)
			)
			def __init__(self, bot:'Bot'):
				super().__init__()
				self.bot = bot
				self._logger = logging.getLogger(__name__)
			async def on_submit(self, interaction:discord.Interaction):
				await interaction.response.defer(ephemeral=True, thinking=True)
				selected_user:discord.Member = self.userCh.component.values[0]
				alias:str = self.userAlias.component.value
				CLIPS_CATEGORY:discord.CategoryChannel|None = next((c for c in self.bot.get_guild(self.bot.peckServer).categories if c.id == self.bot.categoryIDs[CategoryIDs.CLIPS]), None)
				if CLIPS_CATEGORY is None:
					raise LookupError("Could not find the Clips category")
				subjects = CLIPS_CATEGORY.text_channels
				self._logger.debug(f"Subjects: {subjects}")
				self._logger.debug(f"Category: {CLIPS_CATEGORY}")
				if not any([int(i.name) == selected_user.id for i in subjects]):
					await interaction.edit_original_response(content="The selected user does not have a clip channel. Use the command `/upload_clip` to create one")
					return
				channel:discord.TextChannel = [i for i in subjects if int(i.name) == selected_user.id][0]
				async def accept(interaction:discord.Interaction):
					alias:str = interaction.message.content.split("\n")[1].strip('"').lower()
					await interaction.message.delete()
					await interaction.channel.edit(topic=(interaction.channel.topic+"\n" if interaction.channel.topic is not None else "")+f"{alias}")
				async def deny(interaction:discord.Interaction):
					await interaction.message.delete()
				await channel.send(content=f"User '{interaction.user.name}' ({interaction.user.id}) suggested the following alias for user:\n\"{alias}\"\nAwaiting confirmation...", view=genericUtil.genericButtons(acceptFunc=accept, denyFunc=deny, acceptLabel="Add", denyLabel="Delete", timeout=None))
				await interaction.edit_original_response(content=f"Uploaded alias for {selected_user}. Said alias will be accessible after admin confirmation.")
		await interaction.response.send_modal(AddAlias(self.bot))
	
	@discord.app_commands.command(name="remove_alias")
	@discord.app_commands.default_permissions(manage_channels=True)
	@officer_only()
	async def remove_alias(self, interaction:discord.Interaction, alias:str, user:discord.User):
		await interaction.response.defer(thinking=True, ephemeral=True)
		clipCateg = self.bot.get_guild(self.bot.peckServer).categories
		for categ in clipCateg:
			if categ.id != self.bot.categoryIDs[CategoryIDs.CLIPS]: continue
			clipCateg = categ
			break
		else:
			raise LookupError("Could not find clips category in guild")
		userClipCh = None
		for ch in clipCateg.channels:
			if ch.name != str(user.id): continue
			userClipCh = ch
			break
		else:
			await interaction.edit_original_response(content=f"No clips channel could be found for user {user.name}")
			return
		aliases = userClipCh.topic.split("\n")
		for ind, _alias in enumerate(aliases):
			if _alias.lower() != alias.lower(): continue
			aliases.pop(ind)
			userClipCh.topic = "\n".join(aliases)
			await interaction.edit_original_response(content=f"Alias '{alias}' has been removed from user {user.name}")
			break
		else:
			await interaction.edit_original_response(content=f"No such alias found. The following aliases are connected to the given user: {"; ".join(aliases)}")
			return

async def setup(bot:'Bot'):
	await bot.add_cog(ClipsCog(bot))