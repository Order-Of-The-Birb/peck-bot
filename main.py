#General imports
import discord, asyncio, logging
from contextlib import suppress
from logging.handlers import TimedRotatingFileHandler
from os import environ, getenv, chdir, path
from dotenv import load_dotenv
# Custom packages
from cogs import EXTENSIONS
from utils.bot import Bot
from modules.newsAPI import NewsAPI
from fastapi import FastAPI
import uvicorn

bot:'Bot' = None
def main():
	debug:bool
	# region Debug mode setup
	chdir(path.dirname(path.abspath(__file__)))
	if not load_dotenv(".env"):
		raise FileNotFoundError(".env file could not be loaded.")
	debug = int(getenv("DEBUG_MODE", "0")) == 1
	# endregion
	# region Logging
	def log_namer(default_name:str):
		dirname = path.dirname(default_name)
		filename = path.basename(default_name)
		_, _, date = filename.rpartition(".")
		return path.join(dirname, f"{date}.log")
	logger = logging.getLogger()
	handler = TimedRotatingFileHandler("logs/latest.log", when="midnight", interval=1, utc=True, backupCount=5)
	handler.suffix = "%Y-%m-%d"
	formatter = logging.Formatter(f"%(asctime)s:%(name)-{min(max(len(ext) for ext in EXTENSIONS), 30)}s:%(funcName)-15s:%(lineno)-3d:%(levelname)-7s:%(message)s", datefmt="%Y-%m-%d %H:%M:%S")
	handler.setFormatter(formatter)
	handler.namer = log_namer
	logger.addHandler(handler)
	logger.setLevel(logging.DEBUG if debug else logging.INFO)
	logger.debug(f"In environment {environ.get('TERM_PROGRAM')}")
	logging.getLogger("discord").setLevel(logging.WARNING)
	# endregion
	# region Client setup
	loop = asyncio.new_event_loop()
	asyncio.set_event_loop(loop)
	global bot
	bot = Bot(
		command_prefix='.pt ',
		intents=discord.Intents.all(),
		debug=debug,
		runtime=loop,
		logLevel=logger.getEffectiveLevel()
	)
	async def on_load():
		logger.info("Bot is getting ready...")
		bot.status = discord.Status.do_not_disturb
		bot.timeouts["ai"].run()
		bot.timeouts["clip"].run()
		bot.newsAPI=NewsAPI(bot)
		for extension in EXTENSIONS:
			try:
				await bot.load_extension(extension)
			except Exception:
				logger.exception(f"Failed to load extension '{extension}'")
				raise
		try:
			synced = await bot.tree.sync()
			logger.info(f"Synced {len(synced)} command(s)")
		except Exception:
			logging.exception("An error occured while syncing")
		logger.info("Startup complete")
	bot.setup_hook = on_load
	token = getenv("bot_token")
	if token is None:
		logging.critical("Bot Token could not be retrieved. Exiting...")
		return
	# endregion
	# region Cache invalidation
	app = FastAPI()
	@app.post("/invalidate-cache")
	async def invalidate():
		logger.debug("Received signal to invalidate cache")
		bot.db.refresh()
		return {"ok": True}
	config = uvicorn.Config(
		app,
		host="127.0.0.1",
		port=5000,
		log_level="warning",
		loop="asyncio"
	)
	api_server = uvicorn.Server(config)
	async def start_api():
		await api_server.serve()
	# endregion
	async def cleanup_resources():
		if bot is None:
			return
		for timeout in bot.timeouts.values():
			timeout.stop()
		if bot.newsAPI is not None:
			news_tasks = [
				task for task in (bot.newsAPI.periodicTask, bot.newsAPI.periodicChLogTask)
				if task is not None
			]
			for task in news_tasks:
				task.cancel()
			if news_tasks:
				await asyncio.gather(*news_tasks, return_exceptions=True)
			if bot.newsAPI.session is not None and not bot.newsAPI.session.closed:
				await bot.newsAPI.session.close()
				logger.debug("NewsAPI aiohttp session closed.")
		if not bot.is_closed():
			await bot.close()
	async def run_all():
		bot_task = loop.create_task(bot.start(token), name="discord-bot")
		api_task = loop.create_task(start_api(), name="cache-api")
		try:
			done, _ = await asyncio.wait({bot_task, api_task}, return_when=asyncio.FIRST_EXCEPTION)
			for task in done:
				task.result()
		finally:
			api_server.should_exit = True
			if not bot_task.done():
				bot_task.cancel()
			if not api_task.done():
				with suppress(asyncio.CancelledError):
					await api_task
			if not bot_task.done():
				with suppress(asyncio.CancelledError):
					await bot_task
			await cleanup_resources()
	run_task = loop.create_task(run_all())
	try:
		loop.run_until_complete(run_task)
	except KeyboardInterrupt:
		logger.info("Shutting down due to Keyboard Interrupt...")
		run_task.cancel()
		loop.run_until_complete(asyncio.gather(run_task, return_exceptions=True))
	except Exception:
		logger.exception("An exception occurred that caused the program to stall")
	finally:
		pending_tasks = [task for task in asyncio.all_tasks(loop) if not task.done()]
		for task in pending_tasks:
			task.cancel()
		if pending_tasks:
			loop.run_until_complete(asyncio.gather(*pending_tasks, return_exceptions=True))
		loop.run_until_complete(loop.shutdown_asyncgens())
		loop.close()
		exit(0)
if __name__ == "__main__" or __package__ is None:
	main()
