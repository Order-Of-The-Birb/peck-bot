from datetime import datetime, timedelta, UTC, time
from dateutil.parser import isoparse
from enum import StrEnum
from discord.ext import tasks
import bot.client

sqb_brackets = (
	(
		time(hour=1, minute=0),
		time(hour=7, minute=0)
	),
	(
		time(hour=14, minute=0),
		time(hour=22, minute=0)
	)
)

class timestampTypes(StrEnum):
	SHORT_TIME = "t"
	LONG_TIME = "T"
	SHORT_DATE = "d"
	LONG_DATE = "D"
	LONG_DATE_SHORT_TIME = "f"
	DATE_WEEKDAY_TIME = "F"
	RELATIVE = "R"

def toUnix(time:datetime|str):
	return int((isoparse(time) if isinstance(time, str) else time).timestamp())
def discord_timestamp(timestamp:int|datetime, type:timestampTypes) -> str:
	""" <t:UNIX TIMESTAMP:type>
	## Types
	- Short Time: t
	- Long Time: T
	- Short Date: d
	- Long Date: D
	- Long Date with Short Time: f
	- Long Date with Day of week and Short Time: F
	- Relative: R
	"""
	if isinstance(timestamp, datetime):
		return f"<t:{toUnix(timestamp)}:{type}>"
	return f"<t:{timestamp}:{type}>"
def get_sqb_timebracket(include_current:bool=True) -> tuple[datetime, datetime]:
	rn = datetime.now(UTC)
	global sqb_brackets
	today_brackets = [
		(
			datetime.combine(rn.date(), start, tzinfo=UTC),
		 	datetime.combine(rn.date(), end, tzinfo=UTC)
		)
		for start, end in sqb_brackets
	]
	if include_current:
		for start, end in today_brackets: # Currently IN the bracket
			if start <= rn < end:
				return start, end
	future_brackets = [(start, end) for start, end in today_brackets if start > rn] # Find next bracket
	if future_brackets:
		return min(future_brackets, key=lambda r: r[0])
	return today_brackets[0][0]+timedelta(days=1), today_brackets[0][1]+timedelta(days=1)
def isInTimebracket(bracket:tuple[datetime]|None=None) -> bool:
	if bracket is None:
		bracket = get_sqb_timebracket()
	return bracket[0] <= datetime.now(UTC) < bracket[1]

class GenericTimeout:
	cleanupTask:tasks.Loop
	expiry:timedelta
	def __init__(self, timeout_after:int=3, expires_after:timedelta = timedelta(minutes=5)):
		self.timeoutCount:int = timeout_after
		self.cooldowns:dict[int, list[datetime]] = {}
		self.expiry	= expires_after

		self.cleanupTask = self.cleanup
	def isTimedOut(self, user_id:int) -> bool:
		return len(self.cooldowns.get(user_id, [])) >= self.timeoutCount
	def getOldest(self, user_id:int) -> datetime|None:
		tmp = self.cooldowns.get(user_id)
		return min(tmp) if tmp else None
	def add(self, user_id:int):
		now = datetime.now(UTC)
		self.cooldowns.setdefault(user_id, []).append(now)
	def getExpireTime(self, user_id: int) -> datetime | None:
		oldest = self.getOldest(user_id)
		if oldest is None:
			return None

		expire_time = oldest + self.expiry

		next_iter = self.cleanupTask.next_iteration
		if next_iter is not None:
			expire_time = max(expire_time, next_iter)

		return expire_time
	# region Integrated Loop
	@tasks.loop(minutes=1)
	async def cleanup(self):
		rn = datetime.now(UTC)
		for user, entries in list(self.cooldowns.items()):
			new = [e for e in entries if rn - e < self.expiry]
			if new:
				self.cooldowns[user] = new
			else:
				self.cooldowns.pop(user, None)
	@cleanup.before_loop
	async def _beforeCleanup(self):
		await bot.client.BOT.wait_until_ready()
	def stop(self):
		if self.cleanupTask:
			self.cleanupTask.cancel()
	def run(self):
		if self.cleanupTask:
			self.cleanupTask.start()
	# endregion
