from datetime import date, datetime

from pydantic import BaseModel, Field


class GetModel(BaseModel):
	class _clanDataModel(BaseModel):
		name: str
		tag: str
		type: int
		role: int
		id: int

	class _playerLevelModel(BaseModel):
		title: str
		level: int

	nick: str
	last_login: date
	registered_at: datetime
	id: int
	rank: _playerLevelModel
	clan: _clanDataModel | None = Field(default=None, exclude_if=lambda x: x is None)
	numEliteUnits: int
	penaltyStatus: str

class TerseModel(BaseModel):
	clanName: str = Field(default=None, description="Name of the clan the user is in, if applicable", examples=["Order Of The Birb", ""], exclude_if=lambda x: x is None)
	clanTag: str = Field(default=None, description="Clan tag of the clan the user is in, if applicable. Includes border. Key doesn't exist if user is not in a clan", examples=["┾PECK┿"], exclude_if=lambda x: x is None)
	username: str
