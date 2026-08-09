import requests, aiohttp, asyncio, discord, logging, tempfile, re, subprocess
from typing import TYPE_CHECKING, Protocol
from os import path
from io import BytesIO
from json import loads
if TYPE_CHECKING:
	from utils.bot import Bot

MAX_FILE_SIZE = 8 * 1024 * 1024 # 8MB
logger = logging.getLogger(__name__)
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
				self.stop()
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
				self.stop()
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
	if image.size > MAX_FILE_SIZE:
		raise ValueError(f"File is too large to convert. The maximum supported size is {MAX_FILE_SIZE // (1024 * 1024)}MB.")
	try:
		image_data = await image.read()
	except discord.HTTPException as e:
		logger.error(f"Failed to download attachment {image.filename}: {e}")
		raise ValueError("The image could not be downloaded from Discord.")
	def encode() -> BytesIO:
		with tempfile.TemporaryDirectory() as tempdir:
			input_path = path.join(tempdir, f"input.{file_extension}")
			output_path = path.join(tempdir, "output.gif")
			with open(input_path, "wb") as f:
				f.write(image_data)
			try:
				subprocess.run(
					[
						"ffmpeg",
						"-hide_banner",
						"-loglevel", "error",
						"-i", input_path,
						"-filter_complex",
						"[0:v]format=rgba,split[a][b];"
						"[a]palettegen=max_colors=256[p];"
						"[b][p]paletteuse=dither=sierra2_4a",
						"-loop", "0",
						"-y",
						output_path,
					],
					check=True,
					capture_output=True,
					text=True,
					timeout=60,
				)
			except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
				logger.error(f"ffmpeg failed to convert {image.filename}: {e.stderr or e}")
				raise ValueError("The image could not be converted. It may be corrupt or in a format ffmpeg cannot decode.")
			except FileNotFoundError:
				logger.error("ffmpeg was not found, image conversion is unavailable")
				raise ValueError("Image conversion is currently unavailable.")
			with open(output_path, "rb") as file:
				return BytesIO(file.read())
	gif_data = await asyncio.to_thread(encode)
	if len(gif_data.getbuffer()) > MAX_FILE_SIZE:
		raise ValueError("The converted GIF is too large to upload.")
	return discord.File(gif_data, filename="PECK_bot_converted.gif")
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