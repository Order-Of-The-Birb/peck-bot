import asyncio
import json
from contextlib import suppress
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from modules import peck_vehicles


def _catalog(*rows, premium_status=1):
    return f"""
        <script>window.WT_UnitList = '{json.dumps(rows)}';</script>
        <button data-status-id="0"><div class="unit-filter_status-block regular"></div></button>
        <button data-status-id="{premium_status}"><div class="unit-filter_status-block premium"></div></button>
        <button data-status-id="2"><div class="unit-filter_status-block squadron"></div></button>
    """


def _ground_card(rating):
    return f"""
        <div class="game-unit_title"><span class="game-unit_nation">Ground Vehicles</span></div>
        <div class="game-unit_card-info"><div class="game-unit_br">
            <div class="game-unit_br-item"><span class="mode">RB</span><span class="value">{rating}</span></div>
        </div></div>
    """


class VehicleLookupTests(IsolatedAsyncioTestCase):
    def setUp(self):
        self.pages = {
            "/aviation": _catalog(
                ["f_2a", "F-2A", "japan", 8, {}, 0],
                ["f_2a_adtw", "F-2A\u00a0ADTW", "japan", 8, {}, 1],
                ["f2a-1", "F2A-1", "usa", 1, {}, 1],
                ["f_20a", "F-20A", "usa", 8, {}, 1],
                ["bf-109f-2", "Bf 109 F-2", "germany", 2, {}, 0],
            ),
            "/ground": _catalog(
                ["ussr_bmpt", "BMPT", "ussr", 7, {}, 0],
                ["ussr_bmpt_72", "BMPT-72", "ussr", 7, {}, 1],
            ),
            "/unit/f_2a_adtw": """
                <div class="game-unit_card-info"><div class="game-unit_br">
                    <div id="unit-br-air"><div class="game-unit_br-item">
                        <span class="mode">RB</span><span class="value">13.0</span>
                    </div></div>
                    <div id="unit-br-tank"><div class="game-unit_br-item">
                        <span class="mode">RB</span><span class="value">12.0</span>
                    </div></div>
                </div></div>
            """,
            "/unit/ussr_bmpt": _ground_card("12.0"),
        }
        self.enterContext(patch.object(peck_vehicles, "_CATALOG_PATHS", ("/aviation", "/ground")))
        self.enterContext(patch.object(peck_vehicles, "_catalog_cache", {}))
        self.enterContext(patch.object(peck_vehicles, "_catalog_lock", asyncio.Lock()))
        self.fetch = self.enterContext(patch.object(peck_vehicles, "_fetch", AsyncMock(side_effect=self._page)))

    async def _page(self, session, path):
        if path not in self.pages:
            raise peck_vehicles._WikiError("HTTP 503")
        return self.pages[path]

    async def test_qualified_vehicle_uses_the_current_card_and_catalog_is_cached(self):
        result = await peck_vehicles.get_vehicle_br(None, "F-2 Premium from Japan")
        self.assertEqual(result["vehicle"], "F-2A ADTW")
        self.assertEqual(result["battle_ratings"], {"air": {"RB": "13.0"}, "ground": {"RB": "12.0"}})
        self.assertEqual(result["source_url"], "https://wiki.warthunder.com/unit/f_2a_adtw")

        result = await peck_vehicles.get_vehicle_br(None, "BMP-T")
        self.assertEqual(result["vehicle_id"], "ussr_bmpt")
        self.assertEqual(result["battle_ratings"], {"ground": {"RB": "12.0"}})
        paths = [call.args[1] for call in self.fetch.await_args_list]
        self.assertEqual(paths.count("/aviation"), 1)
        self.assertEqual(paths.count("/ground"), 1)

    async def test_short_designation_returns_only_relevant_variants(self):
        result = await peck_vehicles.get_vehicle_br(None, "F-2")
        self.assertEqual(result["status"], "ambiguous")
        self.assertEqual({candidate["vehicle"] for candidate in result["candidates"]}, {"F-2A", "F-2A ADTW"})
        result = await peck_vehicles.get_vehicle_br(None, "F-2 premium from Germany")
        self.assertEqual(result, {"status": "not_found"})

    async def test_premium_status_follows_the_wiki_filter(self):
        self.pages["/aviation"] = _catalog(
            ["f_2a", "F-2A", "japan", 8, {}, 0],
            ["f_2a_adtw", "F-2A ADTW", "japan", 8, {}, 7],
            premium_status=7,
        )
        result = await peck_vehicles.get_vehicle_br(None, "F-2 Premium from Japan")
        self.assertEqual(result["vehicle_id"], "f_2a_adtw")
        self.assertIn("Premium", result["description"])

    async def test_unknown_status_is_reported_as_a_catalog_error(self):
        self.pages["/aviation"] = _catalog(["f_2a_adtw", "F-2A ADTW", "japan", 8, {}, 7])
        with self.assertLogs(peck_vehicles.__name__, "WARNING") as logs:
            result = await peck_vehicles.get_vehicle_br(None, "F-2 Premium from Japan")
        self.assertEqual(result, {"status": "unavailable"})
        self.assertIn("unrecognized status code: 7", logs.output[0])

    async def test_a_fresh_catalog_stays_available_during_background_refresh(self):
        await peck_vehicles.get_vehicle_br(None, "BMP-T")
        _, rows = peck_vehicles._catalog_cache["/ground"]
        peck_vehicles._catalog_cache["/ground"] = (peck_vehicles.monotonic() + 30, rows)
        started = asyncio.Event()

        async def slow_catalog(session, path):
            if path == "/ground":
                started.set()
                await asyncio.Event().wait()
            return await self._page(session, path)

        self.fetch.side_effect = slow_catalog
        refresh = asyncio.create_task(peck_vehicles.maintain_vehicle_catalog(None))
        try:
            await asyncio.wait_for(started.wait(), timeout=1)
            self.pages["/unit/ussr_bmpt"] = _ground_card("11.7")
            result = await asyncio.wait_for(peck_vehicles.get_vehicle_br(None, "BMP-T"), timeout=1)
            self.assertEqual(result["battle_ratings"], {"ground": {"RB": "11.7"}})
        finally:
            refresh.cancel()
            with suppress(asyncio.CancelledError):
                await refresh

    async def test_partial_catalog_cannot_guess_from_a_name(self):
        del self.pages["/aviation"]
        with self.assertLogs(peck_vehicles.__name__, "WARNING"):
            self.assertEqual(await peck_vehicles.get_vehicle_br(None, "BMP-T"), {"status": "unavailable"})

        result = await peck_vehicles.get_vehicle_br(None, "ussr_bmpt")
        self.assertEqual(result["vehicle_id"], "ussr_bmpt")
