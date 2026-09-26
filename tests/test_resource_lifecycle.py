import asyncio
import gc
import json
import logging
import threading
import unittest
import weakref
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from bs4 import BeautifulSoup

from cogs.tasks import Tasks
from utils import wt


class TaskLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_repeated_unload_stops_all_loops_and_releases_cogs(self):
        ready = asyncio.Event()
        bot = SimpleNamespace(
            logLevel=logging.CRITICAL,
            squadVC=SimpleNamespace(),
            wait_until_ready=ready.wait,
            peckServer=1,
            get_guild=lambda _: SimpleNamespace(scheduled_events=[]),
        )
        previous_cogs = []
        for _ in range(4):
            cog = Tasks(bot)
            previous_cogs.append(weakref.ref(cog))
            running = [loop.get_task() for loop in cog._background_loops]
            self.assertEqual(len(running), 4)
            await asyncio.sleep(0)
            self.assertTrue(all(not task.done() for task in running))
            await cog.cog_unload()
            self.assertTrue(all(task.done() for task in running))
            # Saved completed Tasks can themselves retain cancellation tracebacks.
            # Drop the test's task handles before checking the cog's actual owners.
            del running, cog
            await asyncio.sleep(0)
        gc.collect()
        self.assertEqual([index for index, reference in enumerate(previous_cogs) if reference() is not None], [])

    async def test_sqb_fetch_runs_off_event_loop(self):
        cog = Tasks.__new__(Tasks)
        cog.logger = logging.getLogger(__name__)
        cog.bot = SimpleNamespace(wait_until_ready=AsyncMock())
        started = threading.Event()
        release = threading.Event()
        event_loop_thread = threading.get_ident()

        def fetch():
            self.assertNotEqual(threading.get_ident(), event_loop_thread)
            started.set()
            if not release.wait(timeout=5):
                raise AssertionError("Event loop failed to release the worker")
            return None

        async def wait_for_worker():
            while not started.is_set():
                await asyncio.sleep(0.001)

        with patch.object(wt.SQBData, "fetch_data", side_effect=fetch):
            task = asyncio.create_task(Tasks.sqb_post.coro(cog))
            try:
                await asyncio.wait_for(wait_for_worker(), timeout=2)
                # The worker remains blocked while the event loop continues here.
                self.assertFalse(task.done())
            finally:
                release.set()
                await task
        self.assertEqual(cog.pings_cnt, 0)


class SquadronParserTests(unittest.IsolatedAsyncioTestCase):
    async def test_member_values_survive_tree_cleanup(self):
        values = ["header"] * 6 + ["1", "Pilot", "12", "34", "Commander", "26.09.2026"]
        html = '<div class="squadrons-members__table">' + "".join(
            f'<div class="squadrons-members__grid-item">{value}</div>' for value in values
        ) + "</div>"
        squadron = wt.Squadron("Example")
        await squadron.updateMembers(SimpleNamespace(content=AsyncMock(return_value=html)))
        self.assertEqual(len(squadron.members), 1)
        member = squadron.members[0]
        self.assertEqual((member.name, member.sqb_rating, member.activity, member.role),
                         ("Pilot", 12, 34, "Commander"))
        self.assertEqual(member.joindate.isoformat(), "2026-09-26T00:00:00")

    async def test_stats_keep_values_without_retaining_the_parse_tree(self):
        html = """
        <div class="squadrons-profile__header-wrapper">
          <div class="squadrons-profile__header-stat"><ul></ul><ul>
            <li class="squadrons-stat__item-value">unused</li>
            <li class="squadrons-stat__item-value">12</li>
            <li class="squadrons-stat__item-value">34</li>
            <li class="squadrons-stat__item-value">5</li>
            <li class="squadrons-stat__item-value">6h</li>
          </ul></div>
          <div class="squadrons-profile__header-aside">
            <div class="squadrons-counter__count-wrapper">
              <div class="squadrons-counter__item">123 points</div>
              <div class="squadrons-counter__item">456 activity</div>
            </div>
          </div>
        </div>
        """
        references = []

        def parse(*args, **kwargs):
            soup = BeautifulSoup(*args, **kwargs)
            references.append(weakref.ref(soup))
            references.extend(weakref.ref(tag) for tag in soup.find_all("li"))
            return soup

        squadron = wt.Squadron("Example")
        with patch.object(wt, "BeautifulSoup", side_effect=parse):
            await squadron.updateStats(SimpleNamespace(content=AsyncMock(return_value=html)))
        gc.collect()
        self.assertTrue(all(reference() is None for reference in references))
        self.assertEqual(vars(squadron.sqb), {
            "air_kills": 12, "ground_kills": 34, "deaths": 5, "time": "6h"
        })
        self.assertEqual((squadron.sqb_rating, squadron.activity), (123, 456))


class BrowserLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Production has one runtime loop; isolated tests each need a fresh gate.
        self.browser_slot = asyncio.Semaphore(1)
        gate_patch = patch.object(wt, "browser_slot", self.browser_slot)
        gate_patch.start()
        self.addCleanup(gate_patch.stop)

    def make_browser(self):
        html = """
        <div class="_resultItemNames_1umbu_"><ul><li>
          <div class="_resultItemNames__name_1umbu_">Pilot</div>
        </li></ul></div>
        <div class="_resultItemNames_1umbu_"><ul></ul></div>
        """
        page = SimpleNamespace(**{
            name: AsyncMock() for name in (
                "goto", "wait_for_selector", "fill", "click",
                "wait_for_function", "wait_for_load_state"
            )
        }, content=AsyncMock(return_value=html))
        context = SimpleNamespace(
            route=AsyncMock(), new_page=AsyncMock(return_value=page), close=AsyncMock()
        )
        browser = SimpleNamespace(
            new_context=AsyncMock(return_value=context), close=AsyncMock()
        )
        launch = AsyncMock(return_value=browser)
        manager = MagicMock()
        manager.__aenter__ = AsyncMock(return_value=SimpleNamespace(
            firefox=SimpleNamespace(launch=launch)
        ))
        manager.__aexit__ = AsyncMock(return_value=False)
        return manager, launch, browser, context, page

    async def exercise(self, operation, page):
        if operation == "squadron":
            squadron = wt.Squadron("Example")
            with patch.object(squadron._logger, "exception"):
                async with squadron.openPage() as opened:
                    self.assertIs(opened, page)
        else:
            found = await wt.userInReplay(
                "Pilot", 123, SimpleNamespace(email="unused", password="unused")
            )
            self.assertTrue(found)

    async def test_browser_cleanup_on_success_and_partial_failure(self):
        for operation in ("squadron", "replay"):
            for stage in (None, "launch", "new_context", "route", "goto", "close"):
                with self.subTest(operation=operation, stage=stage):
                    manager, launch, browser, context, page = self.make_browser()
                    targets = {
                        "launch": launch, "new_context": browser.new_context,
                        "route": context.route, "goto": page.goto, "close": context.close,
                    }
                    if stage:
                        targets[stage].side_effect = RuntimeError("simulated failure")
                    with patch("playwright.async_api.async_playwright", return_value=manager):
                        if stage:
                            with self.assertRaisesRegex(RuntimeError, "simulated failure"):
                                await self.exercise(operation, page)
                        else:
                            await self.exercise(operation, page)
                    if stage != "launch":
                        browser.close.assert_awaited_once()
                    else:
                        browser.close.assert_not_awaited()
                    if stage not in ("launch", "new_context"):
                        context.close.assert_awaited_once()
                    else:
                        context.close.assert_not_awaited()
                    manager.__aexit__.assert_awaited_once()
                    self.assertFalse(self.browser_slot.locked())

    async def test_squadron_and_replay_share_one_slot_through_browser_shutdown(self):
        manager, launch, browser, _, page = self.make_browser()
        playwright = manager.__aenter__.return_value
        closing = asyncio.Event()
        allow_close = asyncio.Event()
        active = 0
        maximum = 0

        async def enter():
            nonlocal active, maximum
            active += 1
            maximum = max(maximum, active)
            return playwright

        async def exit_manager(*args):
            nonlocal active
            active -= 1
            return False

        async def close():
            closing.set()
            await allow_close.wait()

        manager.__aenter__.side_effect = enter
        manager.__aexit__.side_effect = exit_manager
        browser.close.side_effect = close
        with patch("playwright.async_api.async_playwright", return_value=manager) as start:
            first = asyncio.create_task(self.exercise("squadron", page))
            queued = None
            try:
                await asyncio.wait_for(closing.wait(), timeout=2)
                queued = asyncio.create_task(self.exercise("replay", page))
                await asyncio.sleep(0)
                # The first browser has started closing, but still owns the slot.
                self.assertEqual(start.call_count, 1)
                self.assertEqual(launch.await_count, 1)
                self.assertFalse(queued.done())
            finally:
                allow_close.set()
                await asyncio.gather(first, *([queued] if queued is not None else []))
        self.assertEqual(launch.await_count, 2)
        self.assertEqual((maximum, active), (1, 0))
        self.assertFalse(self.browser_slot.locked())

    async def test_cancelled_waiter_never_starts_playwright_or_leaks_the_slot(self):
        for operation in ("squadron", "replay"):
            with self.subTest(operation=operation):
                manager, launch, _, _, page = self.make_browser()
                with patch("playwright.async_api.async_playwright", return_value=manager) as start:
                    async with self.browser_slot:
                        waiter = asyncio.create_task(self.exercise(operation, page))
                        await asyncio.sleep(0)
                        start.assert_not_called()
                        waiter.cancel()
                        with self.assertRaises(asyncio.CancelledError):
                            await waiter
                    await asyncio.wait_for(self.exercise(operation, page), timeout=2)
                    launch.assert_awaited_once()
                    self.assertFalse(self.browser_slot.locked())

    async def test_browser_cleanup_on_cancellation(self):
        for operation in ("squadron", "replay"):
            with self.subTest(operation=operation):
                manager, _, browser, context, page = self.make_browser()
                page.goto.side_effect = asyncio.CancelledError()
                with patch("playwright.async_api.async_playwright", return_value=manager):
                    with self.assertRaises(asyncio.CancelledError):
                        await self.exercise(operation, page)
                context.close.assert_awaited_once()
                browser.close.assert_awaited_once()
                self.assertFalse(self.browser_slot.locked())


class LeaderboardRequestTests(unittest.TestCase):
    def test_successful_batch_returns_matching_squadron_and_closes_responses(self):
        responses = []

        def get(url, *, timeout):
            self.assertEqual(timeout, (5, 15))
            page = int(url.split("/page/")[1].split("/")[0])
            data = [{"_id": 1061551, "name": "Example", "astat": {"battles_hist": 7}}] if page == 1 else []
            response = MagicMock(status_code=200, ok=True, text=json.dumps({"status": "ok", "data": data}))
            response.__enter__.return_value = response
            responses.append(response)
            return response

        with patch.object(wt.requests, "get", side_effect=get), patch.object(wt, "sleep"):
            result = wt.SQBData.fetch_data()
        self.assertEqual((result.name, result.page_num, result.astat.battles), ("Example", 1, 7))
        self.assertEqual(len(responses), 5)
        for response in responses:
            response.__exit__.assert_called_once()

    def test_rate_limits_stop_after_three_attempts_per_page_and_close_responses(self):
        responses = []

        def get(url, *, timeout):
            self.assertEqual(timeout, (5, 15))
            response = MagicMock(status_code=429)
            response.__enter__.return_value = response
            responses.append(response)
            return response

        with patch.object(wt.requests, "get", side_effect=get), \
             patch.object(wt, "sleep"), patch.object(wt.logger, "error"):
            self.assertIsNone(wt.SQBData.fetch_data())
        self.assertEqual(len(responses), 50 * 3)
        for response in responses:
            response.__exit__.assert_called_once()


if __name__ == "__main__":
    unittest.main()
