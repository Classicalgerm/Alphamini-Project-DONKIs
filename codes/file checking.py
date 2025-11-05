import asyncio
import logging
import mini.mini_sdk as MiniSdk
from mini.dns.dns_browser import WiFiDevice
from mini.apis.api_sound import StartPlayTTS


async def _play_tts():
    block: StartPlayTTS = StartPlayTTS(text="hello! i'm alphamini, test, test, test")
    # return (), response is `ControlTTSResponse`
    (resultType, response) = await block.execute()
    print(f'{response}')
async def test_tts():
    MiniSdk.set_log_level(logging.INFO)
    MiniSdk.set_robot_type(MiniSdk.RobotType.EDU)

    # Step 1: Find your Alpha Mini by serial tail
    device: WiFiDevice = await MiniSdk.get_device_by_name("00213", 10)
    if not device:
        print("❌ Robot not found")
        return

    # Step 2: Connect and enter programming mode
    await MiniSdk.connect(device)
    await MiniSdk.enter_program()

    # Step 3: Use StartPlayTTS to play TTS

    await _play_tts()

    # Step 4: Exit program mode and release resources
    await MiniSdk.quit_program()
    await MiniSdk.release()

    print("✅ TTS test complete.")

# Run the test
if __name__ == "__main__":
    asyncio.run(test_tts())
