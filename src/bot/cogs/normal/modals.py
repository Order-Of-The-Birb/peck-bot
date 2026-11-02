import logging
import re

import discord

import bot.config as Config
import bot.client as Client
import utils.thunderapi as ThunderAPI

_logger = logging.getLogger(__name__)

__reload_deps__ = ("bot.config", "utils.thunderapi")

class ReportModal(discord.ui.Modal, title="Report user"):
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

class ReportView(discord.ui.LayoutView):
	content = discord.ui.Container(
		discord.ui.ActionRow(
			discord.ui.Select(
				id=1,
				placeholder="Select the offending user"
			)
		),
		discord.ui.ActionRow(
			discord.ui.Button(
				label="<",
				style=discord.ButtonStyle.primary,
				disabled=True,
				id=2
			),
			discord.ui.Button(
				label=">",
				style=discord.ButtonStyle.primary,
				disabled=False,
				id=3
			)
		)
	)
	config: Config.GuildConfig
	current_page: int = 1
	max_number: int = -1
	def __init__(self):
		super().__init__(timeout=600)
		self.find_item(1).callback = self.submit
		self.find_item(2).callback = self.pgdown
		self.find_item(3).callback = self.pgup
	@classmethod
	async def create(cls, interaction: Client.Interaction):
		self = cls()
		self.config = interaction.extras["config"]
		await self.change_page()
		return self
	async def submit(self, interaction: discord.Interaction):
		pass
	async def pgup(self, interaction: discord.Interaction):
		await interaction.response.defer()
		self.current_page += 1
		if self.max_number != -1 and self.current_page >= self.max_number:
			self.current_page = self.max_number -1
			self.find_item(3).disabled = True
			await interaction.edit_original_response(view=self)
			return
		self.find_item(2).disabled = False
		await self.change_page()
		await interaction.edit_original_response(view=self)
	async def pgdown(self, interaction: discord.Interaction):
		await interaction.response.defer()
		self.current_page -= 1
		if self.current_page == 1:
			self.find_item(2).disabled = True
		self.find_item(3).disabled = False
		await self.change_page()
		await interaction.edit_original_response(view=self)
	async def change_page(self):
		users = await self.config.management.query(self.current_page, status=Config.GuildConfig._Management.Entry.Status.MEMBER, per_page=25, sort_by=Config.GuildConfig._Management.SortFields.NAME)
		if not users and self.current_page != 1:
			self.current_page -= 1
			self.max_number = self.current_page-1
			self.find_item(3).disabled = True
			return
		if len(users) < 25:
			if self.max_number == -1:
				self.max_number = self.current_page
			self.find_item(3).disabled = True
		select: discord.ui.Select = self.find_item(1)
		select.options = [discord.SelectOption(label=f"{u.username} ({u.gaijin_id})", value=u.gaijin_id) for u in users]
