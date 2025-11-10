import asyncio
import logging
import os
import time
import re
import json
import requests
import speech_recognition as sr

import mini.mini_sdk as MiniSdk
from mini.dns.dns_browser import WiFiDevice
from mini.apis.api_observe import ObserveSpeechRecognise
from mini.apis.api_sound import StartPlayTTS
from mini.apis.api_action import PlayAction, PlayActionResponse
from mini.apis.api_sence import TakePicture, TakePictureRequest
from mini.pb2.codemao_speechrecognise_pb2 import SpeechRecogniseResponse
from mini.apis.base_api import MiniApiResultType

# -----------------------------
# Configuration
# -----------------------------
MiniSdk.set_log_level(logging.INFO)
MiniSdk.set_robot_type(MiniSdk.RobotType.EDU)

ROBOT_SERIAL_SUFFIX = "00213"
PROGRAM_READY_WAIT = 4

# Translation (Ollama) config
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "mistral"
DEFAULT_LANGUAGE = "Spanish"

# Clock (ESP8266)
ESP_IP = "http://172.22.189.238"
REQUEST_TIMEOUT = 5

# Commands
EXIT_COMMANDS = {"stop", "goodbye", "quit", "exit"}
RETURN_COMMANDS = {"back", "return"}
ATTENDANCE_TRIGGER = "take attendance"
WARMUP_TRIGGER = "warm up"
QUIZ_TRIGGER = "quiz"
TRANSLATE_TRIGGER = "translate"
CLOCK_TRIGGER = "clock"

VALID_GRADES = [f"Primary {i}" for i in range(1, 7)] + [f"Secondary {i}" for i in range(1, 5)]

# -----------------------------
# Utilities
# -----------------------------
def normalize_text(text: str) -> str:
    return ''.join(ch for ch in (text or "").lower() if ch not in ".,!?;:").strip()

async def robot_speak(text: str, state: dict):
    """Make Alpha Mini speak via StartPlayTTS. Uses state['speaking'] to avoid overlaps."""
    if not text:
        return
    if state.get("speaking"):
        return
    state["speaking"] = True
    print(f"[Robot]: {text}")
    try:
        await StartPlayTTS(text=text).execute()
    except Exception:
        # fallback to SDK helper if available
        try:
            await MiniSdk.play_tts(text)
        except Exception as e:
            print("[TTS] Error:", e)
    # short pause so hybrid listener doesn't capture robot TTS
    await asyncio.sleep(0.35)
    state["speaking"] = False

def pc_speak(text: str):
    """Console fallback for laptop TTS."""
    print(f"[Laptop]: {text}")

# -----------------------------
# Hybrid listener (Alpha Mini + PC mic)
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

def listen_pc_mic(timeout=6):
    r = sr.Recognizer()
    with sr.Microphone() as source:
        r.adjust_for_ambient_noise(source, duration=0.8)
        try:
            audio = r.listen(source, timeout=timeout, phrase_time_limit=10)
            return r.recognize_google(audio).strip()
        except Exception:
            return ""

async def hybrid_listen():
    """Return the first non-empty result from Alpha Mini or PC mic (normalized)."""
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

    return normalize_text(result)

# -----------------------------
# Attendance Module
# -----------------------------
async def take_photo_log(student_id: int, state: dict):
    """Capture photo with front camera and log filename + timestamp locally."""
    try:
        req = TakePictureRequest(type=0)  # front camera
        block = TakePicture(req)
        result_type, response = await block.execute()
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"student_{student_id}_time_{timestamp}.jpg"
        log_path = os.path.join(os.getcwd(), "photo_log.txt")

        if result_type == MiniApiResultType.Success and getattr(response, "isSuccess", False):
            with open(log_path, "a") as f:
                f.write(f"{filename} captured at {timestamp}\n")
            print(f"[Attendance] Photo saved: {filename}")
            await robot_speak(f"Picture taken for student {student_id}.", state)
            return True
        else:
            print("[Attendance] Photo capture failed:", response)
            await robot_speak("Photo capture failed.", state)
            return False
    except Exception as e:
        print("[Attendance] Error taking photo:", e)
        await robot_speak("Error while taking photo.", state)
        return False

async def attendance_module(state: dict):
    """Run the attendance flow (takes photos and logs). User can say 'back' to return anytime."""
    await robot_speak("Attendance module activated. Say 'back' to return to main menu anytime.", state)
    # adjust number_of_students to your needs
    number_of_students = 3
    for sid in range(1, number_of_students + 1):
        # before taking next picture, confirm or allow exit
        await robot_speak(f"Ready to capture student {sid}.", state)
        # small pause so TTS finishes
        await asyncio.sleep(0.2)
        # allow confirmation or immediate capture; for simplicity we'll capture immediately
        success = await take_photo_log(sid, state)
        await asyncio.sleep(0.3)
        # check for return/exit command non-blocking for a short window
        try:
            resp = await asyncio.wait_for(hybrid_listen(), timeout=2.5)
            if resp and any(c in resp for c in RETURN_COMMANDS | EXIT_COMMANDS):
                if any(c in resp for c in EXIT_COMMANDS):
                    await robot_speak("Exiting assistant.", state)
                    # signal global exit by raising a special exception or return special token (handled by caller)
                    return "EXIT"
                await robot_speak("Returning to main menu.", state)
                return "BACK"
        except asyncio.TimeoutError:
            # no vocal command in the small window -> continue
            pass
    await robot_speak("Attendance complete. Returning to main menu.", state)
    return "BACK"

# -----------------------------
# PE Warmup Module
# -----------------------------
async def do_repetition(action_code: str, reps: int, instruction: str, state: dict):
    await robot_speak(f"Let's do {reps} {instruction}.", state)
    for i in range(1, reps + 1):
        print(f"[PE] {instruction} {i}/{reps}")
        try:
            block = PlayAction(action_name=action_code)
            await block.execute()
        except Exception:
            pass
        # allow quick interruption check
        await asyncio.sleep(1)

async def pe_warmup(state: dict):
    await robot_speak("Starting warmup. Say 'back' to return to main menu anytime.", state)
    exercises = [("012", 5, "push-ups"), ("031", 2, "squats"),
                 ("017", 1, "stretch your arms"), ("028", 2, "lunges")]
    for code, reps, desc in exercises:
        # check for immediate return before each exercise
        await asyncio.sleep(0.2)
        # small non-blocking listen window to detect 'back' or 'exit'
        try:
            resp = await asyncio.wait_for(hybrid_listen(), timeout=0.8)
            if resp and any(c in resp for c in RETURN_COMMANDS | EXIT_COMMANDS):
                if any(c in resp for c in EXIT_COMMANDS):
                    await robot_speak("Exiting assistant.", state)
                    return "EXIT"
                await robot_speak("Returning to main menu.", state)
                return "BACK"
        except asyncio.TimeoutError:
            pass
        await do_repetition(code, reps, desc, state)
    await robot_speak("Warmup complete. Returning to main menu.", state)
    return "BACK"

# -----------------------------
# Clock Module (ESP8266)
# -----------------------------
def send_request(path: str, params=None):
    try:
        url = f"{ESP_IP}/{path}"
        r = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        return r.text
    except Exception as e:
        print("[Clock] Request failed:", e)
        return None

def process_clock_command(command: str):
    if "set alarm" in command or "alarm" in command:
        nums = re.findall(r"\d+", command)
        if len(nums) >= 2:
            return send_request("set_alarm", {"hour": int(nums[0]), "minute": int(nums[1])}) or "Failed"
        if len(nums) == 1:
            return send_request("set_alarm", {"hour": int(nums[0]), "minute": 0}) or "Failed"
        return "Please specify time for the alarm."
    if "timer" in command:
        m = re.search(r"\d+", command)
        mins = int(m.group(0)) if m else 1
        return send_request("set_timer", {"minutes": mins}) or "Failed"
    if "stop" in command or "turn off" in command:
        return send_request("stop_alarm") or "Failed"
    if "time" in command or "what time" in command:
        return send_request("get_time") or "Unknown"
    return "Command not recognized."

async def clock_module(state: dict):
    await robot_speak("Clock module activated. Say 'back' to return to main menu.", state)
    while True:
        cmd = await hybrid_listen()
        if not cmd:
            continue
        if any(c in cmd for c in EXIT_COMMANDS):
            await robot_speak("Exiting assistant.", state)
            return "EXIT"
        if any(c in cmd for c in RETURN_COMMANDS):
            await robot_speak("Returning to main menu.", state)
            return "BACK"
        result = process_clock_command(cmd)
        await robot_speak(result, state)

# -----------------------------
# Translation Module
# -----------------------------
def translate_text(text: str, target_language: str):
    try:
        prompt = f"Translate this sentence into {target_language}. Return ONLY the translated text:\n\n{text}"
        payload = {"model": MODEL_NAME, "prompt": prompt, "stream": False}
        r = requests.post(OLLAMA_URL, json=payload, timeout=30)
        if r.status_code == 200:
            return r.json().get("response", "").strip()
    except Exception as e:
        print("[Translate] Error:", e)
    return None

async def translation_module(state: dict):
    await robot_speak("Translation module activated. Which language?", state)
    lang = await hybrid_listen()
    if not lang:
        lang = DEFAULT_LANGUAGE
        await robot_speak(f"No language detected. Defaulting to {lang}.", state)
    else:
        await robot_speak(f"Language set to {lang}. Say a sentence or 'back' to return.", state)

    while True:
        text = await hybrid_listen()
        if not text:
            continue
        if any(c in text for c in EXIT_COMMANDS):
            await robot_speak("Exiting assistant.", state)
            return "EXIT"
        if any(c in text for c in RETURN_COMMANDS):
            await robot_speak("Returning to main menu.", state)
            return "BACK"
        translated = translate_text(text, lang)
        if translated:
            await robot_speak(translated, state)
        else:
            await robot_speak("Could not translate. Try again or say 'back' to return.", state)

# -----------------------------
# Quiz Module
# -----------------------------
def generate_quiz(topic: str, grade: str, difficulty: str, num_questions: int = 5):
    prompt = (
        f"You are a Singapore educator designing quizzes for {grade} students.\n"
        f"Create {num_questions} multiple-choice questions on \"{topic}\".\n"
        "Return JSON array of objects with keys: question, options (list of 4 strings 'A) ...'), correct_answer (one of 'A','B','C','D')."
    )
    payload = {"model": MODEL_NAME, "prompt": prompt, "stream": False}
    try:
        r = requests.post(OLLAMA_URL, json=payload, timeout=30)
        if r.status_code != 200:
            print("[Quiz] Ollama error:", r.text)
            return None
        result = r.json().get("response", "")
        start, end = result.find("["), result.rfind("]") + 1
        if start == -1 or end == 0:
            return None
        return json.loads(result[start:end])
    except Exception as e:
        print("[Quiz] Error:", e)
        return None

async def ask_question(q: dict, state: dict):
    await robot_speak(f"Question: {q['question']}", state)
    await asyncio.sleep(0.3)
    await robot_speak(" ".join(q["options"]), state)
    await asyncio.sleep(0.2)
    await robot_speak("Give your answer.", state)

async def quiz_module(state: dict):
    await robot_speak("Quiz module activated. What topic?", state)
    topic = await hybrid_listen()
    if not topic:
        topic = "Math"
    await robot_speak("Grade level?", state)
    grade = await hybrid_listen()
    if not grade or grade.title() not in VALID_GRADES:
        grade = "Primary 5"
    await robot_speak("Difficulty: Easy, Medium, or Hard?", state)
    difficulty = await hybrid_listen()
    difficulty = difficulty.capitalize() if difficulty.lower() in ["easy", "medium", "hard"] else "Medium"

    await robot_speak("Generating quiz. Please wait. Say 'back' to cancel.", state)
    quiz = generate_quiz(topic, grade.title(), difficulty)
    if not quiz:
        await robot_speak("Could not generate quiz. Returning to main menu.", state)
        return "BACK"

    for q in quiz:
        while True:
            await ask_question(q, state)
            answer = await hybrid_listen()
            if not answer:
                continue
            if any(c in answer for c in EXIT_COMMANDS):
                await robot_speak("Exiting assistant.", state)
                return "EXIT"
            if any(c in answer for c in RETURN_COMMANDS):
                await robot_speak("Returning to main menu.", state)
                return "BACK"
            correct = q.get("correct_answer", "A").upper()
            options = [opt.split(") ", 1)[1].strip().lower() for opt in q.get("options", [])]
            ans = answer.lower().replace("option ", "").strip()
            if ans.upper() in ["A", "B", "C", "D"]:
                if ans.upper() == correct:
                    await robot_speak("Correct.", state)
                    break
            elif ans in options:
                if ans == options[ord(correct) - 65]:
                    await robot_speak("Correct.", state)
                    break
            await robot_speak("Incorrect. Try again or say 'back' to return.", state)

    await robot_speak("Quiz complete. Returning to main menu.", state)
    return "BACK"

# -----------------------------
# Main assistant
# -----------------------------
async def assistant_main():
    # connect to Alpha Mini
    device: WiFiDevice = await MiniSdk.get_device_by_name(ROBOT_SERIAL_SUFFIX, 10)
    if not device:
        print("[Main] No Alpha Mini found.")
        return
    if not await MiniSdk.connect(device):
        print("[Main] Could not connect to Alpha Mini.")
        return
    try:
        await MiniSdk.enter_program()
    except Exception as e:
        print("[Main] enter_program failed:", e)
        # continue; some SDKs may still allow TTS/actions

    await asyncio.sleep(PROGRAM_READY_WAIT)
    tts_state = {"speaking": False}
    print("Assistant ready. Say: 'take attendance', 'warm up', 'quiz', 'translate', 'clock', or 'exit'.")

    try:
        while True:
            # main menu prompt (spoken once between commands)
            await robot_speak("Awaiting command: attendance, warm up, quiz, translate, clock, or exit.", tts_state)
            cmd = await hybrid_listen()
            if not cmd:
                continue
            print(f"[Main Heard]: {cmd}")

            if any(c in cmd for c in EXIT_COMMANDS):
                await robot_speak("Exiting assistant now.", tts_state)
                break

            # Attendance
            if ATTENDANCE_TRIGGER in cmd:
                res = await attendance_module(tts_state)
                if res == "EXIT":
                    break
                # return to main menu and continue

            # Warm up (PE)
            elif WARMUP_TRIGGER in cmd:
                res = await pe_warmup(tts_state)
                if res == "EXIT":
                    break

            # Quiz
            elif QUIZ_TRIGGER in cmd:
                res = await quiz_module(tts_state)
                if res == "EXIT":
                    break

            # Translate
            elif TRANSLATE_TRIGGER in cmd:
                res = await translation_module(tts_state)
                if res == "EXIT":
                    break

            # Clock
            elif CLOCK_TRIGGER in cmd:
                res = await clock_module(tts_state)
                if res == "EXIT":
                    break

            else:
                await robot_speak("Command not recognized. Please say attendance, warm up, quiz, translate, clock, or exit.", tts_state)

    finally:
        # graceful cleanup
        try:
            await MiniSdk.quit_program()
            await MiniSdk.release()
        except Exception:
            pass
        print("Assistant shutdown complete.")

# -----------------------------
# Entry point
# -----------------------------
if __name__ == "__main__":
    try:
        asyncio.run(assistant_main())
    except KeyboardInterrupt:
        print("\nInterrupted. Exiting.")
