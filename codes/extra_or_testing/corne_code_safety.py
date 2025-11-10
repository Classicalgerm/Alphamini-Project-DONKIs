import asyncio
import logging
import sys
from collections import deque
import time

#  THE CORRECT MODULE NAME IS 'api_sence' (Confirmed)
from mini.apis.api_sence import GetInfraredDistance, GetInfraredDistanceResponse

import mini.mini_sdk as MiniSdk
from mini.dns.dns_browser import WiFiDevice
from mini.apis.api_action import MoveRobot, MoveRobotDirection, MoveRobotResponse
from mini.apis.base_api import MiniApiResultType

MiniSdk.set_log_level(logging.INFO)
MiniSdk.set_robot_type(MiniSdk.RobotType.EDU)

# --- Configuration (original) ---
SERIAL_SUFFIX = "00213"      # <-- *REPLACE with your robot's serial suffix*
STEP_SIZE = 1                # Default steps for forward movement
BACKWARD_STEPS = 2           # Steps to move backward for avoidance
SLEEP_DURATION = 2
SAFE_DISTANCE_CM = 20        # "Soft" avoidance threshold

# --- Safety Configuration (NEW) ---
# 1) Emergency stop
E_STOP_KEY = "e"             # Type 'e' + Enter in console to stop
# 2) Sensor sanity & debounce
MEDIAN_WINDOW = 3            # window for median smoothing
OBSTACLE_CONFIRM_READS = 2   # require N consecutive "too close" readings
HARD_STOP_CM = 8             # "Hard" stop distance (very close)
SENSOR_FAILURE_LIMIT = 5     # consecutive failures before safe stop
# 3) Command rate-limit & bounds
MAX_STEP = 6                 # clamp steps to avoid big jumps
MIN_COMMAND_INTERVAL = 0.4   # seconds between movement commands

# ---------------------
# Globals for safety mechanisms
estop_event = asyncio.Event()
_last_cmd_ts = 0.0
_distance_buf = deque(maxlen=MEDIAN_WINDOW)
_consecutive_close = 0
_consecutive_fail = 0


async def get_device_by_name():
    """Searches for the robot device by its serial suffix."""
    print(f"Searching for device with suffix: {SERIAL_SUFFIX}")
    device = await MiniSdk.get_device_by_name(SERIAL_SUFFIX, 10)
    print(f"Device search result: {device}")
    return device


async def connect_device(device: WiFiDevice) -> bool:
    """Connects to the found robot device."""
    result = await MiniSdk.connect(device)
    print(f"Connect result: {result}")
    return result


async def safe_move_robot(direction: MoveRobotDirection, step: int):
    """
    Safety-wrapped movement:
      - respects E-Stop
      - clamps steps
      - rate-limits command frequency
    """
    global _last_cmd_ts
    if estop_event.is_set():
        print("[SAFETY] E-Stop set: ignoring move command.")
        return

    # Clamp step
    step = max(1, min(int(step), MAX_STEP))

    # Rate-limit
    now = time.monotonic()
    dt = now - _last_cmd_ts
    if dt < MIN_COMMAND_INTERVAL:
        await asyncio.sleep(MIN_COMMAND_INTERVAL - dt)

    block = MoveRobot(step=step, direction=direction)
    resultType, response = await block.execute()

    _last_cmd_ts = time.monotonic()

    if not (resultType == MiniApiResultType.Success and isinstance(response, MoveRobotResponse) and response.isSuccess):
        print(f"[WARN] Move command failed! Direction: {direction.name}, step={step}")


async def get_distance_cm():
    """Gets the infrared distance reading from the sensor (using 'api_sence')."""
    block = GetInfraredDistance()
    resultType, response = await block.execute()

    if resultType == MiniApiResultType.Success and isinstance(response, GetInfraredDistanceResponse):
        return response.distance

    print("[WARN] Failed to get distance reading. Check robot's status.")
    return None


def median(values):
    if not values:
        return None
    s = sorted(values)
    mid = len(s) // 2
    if len(s) % 2 == 1:
        return s[mid]
    return 0.5 * (s[mid - 1] + s[mid])


async def estop_listener():
    """
    Emergency stop listener.
    Type 'e' + Enter in the terminal to trigger an immediate, graceful stop.
    (If stdin is not available in your environment, you still have Ctrl+C.)
    """
    print(f"[SAFETY] Press '{E_STOP_KEY}' then Enter at any time for EMERGENCY STOP.")
    loop = asyncio.get_event_loop()
    try:
        while not estop_event.is_set():
            # Read one line from stdin off the main thread
            line = await loop.run_in_executor(None, sys.stdin.readline)
            if line is None:
                break
            if line.strip().lower() == E_STOP_KEY:
                print("[SAFETY] E-Stop requested by user.")
                estop_event.set()
                break
    except Exception as e:
        print(f"[SAFETY] E-Stop listener error (continuing): {e}")


async def avoid_obstacles():
    """Main loop for autonomous navigation with backward obstacle avoidance + SAFETY."""
    global _consecutive_close, _consecutive_fail

    print("Starting autonomous navigation with BACKWARD avoidance + SAFETY...")
    # Launch E-Stop listener in the background
    asyncio.create_task(estop_listener())

    while not estop_event.is_set():
        distance = await get_distance_cm()

        if distance is None:
            _consecutive_fail += 1
            print(f"[SAFETY] Sensor failure #{_consecutive_fail}/{SENSOR_FAILURE_LIMIT}")
            if _consecutive_fail >= SENSOR_FAILURE_LIMIT:
                print("[SAFETY] Too many sensor failures. Entering safe stop.")
                estop_event.set()
                break
            await asyncio.sleep(0.5)
            continue

        # Reset failure count on success
        _consecutive_fail = 0

        # Sensor sanity: ignore non-positive or absurd values
        if distance <= 0 or distance > 5000:
            print(f"[SAFETY] Discarding out-of-range distance: {distance}")
            await asyncio.sleep(0.2)
            continue

        # Median filter buffer
        _distance_buf.append(float(distance))
        filt = median(list(_distance_buf))
        if filt is None:
            await asyncio.sleep(0.1)
            continue

        print(f"Distance (raw: {distance:.1f} cm, median: {filt:.1f} cm)")

        # HARD stop if extremely close even once
        if filt < HARD_STOP_CM:
            print(f"[SAFETY] HARD STOP: {filt:.1f} cm < {HARD_STOP_CM} cm.")
            # Back away a little then stop loop
            await safe_move_robot(MoveRobotDirection.BACKWARD, step=max(BACKWARD_STEPS, 2))
            estop_event.set()
            break

        # Debounced "soft" avoidance if within SAFE_DISTANCE_CM
        if filt < SAFE_DISTANCE_CM:
            _consecutive_close += 1
        else:
            _consecutive_close = 0

        if _consecutive_close >= OBSTACLE_CONFIRM_READS:
            print(f"Obstacle confirmed ({_consecutive_close} readings). "
                  f"Backing up {BACKWARD_STEPS} and turning right.")
            await safe_move_robot(MoveRobotDirection.BACKWARD, step=BACKWARD_STEPS)
            await safe_move_robot(MoveRobotDirection.RIGHTWARD, step=2)
            _consecutive_close = 0
            await asyncio.sleep(SLEEP_DURATION)
            continue

        # Path clear
        print("Path clear. Moving forward.")
        await safe_move_robot(MoveRobotDirection.FORWARD, step=STEP_SIZE)
        await asyncio.sleep(SLEEP_DURATION)


async def main():
    """Initializes connection and runs the main loop."""
    device = await get_device_by_name()
    if not device:
        print("No device found. Exiting.")
        return

    connected = await connect_device(device)
    if not connected:
        print("Failed to connect. Exiting.")
        return

    try:
        await MiniSdk.enter_program()
        print("Entered programming mode. Starting avoidance loop.")
        await avoid_obstacles()

    except Exception as e:
        print(f"[ERROR] An unexpected error occurred: {e}")
    finally:
        # Graceful shutdown always
        try:
            await MiniSdk.quit_program()
        finally:
            await MiniSdk.release()
        print("Shutdown complete. Robot freed.")


if _name_ == "_main_":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nProgram interrupted by user (Ctrl+C).")
        # Ensure release in case main didn't run
        try:
            asyncio.run(MiniSdk.quit_program())
        except Exception:
            pass
        try:
            asyncio.run(MiniSdk.release())
        except Exception:
            pass
        sys.exit(0)