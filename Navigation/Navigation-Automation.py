import asyncio
import logging
import sys

import mini.mini_sdk as MiniSdk
from mini.dns.dns_browser import WiFiDevice
from mini.apis.api_action import MoveRobot, MoveRobotDirection, MoveRobotResponse
from mini.apis.api_action import PlayAction, PlayActionResponse
from mini.apis.base_api import MiniApiResultType

# === Logging and Configuration ===
MiniSdk.set_log_level(logging.INFO)
MiniSdk.set_robot_type(MiniSdk.RobotType.EDU)

SERIAL_SUFFIX = "00213"  # Change this to match your robot ID
SLEEP_DURATION = 2       # Pause between actions (seconds)
STEP_SIZE = 2            # Step size per move

# === Device Discovery and Connection ===
async def get_device_by_name():
    device: WiFiDevice = await MiniSdk.get_device_by_name(SERIAL_SUFFIX, 10)
    print(f"Device search result: {device}")
    return device

async def connect_device(device: WiFiDevice) -> bool:
    result = await MiniSdk.connect(device)
    print(f"Connect result: {result}")
    return result

# === Robot Action Helpers ===
async def move_robot(direction: MoveRobotDirection, step: int = STEP_SIZE):
    block = MoveRobot(step=step, direction=direction)
    resultType, response = await block.execute()
    if not (
        resultType == MiniApiResultType.Success and
        isinstance(response, MoveRobotResponse) and
        response.isSuccess
    ):
        print(f" Move {direction.name} failed!")
    else:
        print(f" Move {direction.name} successful.")

async def play_builtin_action(name: str):
    block = PlayAction(action_name=name)
    resultType, response = await block.execute()
    ok = (
        resultType == MiniApiResultType.Success and
        isinstance(response, PlayActionResponse) and
        response.isSuccess
    )
    print(f"[→] Action {name} -> {'OK' if ok else 'FAILED'}")

async def raise_hands():
    await play_builtin_action("021")  # Raise both hands action

# === Autonomous Navigation Pattern ===
async def auto_navigation():
    print(" Starting autonomous navigation...")

    # Example navigation path:
    # Move forward -> Turn right -> Move forward -> Turn left -> Raise hands -> Backward
    await move_robot(MoveRobotDirection.FORWARD)
    await asyncio.sleep(SLEEP_DURATION)

    await move_robot(MoveRobotDirection.RIGHTWARD)
    await asyncio.sleep(SLEEP_DURATION)

    await move_robot(MoveRobotDirection.FORWARD)
    await asyncio.sleep(SLEEP_DURATION)

    await move_robot(MoveRobotDirection.LEFTWARD)
    await asyncio.sleep(SLEEP_DURATION)

    await raise_hands()
    await asyncio.sleep(SLEEP_DURATION)

    await move_robot(MoveRobotDirection.BACKWARD)
    await asyncio.sleep(SLEEP_DURATION)

    print("Navigation complete!")

# === Full Main Execution ===
async def main():
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
        print("Entered programming mode.")
        await asyncio.sleep(2)
        await auto_navigation()
    finally:
        await MiniSdk.quit_program()
        await MiniSdk.release()
        print("Shutdown complete.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nProgram interrupted by user.")
    sys.exit(0)