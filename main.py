#General imports
import asyncio, logging
from logging.handlers import TimedRotatingFileHandler
from os import environ, getenv, path
# Custom packages
import shared
from bot.cogs import EXTENSIONS
from utils import newsAPI
from utils import management, network

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
logger.setLevel(logging.DEBUG if shared.DEBUG else logging.INFO)
logger.debug(f"In environment {environ.get('TERM_PROGRAM')}")
logging.getLogger("discord").setLevel(logging.WARNING)

__TOKEN = getenv("bot_token")
if __TOKEN is None:
	raise EnvironmentError("Bot Token could not be retrieved. Exiting...")

def main():
	# region Client setup
	loop = asyncio.new_event_loop()
	asyncio.set_event_loop(loop)
	# endregion
	try:
		loop.run_until_complete(shared._setupBot())
		loop.run_until_complete(
			asyncio.gather(
				management.upd_squadron_id(),
				network.start(), 
				shared.BOT.start(__TOKEN)
			)
		)
	except KeyboardInterrupt:
		logger.info("Shutting down due to Keyboard Interrupt...")
		loop.run_until_complete(network.close())
		if newsAPI._runtime is not None:
			newsAPI._runtime.cancel()
	except Exception:
		logger.exception("An exception occurred that caused the program to stall")
	finally:
		loop.close()
		exit(0)
if __name__ == "__main__" or __package__ is None:
	main()
