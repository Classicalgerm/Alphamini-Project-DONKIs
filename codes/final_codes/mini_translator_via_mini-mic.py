import asyncio
import logging
import requests
import string
import mini.mini_sdk as MiniSdk
from mini.apis.api_sound import StartPlayTTS
from mini.apis.api_observe import ObserveSpeechRecognise
from mini.dns.dns_browser import WiFiDevice
from mini.pb2.codemao_speechrecognise_pb2 import SpeechRecogniseResponse

# ---- Configuration ----
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "mistral"
DEFAULT_LANGUAGE = "Spanish"
ROBOT_NAME = "alpha"
STOP_COMMANDS = {"stop translation", "stop translating"}

# ---- Connection ----
async def find_and_connect():
    device: WiFiDevice = await MiniSdk.get_device_by_name("00213", 10)
    if not device:
        print("No Alpha Mini found.")
        return None
    if not await MiniSdk.connect(device):
        print("Connection failed.")
        return None
    await MiniSdk.enter_program()
    print("Connected to Alpha Mini.")
    return device

async def shutdown():
    await MiniSdk.quit_program()
    await MiniSdk.release()
    print("Disconnected from Alpha Mini.")

# ---- Speech & TTS ----
async def say(text: str):
    if not text:
        return
    tts = StartPlayTTS(text=text)
    await tts.execute()
    await asyncio.sleep(0.3)

# ---- Translation ----
def translate_text(text: str, target_language: str):
    try:
        payload = {
            "model": MODEL_NAME,
            "prompt": f"Translate this into {target_language}. Return only the translation:\n{text}",
            "stream": False
        }
        response = requests.post(OLLAMA_URL, json=payload)
        if response.status_code == 200:
            return response.json().get("response", "").strip()
    except Exception as e:
        print(f"Translation error: {e}")
    return None

# ---- Speech Recognizer ----
class TranslatorState:
    def __init__(self):
        self.listening = False
        self.target_language = DEFAULT_LANGUAGE
        self.active = False
        self.speaking = False

async def handle_speech(msg: SpeechRecogniseResponse, state: TranslatorState):
    text = (msg.text or "").strip()
    if not text or state.speaking:
        return

    cleaned = ''.join(ch for ch in text.lower() if ch not in string.punctuation)
    print(f"Heard: {cleaned}")

    if not state.active:
        if "translate" in cleaned:
            state.active = True
            await say("Which language would you like to translate to?")
        return

    if not state.listening:
        # Set target language
        state.target_language = cleaned.title() if cleaned else DEFAULT_LANGUAGE
        await say(f"Okay, translating into {state.target_language}. Say something to translate.")
        state.listening = True
        return

    if any(cmd in cleaned for cmd in STOP_COMMANDS):
        await say("Stopping translation mode.")
        state.active = False
        state.listening = False
        return

    translated = translate_text(cleaned, state.target_language)
    if translated:
        await say(translated)
    else:
        await say("Sorry, I couldn't translate that.")

async def listen_loop():
    observer = ObserveSpeechRecognise()
    state = TranslatorState()

    def callback(msg: SpeechRecogniseResponse):
        asyncio.create_task(handle_speech(msg, state))

    observer.set_handler(callback)
    observer.start()
    print("Say 'translate' to begin translation mode.")
    await asyncio.Event().wait()

# ---- Main ----
async def main():
    MiniSdk.set_log_level(logging.INFO)
    MiniSdk.set_robot_type(MiniSdk.RobotType.EDU)

    device = await find_and_connect()
    if not device:
        return

    try:
        await listen_loop()
    finally:
        await shutdown()

if __name__ == "__main__":
    asyncio.run(main())
