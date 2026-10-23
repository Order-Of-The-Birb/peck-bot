import asyncio, discord, re
from discord.ui import (
	View, LayoutView, Modal,
	Button, Item, DynamicItem,
	Select, RoleSelect, UserSelect, ChannelSelect, MentionableSelect,
	TextInput, TextDisplay, Container, File, FileUpload,
	Section, Separator, ActionRow, RadioGroup, Checkbox, CheckboxGroup, Label,
	MediaGallery, Thumbnail
)
from discord import (
    Interaction, Member, Attachment, User, Permissions,
	CategoryChannel, TextChannel, VoiceChannel,
	HTTPException, TextStyle, ButtonStyle, NotFound
)
from logging import getLogger as _gL
from typing import Protocol
from utils import wt as wtUtil
from utils import generic as genericUtil
import utils.management as Management
import bot.client as Client
import bot.config as Config
import utils.thunderapi as ThunderAPI

__reload_deps__ = ("utils.generic", "utils.wt", "utils.management", "bot.client", "bot.config", "utils.thunderapi")
_logger = _gL(__name__)

class CreateClipCh(Modal, title="Upload Clip"):
	VIDEO_FORMATS = [".mp4", ".mov", ".webm"]
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

		config = Config.get(interaction.guild_id)
		if not config:
			await interaction.edit_original_response(content="Could not get guild configs. No changes were made.")
			return

		selected_user:Member = self.find_item(0).values[0]
		clips:list[Attachment] = self.find_item(1).values
		medal_url:str = self.find_item(2).value
		_logger.debug(f"clips={clips}, selected_user={selected_user}, medal_url={medal_url}")
		if not clips and not medal_url:
			await interaction.edit_original_response(content=f"You didn't provide a clip nor a medal url.")
			return
		for clip in clips:
			for ext in self.VIDEO_FORMATS:
				if clip.filename.lower().endswith(ext): break
			else:
				await interaction.edit_original_response(content=f"One of the attachments were not an accepted video format. The following formats are accepted: {", ".join(self.VIDEO_FORMATS)}")
				return
		CLIPS_CATEGORY = config.get_category(Config.GuildConfig.Categories.CLIPS)
		if CLIPS_CATEGORY is None:
			raise LookupError("Could not find the Clips category")
		subjects = CLIPS_CATEGORY.text_channels
		_logger.debug(f"Subjects: {subjects}")
		_logger.debug(f"Category: {CLIPS_CATEGORY}")
		async def accept(interaction:Interaction):
			original_msg = await interaction.original_response()
			await original_msg.edit(content=original_msg.content.removesuffix("\nAwaiting confirmation..."))
			return True
		async def deny(interaction:Interaction):
			await interaction.message.delete()
			if len([i async for i in interaction.message.channel.history(limit=1)]) == 0:
				await interaction.message.channel.delete("Clips channel became empty")
			return True
		if not any([int(i.name) == selected_user.id for i in subjects]):
			channel = await CLIPS_CATEGORY.create_text_channel(str(selected_user.id), reason="User clip channel request")
		else:
			channel = [i for i in subjects if int(i.name) == selected_user.id][0]
		for clip in clips:
			await channel.send(f"Sent by: {interaction.user.name} ({interaction.user.id})\nAwaiting confirmation...", view=genericButtons(acceptFunc=accept, denyFunc=deny, removeButtonsAfter=True, acceptLabel="Accept", denyLabel="Delete", timeout=None), file=await clip.to_file())
		if medal_url:
			try:
				file = await genericUtil.medalDownload(medal_url)
			except LookupError as e:
				await interaction.edit_original_response(content=f"Something went wrong when trying to download the clip: {e}")
				return
			while Client.BOT.is_ws_ratelimited():
				await asyncio.sleep(0.5)
			try:
				await channel.send(f"Sent by: {interaction.user.name} ({interaction.user.id})\nAwaiting confirmation...", view=genericButtons(acceptFunc=accept, denyFunc=deny, removeButtonsAfter=True, acceptLabel="Accept", denyLabel="Delete", timeout=None), file=file)
			except HTTPException as e:
				if e.status == 413:
					await interaction.edit_original_response(content=f"The medal file appears to be too big")
					return
				raise
		await interaction.edit_original_response(content=f"Uploaded clip for {selected_user}.")

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

		config = Config.get(interaction.guild_id)
		if not config:
			await interaction.edit_original_response(content="Could not get guild configs. No changes were made.")
			return

		selected_user:Member = self.userCh.component.values[0]
		alias:str = self.userAlias.component.value
		CLIPS_CATEGORY = config.get_category(Config.GuildConfig.Categories.CLIPS)
		if CLIPS_CATEGORY is None:
			raise LookupError("Could not find the Clips category")
		subjects = CLIPS_CATEGORY.text_channels
		_logger.debug(f"Subjects: {subjects}")
		_logger.debug(f"Category: {CLIPS_CATEGORY}")
		if not any([int(i.name) == selected_user.id for i in subjects]):
			await interaction.edit_original_response(content="The selected user does not have a clip channel. Use the command `/upload_clip` to create one")
			return
		channel:TextChannel = [i for i in subjects if int(i.name) == selected_user.id][0]
		async def accept(interaction:Interaction):
			alias:str = interaction.message.content.split("\n")[1].strip('"').lower()
			await interaction.message.delete()
			await interaction.channel.edit(topic=(interaction.channel.topic+"\n" if interaction.channel.topic is not None else "")+f"{alias}")
			return True
		async def deny(interaction:Interaction):
			await interaction.message.delete()
			return True
		await channel.send(content=f"User '{interaction.user.name}' ({interaction.user.id}) suggested the following alias for user:\n\"{alias}\"\nAwaiting confirmation...", view=genericButtons(acceptFunc=accept, denyFunc=deny, acceptLabel="Add", denyLabel="Delete", timeout=None))
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
		await interaction.response.defer(thinking=True, ephemeral=True)

		config = Config.get(interaction.guild_id)
		if not config:
			await interaction.edit_original_response(content="Could not get guild configs. No changes were made.")
			return

		url:str = self.replayURL.component.value.strip().rstrip("/")
		report_category:Select = self.find_item(69)

		member = await Management.get(username=username)
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
		replay = ThunderAPI.replay(REPLAY_URL_REGEX.group(1))
		username:str = self.user.component.value.strip()
		report_msg:str = self.message.component.value.strip()
		if (_ := await Management.get(username=username)) is None or not any(i.status == Management.Entry.Status.MEMBER for i in _):


		if not isInReplay:
			await interaction.edit_original_response(content=f"The match you provided a link to does not have the user '{username}' in it.")
			return
		embed = discord.Embed(title=f"Report")
		embed.set_author(name=f"{interaction.user.name} (ID: {interaction.user.id})", icon_url=interaction.user.display_avatar.url)
		embed.add_field(name="WT username", value=username, inline=False)
		if report_msg:
			embed.add_field(name="Report message", value=report_msg, inline=False)
		embed.add_field(name="Category", value=report_category.values[0])
		embed.add_field(name="Evidence URL", value=url, inline=False)
		_logger.debug(f"Report from {interaction.user.name} ({interaction.user.id})\nWT username: {username}\nReport message: {report_msg}")
		await Client.BOT.get_channel(Client.BOT.channelIDs[ChannelIDs.SPAM]).send(embed=embed)
		await interaction.edit_original_response(content="Report submitted!")
	async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
		await interaction.edit_original_response(content='Oops! Something went wrong.')
		_logger.exception("An error occured while reporting", exc_info=error)

class callbackProtocol(Protocol):
	async def __call__(
		self,
		interaction: Interaction,
		**kwargs
	) -> bool|None: ...
class genericButtons(View):
	def __init__(self, *, acceptFunc:callbackProtocol, denyFunc:callbackProtocol|None=None, timeout:int|None = 180, acceptLabel:str = "Yes", denyLabel:str="No", deny:bool=True, removeButtonsAfter:bool=False, requiredPerms:Permissions|None=None, **kwargs):
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

class dataCheckView(discord.ui.LayoutView):

	def __init__(self, ):
		self.bracket = wtUtil.get_sqb_br(datetime.combine(_date, _time, UTC))
		self._1 = discord.ui.TextDisplay("The following data have been given, and the event will be created according to them. Are these correct?")
		self._2 = discord.ui.Section(
			discord.ui.TextDisplay(f"Start time: <t:{round(planned_start.timestamp())}:s>"),
			discord.ui.TextDisplay(f"End time: <t:{round(planned_end.timestamp())}:s>"),
			discord.ui.TextDisplay(f"Current BR: {bracket.br if bracket else "Could not retrieve BR data for the given date"}"),
			accessory=discord.ui.Button(
				style=discord.ButtonStyle.green,
				label="Yes"
			)
		)

		self._2.accessory.callback = self.acceptButton
		super().__init__(timeout=180)
	async def acceptButton(self, interaction:discord.Interaction):
		event = await guild.create_scheduled_event(
			name="[SQB] Scheduled session",
			description=f"Current BR: {self.bracket.br if self.bracket else 'Could not retrieve BR data for the given date'}\nCreated by: {interaction.user.name} ({interaction.user.id})",
			channel=guild.get_channel(Client.BOT.channelIDs[ChannelIDs.SQB]),
			entity_type=discord.EntityType.voice,
			privacy_level=discord.PrivacyLevel.guild_only,
			start_time=planned_start,
			end_time=planned_end
		)
		await interaction.response.send_message(f"The event can be found at the following place: {event.url}", ephemeral=True)
