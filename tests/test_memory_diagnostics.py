import asyncio
from collections import deque
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

import psutil

from cogs.owner import OwnerCog
from utils.generic import MAX_FILE_SIZE, convertImageToGif
from utils.memory import cache_counts, process_memory


class MemoryDiagnosticsTests(unittest.TestCase):
	def test_processes_disappearing_during_snapshot_are_skipped(self):
		child = Mock()
		child.memory_info.return_value = SimpleNamespace(rss=512)
		child.memory_full_info.return_value = SimpleNamespace(pss=400)
		gone = Mock()
		gone.memory_info.side_effect = psutil.NoSuchProcess(10)
		process = Mock(pid=99)
		process.memory_info.return_value = SimpleNamespace(rss=1024)
		process.memory_full_info.return_value = SimpleNamespace(uss=800, pss=900)
		process.children.return_value = [child, gone]
		with patch("utils.memory.psutil.Process", return_value=process), patch.object(Path, "read_text", side_effect=FileNotFoundError):
			result = process_memory()
		self.assertEqual(result["rss"], 1024)
		self.assertEqual(result["children_rss"], 512)
		self.assertEqual(result["children_pss"], 400)
		self.assertEqual(result["children"], 1)
		self.assertEqual(result["uss"], 800)
		self.assertIsNone(result["cgroup_current"])

	def test_optional_memory_metrics_and_host_root_cgroup(self):
		process = Mock(pid=99)
		process.memory_info.return_value = SimpleNamespace(rss=1024)
		process.memory_full_info.side_effect = psutil.AccessDenied(99)
		process.children.return_value = []
		with patch("utils.memory.psutil.Process", return_value=process), patch.object(Path, "read_text", return_value="0::/\n"):
			result = process_memory()
		self.assertIsNone(result["uss"])
		self.assertIsNone(result["cgroup_current"])

	def test_service_cgroup_memory_and_peak(self):
		process = Mock(pid=99)
		process.memory_info.return_value = SimpleNamespace(rss=1024)
		process.memory_full_info.return_value = SimpleNamespace(uss=800, pss=900)
		process.children.return_value = []
		with patch("utils.memory.psutil.Process", return_value=process), patch.object(Path, "read_text", side_effect=["0::/system.slice/peckbot.service\n", "2048\n", "4096\n"]):
			result = process_memory()
		self.assertEqual(result["cgroup_current"], 2048)
		self.assertEqual(result["cgroup_peak"], 4096)

	def test_cache_counts_do_not_copy_public_cache_lists(self):
		state = SimpleNamespace(_messages=deque([1, 2]), max_messages=1000,
			_view_store=SimpleNamespace(_modals={"x": object()}, _views={10: {}, 11: {}}))
		bot = SimpleNamespace(_connection=state, guilds=[SimpleNamespace(member_count=5, _members={1: object()})], db=[1, 2, 3])
		counts = cache_counts(bot)
		self.assertEqual(counts["messages"], 2)
		self.assertEqual(counts["cached_members"], 1)
		self.assertEqual(counts["modals"], 1)
		self.assertEqual(counts["repository_users"], 3)


class AsyncMemoryTests(unittest.IsolatedAsyncioTestCase):
	async def test_diagnostics_command_returns_private_snapshot(self):
		interaction = SimpleNamespace(response=SimpleNamespace(defer=AsyncMock()), edit_original_response=AsyncMock())
		metrics = dict(rss=1024, uss=800, pss=900, children=0, children_rss=0, children_pss=0, cgroup_current=2048, cgroup_peak=4096)
		counts = dict(messages=2, message_limit=1000, cached_members=1, members=2, modals=3, view_message_keys=4, repository_users=5)
		with patch("cogs.owner.process_memory", return_value=metrics), patch("cogs.owner.cache_counts", return_value=counts):
			await OwnerCog.memory.callback(SimpleNamespace(bot=object()), interaction)
		interaction.response.defer.assert_awaited_once_with(ephemeral=True)
		self.assertIn("Open forms: 3", interaction.edit_original_response.await_args.kwargs["content"])

	async def test_oversized_gif_is_rejected_before_reading_output(self):
		image = SimpleNamespace(filename="test.png", size=8, read=AsyncMock(return_value=b"png-data"))
		with tempfile.TemporaryDirectory() as directory:
			def encode(command, **kwargs):
				# No output file: attempting to open it would fail. Size check must win.
				pass
			with patch("utils.generic.subprocess.run", side_effect=encode), patch("utils.generic.path.getsize", return_value=MAX_FILE_SIZE + 1):
				with self.assertRaisesRegex(ValueError, "converted GIF is too large"):
					await convertImageToGif(image)


if __name__ == "__main__":
	unittest.main()
