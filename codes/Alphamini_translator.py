import asyncio
import time
import requests
import mini.mini_sdk as MiniSdk
from mini.dns.dns_browser import WiFiDevice
from mini.apis.api_sound import SpeechRecogniseRequest

# -----------------------------
# SDK Setup
# -----------------------------
MiniSdk.set_log_level(20)  # INFO
MiniSdk.set_robot_type(MiniSdk.RobotType.EDU)

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "mistral"

# -----------------------------
# Translator (OLLAMA LLM)
# -----------------------------
def translate_text(text: str, target_language: str) -> str:
#---------- prompt to send to LLM for translation----------
    prompt = (
        f"Translate the following text into {target_language}. "
        f"Output ONLY the translated words. Do not add explanations.\n\n{text}"
    )
    payload = {"model": MODEL_NAME, "prompt": prompt, "stream": False}

    try:
        response = requests.post(OLLAMA_URL, json=payload)
        if response.status_code == 200:
            translated = response.json().get("response", "").strip()
            return translated.replace("\n", " ").strip()
        else:
            print("LLM Error:", response.text)
            return None
    except Exception as e:
        print("LLM Error:", e)
        return None

# -----------------------------
# Alpha Mini helpers
# -----------------------------
async def get_device_by_serial(serial_tail: str = "00213") -> WiFiDevice:
    return await MiniSdk.get_device_by_name(serial_tail, 10)

async def connect_robot(device: WiFiDevice) -> bool:
    return await MiniSdk.connect(device)

async def enter_program_mode():
    await MiniSdk.enter_program()

async def disconnect_robot():
    await MiniSdk.quit_program()
    await MiniSdk.release()

async def say(text: str):
    """Speak text with Alpha Mini"""
    try:
        await MiniSdk.play_tts(text)
    except AttributeError:
        try:
            await MiniSdk.tts_play(text)
        except Exception as e:
            print(f"TTS error: {e}")
    except Exception as e:
        print(f"TTS error: {e}")

async def listen_to_user(duration_sec: int = 3) -> str:
    try:
        req = SpeechRecogniseRequest()
        # Some SDKs allow timeout/recording length; if not, we manually sleep
        _, response = await req.execute()
        # wait for duration_sec to simulate listening period
        await asyncio.sleep(duration_sec)
        if response and hasattr(response, "text"):
            return response.text.strip()
        else:
            return ""
    except Exception as e:
        print(f"Voice recognition error: {e}")
        return ""

# -----------------------------
# Main Loop
# -----------------------------
async def main():
    # 1️⃣ Connect to Alpha Mini
    device = await get_device_by_serial("00213")
    if not device:
        print("Alpha Mini not found")
        return

    if not await connect_robot(device):
        print("Failed to connect to Alpha Mini")
        return

    await enter_program_mode()
    print("Alpha Mini connected.")

    try:
        while True:
            # Step 1: Ask for text to translate
            await say("Speak what you want to translate")
            text_input = await listen_to_user(duration_sec=4)  # listen ~4 seconds
            if not text_input:
                print("Could not detect speech.")
                continue
            print(f"User said: {text_input}")

            # Step 2: Ask for target language
            await say("What language do you want to translate to?")
            target_lang = await listen_to_user(duration_sec=2)  # listen ~2 seconds
            if not target_lang:
                print("Could not detect target language. Using Chinese as default.")
                target_lang = "Chinese"
            print(f"Target language: {target_lang}")

            # Step 3: Translate using LLM
            translated_text = translate_text(text_input, target_lang)
            if not translated_text:
                await say("Translation failed")
                continue

            print(f"Translated text: {translated_text}")

            # Step 4: Speak translated text
            await say(translated_text)

            # Optional: small pause before next loop
            await asyncio.sleep(1)

    except KeyboardInterrupt:
        print("Stopped by user")

    finally:
        await disconnect_robot()
        print("Disconnected from Alpha Mini.")

# -----------------------------
# Run
# -----------------------------
if __name__ == "__main__":
    asyncio.run(main())
