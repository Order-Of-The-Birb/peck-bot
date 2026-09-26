import unittest
from collections import Counter
from datetime import datetime, UTC
from itertools import product
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call, patch

from cogs.listeners import Listeners
from modules.db import UserRepository
from utils.bot import Bot, ChannelIDs


class ClipHistoryTests(unittest.IsolatedAsyncioTestCase):
    def make_listener(self, count, *, timed_out=False):
        progress = SimpleNamespace(read=0)
        urls = [f"https://clips.example/{index}.mp4" for index in range(count)]

        async def history(**kwargs):
            yield SimpleNamespace(attachments=[])
            for url in urls:
                progress.read += 1
                yield SimpleNamespace(attachments=[SimpleNamespace(url=url)])
            yield SimpleNamespace(attachments=[])

        subject = SimpleNamespace(name="pilot", topic=None, history=Mock(side_effect=history))
        category = SimpleNamespace(name="user-clips", text_channels=[subject])
        timeout = SimpleNamespace(
            isTimedOut=Mock(return_value=timed_out),
            getOldest=Mock(return_value=datetime(2026, 1, 1, tzinfo=UTC)),
            add=Mock(),
        )
        bot = SimpleNamespace(
            logLevel=20,
            botIDs=[],
            peckServer=1,
            channelIDs={ChannelIDs.WTNEWS: 2},
            get_guild=Mock(return_value=SimpleNamespace(categories=[category])),
            timeouts={"clip": timeout},
        )
        message = SimpleNamespace(
            author=SimpleNamespace(id=10),
            channel=SimpleNamespace(id=3),
            content="clips for pilot",
            reply=AsyncMock(),
        )
        return Listeners(bot), message, subject, timeout, progress, urls

    async def test_batches_keep_every_url_in_order(self):
        for count in (0, 1, 10, 11, 20, 21):
            with self.subTest(count=count):
                listener, message, subject, timeout, progress, urls = self.make_listener(count)
                reads_at_reply = []

                async def record_reply(*args, **kwargs):
                    reads_at_reply.append(progress.read)

                message.reply.side_effect = record_reply
                await listener.on_message(message)

                if count <= 10:
                    expected = ["Here you go\n" + "\n".join(urls)]
                else:
                    expected = [
                        f"Part {index // 10 + 1}:\n" + "\n".join(urls[index:index + 10])
                        for index in range(0, count, 10)
                    ]
                self.assertEqual(
                    message.reply.await_args_list,
                    [call(content, mention_author=False) for content in expected],
                )
                subject.history.assert_called_once_with(limit=None, oldest_first=True)
                timeout.add.assert_called_once_with(message.author.id)
                if count > 10:
                    # Start replying with one attachment of lookahead, before scanning the rest.
                    self.assertEqual(reads_at_reply[0], 11)

    async def test_cooldown_does_not_fetch_history(self):
        listener, message, subject, timeout, progress, _ = self.make_listener(21, timed_out=True)
        await listener.on_message(message)
        subject.history.assert_not_called()
        timeout.add.assert_not_called()
        self.assertEqual(progress.read, 0)
        message.reply.assert_awaited_once()
        self.assertTrue(message.reply.await_args.args[0].startswith("You are under cooldown."))
        self.assertEqual(message.reply.await_args.kwargs, {"delete_after": 5})


class PropagandaHistoryTests(unittest.IsolatedAsyncioTestCase):
    def make_bot(self, groups):
        async def history(**kwargs):
            for urls in groups:
                yield SimpleNamespace(attachments=[SimpleNamespace(url=url) for url in urls])

        channel = SimpleNamespace(history=Mock(side_effect=history))
        bot = SimpleNamespace(
            channelIDs={ChannelIDs.PROPAGANDA: 5},
            get_channel=Mock(return_value=channel),
        )
        return bot, channel

    async def test_empty_history_raises(self):
        bot, _ = self.make_bot([[], []])
        with self.assertRaisesRegex(LookupError, "No propaganda posts found"):
            await Bot.random_propaganda(bot)

    async def test_single_attachment(self):
        bot, channel = self.make_bot([[], ["only"], []])
        self.assertEqual(await Bot.random_propaganda(bot), "only")
        channel.history.assert_called_once_with(limit=None)

    async def test_reservoir_weights_each_attachment_equally(self):
        selected = Counter()
        # Exhaust the six equally likely random paths for three attachments.
        for draws in product(range(1), range(2), range(3)):
            bot, _ = self.make_bot([["first", "second"], [], ["third"]])
            with patch("utils.bot.randrange", side_effect=draws) as draw:
                selected[await Bot.random_propaganda(bot)] += 1
                self.assertEqual(draw.call_args_list, [call(1), call(2), call(3)])
        self.assertEqual(selected, {"first": 2, "second": 2, "third": 2})


class CacheStorageTests(unittest.TestCase):
    def test_squad_voice_channels_are_per_instance(self):
        first = Bot._SquadVC()
        second = Bot._SquadVC()
        first.channels.append(object())
        first.checkDelay = 30
        self.assertEqual(second.channels, [])
        self.assertEqual(second.checkDelay, 0)

    def test_repository_decodes_each_page_once(self):
        repository = UserRepository.__new__(UserRepository)
        list.__init__(repository, [object()])
        repository._UserRepository__base_url = "https://management.example/api/v1/"
        repository._UserRepository__api_token = "test-token"
        first_page = Mock()
        first_page.json.return_value = {"data": [{"gaijin_id": 1, "username": "pilot"}]}
        empty_page = Mock()
        empty_page.json.return_value = {"data": []}
        with patch("modules.db.get", side_effect=[first_page, empty_page]):
            repository.refresh()
        first_page.json.assert_called_once_with()
        empty_page.json.assert_called_once_with()
        self.assertEqual(len(repository), 1)
        self.assertEqual(repository[0].gaijin_id, 1)


if __name__ == "__main__":
    unittest.main()
