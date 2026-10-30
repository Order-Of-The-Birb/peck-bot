import asyncio
import logging
import re
import subprocess
import tempfile
from io import BytesIO
from json import loads
from os import path

import aiohttp
import anyio
import discord
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

async def convertImageToGif(guild: discord.Guild, image:discord.Attachment, name_appendix: str | None = None) -> discord.File:
	allowed_types = ["png", "jpg", "jpeg", "webp"]
	file_extension = image.filename.split(".")[-1].lower()
	if file_extension not in allowed_types:
		raise ValueError(f"File was not provided in a supported format.\nThe following formats are supported: {", ".join(allowed_types)}")
	if image.size > guild.filesize_limit:
		raise ValueError(f"File is too large to convert. The maximum supported size is {guild.filesize_limit // (1024 * 1024)}MB.")
	try:
		image_data = await image.read()
	except discord.HTTPException as e:
		logger.error(f"Failed to download attachment {image.filename}: {e}")
		raise ValueError("The image could not be downloaded from Discord.") from e
	async def encode() -> BytesIO:
		with tempfile.TemporaryDirectory() as tempdir:
			input_path = path.join(tempdir, f"input.{file_extension}")
			output_path = path.join(tempdir, "output.gif")
			async with await anyio.open_file(input_path, "wb") as f:
				f.write(image_data)
			try:
				await asyncio.to_thread(
					subprocess.run
					[
						"ffmpeg",
						"-hide_banner",
						"-loglevel", "error",
						"-i", input_path,
						"-filter_complex",
						(
							"[0:v]format=rgba,split[a][b];"
							"[a]palettegen=max_colors=256[p];"
							"[b][p]paletteuse=dither=sierra2_4a"
						),
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
				raise ValueError("The image could not be converted. It may be corrupt or in a format ffmpeg cannot decode.") from e
			except FileNotFoundError as e:
				logger.error("ffmpeg was not found, image conversion is unavailable")
				raise ValueError("Image conversion is currently unavailable.") from e
			# Reject oversized output before allocating a buffer for the whole GIF.
			if await asyncio.to_thread(path.getsize, output_path) > guild.filesize_limit:
				raise ValueError("The converted GIF is too large to upload.")
			async with await anyio.open_file(output_path, "rb") as file:
				return BytesIO(file.read())
	gif_data = await encode()
	if len(gif_data.getbuffer()) > guild.filesize_limit:
		raise ValueError("The converted GIF is too large to upload.")
	if name_appendix:
		filename = f"PECK_bot_converted_{name_appendix}.gif"
	else:
		filename = "PECK_bot_converted.gif"
	return discord.File(gif_data, filename=filename)
# region Media Downloaders
async def medalDownload(guild: discord.Guild, share_url:str) -> discord.File:
	URL_REGEX = re.compile(r"https://medal.tv/games/.+/clips/.+")
	if URL_REGEX.fullmatch(share_url) is None:
		raise LookupError("Given Medal URL is invalid.")
	async with aiohttp.ClientSession() as session:
		async with session.get(share_url) as response:
			if response.status != 200:
				raise LookupError(f"Medal website returned {response.status}")
			raw = await response.text()
		html = BeautifulSoup(raw, "html.parser")
		title = "-".join(html.select_one("title").get_text().split("-")[:-1]).replace(" ", "_").lower()
		file_url = None
		if '"contentUrl":"' in raw:
			file_url = raw.split('"contentUrl":"')[1].split('","')[0]
		if not file_url:
			raise LookupError("Could not find download URL in website")
		with tempfile.TemporaryDirectory() as tmpdir:
			input_path = path.join(tmpdir, "input.mp4")
			output_path = path.join(tmpdir, "output.mp4")
			async with session.get(file_url) as r, await anyio.open_file(input_path, "wb") as f:
				async for chunk in r.content.iter_chunked(1024 * 1024):
					f.write(chunk)
			# Get duration using ffprobe
			probe = await asyncio.to_thread(
				subprocess.run,
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
			target_bits = guild.filesize_limit * 8
			total_bitrate = int(target_bits / duration)
			# Reserve some bitrate for audio
			audio_bitrate = 128_000
			video_bitrate = max(total_bitrate - audio_bitrate, 300_000)
			# Compress
			await asyncio.to_thread(
				subprocess.run
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
			return discord.File(output_path, filename=f"{title}.mp4")
# endregion
