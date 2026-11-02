import asyncio

import discord

import bot.client as Client
import bot.config as Config
import utils.helper as helperUtil


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

class CreateClip(discord.ui.Modal, title="Propose new clip"):
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

		voting_thread, _ = await setup_channel(clips_channel, user)
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

class CreateAlias(discord.ui.Modal, title="Propose new alias"):
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

		voting_thread, _ = await setup_channel(clips_channel, selected_user)
		msg = await voting_thread.send(
			content=f"## Alias vote\nProposed by: {interaction.user.mention}\nProposed for: {selected_user.mention}\nAlias: \"{alias}\"\nAwaiting vote..."
		)
		await msg.add_reaction(interaction.client.get_emoji(1277999470038220902))
		await asyncio.sleep(0.2)
		await msg.add_reaction(interaction.client.get_emoji(1277999500262244362))
		await interaction.edit_original_response(content=f"Alias for {selected_user.mention} has been cast to vote.")

class RemoveAlias(discord.ui.LayoutView):
	#TODO: Implement alias removal view
	pass
