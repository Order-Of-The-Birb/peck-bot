import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import aiohttp

from cogs.ai import PeckAICog
from modules.peck_ai import PeckAI
from modules.peck_lookup import DATA_API_ERROR, format_lookup, match_lookup
from utils.bot import ChannelIDs


class LookupTests(unittest.TestCase):
    def test_compound_sqb_question_and_mode_specific_vehicle(self):
        sqb = match_lookup("What SQB tier is today? When does it start in my local time?")
        self.assertEqual(sqb.tool, "get_sqb_today")
        vehicle = match_lookup("What's the battle rating of the F-2 Premium from Japan in Realistic Battles?")
        self.assertEqual(vehicle.vehicle, "F-2 Premium from Japan")
        self.assertEqual(vehicle.mode, "RB")
        self.assertIsNone(match_lookup("Who has the top 3 SQB ratings in PECK?"))

    def test_closed_sqb_queue_still_shows_cap_and_next_start(self):
        result = format_lookup(match_lookup("What BR is SQB at currently?"), {
            "active_window": None,
            "next_window": {"max_br": 10.7, "discord_start": "<t:1794790800:F>"},
            "max_br": 12.0,
        })
        for value in ("12.0", "closed", "<t:1794790800:F>", "10.7"):
            self.assertIn(value, result)


class DiscordLookupTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot = SimpleNamespace(
            user=SimpleNamespace(id=123), peckServer=12,
            channelIDs={ChannelIDs.WTNEWS: 14}, db=SimpleNamespace(getByDID=lambda _: []),
        )
        self.ai = PeckAI("http://127.0.0.1:1234/v1", "unused")
        self.ai.answer = AsyncMock(return_value="General chat")
        self.cog = PeckAICog(self.bot, self.ai)
        self.message = SimpleNamespace(
            guild=SimpleNamespace(id=12), channel=SimpleNamespace(id=15),
            author=SimpleNamespace(id=9, bot=False), webhook_id=None, reply=AsyncMock(),
        )

    async def ask(self, question):
        self.message.content = f"<@123>, {question}"
        await self.cog.on_message(self.message)
        args = self.message.reply.await_args
        self.assertEqual(args.kwargs["allowed_mentions"].to_dict()["parse"], [])
        return args.args[0]

    async def test_screenshot_sequence_calls_data_even_with_ai_busy(self):
        async def source(_session, function, _timezone):
            if function["name"] == "get_sqb_today":
                return {"max_br": 12.0, "next_window": {"discord_start": "<t:1794790800:F>"}}
            if "F-2 Premium from Japan" in function["arguments"]:
                return {"status": "ok", "vehicle": "F-2A ADTW", "battle_ratings": {"air": {"RB": "13.0"}}}
            self.assertIn("BMP-T", function["arguments"])
            return {"status": "ok", "vehicle": "BMPT", "battle_ratings": {"ground": {"RB": "12.0"}}}

        self.ai._call_tool = AsyncMock(side_effect=source)
        async with self.cog.inference:
            self.assertIn("12.0", await self.ask("what BR is SQB at currently?"))
            self.assertIn("12.0", await self.ask("Realistic Squadron Battles"))
            self.assertIn("Air: RB **13.0**", await self.ask("What BR is the F-2 Premium from Japan"))
            self.assertIn("Ground: RB **12.0**", await self.ask("what BR is the BMP-T"))
        self.ai.answer.assert_not_awaited()
        self.assertEqual(self.ai._call_tool.await_count, 4)

    async def test_request_failure_is_not_vehicle_disambiguation(self):
        class OfflineSession:
            def get(self, *_args, **_kwargs):
                raise aiohttp.ClientConnectionError

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                pass

        with patch("modules.peck_ai.aiohttp.ClientSession", OfflineSession), self.assertLogs("modules.peck_ai", "WARNING") as logs:
            self.assertEqual(await self.ask("what BR is the BMP-T"), DATA_API_ERROR)
        self.assertIn("/v1/vehicles/br", logs.output[0])

    async def test_general_chat_has_no_per_user_quota(self):
        for _ in range(5):
            self.assertEqual(await self.ask("Hello!"), "General chat")
        self.assertEqual(self.ai.answer.await_count, 5)

    async def test_chat_waits_for_airbot_instead_of_being_rejected_if_busy(self):
        async with self.cog.inference:
            pending = asyncio.create_task(self.ask("Hello!"))
            await asyncio.sleep(0)
            self.message.reply.assert_not_awaited()
        self.assertEqual(await pending, "General chat")
