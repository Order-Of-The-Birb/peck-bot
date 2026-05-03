import requests, aiohttp, random, asyncio, discord, logging, tempfile, re, subprocess
from typing import TYPE_CHECKING, Protocol
from os import path
from json import loads
if TYPE_CHECKING:
	from utils.bot import Bot

MAX_FILE_SIZE = 8 * 1024 * 1024 # 8MB
class callbackProtocol(Protocol):
	async def __call__(
		self,
		interaction: discord.Interaction,
		**kwargs
	) -> bool|None: ...
class genericButtons(discord.ui.View):
	def __init__(self, *, acceptFunc:callbackProtocol, denyFunc:callbackProtocol|None=None, timeout:int|None = 180, acceptLabel:str = "Yes", denyLabel:str="No", deny:bool=True, removeButtonsAfter:bool=False, requiredPerms:discord.Permissions|None=None, **kwargs):
		self._logger = logging.getLogger(__name__)
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
		async def yes_callback(interaction: discord.Interaction):
			await interaction.response.edit_message(view=self)
			if self.requiredPerms is not None and not all(getattr(interaction.user.guild_permissions, p[0], False) for p in self.requiredPerms if p[1]):
				self._logger.warning(f"Accept attempt by: {interaction.user.name} ({interaction.user.id})")
				await interaction.followup.send("You do not have the required permission to use this!", ephemeral=True)
				return
			result = await acceptFunc(interaction, **kwargs)
			if result:
				yes.disabled = True
				if deny:
					no.disabled = True
				if removeButtonsAfter:
					await interaction.edit_original_response(view=None)
		async def no_callback(interaction: discord.Interaction):
			await interaction.response.edit_message(view=self)
			if self.requiredPerms is not None and not all(getattr(interaction.user.guild_permissions, p[0], False) for p in self.requiredPerms if p[1]):
				self._logger.warning(f"Deny attempt by: {interaction.user.name} ({interaction.user.id})")
				await interaction.followup.send("You do not have the required permission to use this!", ephemeral=True)
				return
			result = await denyFunc(interaction, **kwargs)
			if result:
				yes.disabled = True
				no.disabled = True
				if removeButtonsAfter:
					await interaction.edit_original_response(view=None)
		yes.callback = yes_callback
		no.callback = no_callback
		self.add_item(yes)
		if deny and denyFunc is not None:
			self.add_item(no)

def httperror(response:requests.Response|aiohttp.ClientResponse) -> str:
	if isinstance(response, aiohttp.ClientResponse):
		return requests.status_codes._codes[response.status][0]
	return requests.status_codes._codes[response.status_code][0]
async def convertImageToGif(image:discord.Attachment) -> discord.File:
	allowed_types = ["png", "jpg", "jpeg", "webp"]
	file_extension = image.filename.split(".")[-1].lower()
	if not file_extension in allowed_types:
		raise ValueError(f"File was not provided in a supported format.\nThe following formats are supported: {", ".join(allowed_types)}")
	with tempfile.TemporaryDirectory() as tempdir:
		input_path = path.join(tempdir, f"input.{image.filename.split(".")[-1]}")
		output_path = path.join(tempdir, "output.gif")
		with open(input_path, "wb") as f:
			f.write(await image.read())
		subprocess.run(
			[
				"ffprobe", 
				"-v", "error", 
				"-select_streams", "v:0", 
				"-of", "json", 
				input_path
			]
		)
		subprocess.run(
			[
				"ffmpeg", 
				"-i", input_path, 
				"-frames:v", "1",
				output_path
			]
		)
		return discord.File(output_path, filename="PECK_bot_converted.gif")
def demarkdownify(text:str):
	replace_list = ["_", "*", "#", "~", "`", "|"]
	for i in replace_list:
		text = text.replace(i, "\\"+i)
	return text
# region Media Downloaders
async def medalDownload(share_url:str) -> discord.File:
	URL_REGEX = re.compile(r"https://medal.tv/games/.+/clips/.+")
	if URL_REGEX.fullmatch(share_url) is None: raise LookupError(f"Given Medal URL is invalid.")
	async with aiohttp.ClientSession() as session:
		async with session.get(share_url) as response:
			if response.status != 200: 
				raise LookupError(f"Medal website returned {response.status} ({httperror(response)})")
			html = await response.text()
		file_url = None
		if '"contentUrl":"' in html:
			file_url = html.split('"contentUrl":"')[1].split('","')[0]
		if not file_url: 
			raise LookupError("Could not find download URL in website")
		with tempfile.TemporaryDirectory() as tmpdir:
			input_path = path.join(tmpdir, "input.mp4")
			output_path = path.join(tmpdir, "output.mp4")
			async with session.get(file_url) as r:
				with open(input_path, "wb") as f:
					async for chunk in r.content.iter_chunked(1024 * 1024):
						f.write(chunk)
			# Get duration using ffprobe
			probe = subprocess.run(
				[
					"ffprobe",
					"-v", "error",
					"-select_streams", "v:0",
					"-show_entries", "format=duration",
					"-of", "json",
					input_path
				],
				capture_output=True,
				text=True
			)

			duration = float(loads(probe.stdout)["format"]["duration"])
			# Discord 10 MB limit
			target_bits = 10 * 1024 * 1024 * 8
			total_bitrate = int(target_bits / duration)
			# Reserve some bitrate for audio
			audio_bitrate = 128_000
			video_bitrate = max(total_bitrate - audio_bitrate, 300_000)
			# Compress
			subprocess.run(
				[
					"ffmpeg", "-y",
					"-i", input_path,
					"-c:v", "libx264",
					"-b:v", str(video_bitrate),
					"-maxrate", str(video_bitrate),
					"-bufsize", str(video_bitrate * 2),
					"-c:a", "aac",
					"-b:a", str(audio_bitrate),
					output_path
				],
				check=True
			)
			return discord.File(output_path, filename="clip.mp4")
# endregion