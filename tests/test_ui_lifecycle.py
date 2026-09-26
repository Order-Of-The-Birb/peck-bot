"""Exercise Discord UI retention without connecting to Discord."""

import asyncio
import gc
import logging
import unittest
import weakref
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from discord.ui.view import ViewStore

from cogs.clips import ClipsCog
from cogs.normal import NormalCog
from cogs.vc import VcCog
from utils.bot import CategoryIDs


class ModalLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_abandoned_forms_expire_and_leave_the_dispatch_store(self):
        bot = SimpleNamespace(db=SimpleNamespace(getByDID=Mock(return_value=[])))
        cog = SimpleNamespace(bot=bot, logger=logging.getLogger(__name__))

        for command in (NormalCog.apply, NormalCog.report, ClipsCog.upload_clip, ClipsCog.add_alias):
            with self.subTest(command=command.name):
                interaction = SimpleNamespace(
                    user=SimpleNamespace(id=123),
                    response=SimpleNamespace(send_modal=AsyncMock()),
                )
                await command.callback(cog, interaction)
                modal = interaction.response.send_modal.await_args.args[0]
                self.assertEqual(modal.timeout, 15 * 60)

                # Exercise real expiry using a short deadline, without sleeping for 15 minutes.
                modal.timeout = 0.01
                store = ViewStore(state=None)
                store.add_view(modal)
                self.assertIn(modal.custom_id, store._modals)
                self.assertTrue(await asyncio.wait_for(modal.wait(), timeout=1))
                self.assertNotIn(modal.custom_id, store._modals)

    async def test_completed_alias_approvals_release_their_views(self):
        for button_label in ("Add", "Delete"):
            with self.subTest(button=button_label):
                channel = SimpleNamespace(name="456", topic=None, send=AsyncMock(), edit=AsyncMock())
                category = SimpleNamespace(id=10, text_channels=[channel])
                bot = SimpleNamespace(
                    peckServer=42,
                    categoryIDs={CategoryIDs.CLIPS: 10},
                    get_guild=Mock(return_value=SimpleNamespace(categories=[category])),
                )
                interaction = SimpleNamespace(
                    user=SimpleNamespace(id=123, name="requester"),
                    response=SimpleNamespace(send_modal=AsyncMock(), defer=AsyncMock()),
                    edit_original_response=AsyncMock(),
                )
                await ClipsCog.add_alias.callback(SimpleNamespace(bot=bot), interaction)
                modal = interaction.response.send_modal.await_args.args[0]
                modal.userCh.component._values = [SimpleNamespace(id=456)]
                modal.userAlias.component._value = "Test Alias"
                await modal.on_submit(interaction)

                sent = channel.send.await_args.kwargs
                view = sent["view"]
                store = ViewStore(state=None)
                store.add_view(view, message_id=321)
                message = SimpleNamespace(content=sent["content"], delete=AsyncMock())
                click = SimpleNamespace(
                    message=message,
                    channel=channel,
                    response=SimpleNamespace(edit_message=AsyncMock()),
                )
                button = next(item for item in view.children if item.label == button_label)
                try:
                    await button.callback(click)
                    message.delete.assert_awaited_once()
                    if button_label == "Add":
                        channel.edit.assert_awaited_once_with(topic="test alias")
                    else:
                        channel.edit.assert_not_awaited()
                    self.assertTrue(view.is_finished())
                    self.assertNotIn(321, store._views)
                    self.assertNotIn(321, store._synced_message_views)
                finally:
                    modal.stop()
                    view.stop()


class VoiceCogLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_unloading_before_ready_cancels_init_and_releases_old_cog(self):
        ready = asyncio.Event()
        bot = SimpleNamespace(runtime=asyncio.get_running_loop(), wait_until_ready=ready.wait)
        cog = VcCog(bot)
        cog_ref = weakref.ref(cog)
        await asyncio.sleep(0)
        task = cog._init_task
        self.assertFalse(task.done())
        await cog.cog_unload()
        self.assertTrue(task.cancelled())
        await cog.cog_unload()  # Cleanup is safe when repeated.
        # A test-local cancelled Task can itself retain its cancellation traceback.
        # Drop that artificial owner and let completion callbacks finish first.
        del task, cog
        await asyncio.sleep(0)
        gc.collect()
        self.assertIsNone(cog_ref())

    async def test_unloading_after_init_completes_is_safe(self):
        category = SimpleNamespace(id=10, voice_channels=[])
        bot = SimpleNamespace(
            runtime=asyncio.get_running_loop(),
            wait_until_ready=AsyncMock(),
            squadVC=SimpleNamespace(channels=[]),
            peckServer=42,
            categoryIDs={CategoryIDs.SQUAD_VC: 10},
            get_guild=Mock(return_value=SimpleNamespace(categories=[category])),
        )
        cog = VcCog(bot)
        await cog._init_task
        await cog.cog_unload()
        self.assertTrue(cog._init_task.done())
        self.assertFalse(cog._init_task.cancelled())

    async def test_init_failures_are_logged_and_do_not_break_unload(self):
        bot = SimpleNamespace(
            runtime=asyncio.get_running_loop(),
            wait_until_ready=AsyncMock(),
            squadVC=SimpleNamespace(channels=[]),
            peckServer=42,
            categoryIDs={CategoryIDs.SQUAD_VC: 10},
            get_guild=Mock(return_value=SimpleNamespace(categories=[])),
        )
        cog = VcCog(bot)
        with self.assertLogs("cogs.vc", level="ERROR") as logs:
            results = await asyncio.gather(cog._init_task, return_exceptions=True)
        self.assertIsInstance(results[0], ValueError)
        self.assertIn("Failed to initialize squad voice channels", logs.output[0])
        await cog.cog_unload()


if __name__ == "__main__":
    unittest.main()
