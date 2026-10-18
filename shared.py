import discord, logging
from asyncio import get_running_loop
from utils.bot import Bot
from dotenv import load_dotenv
from os import getenv
from dataclasses import dataclass
from enum import StrEnum
from datetime import timedelta, datetime, UTC

_logger = logging.getLogger() 

if not load_dotenv(".env"):
	raise FileNotFoundError(".env file could not be loaded.")
DEBUG: bool = int(getenv("DEBUG_MODE", "0")) == 1

BOT: 'Bot' = None

# region ID Enums
class ChannelIDs(StrEnum):
	LOGS = "logs"
	SPAM = "spam"
	ANNOUNCEMENTS = "announcements"
	SQB = "sqb"
	WTNEWS = "wtNews"
	SCORE = "score"
	PROPAGANDA = "propaganda"
	AUDIT_LOG = "auditLog"
class RoleIDs(StrEnum):
	MEMBER = "member"
	PING = "ping"
	OLD_TIMER = "oldTimer"
	RETIRED = "retired"
	MAJOR_NEWS = "majorNews"
	EVENT_NEWS = "eventNews"
	APPLICANT = "applicant"
class CategoryIDs(StrEnum):
	CLIPS = "clips"
	SQUAD_VC = "squadVC"
# endregion
# region Bot IDs static Config
@dataclass(frozen=True)
class _GuildConfig:
	channel_ids: dict[ChannelIDs, int]
	role_ids: dict[RoleIDs, int]
	category_ids: dict[CategoryIDs, int]
	common_roles: tuple[int, ...]
	peck_server: int
	sqb_plan_check_limit: timedelta
	authority_role_ids: tuple[int, ...]

GUILD_CONFIGS = {
	917850361019125820: _GuildConfig(
		channel_ids={
			ChannelIDs.LOGS: 1229136570498682900,
			ChannelIDs.SPAM: 1229136570498682900,
			ChannelIDs.ANNOUNCEMENTS: 931263111992848395,
			ChannelIDs.SQB: 1353122797504827422,
			ChannelIDs.WTNEWS: 920311640161943552,
			ChannelIDs.SCORE: 1125129523499896974,
			ChannelIDs.PROPAGANDA: 1066119609914232842,
			ChannelIDs.AUDIT_LOG: 1490460729994641408,
		},
		role_ids={
			RoleIDs.MEMBER: 919803983286128661,
			RoleIDs.PING: 1065769588849115248,
			RoleIDs.OLD_TIMER: 917946204736860190,
			RoleIDs.RETIRED: 983021494739292250,
			RoleIDs.MAJOR_NEWS: 1476690321051222119,
			RoleIDs.EVENT_NEWS: 1489360745039921222,
			RoleIDs.APPLICANT: 1184950087873466438,
		},
		category_ids={
			CategoryIDs.CLIPS: 1428798448102277263,
			CategoryIDs.SQUAD_VC: 917850361019125821,
		},
		common_roles=(917852847482232852, 923683349611053106),
		peck_server=917850361019125820,
		sqb_plan_check_limit=timedelta(minutes=30),
		authority_role_ids=(
			917852215014727742,  # The Birbman
			917944202015408189, # Deputy
			917945129921302599, # Officer
			918571367027322890, # Administr8ors
			1185637328446816299 # Emergency Admin
		)
	),
	685948316541779974: _GuildConfig(
		channel_ids={
			ChannelIDs.LOGS: 1453040931703095550,
			ChannelIDs.SPAM: 1453040954343821513,
			ChannelIDs.ANNOUNCEMENTS: 1453040983934767277,
			ChannelIDs.SQB: 1453041059746676837,
			ChannelIDs.WTNEWS: 1453041016969101458,
			ChannelIDs.SCORE: 1456770254972784780,
			ChannelIDs.PROPAGANDA: 1456788537755045931,
			ChannelIDs.AUDIT_LOG: 1490460729994641408,
		},
		role_ids={
			RoleIDs.MEMBER: 1073297853587398696,
			RoleIDs.PING: 1456660597616803956,
			RoleIDs.OLD_TIMER: 1454228913742938112,
			RoleIDs.RETIRED: 1456971952165093467,
			RoleIDs.MAJOR_NEWS: 1476690625612222647,
			RoleIDs.EVENT_NEWS: 1489360453233541170,
			RoleIDs.APPLICANT: 1477308945759735900,
		},
		category_ids={
			CategoryIDs.CLIPS: 1454228135280119982,
			CategoryIDs.SQUAD_VC: 1453040903626293338,
		},
		common_roles=(1124647932696743948,),
		peck_server=685948316541779974,
		sqb_plan_check_limit=timedelta(minutes=2),
		authority_role_ids=(
			1477307536305557516, # Testing server Officer
		)
	)
}
# endregion
# region Bot dynamic values
@dataclass(slots=True)
class SquadVC:
	def __init__(self):
		self.channels:list['SquadVC.SquadVCData'] = []
		self.checkDelay:int = 0
	
	class SquadVCData:
		_id:int
		last_seen_person_time:float
		owner:int|None
		created:float
	
	def add(self, channel:discord.VoiceChannel, owner: int|discord.Member):
		if any(i._id == channel.id for i in self.channels):
			return None
		owner = owner if isinstance(owner, int) else owner.id
		self.channels.append(
			self.SquadVCData(
				channel.id,
				datetime.now(UTC).timestamp(),
				owner,
				channel.created_at
			)
		)

@dataclass(slots=True)
class _guildValues:
	squad_vcs: SquadVC
GUILD_VALUES = {
	917850361019125820: _guildValues(
		squad_vcs=[

		]
	)
}
# endregion

YOSHINO_ID: int = 332030423913725953
ICON_URL: str ='https://cdn.discordapp.com/icons/917850361019125820/325129a273dac84e31f9aa5de51f1936.png?size=128'
RUNNING_SINCE: datetime = datetime.now(UTC)

async def _setupBot():
	global BOT
	loop = get_running_loop()

	intents = discord.Intents.all()
	# No features consume member presence or typing updates. Keep member and
	# message caches for role lookups and edit/delete audit logs.
	intents.presences = False
	intents.typing = False
	BOT = Bot(
		command_prefix='.pt ',
		intents=intents,
		debug=DEBUG,
		runtime=loop,
		logLevel=_logger.getEffectiveLevel()
	)