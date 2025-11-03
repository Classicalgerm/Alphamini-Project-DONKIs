import asyncio
import logging
import sys

#  THE CORRECT MODULE NAME IS 'api_sence' (Confirmed)
from mini.apis.api_sence import GetInfraredDistance, GetInfraredDistanceResponse

import mini.mini_sdk as MiniSdk
from mini.dns.dns_browser import WiFiDevice
from mini.apis.api_action import MoveRobot, MoveRobotDirection, MoveRobotResponse
from mini.apis.base_api import MiniApiResultType

MiniSdk.set_log_level(logging.INFO)
MiniSdk.set_robot_type(MiniSdk.RobotType.EDU)

# --- Configuration ---
SERIAL_SUFFIX = "00213"  # <-- *REPLACE with your robot's serial suffix*
STEP_SIZE = 1  # Default steps for forward movement
BACKWARD_STEPS = 2  # Steps to move backward for avoidance
SLEEP_DURATION = 2
SAFE_DISTANCE_CM = 20


# ---------------------

# The sensor discovery logic is no longer dynamic since we confirmed the name.
# We will use the direct imports and correct class names found by the previous run.
# Assuming your previous run found the classes, we use the standard names now.

# We must keep a simplified structure now that the error is resolved.
# We trust that GetInfraredDistance and GetInfraredDistanceResponse are the correct class names.


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


async def move_robot(direction: MoveRobotDirection, step: int = STEP_SIZE):
    """Sends a movement command to the robot."""
    block = MoveRobot(step=step, direction=direction)
    resultType, response = await block.execute()

    if not (resultType == MiniApiResultType.Success and isinstance(response, MoveRobotResponse) and response.isSuccess):
        print(f" Move command failed! Direction: {direction.name}")


async def get_distance_cm():
    """Gets the infrared distance reading from the sensor (using 'api_sence')."""
    # Assuming GetInfraredDistance is the correct class name that worked previously
    block = GetInfraredDistance()
    resultType, response = await block.execute()

    if resultType == MiniApiResultType.Success and isinstance(response, GetInfraredDistanceResponse):
        # The 'distance' attribute is retrieved here
        return response.distance

    print(" Failed to get distance reading. Check robot's status.")
    return None


async def avoid_obstacles():
    """Main loop for autonomous navigation with backward obstacle avoidance."""
    print(" Starting autonomous navigation with BACKWARD avoidance...")

    while True:
        distance = await get_distance_cm()

        if distance is None:
            await asyncio.sleep(1)
            continue

        print(f"Distance: {distance} cm")

        if distance < SAFE_DISTANCE_CM:
            # --- MODIFIED LOGIC HERE: Move Backward 2 Steps ---
            print(f"Obstacle detected! Moving backward {BACKWARD_STEPS} steps...")
            await move_robot(MoveRobotDirection.BACKWARD, step=BACKWARD_STEPS)

            # After moving back, turn right to avoid the obstacle and continue
            print("Turning right to find a clear path.")
            await move_robot(MoveRobotDirection.RIGHTWARD, step=2)
            await asyncio.sleep(SLEEP_DURATION)

        else:
            print("Path clear. Moving forward.")
            await move_robot(MoveRobotDirection.FORWARD, step=STEP_SIZE)
            await asyncio.sleep(SLEEP_DURATION)


async def main():
    """Initializes connection and runs the main loop."""
    # Omitted for brevity: get_device_by_name and connect_device calls

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
        print(f"An unexpected error occurred: {e}")
    finally:
        await MiniSdk.quit_program()
        await MiniSdk.release()
        print("Shutdown complete. Robot freed.")


if _name_ == "_main_":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nProgram interrupted by user (Ctrl+C).")
        sys.exit(0)