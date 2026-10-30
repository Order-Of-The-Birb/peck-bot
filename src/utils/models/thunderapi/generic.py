from datetime import datetime
from enum import IntEnum
from typing import Literal

from pydantic import BaseModel, Field


class NewsModel(BaseModel):
	class ImportanceLevel(IntEnum):
		REGULAR = 0
		MINOR = 1
		EVENT = 2
		MAJOR = 3
	class Image(BaseModel):
		src: str
		width: int
		height: int
	id:int
	anons:str # Short description
	title:str # Title
	link:str # URL
	pinned:bool
	images:list['Image'] # Attached images
	tags:set[Literal["Event", "Development", "Video", "Shop", "Fixed", "eSport", "Market", "Special", "Warbonds", "Fair Play", "Update"]] # Attached tags
	platforms:set[Literal["pc", "ps4", "ps5"]] # Affected platforms
	project:str # Game (100% of the time War Thunder with different version numbers)
	type:Literal["news", "changelog", "forum"] # Article Type
	created:datetime # Article Creation Time
	importance:ImportanceLevel

class ReplayResultsModel(BaseModel):
	class UserModel(BaseModel):
		class StatsModel(BaseModel):
			kills: int
			groundKills: int
			humanKills: int
			navalKills: int
			teamKills: int
			aiKills: int
			aiGroundKills: int
			aiNavalKills: int
			assists: int
			deaths: int
			captureZone: int
			damageZone: int
			score: int
			awardDamage: int
			missileEvades: int
			ammoInterceptions: int
		class LineupModel(BaseModel):
			class VehicleModel(BaseModel):
				rank: int
				battlerating: float
			vehicles: dict[str, VehicleModel] = Field(
				description="Vehicles in the lineup of the player. Key is the internal name of the vehicle, such as `germ_leopard_2pl`",
				examples=[
				{
					"ef_2000_block_10": {
						"rank": 9,
						"battlerating": 13.3
					},
				}, {
					"germ_leopard_2pl": {
						"rank": 8,
						"battlerating": 11.3
					},
				}, {
					"tiger_had_spain": {
						"rank": 7,
						"battlerating": 9.7
					}
				}]
			)
			maxBr: float = Field(description="Maximum battle rating of the user's lineup", examples=[6.7, 8.0, 9.7])
		clanTag: str | None = Field(default=None, description="Clan tag of the user, if applicable. Includes border", examples=["┾PECK┿", ""])
		userId: int
		autosquad: bool = Field(description="Whether the user was assigned into a squad automatically")
		squadId: int = Field(description="Squad ID of the user. Number is still generated if not in a squad. Looks like 4000+ are players playing alone", examples=[1001, 1002, 1000, 4096, 4097, 4098])
		stats: StatsModel
		lineup: LineupModel

	team1: dict[str, UserModel]
	team2: dict[str, UserModel]
