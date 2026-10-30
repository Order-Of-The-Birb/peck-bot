import re
from datetime import timedelta
from logging import getLogger as _gL
from typing import Protocol

import discord
from discord import (
	Attachment,
	ButtonStyle,
	Interaction,
	Member,
	NotFound,
	Permissions,
	TextChannel,
	TextStyle,
)
from discord.ui import (
	Button,
	FileUpload,
	Label,
	Modal,
	Select,
	TextDisplay,
	TextInput,
	UserSelect,
	View,
)

import bot.client as Client
import bot.config as Config
import utils.media as Media
import utils.thunderapi as ThunderAPI

__reload_deps__ = ("utils.media", "bot.client", "bot.config", "utils.thunderapi")
_logger = _gL(__name__)

class Persistent:
	pass

class Modals:
	class CreateClipCh(Modal, title="Upload Clip"):
		userCh = Label(
			text="User to upload for",
			component=UserSelect(
				required=True,
				max_values=1,
				min_values=1,
				id=0
			)
		)
		_ = TextDisplay(content="Provide at least one of the items below")
		clips = Label(
			text="Clip",
			component=FileUpload(
				min_values=1,
				required=False,
				id=1
			)
		)
		medal_url = Label(
			text="Medal share link",
			component=TextInput(
				placeholder="https://medal.tv/games/war-thunder/clips/...",
				min_length=42,
				required=False,
				id=2
			)
		)
		def __init__(self):
			super().__init__(timeout=15 * 60)
		async def on_submit(self, interaction:Interaction):
			await interaction.response.defer(ephemeral=True, thinking=True)
			VIDEO_FORMATS = [".mp4", ".mov", ".webm"]

			config = await Config.get(interaction.guild_id)
			if not config:
				await interaction.edit_original_response(content="Could not get guild configs. No changes were made.")
				return

			selected_user:Member = self.find_item(0).values[0]

			clips_channel = config.get(Config.Channels.CLIPS)
			if clips_channel is None:
				await interaction.edit_original_response(content="This server is not configured for clips.")
				return
			voting_thread: discord.Thread | None = None
			user_thread: discord.Thread | None = None
			for thread in clips_channel.threads:
				if voting_thread is None and thread.flags.pinned:
					voting_thread = thread
					continue
				try:
					if int(thread.name) == selected_user.id:
						user_thread = thread
						continue
				except ValueError:
					if "voting" in thread.name.strip().lower():
						voting_thread = await thread.edit(pinned=True)
				if voting_thread is not None and user_thread is not None:
					break
			else:
				async for thread in clips_channel.archived_threads(limit=None):
					if voting_thread is None and thread.flags.pinned:
						voting_thread = thread
						continue
					if int(thread.name) == selected_user.id:
						user_thread = thread
						continue
			if voting_thread is None:
				voting_thread = await clips_channel.create_thread(
					name="Voting Booth",
					reason="No voting thread beforehand",
					content="This thread is used to vote about uploaded clips, about whether they are worthy, or relevant to the user"
				)
				await thread.edit(pinned=True)

			clips:list[Attachment] = self.find_item(1).values
			medal_url:str = self.find_item(2).value
			if not (clips or medal_url):
				await interaction.edit_original_response(content="You didn't provide a clip nor a medal url.")
				return
			for clip in clips:
				for ext in VIDEO_FORMATS:
					if clip.filename.lower().endswith(ext):
						break
				else:
					await interaction.edit_original_response(content=f"One of the attachments were not an accepted video format. The following formats are accepted: {", ".join(VIDEO_FORMATS)}")
					return

			if user_thread is None:
				user_thread = await clips_channel.create_thread(
					name=str(selected_user.id),
					content=f"Channel for clips about {selected_user.mention}\nKnown aliases:\n",
					reason="User clip channel request"
				)
			if medal_url:
				try:
					clips = [await Media.medalDownload(interaction.guild_id, medal_url)]
				except LookupError as e:
					await interaction.edit_original_response(content=f"Something went wrong when trying to download the clip: {e}")
					return
			else:
				clips = [await clip.to_file() for clip in clips]

			clipPoll = discord.Poll(
				question=f"Is this appropriate for being related to {selected_user.mention}?",
				duration=timedelta(days=3)
			)
			clipPoll.add_answer(text="Yes", emoji="✅") # :white_check_mark:
			clipPoll.add_answer(text="No", emoji=Client.BOT.get_emoji(758380151238033419)) # :redcross:
			for clip in clips:
				await voting_thread.send(
					content=f"Sent by: {interaction.user.mention}\nDestination: {user_thread.mention}\nAwaiting vote...\n\nResults so far:\n\tFor: 0\n\tAgainst: 0",
					file=clip,
					poll=clipPoll
				)
			await interaction.edit_original_response(content=f"Clip for {selected_user} has been cast to vote.")

	class AddAlias(Modal, title="Add alias to user"):
		userCh = Label(
			text="User to upload for",
			component=UserSelect(
				required=True,
				max_values=1,
				min_values=1,
				id=0
			)
		)
		userAlias = Label(
			text="Alias of user",
			component=TextInput(
				required=True,
				min_length=1,
				max_length=64,
				style=TextStyle.short
			)
		)
		def __init__(self):
			super().__init__(timeout=15 * 60)
		async def on_submit(self, interaction:Interaction):
			await interaction.response.defer(ephemeral=True, thinking=True)

			config =await Config.get(interaction.guild_id)
			if not config:
				await interaction.edit_original_response(content="Could not get guild configs. No changes were made.")
				return

			selected_user:Member = self.userCh.component.values[0]
			alias:str = self.userAlias.component.value
			CLIPS_CATEGORY = config.get(Config.Categories.CLIPS)
			if CLIPS_CATEGORY is None:
				raise LookupError("Could not find the Clips category")
			subjects = CLIPS_CATEGORY.text_channels
			_logger.debug(f"Subjects: {subjects}")
			_logger.debug(f"Category: {CLIPS_CATEGORY}")
			if not any(int(i.name) == selected_user.id for i in subjects):
				await interaction.edit_original_response(content="The selected user does not have a clip channel. Use the command `/upload_clip` to create one")
				return
			channel:TextChannel = next(i for i in subjects if int(i.name) == selected_user.id)
			await channel.send(content=f"User '{interaction.user.name}' ({interaction.user.id}) suggested the following alias for user:\n\"{alias}\"\nAwaiting confirmation...")
			await interaction.edit_original_response(content=f"Uploaded alias for {selected_user}. Said alias will be accessible after admin confirmation.")

	class ReportModal(Modal, title="Report user"):
		user = Label(
			text="War Thunder Username",
			component=TextInput(
				min_length=2,
				max_length=16,
				required=True,
				style=discord.TextStyle.short,
				custom_id="report_username",
				placeholder="username"
			),
			description="The War Thunder username of the player. If they are on console adding the @psn or @live tags is optional"
		)
		type = Label(
			text="Category",
			component=Select(
				min_values=1,
				max_values=1,
				options=[
					discord.SelectOption(label="Cheating", value="cheating", description="Aimbot, ESP/Wallhacks, Botted gameplay, etc."),
					discord.SelectOption(label="Toxicity", value="chat"),
					discord.SelectOption(label="Annoying", value="annoying", description="If your only problem is this user being annoying"),
					discord.SelectOption(label="Sabotage", value="sabotage", description="Teamkilling, stealing air slots, etc.")
				],
				required=True,
				custom_id="report_category",
				id=69
			),
			description="The category the user's infraction would fall under"
		)
		message = Label(
			text="Message",
			component=TextInput(
				min_length=1,
				max_length=2048,
				custom_id="report_msg",
				style=discord.TextStyle.paragraph,
				placeholder="I would like to report...",
				required=False
			),
			description="The message you wish for us to see"
		)
		replayURL = Label(
			text="Evidence replay URL",
			component=TextInput(
				min_length=44,
				max_length=70,
				placeholder="https://warthunder.com/en/tournament/replay/...",
				required=True,
				custom_id="evidence",
				style=discord.TextStyle.short
			)
		)
		def __init__(self):
			super().__init__(timeout=15 * 60)
		async def on_submit(self, interaction: discord.Interaction):
			#raise NotImplementedError("Currently rebuilding this code")
			await interaction.response.defer(thinking=True, ephemeral=True)

			config =await Config.get(interaction.guild_id)
			if not config:
				await interaction.edit_original_response(content="Could not get guild configs. No changes were made.")
				return
			management = config.management
			if management is None:
				await interaction.edit_original_response(content="This server's management token is not yet configured.")
				return

			url:str = self.replayURL.component.value.strip().rstrip("/")
			report_category:Select = self.find_item(69)

			username:str = self.user.component.value.strip()
			member = await management.get(username=username)
			if member is None:
				await interaction.edit_original_response(content="No such user exists in our database")
				return
			if member.status == member.Status.EX_MEMBER:
				await interaction.edit_original_response(content="This user is no longer a part of our squadron")
				return

			REPLAY_URL_REGEX = re.match(r"^https://warthunder\.com/[a-z]{2}/tournament/replay/([A-Fa-f0-9]{1,16})$", url)
			if not REPLAY_URL_REGEX:
				await interaction.edit_original_response(content="**Invalid replay URL format.** Please use a valid War Thunder replay link: `https://warthunder.com/en/tournament/replay/<id>`")
				return
			replay = await ThunderAPI.replay(REPLAY_URL_REGEX.group(1))
			for player in replay.team1:
				if int(player) == member.gaijin_id:
					break
			else:
				await interaction.edit_original_response(content=f"The match you provided a link to does not have the user '{username}' in it.")
				return

			report_msg:str = self.message.component.value.strip()
			embed = discord.Embed(title="Report")
			embed.set_author(name=f"{interaction.user.name} (ID: {interaction.user.id})", icon_url=interaction.user.display_avatar.url)
			embed.add_field(name="WT username", value=username, inline=False)
			if report_msg:
				embed.add_field(name="Report message", value=report_msg, inline=False)
			embed.add_field(name="Category", value=report_category.values[0])
			embed.add_field(name="Evidence URL", value=url, inline=False)
			_logger.debug(f"Report from {interaction.user.name} ({interaction.user.id})\nWT username: {username}\nReport message: {report_msg}")
			await config.get(Config.Channels.LOGS).send(embed=embed)
			await interaction.edit_original_response(content="Report submitted!")
		async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
			await interaction.edit_original_response(content='Oops! Something went wrong.')
			_logger.exception("An error occured while reporting", exc_info=error)

class Views:
	class genericButtons(View):
		class _callbackProtocol(Protocol):
			async def __call__(
				self,
				interaction: Interaction,
				**kwargs
			) -> bool|None: ...
		def __init__(self, *, acceptFunc:_callbackProtocol, denyFunc:_callbackProtocol|None=None, timeout:int|None = 180, acceptLabel:str = "Yes", denyLabel:str="No", deny:bool=True, removeButtonsAfter:bool=False, requiredPerms:Permissions|None=None, id: str | None = None, **kwargs):
			if deny and denyFunc is None:
				raise ValueError("deny=True requires denyFunc to be provided")
			self.requiredPerms = requiredPerms
			super().__init__(timeout=timeout)
			yes = Button(
				label=acceptLabel,
				style=ButtonStyle.green,
				custom_id="accept"
			)
			no = Button(
				label=denyLabel,
				style=ButtonStyle.red,
				custom_id="deny"
			)
			async def yes_callback(interaction: Interaction):
				await interaction.response.edit_message(view=self)
				if self.requiredPerms is not None and not all(getattr(interaction.user.guild_permissions, p[0], False) for p in self.requiredPerms if p[1]):
					_logger.warning(f"Accept attempt by: {interaction.user.name} ({interaction.user.id})")
					await interaction.followup.send("You do not have the required permission to use this!", ephemeral=True)
					return
				result = await acceptFunc(interaction, **kwargs)
				if result:
					yes.disabled = True
					if deny:
						no.disabled = True
					self.stop()
					if removeButtonsAfter:
						try:
							await interaction.edit_original_response(view=None)
						except NotFound:
							pass # The callback may already have deleted the message.
			async def no_callback(interaction: Interaction):
				await interaction.response.edit_message(view=self)
				if self.requiredPerms is not None and not all(getattr(interaction.user.guild_permissions, p[0], False) for p in self.requiredPerms if p[1]):
					_logger.warning(f"Deny attempt by: {interaction.user.name} ({interaction.user.id})")
					await interaction.followup.send("You do not have the required permission to use this!", ephemeral=True)
					return
				result = await denyFunc(interaction, **kwargs)
				if result:
					yes.disabled = True
					no.disabled = True
					self.stop()
					if removeButtonsAfter:
						try:
							await interaction.edit_original_response(view=None)
						except NotFound:
							pass # The callback may already have deleted the message.
			yes.callback = yes_callback
			no.callback = no_callback
			self.add_item(yes)
			if deny and denyFunc is not None:
				self.add_item(no)
