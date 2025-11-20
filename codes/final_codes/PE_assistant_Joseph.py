import asyncio
import logging
import mini.mini_sdk as MiniSdk
from mini.dns.dns_browser import WiFiDevice
from mini.apis.base_api import MiniApiResultType
from mini.apis.api_action import PlayAction, PlayActionResponse
from mini.apis.api_sound import StartPlayTTS
import speech_recognition as sr

# ==============================
# CONFIGURATION
# ==============================
MiniSdk.set_log_level(logging.INFO)
MiniSdk.set_robot_type(MiniSdk.RobotType.EDU)

ROBOT_SERIAL_SUFFIX = "213"  # last digits of your robot serial
PROGRAM_READY_WAIT = 4
_connected = False


# ==============================
# CONNECTION FUNCTIONS
# ==============================
async def discover_robot(serial_suffix, timeout_s=10):
    print("[DISCOVERY] Searching for Alpha Mini...")
    try:
        dev = await MiniSdk.get_device_by_name(serial_suffix, timeout_s)
        if dev:
            print("[DISCOVERY] Found:", dev)
            return dev
    except Exception as e:
        print("[DISCOVERY] Error:", e)
    print("[DISCOVERY] No robot found.")
    return None


async def connect_robot(dev: WiFiDevice):
    global _connected
    ok = await MiniSdk.connect(dev)
    if ok:
        _connected = True
        print("[CONNECT] Connected to Alpha Mini.")
    else:
        print("[CONNECT] Connection failed.")
    return ok


async def enter_program_mode():
    print("[MODE] Entering program mode...")
    await MiniSdk.enter_program()
    await asyncio.sleep(PROGRAM_READY_WAIT)


async def safe_shutdown():
    global _connected
    if not _connected:
        return
    print("[SHUTDOWN] Disconnecting...")
    try:
        await MiniSdk.quit_program()
        await MiniSdk.release()
    except Exception as e:
        print("[SHUTDOWN] Error:", e)
    print("[SHUTDOWN] Done.")


# ==============================
# TEXT-TO-SPEECH
# ==============================
async def tts_speak(text: str):
    print(f"[TEACHER] {text}")
    resultType, response = await StartPlayTTS(text=text).execute()
    if not (resultType == MiniApiResultType.Success and response and response.isSuccess):
        print("[TTS] Failed to speak.")


# ==============================
# PLAY BUILT-IN ACTION
# ==============================
async def play_builtin_action(action_code: str):
    print(f"[ACTION] Sending built-in action command: {action_code}...")
    block = PlayAction(action_name=action_code)
    resultType, response = await block.execute()

    if (
            resultType == MiniApiResultType.Success and
            response is not None and
            isinstance(response, PlayActionResponse) and
            response.isSuccess
    ):
        print(f"[ACTION] Built-in action ({action_code}) started successfully.")
    else:
        error_code = response.resultCode if response else 'N/A'
        print(f"[ACTION] Built-in action ({action_code}) failed! Result type: {resultType}, Code: {error_code}")


# ==============================
# EXERCISE ROUTINE
# ==============================
async def do_repetition(action_code: str, reps: int, instruction: str):
    # Speak instruction
    await tts_speak(f"Let's do {reps} {instruction}!")
    for i in range(1, reps + 1):
        print(f"[ROBOT] {instruction} {i}/{reps}")
        await play_builtin_action(action_code)
        await asyncio.sleep(1)  # small delay between repetitions


async def physical_ed_class():
    # Push-ups: 012
    await do_repetition("012", 1, "push-ups")

    # Squats: 031
    await do_repetition("031", 2, "squats")

    # Raise hands / stretch arms: 017
    await do_repetition("017", 1, "stretch your arms")

    # Right Lunge: 028
    await do_repetition("028", 2, "Lunges")


# ==============================
# VOICE COMMAND
# ==============================
def recognize_speech():
    r = sr.Recognizer()
    with sr.Microphone() as source:
        print("Listening for command: 'start class' ...")
        audio = r.listen(source, phrase_time_limit=5)
    try:
        command = r.recognize_google(audio)
        print(f"You said: {command}")
        return command.lower()
    except sr.UnknownValueError:
        print("Could not understand audio.")
        return ""
    except sr.RequestError:
        print("Speech Recognition service unavailable.")
        return ""


# ==============================
# MAIN
# ==============================
async def main():
    dev = await discover_robot(ROBOT_SERIAL_SUFFIX)
    if not dev:
        print("[FATAL] Robot not found.")
        return

    if not await connect_robot(dev):
        print("[FATAL] Connection failed.")
        return

    await enter_program_mode()

    print("[INFO] Ready for voice command.")
    while True:
        command = recognize_speech()

        if "start warm up" in command:
            print("[CLASS] Starting warmup routine...")

            # Step 1: Intro
            await tts_speak("Class time for warmups.")

            # Step 2: Push-ups
            await tts_speak("Let's do 5 push-ups.")
            await do_repetition("012", 1, "push-ups")

            # Step 3: Squats
            await tts_speak("Let's do 2 squats.")
            await do_repetition("031", 2, "squats")

            # Step 4: Stretch arms
            await tts_speak("Let's stretch our arms.")
            await do_repetition("017", 1, "stretch your arms")

            # Step 5: Lunges
            await tts_speak("Let's do lunges.")
            await do_repetition("028", 2, "lunges")

            # Step 6: Wrap-up
            await tts_speak("Good job class. Warmup complete.")
            print("[CLASS] Warmup routine complete.")

        elif "exit" in command or "quit" in command:
            print("[INFO] Exiting...")
            break
        else:
            print("[INFO] Command not recognized. Say 'Start warmups' or 'exit'.")

    await safe_shutdown()

if __name__ == "__main__":
    asyncio.run(main())