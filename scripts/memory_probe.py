"""Read-only JSON memory measurements; never logs in or loads .env.

python scripts/memory_probe.py --pid 1275 --samples 10 --interval 60
python scripts/memory_probe.py --imports --runs 3 --source-root /path/to/checkout
"""
import argparse
from datetime import datetime, UTC
import json
from pathlib import Path
import subprocess
import sys
import time

import psutil


def snapshot(pid):
	process = psutil.Process(pid)
	result = {"time": datetime.now(UTC).isoformat(), "pid": pid,
		"rss": process.memory_info().rss,
		"uptime_seconds": time.time() - process.create_time(),
		"children_rss": 0, "children": 0}
	try:
		full = process.memory_full_info()
		result.update({key: getattr(full, key, None) for key in ("uss", "pss", "swap")})
	except (psutil.AccessDenied, NotImplementedError):
		pass
	for child in process.children(recursive=True):
		try:
			result["children_rss"] += child.memory_info().rss
			result["children"] += 1
		except (psutil.NoSuchProcess, psutil.AccessDenied):
			pass
	return result


def main():
	parser = argparse.ArgumentParser(description=__doc__)
	mode = parser.add_mutually_exclusive_group(required=True)
	mode.add_argument("--pid", type=int)
	mode.add_argument("--imports", action="store_true")
	parser.add_argument("--samples", type=int, default=1)
	parser.add_argument("--interval", type=float, default=60)
	parser.add_argument("--runs", type=int, default=3)
	parser.add_argument("--source-root", type=Path, default=Path(__file__).resolve().parents[1])
	args = parser.parse_args()
	if min(args.samples, args.runs) < 1 or args.interval < 0:
		parser.error("counts must be positive and interval must be nonnegative")
	if args.imports:
		# New interpreter for each run: repeated imports in one process are cached.
		code = """
import gc, importlib, json, psutil, sys
import main
from cogs import EXTENSIONS
for extension in EXTENSIONS:
    importlib.import_module(extension)
gc.collect()
p = psutil.Process()
full = p.memory_full_info()
print(json.dumps({'rss': p.memory_info().rss, 'uss': getattr(full, 'uss', None),
    'pss': getattr(full, 'pss', None), 'playwright_loaded': 'playwright.async_api' in sys.modules,
    'python': sys.version.split()[0]}))
"""
		for run in range(args.runs):
			completed = subprocess.run([sys.executable, "-B", "-c", code], cwd=args.source_root,
				capture_output=True, text=True, check=True, timeout=60)
			result = json.loads(completed.stdout)
			result.update({"mode": "imports", "run": run + 1})
			print(json.dumps(result), flush=True)
	else:
		# Reject PID reuse, rather than recording a different service after restart.
		created = psutil.Process(args.pid).create_time()
		for sample in range(args.samples):
			if psutil.Process(args.pid).create_time() != created:
				raise RuntimeError("Target process restarted; select its new PID")
			print(json.dumps(snapshot(args.pid)), flush=True)
			if sample + 1 < args.samples:
				time.sleep(args.interval)


if __name__ == "__main__":
	main()
