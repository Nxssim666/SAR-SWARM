"""
MAVSDK runs every blocking call (arm, takeoff, hold...) in the event loop's default
executor. With asyncio's default pool (min(32, cpus + 4) threads: 8 on a 4-core host), a
bulk command to 25 PX4 aircraft queued behind it and some answers exceeded the command
timeout (the M2b scale run on GitHub). With MAVLink links, the runtime gives the loop a
pool large enough for a bulk command to the whole fleet at once.
"""

import asyncio
import contextlib
import threading
from pathlib import Path

from fleet_service.clock import SystemClock
from fleet_service.config import Settings
from fleet_service.db import migrate
from fleet_service.db.engine import Database
from fleet_service.services.runtime import Runtime

from support import START


async def _concurrent_blocking_calls(count: int) -> int:
    """How many blocking calls ran at the same time when ``count`` were started together."""
    loop = asyncio.get_running_loop()
    barrier = threading.Barrier(count, timeout=5.0)
    running = 0
    peak = 0
    lock = threading.Lock()

    def blocking() -> None:
        nonlocal running, peak
        with lock:
            running += 1
            peak = max(peak, running)
        with contextlib.suppress(threading.BrokenBarrierError):
            barrier.wait()  # every call must be in a thread at once, or the barrier breaks
        with lock:
            running -= 1

    await asyncio.gather(*(loop.run_in_executor(None, blocking) for _ in range(count)))
    return peak


async def test_with_mavlink_links_a_bulk_command_to_fifty_aircraft_is_not_queued(
    tmp_path: Path,
) -> None:
    migrate.upgrade_all(tmp_path, START)
    settings = Settings(data_dir=tmp_path, mavlink_links=True)
    database = Database(tmp_path)
    runtime = Runtime(settings, SystemClock(), database)
    await runtime.start(start_loops=False)
    try:
        assert await _concurrent_blocking_calls(50) == 50
    finally:
        await runtime.stop()
        await database.dispose()
