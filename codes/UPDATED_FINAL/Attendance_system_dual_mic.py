import asyncio
import logging
import os
import time
import string
import mini.mini_sdk as MiniSdk
from mini.dns.dns_browser import WiFiDevice
from mini.apis.api_sence import TakePicture, TakePictureRequest
from mini.apis.api_observe import ObserveSpeechRecognise
from mini.pb2.codemao_speechrecognise_pb2 import SpeechRecogniseResponse
import speech_recognition as sr

# -----------------------------
# SDK Setup
# -----------------------------
MiniSdk.set_log_level(logging.INFO)
MiniSdk.set_robot_type(MiniSdk.RobotType.EDU)
ROBOT_SERIAL_SUFFIX = "213"

# -----------------------------
# TTS Helper
# -----------------------------
async def say(text: str, state: dict = None):
    if state is not None:
        state["speaking"] = True
    try:
        await MiniSdk.play_tts(text)
    except AttributeError:
        await MiniSdk.tts_play(text)
    except Exception as e:
        print(f"[TTS] Error: {e}")
    await asyncio.sleep(0.3)
    if state is not None:
        state["speaking"] = False

# -----------------------------
# Camera Helper
# -----------------------------
async def take_photo_log(student_id: int):
    print(f"Capturing photo for student {student_id} ...")
    try:
        req = TakePictureRequest(type=0)  # front camera
        block = TakePicture(req)
        result_type, response = await block.execute()

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"student_{student_id}_time_{timestamp}.jpg"
        log_path = os.path.join(os.getcwd(), "photo_log.txt")

        if response and getattr(response, "isSuccess", False):
            print("Photo captured successfully.")
            with open(log_path, "a") as log_file:
                log_file.write(f"{filename} captured at {timestamp}\n")
            await say(f"Picture taken for student {student_id}")
        else:
            print(f"Photo capture failed: {response}")
            await say("Photo capture failed, please try again")

    except Exception as e:
        print(f"Error taking photo: {e}")
        await say("Error while taking picture")

# -----------------------------
# PC Microphone Listener
# -----------------------------
def listen_pc_mic(timeout=6):
    recognizer = sr.Recognizer()
    with sr.Microphone() as source:
        recognizer.adjust_for_ambient_noise(source)
        try:
            audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=8)
            return recognizer.recognize_google(audio).strip()
        except Exception:
            return ""

# -----------------------------
# Alpha Mini Microphone Listener
# -----------------------------
async def listen_alpha_mic(timeout=8):
    future = asyncio.get_event_loop().create_future()
    observer = ObserveSpeechRecognise()

    def handler(msg: SpeechRecogniseResponse):
        text = (msg.text or "").strip()
        if text and not future.done():
            future.set_result(text)

    observer.set_handler(handler)
    observer.start()
    try:
        return await asyncio.wait_for(future, timeout=timeout)
    except asyncio.TimeoutError:
        return ""
    finally:
        observer.stop()

# -----------------------------
# Hybrid Listener
# -----------------------------
async def hybrid_listen():
    task_alpha = asyncio.create_task(listen_alpha_mic())
    loop = asyncio.get_event_loop()
    task_pc = loop.run_in_executor(None, listen_pc_mic)

    done, pending = await asyncio.wait([task_alpha, task_pc], return_when=asyncio.FIRST_COMPLETED)

    result = ""
    for d in done:
        try:
            result = d.result()
            if result:
                break
        except asyncio.CancelledError:
            pass

    for p in pending:
        p.cancel()
        try:
            await p
        except asyncio.CancelledError:
            pass

    return ''.join(ch for ch in result if ch not in string.punctuation).strip()

# -----------------------------
# Attendance Routine
# -----------------------------
async def handle_attendance():
    for student_id in range(1, 4):  # adjust as needed
        await take_photo_log(student_id)
        await say(f"Next student")
        await asyncio.sleep(1)

# -----------------------------
# Listen for Command
# -----------------------------
async def listen_for_commands(tts_state):
    await say("Say take attendance to start.", tts_state)
    print("Listening for command 'take attendance'...")

    while True:
        spoken_text = await hybrid_listen()
        if not spoken_text:
            continue

        print(f"Heard: {spoken_text.lower()}")
        if "take attendance" in spoken_text.lower():
            await say("Starting attendance now.", tts_state)
            await handle_attendance()
            await say("Attendance complete.", tts_state)
            break

        await asyncio.sleep(0.5)

# -----------------------------
# Connection Helpers
# -----------------------------
async def find_and_connect():
    device: WiFiDevice = await MiniSdk.get_device_by_name(ROBOT_SERIAL_SUFFIX, 10)
    if not device:
        print("No robot found.")
        return None
    if not await MiniSdk.connect(device):
        print("Could not connect to robot.")
        return None
    await MiniSdk.enter_program()
    print("Connected to Alpha Mini.")
    return device

async def shutdown():
    await MiniSdk.quit_program()
    await MiniSdk.release()
    print("Disconnected from Alpha Mini.")

# -----------------------------
# Main
# -----------------------------
async def main():
    tts_state = {"speaking": False}
    device = await find_and_connect()
    if not device:
        return

    try:
        await listen_for_commands(tts_state)
    finally:
        await shutdown()

# -----------------------------
# Entry
# -----------------------------
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted. Exiting.")
