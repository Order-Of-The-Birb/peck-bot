"""Small on-demand memory snapshots; never walk or retain the Python heap."""
from pathlib import Path

import psutil


def process_memory(pid: int | None = None) -> dict[str, int | None]:
	process = psutil.Process(pid)
	result = {"rss": process.memory_info().rss, "uss": None, "pss": None,
		"children_rss": 0, "children_pss": 0, "children": 0, "cgroup_current": None,
		"cgroup_peak": None}
	try:
		full = process.memory_full_info()
		result["uss"] = getattr(full, "uss", None)
		result["pss"] = getattr(full, "pss", None)
	except (psutil.AccessDenied, psutil.NoSuchProcess, NotImplementedError):
		pass
	for child in process.children(recursive=True):
		try:
			result["children_rss"] += child.memory_info().rss
			result["children"] += 1
			try:
				pss = getattr(child.memory_full_info(), "pss", None)
				if pss is None:
					result["children_pss"] = None
				elif result["children_pss"] is not None:
					result["children_pss"] += pss
			except (psutil.NoSuchProcess, psutil.AccessDenied, NotImplementedError):
				result["children_pss"] = None
		except (psutil.NoSuchProcess, psutil.AccessDenied):
			pass
	# Linux cgroup v2 accounts for the entire service, including file cache.
	# A root cgroup is host-wide, so do not label it as this bot's service.
	try:
		for line in Path(f"/proc/{process.pid}/cgroup").read_text().splitlines():
			if not line.startswith("0::"):
				continue
			relative = line[3:].lstrip("/")
			if not relative or ".." in Path(relative).parts:
				break
			root = Path("/sys/fs/cgroup") / relative
			for key, filename in (("cgroup_current", "memory.current"), ("cgroup_peak", "memory.peak")):
				try:
					result[key] = int((root / filename).read_text().strip())
				except (OSError, ValueError):
					pass
			break
	except OSError:
		pass
	return result


def cache_counts(bot) -> dict[str, int | None]:
	"""Use lengths only, without copying messages/members into new lists.

	Discord has no public modal-count API. Optional private counters are
	guarded for version changes; tested with deployed discord.py 2.7.1.
	"""
	state = bot._connection
	store = getattr(state, "_view_store", None)
	messages = getattr(state, "_messages", None)
	modals = getattr(store, "_modals", None)
	views = getattr(store, "_views", None)
	return {
		"messages": len(messages) if messages is not None else 0,
		"message_limit": getattr(state, "max_messages", None),
		"members": sum(guild.member_count or 0 for guild in bot.guilds),
		"cached_members": sum(len(guild._members) for guild in bot.guilds),
		"modals": len(modals) if modals is not None else None,
		"view_message_keys": len(views) if views is not None else None,
		"repository_users": len(bot.db),
	}
