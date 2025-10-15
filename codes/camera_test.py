import asyncio
import logging
import os
import shutil
import mini.mini_sdk as MiniSdk
from mini.dns.dns_browser import WiFiDevice
from mini.apis.api_sence import TakePicture, TakePictureRequest

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
    result: WiFiDevice = await MiniSdk.get_device_by_name("00213", 10)
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
        # Some SDKs use tts_play
        await MiniSdk.tts_play(text)
    except Exception as e:
        print(f"⚠️ TTS error: {e}")

# -----------------------------
# Camera
# -----------------------------
async def take_and_download_photo():
    """Take a photo from Alpha Mini and save it locally"""
    print("📸 Taking a photo...")
    try:
        # Create TakePicture request using numeric type 0 (front camera)
        req = TakePictureRequest(type=0)
        block = TakePicture(req)

        # Execute the photo capture asynchronously
        result_type, response = await block.execute()

        if response and getattr(response, "isSuccess", False):
            print("✅ Picture captured on robot.")
            remote_path = getattr(response, "file_path", None)
            if remote_path:
                local_name = os.path.basename(remote_path)
                local_path = os.path.join(os.getcwd(), local_name)

                # Copy locally if file exists (some SDKs auto-download)
                if os.path.exists(remote_path):
                    shutil.copy(remote_path, local_path)
                    print(f"💾 Photo saved to: {local_path}")
                else:
                    print(f"⚠️ Photo success, but file not found locally. File should be on robot: {remote_path}")
            else:
                print("⚠️ Robot did not return file path.")
        else:
            print(f"❌ Photo capture failed: {response}")

    except Exception as e:
        print(f"⚠️ Error taking photo: {e}")

# -----------------------------
# Main logic
# -----------------------------
async def main():
    device: WiFiDevice = await test_get_device_by_name()
    if not device:
        print("❌ No device found.")
        return

    connected = await test_connect(device)
    if not connected:
        print("❌ Could not connect to robot.")
        return

    await test_start_run_program()

    try:
        # Speak prompt
        await say("Please show your QR code one by one!")
        await asyncio.sleep(2)

        # Take photo
        await take_and_download_photo()

    finally:
        await shutdown()
        print("🔌 Disconnected from robot.")

# -----------------------------
# Entry point
# -----------------------------
if __name__ == "__main__":
    asyncio.run(main())
