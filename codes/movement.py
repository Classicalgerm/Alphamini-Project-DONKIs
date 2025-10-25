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

SERIAL_SUFFIX = "00213"  # AlphaMini number
SLEEP_DURATION = 6
STEP_SIZE = 1

# === Device Discovery and Connection ===
async def get_device_by_name():
    device: WiFiDevice = await MiniSdk.get_device_by_name(SERIAL_SUFFIX, 10)
    print(f"Device search result: {device}")
    return device

async def connect_device(device: WiFiDevice) -> bool:
    result = await MiniSdk.connect(device)
    print(f"Connect result: {result}")
    return result

# === Movement Logic ===
async def move_robot(direction: MoveRobotDirection, step: int = STEP_SIZE):
    block = MoveRobot(step=step, direction=direction)
    resultType, response = await block.execute()
    print(f"move_robot result: {response}")
    if not (
        resultType == MiniApiResultType.Success and
        response is not None and
        isinstance(response, MoveRobotResponse) and
        response.isSuccess
    ):
        print("Move command failed!")

# === Built-in Actions ===
async def play_builtin_action(name: str):
    block = PlayAction(action_name=name)
    resultType, response = await block.execute()
    ok = (
        resultType == MiniApiResultType.Success and
        isinstance(response, PlayActionResponse) and
        response is not None and
        response.isSuccess
    )
    print(f"[→] action {name} -> {'OK' if ok else 'FAILED'}")

async def raise_hands():
    await play_builtin_action("021")

# === Control Loop ===
async def control_loop():
    print("Control the robot with WASD keys. Press Q to quit.")
    while True:
        key = input("Enter command (W/A/S/D/R/Q): ").strip().lower()
        if key == "w":
            await move_robot(MoveRobotDirection.FORWARD)
        elif key == "s":
            await move_robot(MoveRobotDirection.BACKWARD)
        elif key == "a":
            await move_robot(MoveRobotDirection.LEFTWARD)
        elif key == "d":
            await move_robot(MoveRobotDirection.RIGHTWARD)
        elif key == "r":
            await raise_hands()
        elif key == "q":
            print("Exiting control loop...")
            break
        else:
            print("Invalid input! Use W/A/S/D for movement, R to raise hands, or Q to quit.")

# === Main Code ===
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
        await asyncio.sleep(SLEEP_DURATION)
        await control_loop()
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
