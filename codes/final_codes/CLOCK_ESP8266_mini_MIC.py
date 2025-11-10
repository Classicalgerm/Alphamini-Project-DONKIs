"""
Smart Voice Clock Controller (fixed)
-----------------------------------
Merged Alpha Mini + laptop mic voice controller for ESP8266 clock.
This version ensures we connect to Alpha Mini before using SDK APIs.
"""

import asyncio
import logging
import re
import string
import time
import requests
import speech_recognition as sr
import mini.mini_sdk as MiniSdk
from mini.apis.api_observe import ObserveSpeechRecognise
from mini.apis.api_sound import StartPlayTTS
from mini.pb2.codemao_speechrecognise_pb2 import SpeechRecogniseResponse

# ---------------------------
# --- ESP8266 Configuration ---
# ---------------------------
ESP_IP = "http://172.22.189.238"   # Replace with your ESP8266's IP (no trailing slash)
REQUEST_TIMEOUT = 5               # Seconds before request fails

# ---------------------------
# --- Alpha Mini Configuration ---
# ---------------------------
MiniSdk.set_log_level(logging.INFO)
MiniSdk.set_robot_type(MiniSdk.RobotType.EDU)

ROBOT_NAME = "alpha"              # Wake word for Alpha Mini
EXIT_COMMANDS = {"stop", "goodbye", "sleep"}
SLEEP_DURATION = 6                # Time between Alpha Mini's setup and listening

# ---------------------------
# --- Utility Functions ---
# ---------------------------
def normalize_text(text: str) -> str:
    """Cleans and lowers the text for easier command processing."""
    if not text:
        return ""
    text = text.lower()
    return ''.join(ch for ch in text if ch not in string.punctuation).strip()

async def robot_speak(text: str, state: dict):
    """Makes Alpha Mini speak using its TTS (non-blocking wrapper)."""
    if not text or state.get("speaking"):
        return
    state["speaking"] = True
    print(f"[AlphaMini 🗣️]: {text}")
    try:
        await StartPlayTTS(text=text).execute()
    except Exception as e:
        print("[AlphaMini TTS] Error:", e)
    await asyncio.sleep(0.3)
    state["speaking"] = False

def pc_speak(text: str):
    """Fallback TTS for laptop (simple console speak)."""
    print(f"[Laptop 🗣️]: {text}")

# ---------------------------
# --- ESP8266 Communication ---
# ---------------------------
def send_request(path: str, params=None):
    """Handles all GET requests to ESP8266 and returns text or None on failure."""
    try:
        url = f"{ESP_IP}/{path}"
        response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        return response.text
    except requests.exceptions.RequestException as e:
        print("[ESP] Request failed:", e)
        return None

def set_alarm(hour: int, minute: int):
    resp = send_request("set_alarm", {"hour": hour, "minute": minute})
    return "Alarm set successfully." if resp else "Failed to set alarm."

def set_timer(minutes: int):
    resp = send_request("set_timer", {"minutes": minutes})
    return f"Timer started for {minutes} minutes." if resp else "Failed to start timer."

def stop_all():
    resp = send_request("stop_alarm")
    return "All alarms and timers cleared." if resp else "Failed to stop timer."

def get_current_time():
    resp = send_request("get_time")
    return f"The current time is {resp}." if resp else "Unable to reach the clock."

# ---------------------------
# --- Voice Command Handling ---
# ---------------------------
def process_command(command: str):
    """Processes recognized voice commands into actions."""
    if not command:
        return "No command detected."

    if "set alarm" in command:
        numbers = re.findall(r"\d+", command)
        if len(numbers) >= 2:
            return set_alarm(int(numbers[0]), int(numbers[1]))
        elif len(numbers) == 1:
            return set_alarm(int(numbers[0]), 0)
        else:
            return "Please specify the time for the alarm."

    elif "timer" in command or "countdown" in command:
        match = re.search(r"(\d+)", command)
        minutes = int(match.group(1)) if match else 1
        return set_timer(minutes)

    elif "stop" in command or "turn off" in command:
        return stop_all()

    elif "what time" in command or "current time" in command:
        return get_current_time()

    elif command in EXIT_COMMANDS:
        return "Goodbye."

    return "Sorry, I didn’t understand that."

# ---------------------------
# --- Alpha Mini Speech Handler ---
# ---------------------------
async def alpha_speech_handler(msg: SpeechRecogniseResponse, state: dict):
    text = normalize_text(msg.text or "")
    if not text:
        return

    # Ignore speech while robot is talking
    if state.get("speaking"):
        return

    # Wake word detection
    if not state["awake"]:
        if ROBOT_NAME in text:
            state["awake"] = True
            await robot_speak(f"Hello! I am {ROBOT_NAME}. How can I help you?", state)
        return

    # Handle exit command
    if text in EXIT_COMMANDS:
        await robot_speak("Going to sleep. Call my name when you need me.", state)
        state["awake"] = False
        return

    # Process recognized command
    result = process_command(text)
    await robot_speak(result, state)
    print(f"[AlphaMini Result]: {result}")

async def alpha_listen_loop():
    """Continuously listens for Alpha Mini speech input."""
    observe = ObserveSpeechRecognise()
    state = {"awake": False, "speaking": False}

    def handler(msg: SpeechRecogniseResponse):
        # spawn handler task for each incoming recognition event
        asyncio.create_task(alpha_speech_handler(msg, state))

    observe.set_handler(handler)
    observe.start()
    print(f"[AlphaMini] Listening... Say '{ROBOT_NAME}' to wake me.")
    await asyncio.Event().wait()  # Keeps running indefinitely

# ---------------------------
# --- Laptop Microphone Handler ---
# ---------------------------
def listen_from_laptop():
    """Captures voice command from laptop mic as backup."""
    recognizer = sr.Recognizer()
    with sr.Microphone() as source:
        print("[Laptop 🎤] Listening for a command...")
        audio = recognizer.listen(source, phrase_time_limit=5)

    try:
        command = recognizer.recognize_google(audio).lower()
        command = normalize_text(command)
        print(f"[Laptop 🧠] Heard: '{command}'")
        return command
    except sr.UnknownValueError:
        print("[Laptop] Didn't catch that.")
        return ""
    except sr.RequestError:
        print("[Laptop] Speech service unavailable.")
        return ""

def laptop_listener_loop():
    """Continuously listens on laptop mic and acts on valid commands."""
    while True:
        cmd = listen_from_laptop()
        if cmd:
            result = process_command(cmd)
            pc_speak(result)
            print(f"[Laptop Result]: {result}")
            if "goodbye" in cmd or "exit" in cmd:
                break

# ---------------------------
# --- Robot connection helper ---
# ---------------------------
async def connect_to_robot():
    """Discover and connect to Alpha Mini robot safely."""
    print("[Connection] Searching for Alpha Mini...")

    # Try to find a specific robot by name
    device: WiFiDevice = await MiniSdk.get_device_by_name("00213", 10)

    if not device:
        devices = await MiniSdk.get_device_list(10)
        if not devices:
            print("[Connection ❌] No robots found on the network.")
            return False
        device = devices[0]

    # --- Detect field names safely ---
    attrs = vars(device)
    print(f"[Debug] WiFiDevice attributes: {attrs}")

    # Retrieve possible fields
    name = attrs.get("name") or attrs.get("deviceName") or "Unknown"
    ip = attrs.get("ip") or attrs.get("ipAddr") or attrs.get("ip_addr") or "Unknown"

    print(f"[Connection] Connecting to {name} at {ip} ...")

    connected = await MiniSdk.connect(device)
    if connected:
        print("[Connection ✅] Connected successfully!")
        return True
    else:
        print("[Connection ❌] Failed to connect.")
        return False


# ---------------------------
# --- Main Execution ---
# ---------------------------
async def main():
    # 1) Connect to robot (retry & manual fallback)
    connected = await connect_to_robot()
    if not connected:
        print("[Main] Could not connect to Alpha Mini. Exiting.")
        return

    # 2) Enter program mode (safe now because we are connected)
    try:
        await MiniSdk.enter_program()
    except Exception as e:
        print("[Main] enter_program failed:", e)
        return

    await asyncio.sleep(SLEEP_DURATION)

    # 3) Run both listeners in parallel (Alpha Mini + laptop mic)
    print("[System] Running Alpha Mini and laptop voice control together.")
    try:
        await asyncio.gather(
            alpha_listen_loop(),
            asyncio.to_thread(laptop_listener_loop)
        )
    finally:
        # Ensure we try to leave program and release SDK cleanly
        try:
            await MiniSdk.quit_program()
            await MiniSdk.release()
            print("[Main] Cleaned up SDK (quit_program/release).")
        except Exception as e:
            print("[Main] Cleanup error:", e)

# --- Entry Point ---
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[Main] Interrupted. Exiting...")
