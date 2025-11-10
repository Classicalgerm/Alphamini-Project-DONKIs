import asyncio
import logging
import mini.mini_sdk as MiniSdk
from mini.dns.dns_browser import WiFiDevice

# -----------------------------
# Robot connection helpers
# -----------------------------
async def test_get_device_by_name():
    result: WiFiDevice = await MiniSdk.get_device_by_name("00213", 10)
    print(f"[DISCOVERY] Result: {result}")
    return result

async def test_connect(dev: WiFiDevice) -> bool:
    ok = await MiniSdk.connect(dev)
    if ok:
        print("[CONNECT] Connected to Alpha Mini.")
    else:
        print("[CONNECT] Connection failed.")
    return ok

async def test_start_run_program():
    await MiniSdk.enter_program()
    print("[MODE] Entered program mode.")

async def shutdown():
    await MiniSdk.quit_program()
    await MiniSdk.release()
    print("[SHUTDOWN] Disconnected from Alpha Mini.")

# -----------------------------
# Danger prevention functions
# -----------------------------
async def check_front_obstacle():
    """
    Checks the front ultrasonic sensor distance and prints danger level.
    """
    try:
        distance = await MiniSdk.get_front_ultrasonic_distance()  # in cm
        print(f"[SENSOR] Front distance: {distance} cm")
        if distance < 15:
            print("[DANGER] HIGH: Obstacle very close!")
        elif distance < 30:
            print("[DANGER] MEDIUM: Obstacle nearby")
        else:
            print("[DANGER] LOW: Path clear")
    except Exception as e:
        print("[OBSTACLE] Sensor read error:", e)

# -----------------------------
# Main program
# -----------------------------
async def main():
    MiniSdk.set_log_level(logging.INFO)
    MiniSdk.set_robot_type(MiniSdk.RobotType.EDU)

    # Connect
    device: WiFiDevice = await test_get_device_by_name()
    if not device:
        print("[EXIT] No robot found. Exiting test.")
        return

    if not await test_connect(device):
        print("[EXIT] Connection failed. Exiting test.")
        return

    # Start program mode
    await test_start_run_program()

    # Danger prevention test
    print("[INFO] Starting danger prevention test run...")
    for _ in range(5):  # check 5 times as a test run
        await check_front_obstacle()
        await asyncio.sleep(2)

    # Shutdown
    await shutdown()

if __name__ == '__main__':
    asyncio.run(main())
