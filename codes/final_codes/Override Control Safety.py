import asyncio
import logging
import sys

# --- AlphaMini SDK imports (EDU layout) ---
from mini.apis.api_sence import GetInfraredDistance
import mini.mini_sdk as MiniSdk
from mini.dns.dns_browser import WiFiDevice
from mini.apis.api_action import MoveRobot, MoveRobotDirection
from mini.apis.base_api import MiniApiResultType

# ---------- Configuration ----------
SERIAL_SUFFIX = "213"     # <-- CHANGE THIS
SAFE_DISTANCE_CM = 20
STEP_SIZE = 1
SLEEP_DURATION = 0.8
LOG_LEVEL = logging.INFO
# -----------------------------------

MiniSdk.set_log_level(LOG_LEVEL)
MiniSdk.set_robot_type(MiniSdk.RobotType.EDU)

# Global control flags
override_event = asyncio.Event()   # Teacher Override ON when set
shutdown_event = asyncio.Event()   # Quit program

# ------------- SDK helpers -------------
async def connect_robot(suffix: str):
    """Connect to AlphaMini using serial suffix and return device object."""
    print("[CONNECT] Searching for AlphaMini robots on network...")
    devices = await MiniSdk.get_device_list(timeout=5)  # <-- added timeout argument
    if not devices:
        print("[ERROR] No devices found. Check that AlphaMini is powered and on the same Wi-Fi.")
        return None

    target = None
    for d in devices:
        if getattr(d, "sn", None) and d.sn.endswith(suffix):
            target = d
            break

    if not target:
        print(f"[ERROR] No AlphaMini found with serial ending '{suffix}'.")
        return None

    ok = await MiniSdk.connect(target)
    if not ok:
        print("[ERROR] Failed to connect to AlphaMini.")
        return None

    print(f"[SUCCESS] Connected to AlphaMini [{target.sn}]")
    return target


async def safe_move(direction: MoveRobotDirection, steps: int = STEP_SIZE):
    """Perform movement safely and rate-limited."""
    if shutdown_event.is_set():
        return
    req = MoveRobot(direction=direction, step=steps)
    resp = await req.exec()  # no annotation
    if resp.result != MiniApiResultType.Success:
        print(f"[WARN] Move failed: {resp.result}")

async def stop_motion():
    await asyncio.sleep(0)

# ------------- Sensors -------------
async def read_front_distance_cm():
    """Return front IR distance (cm), or None on failure."""
    resp = await GetInfraredDistance().exec()
    if resp.result != MiniApiResultType.Success:
        return None
    try:
        values = list(resp.distance)
        if not values:
            return None
        return min(max(1, int(values[0])), 5000)
    except Exception:
        return None

# ------------- Autonomy (simple wander + avoid) -------------
async def autonomous_loop():
    print("[AUTO] Started autonomous navigation.")
    try:
        while not shutdown_event.is_set():
            if override_event.is_set():
                # Teacher override engaged — pause autonomy
                await asyncio.sleep(0.1)
                continue

            dist = await read_front_distance_cm()
            if dist is None:
                await asyncio.sleep(0.2)
                continue

            if dist <= SAFE_DISTANCE_CM:
                print(f"[AUTO] Obstacle at {dist} cm → avoid")
                await safe_move(MoveRobotDirection.Backward, steps=2)
                await asyncio.sleep(SLEEP_DURATION)
                await safe_move(MoveRobotDirection.RightTurn, steps=1)
                await asyncio.sleep(SLEEP_DURATION)
            else:
                await safe_move(MoveRobotDirection.Forward, steps=STEP_SIZE)
                await asyncio.sleep(SLEEP_DURATION)
    finally:
        print("[AUTO] Exiting autonomous loop.")

# ------------- Manual (Teacher Override) -------------
HELP_TEXT = (
    "\n[OVERRIDE - Manual Mode]\n"
    "  w=forward  s=backward  a=left  d=right  x=stop\n"
    "  o=exit override (resume auto)  q=quit\n"
)

async def manual_loop():
    print(HELP_TEXT)
    while override_event.is_set() and not shutdown_event.is_set():
        line = await _readline_async()
        if not line:
            continue
        cmd = line.strip().lower()

        if cmd == 'w':
            await safe_move(MoveRobotDirection.Forward, steps=STEP_SIZE)
        elif cmd == 's':
            await safe_move(MoveRobotDirection.Backward, steps=STEP_SIZE)
        elif cmd == 'a':
            await safe_move(MoveRobotDirection.LeftTurn, steps=STEP_SIZE)
        elif cmd == 'd':
            await safe_move(MoveRobotDirection.RightTurn, steps=STEP_SIZE)
        elif cmd == 'x':
            await stop_motion()
        elif cmd == 'o':
            override_event.clear()
            print("[OVERRIDE] Released. Resuming autonomy.")
            break
        elif cmd == 'q':
            shutdown_event.set()
            print("[SYSTEM] Quit requested.")
            break
        else:
            print("[OVERRIDE] Unknown command. Try: w s a d x | o | q")

# ------------- Console listeners -------------
async def keyboard_listener():
    """Listen for override and quit keys globally."""
    print(
        "\nControls:\n"
        "  o = toggle Teacher Override\n"
        "  q = quit program\n"
        "While in override: use w/s/a/d/x, and 'o' to resume.\n"
    )
    while not shutdown_event.is_set():
        line = await _readline_async()
        if not line:
            continue
        key = line.strip().lower()
        if key == 'o':
            if override_event.is_set():
                print("[INFO] Already in override (manual mode).")
            else:
                override_event.set()
                print("[OVERRIDE] Engaged. Autonomy paused; entering manual mode.")
                await manual_loop()
        elif key == 'q':
            shutdown_event.set()
            print("[SYSTEM] Quit requested.")
            break

# Helper: non-blocking stdin
async def _readline_async():
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(None, sys.stdin.readline)
    except Exception:
        return None

# ------------- Main orchestration -------------
async def main():
    dev = await connect_robot(SERIAL_SUFFIX)
    if not dev:
        return
    try:
        auto_task = asyncio.create_task(autonomous_loop())
        kb_task = asyncio.create_task(keyboard_listener())

        await shutdown_event.wait()

        # Cleanup
        if not auto_task.done():
            auto_task.cancel()
            try:
                await auto_task
            except asyncio.CancelledError:
                pass

        if not kb_task.done():
            kb_task.cancel()
            try:
                await kb_task
            except asyncio.CancelledError:
                pass

    finally:
        try:
            await MiniSdk.disconnect()
        except Exception:
            pass
        print("[SYSTEM] Disconnected. Bye.")

if __name__ == "__main__":
    asyncio.run(main())