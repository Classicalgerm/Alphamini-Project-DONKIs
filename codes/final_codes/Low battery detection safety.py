# low_battery_testing_code_edu.py
import asyncio
import logging
import sys
import time
from typing import Optional

import mini.mini_sdk as MiniSdk
from mini.dns.dns_browser import WiFiDevice
from mini.apis.base_api import MiniApiResultType
from mini.apis.api_action import MoveRobot, MoveRobotDirection, MoveRobotResponse

MiniSdk.set_log_level(logging.INFO)
MiniSdk.set_robot_type(MiniSdk.RobotType.EDU)

# ---------------------
# CONFIG
# ---------------------
SERIAL_SUFFIX = "213"           # <- change to your robot's suffix
BATTERY_LOW_THRESHOLD = 20        # %
CHECK_INTERVAL_S = 5              # seconds between mock battery polls
ANNOUNCE_ON_LOW = True

# Motion safety config
STEP_MIN = 1
STEP_MAX = 6
RATE_LIMIT_S = 0.4

# Mock battery (since EDU SDK has no battery API)
TESTING_BATTERY_START = 35
TESTING_DRAIN_PER_CYCLE = 3

# Predefined simple route to Idle Hub (adjust to your space)
RETURN_ROUTE = [
    ("FORWARD", 4),
    ("LEFT", 2),
    ("FORWARD", 6),
    ("RIGHT", 2),
    ("FORWARD", 4),
]
# ---------------------

_last_move_ts = 0.0
_estop = asyncio.Event()
_is_returning = asyncio.Event()


def _clamp_steps(n: int) -> int:
    return max(STEP_MIN, min(STEP_MAX, int(n)))


async def safe_move(direction: MoveRobotDirection, steps: int = 1) -> bool:
    """Rate-limited, clamped, e-stop aware move."""
    global _last_move_ts
    if _estop.is_set():
        logging.warning("E-STOP active: ignoring move.")
        return False

    steps = _clamp_steps(steps)
    # rate limit
    to_wait = max(0.0, RATE_LIMIT_S - (time.time() - _last_move_ts))
    if to_wait > 0:
        await asyncio.sleep(to_wait)

    req = MoveRobot(direction=direction, step=steps)
    res = await req.execute()
    _last_move_ts = time.time()
    ok = (res.result == MiniApiResultType.Ok)
    if not ok:
        logging.error(f"Move failed: {res.result}")
    return ok


async def stop_all():
    _estop.set()
    logging.info("Stopping all actions (E-STOP).")


class MockBattery:
    def _init_(self, start=TESTING_BATTERY_START, drain=TESTING_DRAIN_PER_CYCLE):
        self.pct = start
        self.drain = drain

    def tick(self) -> int:
        self.pct = max(0, self.pct - self.drain)
        return self.pct


async def announce(text: str):
    # If you have TTS, call it here; logging is fine for EDU
    logging.info(f"[AlphaMini says] {text}")


async def go_to_idle_hub():
    logging.info("Navigating to Idle Hub…")
    for direction_name, steps in RETURN_ROUTE:
        if _estop.is_set():
            logging.warning("E-STOP during return; aborting path.")
            return
        direction = getattr(MoveRobotDirection, direction_name)
        ok = await safe_move(direction, steps)
        if not ok:
            logging.error(f"Path step failed: {direction_name} {steps}")
            break
        await asyncio.sleep(0.6)
    logging.info("Arrived at Idle Hub (end of scripted path).")


async def low_battery_return_loop():
    """Background task: mock battery → triggers one safe return."""
    mock = MockBattery()
    told_low = False

    while not _estop.is_set():
        pct = mock.tick()
        logging.info(f"Battery (mock): {pct}%")

        if pct <= BATTERY_LOW_THRESHOLD and not _is_returning.is_set():
            _is_returning.set()
            if ANNOUNCE_ON_LOW and not told_low:
                await announce(f"Battery low at {pct} percent. Returning to charging station.")
                told_low = True
            await asyncio.sleep(0.8)
            await go_to_idle_hub()
            await announce("Docking complete. Entering low-power standby.")
            await stop_all()
            break

        await asyncio.sleep(CHECK_INTERVAL_S)


async def estop_listener():
    """Press 'e' + Enter in console to trigger emergency stop."""
    loop = asyncio.get_event_loop()
    def _readline():
        try:
            return sys.stdin.readline()
        except Exception:
            return ""
    while not _estop.is_set():
        line = await loop.run_in_executor(None, _readline)
        if line.strip().lower() == "e":
            logging.warning("E-STOP requested by operator.")
            _estop.set()
            break
        await asyncio.sleep(0.05)


async def connect_and_run():
    logging.info("Scanning for AlphaMini…")
    # NOTE: timeout IS REQUIRED on your SDK
    devices = await MiniSdk.get_device_list(timeout=5)

    target: Optional[WiFiDevice] = None
    for d in devices:
        if d.sn.endswith(SERIAL_SUFFIX):
            target = d
            break
    if not target:
        raise RuntimeError(f"Robot with suffix {SERIAL_SUFFIX} not found on LAN.")

    ok = await MiniSdk.connect(target)
    if not ok:
        raise RuntimeError("Failed to connect to AlphaMini.")

    logging.info("Connected to AlphaMini.")
    try:
        tasks = [
            asyncio.create_task(low_battery_return_loop()),
            asyncio.create_task(estop_listener()),
        ]

        # Gentle wandering until low-battery triggers the return path
        while not _estop.is_set() and not _is_returning.is_set():
            await safe_move(MoveRobotDirection.FORWARD, 2)
            await asyncio.sleep(1.2)
            await safe_move(MoveRobotDirection.LEFT, 1)
            await asyncio.sleep(0.8)

        for t in tasks:
            if not t.done():
                t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    finally:
        try:
            await MiniSdk.disconnect()
        except Exception:
            pass
        logging.info("Disconnected.")


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.info("Low Battery Safe Return (EDU Test) starting…")
    try:
        asyncio.run(connect_and_run())
    except KeyboardInterrupt:
        logging.warning("Interrupted by user.")
    except Exception as e:
        logging.error(f"Fatal error: {e}")


if __name__ == "__main__":
    main()