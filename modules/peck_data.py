"""Run the read-only Peck tool endpoints separately from the Discord bot."""

import asyncio
from contextlib import asynccontextmanager, suppress
from typing import Annotated

import aiohttp
from fastapi import FastAPI, HTTPException, Query, Request

from modules.peck_leaderboard import get_sqb_leaderboard
from modules.peck_sqb import get_sqb_today
from modules.peck_vehicles import get_vehicle_br, maintain_vehicle_catalog


@asynccontextmanager
async def _lifespan(app: FastAPI):
    async with aiohttp.ClientSession(cookie_jar=aiohttp.DummyCookieJar()) as session:
        app.state.wiki_session = session
        refresh = asyncio.create_task(maintain_vehicle_catalog(session))
        try:
            yield
        finally:
            refresh.cancel()
            with suppress(asyncio.CancelledError):
                await refresh


app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=_lifespan)


@app.get("/healthz")
async def health() -> dict:
    return {"service": "peck-data"}


@app.get("/v1/sqb/today")
async def sqb_today(timezone: Annotated[str, Query(min_length=1, max_length=64)] = "UTC") -> dict:
    try:
        return await get_sqb_today(timezone=timezone)
    except ValueError:
        raise HTTPException(status_code=422, detail="Use an IANA timezone or UTC offset.") from None


@app.get("/v1/vehicles/br")
async def vehicle_br(request: Request, vehicle: Annotated[str, Query(min_length=2, max_length=80)]) -> dict:
    return await get_vehicle_br(request.app.state.wiki_session, vehicle)


@app.get("/v1/sqb/leaderboard")
async def sqb_leaderboard(limit: Annotated[int, Query(ge=1, le=10)] = 8) -> dict:
    return await get_sqb_leaderboard(limit)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=5001)
