import asyncio
import logging
import time
import requests
import speech_recognition as sr
import mini.mini_sdk as MiniSdk
from mini.dns.dns_browser import WiFiDevice

# -----------------------------
# LLM / Translation Config
# -----------------------------
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "mistral"
DEFAULT_LANGUAGE = "Spanish"

# -----------------------------
# Connection Helpers (your code)
# -----------------------------
async def test_get_device_by_name():
    result: WiFiDevice = await MiniSdk.get_device_by_name("00213", 10)
    print(f"test_get_device_by_name result:{result}")
    return result

async def test_connect(dev: WiFiDevice) -> bool:
    return await MiniSdk.connect(dev)

async def test_start_run_program():
    await MiniSdk.enter_program()

async def shutdown():
    await MiniSdk.quit_program()
    await MiniSdk.release()
    print("🔌 Disconnected from robot.")

# -----------------------------
# TTS
# -----------------------------
async def say(text: str):
    try:
        await MiniSdk.play_tts(text)
    except AttributeError:
        await MiniSdk.tts_play(text)
    except Exception as e:
        print(f"⚠️ TTS error: {e}")

# -----------------------------
# Translation
# -----------------------------
def translate_text(text: str, target_language: str):
    try:
        prompt = (
            f"Translate this sentence into {target_language}. "
            f"Return ONLY the translated text with no explanations:\n\n{text}"
        )
        payload = {"model": MODEL_NAME, "prompt": prompt, "stream": False}

        response = requests.post(OLLAMA_URL, json=payload)
        if response.status_code == 200:
            result = response.json()
            return result.get("response", "").strip()
        else:
            print("Error:", response.text)
            return None
    except Exception as e:
        print(f"⚠️ Translation failed: {e}")
        return None

# -----------------------------
# PC Microphone Speech Input
# -----------------------------
def listen_pc_mic(timeout=6):
    r = sr.Recognizer()
    with sr.Microphone() as source:
        print("🎤 Listening... Speak now.")
        r.adjust_for_ambient_noise(source)
        try:
            audio = r.listen(source, timeout=timeout)
            text = r.recognize_google(audio)
            print(f"🗣️ Recognized: {text}")
            return text
        except Exception as e:
            print(f"⚠️ Could not recognize speech: {e}")
            return None

# -----------------------------
# Main Voice Translator Loop
# -----------------------------
async def main():
    # 1️⃣ Connect to robot
    device: WiFiDevice = await test_get_device_by_name()
    if not device:
        print("❌ No device found.")
        return

    connected = await test_connect(device)
    if not connected:
        print("❌ Could not connect to robot.")
        return

    await test_start_run_program()
    print("✅ Connected to Alpha Mini")

    try:
        # 2️⃣ Ask for target language
        await say("Which language do you want to translate to?")
        await asyncio.sleep(1)

        try:
            target_language = listen_pc_mic(timeout=6)
            if not target_language or not target_language.strip():
                raise ValueError("No valid language detected")
        except Exception:
            target_language = DEFAULT_LANGUAGE
            await say(f"I did not catch a valid language. Defaulting to {DEFAULT_LANGUAGE}.")

        print(f"🎯 Target language set to: {target_language}")

        # 3️⃣ Continuous translation loop
        while True:
            await say("Speak the sentence you want to translate. Say 'stop translation' to exit.")
            await asyncio.sleep(1)

            user_input = listen_pc_mic(timeout=8)
            if not user_input:
                await say("I did not catch anything. Please try again.")
                continue

            # 4️⃣ Check for stop command
            if user_input.lower() in ["stop translation", "stop translating"]:
                await say("Stopping translation. Goodbye.")
                break

            # 5️⃣ Translate and speak
            translated = translate_text(user_input, target_language)
            if translated:
                print(f"🌐 Original: {user_input}")
                print(f"🌐 Translated: {translated}")
                await say(translated)
            else:
                await say("Sorry, I could not translate that.")

    finally:
        await shutdown()

# -----------------------------
# Entry Point
# -----------------------------
if __name__ == "__main__":
    MiniSdk.set_log_level(logging.INFO)
    MiniSdk.set_robot_type(MiniSdk.RobotType.EDU)
    asyncio.run(main())
