import asyncio
import logging
import os
import time
import mini.mini_sdk as MiniSdk
from mini.dns.dns_browser import WiFiDevice
from mini.apis.api_sence import TakePicture, TakePictureRequest
from mini.apis.api_sence import StartSpeechRecognize, StartSpeechRecognizeRequest, StopSpeechRecognize

# -----------------------------
# SDK Setup
# -----------------------------
MiniSdk.set_log_level(logging.INFO)
MiniSdk.set_robot_type(MiniSdk.RobotType.EDU)

# -----------------------------
# Connection helpers
# -----------------------------
async def test_get_device_by_name():
    """Search for the robot based on serial suffix"""
    result: WiFiDevice = await MiniSdk.get_device_by_name("213", 10)
    print(f"Found device: {result}")
    return result

async def test_connect(dev: WiFiDevice) -> bool:
    """Connect to the robot"""
    return await MiniSdk.connect(dev)

async def test_start_run_program():
    """Enter programming mode"""
    await MiniSdk.enter_program()

async def shutdown():
    """Disconnect and release resources"""
    await MiniSdk.quit_program()
    await MiniSdk.release()

# -----------------------------
# Robot TTS
# -----------------------------
async def say(text: str):
    """Play text-to-speech using robot"""
    try:
        await MiniSdk.play_tts(text)
    except AttributeError:
        await MiniSdk.tts_play(text)
    except Exception as e:
        print(f"TTS error: {e}")

# -----------------------------
# Camera
# -----------------------------
async def take_photo_log(student_id: int):
    """Take a photo from Alpha Mini and log locally."""
    print(f"Capturing photo for student {student_id} ...")
    try:
        req = TakePictureRequest(type=0)  # 0 = front camera
        block = TakePicture(req)
        result_type, response = await block.execute()

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"student_{student_id}_time_{timestamp}.jpg"
        log_path = os.path.join(os.getcwd(), "photo_log.txt")

        if response and getattr(response, "isSuccess", False):
            print(f"Photo captured on robot.")
            with open(log_path, "a") as log_file:
                log_file.write(f"{filename} captured at {timestamp}\n")
            print(f"Logged photo entry locally: {log_path}")
            await say("Picture taken")
        else:
            print(f"Photo capture failed: {response}")
            await say("Photo failed, please try again")

    except Exception as e:
        print(f"Error taking photo: {e}")
        await say("Error while taking picture")

# -----------------------------
# Speech Recognition Handler
# -----------------------------
async def listen_for_commands():
    """Continuously listen for 'take attendance' command."""
    print("Listening for command 'take attendance' ...")
    await say("Say take attendance to start")

    req = StartSpeechRecognizeRequest(language=1)  # English = 1
    recognize = StartSpeechRecognize(req)

    while True:
        result_type, response = await recognize.execute()
        if response and hasattr(response, "text") and response.text:
            recognized_text = response.text.strip().lower()
            print(f"You said: {recognized_text}")

            if "take attendance" in recognized_text:
                await say("Starting attendance now")
                await handle_attendance()
                await say("Attendance complete")
                break

        await asyncio.sleep(1)

# -----------------------------
# Attendance Logic
# -----------------------------
async def handle_attendance():
    """Run the attendance-taking routine."""
    for student_id in range(1, 3):  # you can change the range
        await take_photo_log(student_id)
        await say(f"Next student")
        await asyncio.sleep(2)

# -----------------------------
# Main logic
# -----------------------------
async def main():
    device: WiFiDevice = await test_get_device_by_name()
    if not device:
        print("No device found.")
        return

    connected = await test_connect(device)
    if not connected:
        print("Could not connect to robot.")
        return

    await test_start_run_program()

    try:
        await listen_for_commands()
    finally:
        await shutdown()
        print("Disconnected from robot.")

# -----------------------------
# Entry point
# -----------------------------
if __name__ == "__main__":
    asyncio.run(main())
