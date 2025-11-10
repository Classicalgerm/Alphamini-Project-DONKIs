import asyncio
import logging
import string
import requests
import speech_recognition as sr
import mini.mini_sdk as MiniSdk
from mini.dns.dns_browser import WiFiDevice
from mini.apis.api_observe import ObserveSpeechRecognise
from mini.pb2.codemao_speechrecognise_pb2 import SpeechRecogniseResponse

# -----------------------------
# Robot / Translation Config
# -----------------------------
MiniSdk.set_log_level(logging.INFO)
MiniSdk.set_robot_type(MiniSdk.RobotType.EDU)

ROBOT_SERIAL_SUFFIX = "00213"  # last digits of your robot serial
PROGRAM_READY_WAIT = 4

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "mistral"
DEFAULT_LANGUAGE = "Spanish"

# -----------------------------
# TTS with speaking flag
# -----------------------------
async def text_to_speech(text: str, state: dict):
    if not text or not isinstance(text, str):
        return
    text = text.strip()
    if not text:
        return
    state["speaking"] = True
    try:
        await MiniSdk.play_tts(text)
    except AttributeError:
        await MiniSdk.tts_play(text)
    except Exception as e:
        print(f"[TTS] Error: {e}")
    await asyncio.sleep(0.5)
    state["speaking"] = False

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
            print("[TRANSLATION] Error:", response.text)
            return None
    except Exception as e:
        print(f"[TRANSLATION] Failed: {e}")
        return None

# -----------------------------
# Alpha Mini Microphone
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
        result = await asyncio.wait_for(future, timeout=timeout)
        return result
    except asyncio.TimeoutError:
        return ""
    finally:
        observer.stop()

# -----------------------------
# PC Microphone
# -----------------------------
def listen_pc_mic(timeout=6):
    recognizer = sr.Recognizer()
    with sr.Microphone() as source:
        recognizer.adjust_for_ambient_noise(source)
        try:
            audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=10)
            text = recognizer.recognize_google(audio)
            return text.strip()
        except Exception:
            return ""

# -----------------------------
# Hybrid Microphone
# -----------------------------
async def hybrid_listen():
    task_alpha = asyncio.create_task(listen_alpha_mic())
    loop = asyncio.get_event_loop()
    task_pc = loop.run_in_executor(None, listen_pc_mic)

    done, pending = await asyncio.wait(
        [task_alpha, task_pc],
        return_when=asyncio.FIRST_COMPLETED
    )

    # Get first meaningful result
    result = ""
    for d in done:
        try:
            text = d.result()
            if text:
                result = text
                break
        except asyncio.CancelledError:
            pass

    # Cancel the other task gracefully
    for p in pending:
        p.cancel()
        try:
            await p
        except asyncio.CancelledError:
            pass

    # Normalize
    result = ''.join(ch for ch in result if ch not in string.punctuation).strip()
    return result

# -----------------------------
# Main Voice Translator Loop
# -----------------------------
async def translator_main():
    state = {"speaking": False}

    # Discover and connect
    device: WiFiDevice = await MiniSdk.get_device_by_name(ROBOT_SERIAL_SUFFIX, 10)
    if not device:
        print("[ERROR] Alpha Mini not found.")
        return
    if not await MiniSdk.connect(device):
        print("[ERROR] Could not connect to Alpha Mini.")
        return

    await MiniSdk.enter_program()
    await asyncio.sleep(PROGRAM_READY_WAIT)
    print("[INFO] Connected. Ready for translation.")

    try:
        # Ask for target language
        await text_to_speech("Which language do you want to translate to?", state)
        await asyncio.sleep(1)
        target_language = await hybrid_listen()
        if not target_language:
            target_language = DEFAULT_LANGUAGE
            await text_to_speech(f"I did not catch a valid language. Defaulting to {DEFAULT_LANGUAGE}.", state)
        else:
            await text_to_speech(f"Language set to {target_language}.", state)

        print(f"[LANGUAGE] Target: {target_language}")

        # Translation loop
        while True:
            await text_to_speech("Speak the sentence you want to translate. Say 'stop translation' to exit.", state)
            await asyncio.sleep(1)

            spoken_text = await hybrid_listen()
            if not spoken_text:
                await text_to_speech("I did not catch anything. Please try again.", state)
                continue

            if spoken_text.lower() in ["stop translation", "stop translating"]:
                await text_to_speech("Stopping translation. Goodbye.", state)
                break

            translated_text = translate_text(spoken_text, target_language)
            if translated_text:
                print(f"[SOURCE] {spoken_text}")
                print(f"[TRANSLATED] {translated_text}")
                await text_to_speech(translated_text, state)
            else:
                await text_to_speech("Sorry, I could not translate that.", state)

    finally:
        print("[SHUTDOWN] Disconnecting...")
        await MiniSdk.quit_program()
        await MiniSdk.release()
        print("[SHUTDOWN] Done.")

# -----------------------------
# Entry Point
# -----------------------------
if __name__ == "__main__":
    try:
        asyncio.run(translator_main())
    except KeyboardInterrupt:
        print("\n[MAIN] Interrupted. Exiting.")
