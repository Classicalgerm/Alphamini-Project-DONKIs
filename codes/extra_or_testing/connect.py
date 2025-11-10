import asyncio
import logging
import mini.mini_sdk as MiniSdk
from mini.dns.dns_browser import WiFiDevice

async def test_get_device_by_name():
    result: WiFiDevice = await MiniSdk.get_device_by_name("00213", 10)
    print(f"test_get_device_by_name result:{result}")
    return result

async def test_get_device_list():
    results = await MiniSdk.get_device_list(10)
    print(f"test_get_device_list results = {results}")
    return results
async def test_connect(dev: WiFiDevice) -> bool:
    return await MiniSdk.connect(dev)

# Enter the programming mode, the robot has a tts broadcast, here through asyncio.sleep, let the current coroutine wait 6 seconds to return, let the robot finish the broadcast
async def test_start_run_program():
    await MiniSdk.enter_program()

# Disconnect and release resources
async def shutdown():
    await MiniSdk.quit_program()
    await MiniSdk.release()

# The default log level is Warning, set to INFO
MiniSdk.set_log_level(logging.INFO)
# Set robot type
MiniSdk.set_robot_type(MiniSdk.RobotType.EDU)

async def main():
    device: WiFiDevice = await test_get_device_by_name()
    if device:
        await test_connect(device)
        await shutdown()

if __name__ == '__main__':
    asyncio.run(main())
