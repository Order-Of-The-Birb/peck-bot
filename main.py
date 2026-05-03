#General imports
import discord, asyncio, logging
from logging.handlers import TimedRotatingFileHandler
from os import environ, getenv, chdir, path
from dotenv import load_dotenv
from uvicorn import server
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
	debug = environ.get('TERM_PROGRAM') == 'vscode'
	if not debug:
		from argparse import ArgumentParser
		parser = ArgumentParser()
		parser.add_argument("-d", "--debug", help="Debug mode switch", action="store_true")
		debug = parser.parse_args().debug
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
	chdir(path.dirname(path.abspath(__file__)))
	if not load_dotenv(".env"):
		logger.critical(".env file could not be loaded.")
		return
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
	async def start_api():
		config = uvicorn.Config(
			app,
			host="127.0.0.1",
			port=5000,
			log_level="warning",
			loop="asyncio"
		)
		server = uvicorn.Server(config)
		await server.serve()
	# endregion
	async def run_all():
		await asyncio.gather(bot.start(token), start_api())
	try:
		loop.run_until_complete(run_all())
	except KeyboardInterrupt:
		logger.info("Shutting down due to Keyboard Interrupt...")
		if bot is not None and bot.newsAPI is not None:
			if bot.newsAPI.session is not None and not bot.newsAPI.session.closed:
				loop.run_until_complete(bot.newsAPI.session.close())
				logger.debug("NewsAPI aiohttp session closed.")
			if bot.newsAPI.periodicTask is not None:
				bot.newsAPI.periodicTask.cancel()
			if bot.newsAPI.periodicChLogTask is not None:
				bot.newsAPI.periodicChLogTask.cancel()
	except Exception:
		logger.exception("An exception occurred that caused the program to stall")
	finally:
		loop.close()
		exit(0)
if __name__ == "__main__" or __package__ is None:
	main()
