import asyncio
import json
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from modules import peck_vehicles


def _catalog(*rows):
    return f"<script>window.WT_UnitList = '{json.dumps(rows)}';</script>"


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

    async def test_partial_catalog_cannot_guess_from_a_name(self):
        del self.pages["/aviation"]
        with self.assertLogs(peck_vehicles.__name__, "WARNING"):
            self.assertEqual(await peck_vehicles.get_vehicle_br(None, "BMP-T"), {"status": "unavailable"})

        result = await peck_vehicles.get_vehicle_br(None, "ussr_bmpt")
        self.assertEqual(result["vehicle_id"], "ussr_bmpt")
