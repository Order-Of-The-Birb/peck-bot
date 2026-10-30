from pydantic import BaseModel, Field


class ItemModel(BaseModel):
	hash_name: str = Field(description="The internal name of the item", examples=["ugcitem_1000574", "Object 279 (USSR)", "id50257_object_292_ussr"])
	name: str = Field(description="The display name of the item", examples=["Object 279 'Sledgehammer'", "Object 279 (USSR)", "Object 292 (USSR)"])
	commodity: bool
	icon: str = Field(description="The URL to the icon of said item")
	buy_price: float = Field(description="The highest 'buy' price")
	buy_orders: int = Field(description="The amount of buy orders on this item")
	sell_price: float = Field(description="The lowest 'sell' price")
	sell_orders: int = Field(description="The amount of sell orders on this item")
	tags: dict = Field(description="The tags associated with this item", examples=[
		{
			"type": "skin",
			"quality": "junk",
			"vehicleType": "tank",
			"country": "ussr",
			"inGamePreview": True,
			"eventName": "camo_trophy_2_37",
			"authenticity": "fictional"
		},
		{
			"type": "tank",
			"quality": "ultraRare",
			"country": "ussr",
			"inGamePreview": True
		},
	])

class OrderHistoryModel(BaseModel):
	class HistoryModel(BaseModel):
		timestamp: int
		price: float
		transactions_count: int
	short: list[HistoryModel]
	whole: list[HistoryModel]

class OrdersModel(BaseModel):
	class PriceModel(BaseModel):
		price: float
		amount: int
	buy_orders: int
	sell_orders: int
	buy_prices: list[PriceModel]
	sell_prices: list[PriceModel]
