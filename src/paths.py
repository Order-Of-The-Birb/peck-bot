from pathlib import Path
from dotenv import load_dotenv
from os import getenv

if not load_dotenv(Path(__file__).parent.parent / ".env"):
	raise FileNotFoundError(".env file could not be loaded.")
DEBUG: bool = int(getenv("DEBUG_MODE", "0")) == 1

DATA = Path("/data") if not DEBUG else Path(__file__).parent.parent / "data"

GUILDS = DATA / "guilds"
LOGS = DATA / "logs"
