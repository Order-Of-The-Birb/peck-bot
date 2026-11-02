import asyncio
import re
from logging import getLogger as _gL
from typing import Protocol

import discord
from discord.ui import Modal, View

import bot.config as Config
import utils.helper as helperUtil
import utils.thunderapi as ThunderAPI

__reload_deps__ = ("utils.media", "bot.client", "bot.config", "utils.thunderapi")
_logger = _gL(__name__)

class Persistent:
	pass

class Modals:
	class Clips:
		@staticmethod
		async def setup_channel(channel: discord.ForumChannel, user: discord.Member):
			voting_thread, user_thread = await helperUtil.get_clip_threads(channel, user.id)
			if voting_thread is None:
				tmp = await channel.create_thread(
					name="Voting Booth",
					reason="No voting thread beforehand",
					content="This thread is used to vote about uploaded clips, about whether they are worthy, or relevant to the user"
				)
				voting_thread = tmp.thread
				await voting_thread.edit(pinned=True)
			if user_thread is None:
				tmp = await channel.create_thread(
					name=str(user.id),
					content=f"Channel for clips about {user.mention}\nKnown aliases:\n",
					reason="User clip channel request"
				)
				user_thread = tmp.thread
			return voting_thread, user_thread

		class CreateClip(Modal, title="Clip upload"):
			user = discord.ui.Label(
				text="User",
				component=discord.ui.UserSelect(
					custom_id="selected_user",
					min_values=1,
					max_values=1,
					required=True,
					id=0
				),
				description="The user this clip will be added under"
			)
			files = discord.ui.Label(
				text="The clip(s)",
				component=discord.ui.FileUpload(
					min_values=1,
					max_values=10,
					required=True,
					id=1
				),
				description="Please keep it relevant to the given user"
			)
			def __init__(self):
				super().__init__(timeout=600)

			async def on_submit(self, interaction: Client.Interaction):
				self.stop()
				await interaction.response.defer(thinking=True, ephemeral=True)

				config = await Config.get(interaction.guild_id)
				if not config:
					await interaction.edit_original_response(content="Could not get guild configs. No changes were made.")
					return

				clips_channel = config.get(Config.Channels.CLIPS)
				if clips_channel is None:
					await interaction.edit_original_response(content="This server is not configured for clips.")
					return

				VIDEO_FORMATS = [".mp4", ".mov", ".webm"]
				files: list[discord.File] = []
				for file in self.find_item(1).values:
					file: discord.Attachment
					if not any(file.filename.endswith(i) for i in VIDEO_FORMATS):
						raise ValueError("Invalid file format given for one of the clips")
					files.append(await file.to_file())

				user: discord.Member = self.find_item(0).values[0]

				voting_thread, _ = await Modals.Clips.setup_channel(clips_channel, user)
				for clip in files:
					msg = await voting_thread.send(
						content=f"## Clip vote\nProposed by: {interaction.user.mention}\nProposed for: {user.mention}\nAwaiting vote...",
						file=clip
					)
					await msg.add_reaction(interaction.client.get_emoji(1277999470038220902))
					await asyncio.sleep(0.2)
					await msg.add_reaction(interaction.client.get_emoji(1277999500262244362))
					await asyncio.sleep(0.5)
				await interaction.edit_original_response(content=f"Clip for {user.mention} has been cast to vote.")

		class CreateAlias(Modal, title="Add alias"):
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
			def __init__(self):
				super().__init__(timeout=600)

			async def on_submit(self, interaction:Client.Interaction):
				await interaction.response.defer(ephemeral=True, thinking=True)

				config =await Config.get(interaction.guild_id)
				if not config:
					await interaction.edit_original_response(content="Could not get guild configs. No changes were made.")
					return

				clips_channel = config.get(Config.Channels.CLIPS)
				if clips_channel is None:
					await interaction.edit_original_response(content="This server is not configured for clips.")
					return

				selected_user:discord.Member = self.userCh.component.values[0]
				alias:str = self.userAlias.component.value

				voting_thread, _ = await Modals.Clips.setup_channel(clips_channel, selected_user)
				msg = await voting_thread.send(
					content=f"## Alias vote\nProposed by: {interaction.user.mention}\nProposed for: {selected_user.mention}\nAlias: \"{alias}\"\nAwaiting vote..."
				)
				await msg.add_reaction(interaction.client.get_emoji(1277999470038220902))
				await asyncio.sleep(0.2)
				await msg.add_reaction(interaction.client.get_emoji(1277999500262244362))
				await interaction.edit_original_response(content=f"Alias for {selected_user.mention} has been cast to vote.")

	class AddAlias(Modal, title="Add alias to user"):
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
		def __init__(self):
			super().__init__(timeout=15 * 60)
		async def on_submit(self, interaction:Client.Interaction):
			await interaction.response.defer(ephemeral=True, thinking=True)

			config =await Config.get(interaction.guild_id)
			if not config:
				await interaction.edit_original_response(content="Could not get guild configs. No changes were made.")
				return

			selected_user:discord.Member = self.userCh.component.values[0]
			alias:str = self.userAlias.component.value
			clips_channel = config.get(Config.Channels.CLIPS)
			if clips_channel is None:
				raise LookupError("Could not find the Clips channel")
			async for thread in helperUtil.get_threads(clips_channel):
				if not thread.flags.pinned:
					continue
				msg = await thread.send(f"## Alias vote\nNew alias proposed for user {selected_user.mention}:\n\t{alias}\n\nAwaiting vote...")
				await msg.add_reaction(interaction.client.get_emoji(1277999470038220902))
				await asyncio.sleep(0.2)
				await msg.add_reaction(interaction.client.get_emoji(1277999500262244362))
				await asyncio.sleep(0.5)

	class ReportModal(Modal, title="Report user"):
		user = discord.ui.Label(
			text="War Thunder Username",
			component=discord.ui.TextInput(
				min_length=2,
				max_length=16,
				required=True,
				style=discord.TextStyle.short,
				custom_id="report_username",
				placeholder="username"
			),
			description="The War Thunder username of the player. If they are on console adding the @psn or @live tags is optional"
		)
		type = discord.ui.Label(
			text="Category",
			component=discord.ui.Select(
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
		message = discord.ui.Label(
			text="Message",
			component=discord.ui.TextInput(
				min_length=1,
				max_length=2048,
				custom_id="report_msg",
				style=discord.TextStyle.paragraph,
				placeholder="I would like to report...",
				required=False
			),
			description="The message you wish for us to see"
		)
		replayURL = discord.ui.Label(
			text="Evidence replay URL",
			component=discord.ui.TextInput(
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
		async def on_submit(self, interaction: Client.Interaction):
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
			report_category:discord.ui.Select = self.find_item(69)

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
		async def on_error(self, interaction: Client.Interaction, error: Exception) -> None:
			await interaction.edit_original_response(content='Oops! Something went wrong.')
			_logger.exception("An error occured while reporting", exc_info=error)

class Views:
	class genericButtons(View):
		class _callbackProtocol(Protocol):
			async def __call__(
				self,
				interaction: Client.Interaction,
				**kwargs
			) -> bool|None: ...
		def __init__(self, *, acceptFunc:_callbackProtocol, denyFunc:_callbackProtocol|None=None, timeout:int|None = 180, acceptLabel:str = "Yes", denyLabel:str="No", deny:bool=True, removeButtonsAfter:bool=False, requiredPerms:discord.Permissions|None=None, id: str | None = None, **kwargs):
			if deny and denyFunc is None:
				raise ValueError("deny=True requires denyFunc to be provided")
			self.requiredPerms = requiredPerms
			super().__init__(timeout=timeout)
			yes = discord.ui.Button(
				label=acceptLabel,
				style=discord.ButtonStyle.green,
				custom_id="accept"
			)
			no = discord.ui.Button(
				label=denyLabel,
				style=discord.ButtonStyle.red,
				custom_id="deny"
			)
			async def yes_callback(interaction: Client.Interaction):
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
						except discord.NotFound:
							pass # The callback may already have deleted the message.
			async def no_callback(interaction: Client.Interaction):
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
						except discord.NotFound:
							pass # The callback may already have deleted the message.
			yes.callback = yes_callback
			no.callback = no_callback
			self.add_item(yes)
			if deny and denyFunc is not None:
				self.add_item(no)

class LayoutViews:
	pass
