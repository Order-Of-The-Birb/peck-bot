from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class MemberModel(BaseModel):
	class enumModel(BaseModel):
		name: str
		value: int
	uid: int
	nickname: str
	rank: enumModel
	platform: enumModel | None = None
	max_unit_rank: int | None = None
	accepted_by: int | None = None
	accepted_by_nick: str | None = None
	joined_at: int
class ApplicantModel(BaseModel):
	uid: int
	nickname: str
	timestamp: int
	comment: str
	class GeolocationDataModel(BaseModel):
		offset: float
		country: str
		city: str
	geo:GeolocationDataModel = Field(default=None)

class ClanModel(BaseModel):
	model_config = ConfigDict(extra="allow")

	pos: int | None = None
	id: int | None = None
	autoaccept: bool | None = None
	cdate: int | None = None
	changed_by_uid: int | None = None
	changed_time: int | None = None
	creator_uid: int | None = None
	desc: str | None = None
	members_cnt: int | None = None
	name: str | None = None
	region: str | None = None
	slogan: str | None = None
	status: str | None = None
	tag: str | None = None
	members: list[MemberModel] | None = None
	applicants: list[ApplicantModel] | None = Field(default=None, exclude_if=lambda x: x is None)

class ClanSearchModel(BaseModel):
	id: int
	name: str
	tag: str
	members: list[MemberModel]
	desc: str
	slogan: str
	region: str

class SQBTimeBracket(BaseModel):
	start: datetime
	end: datetime
	br: float

class CurrentSQBBracket(BaseModel):
	bracket: SQBTimeBracket
	start: datetime
	end: datetime

class ClanLeaderboardModel(BaseModel):
	class ClanStatsModel(BaseModel):
		rating: int
		flight_time: float
		air_kills: int
		ground_kills: int
		battles: int
		wins: int
		deaths: int
		activity: int
	id: int
	pos: int
	stats: ClanStatsModel
	name: str
	tag: str
