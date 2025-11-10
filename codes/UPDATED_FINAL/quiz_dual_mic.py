import asyncio
import logging
import string
import json
import requests
import mini.mini_sdk as MiniSdk
from mini.apis.api_sound import StartPlayTTS
from mini.apis.api_observe import ObserveSpeechRecognise
from mini.dns.dns_browser import WiFiDevice
from mini.pb2.codemao_speechrecognise_pb2 import SpeechRecogniseResponse

# -----------------------------
# Configuration
# -----------------------------
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "mistral"
ROBOT_SERIAL_SUFFIX = "00213"
STOP_COMMANDS = {"stop quiz", "stop quizzing"}
VALID_GRADES = [f"Primary {i}" for i in range(1, 7)] + [f"Secondary {i}" for i in range(1, 5)]

# -----------------------------
# State
# -----------------------------
class QuizState:
    def __init__(self):
        self.active = False
        self.step = "idle"
        self.topic = ""
        self.grade = ""
        self.difficulty = ""
        self.quiz = []
        self.current_index = 0
        self.awaiting_answer = False

# -----------------------------
# Text-to-Speech
# -----------------------------
async def text_to_speech(text: str, state: dict):
    if not text:
        return
    state["speaking"] = True
    try:
        await MiniSdk.play_tts(text)
    except AttributeError:
        await MiniSdk.tts_play(text)
    except Exception as e:
        print(f"[TTS] Error: {e}")
    await asyncio.sleep(0.3)
    state["speaking"] = False

# -----------------------------
# Quiz Generation
# -----------------------------
def generate_quiz(topic: str, grade: str, difficulty: str, num_questions: int = 5):
    prompt = f"""
    You are a Singapore educator designing quizzes based on the MOE syllabus.
    Create {num_questions} multiple-choice questions for {grade} students on the topic "{topic}".
    Each question must have:
    - Four options labeled A, B, C, D
    - One correct answer clearly marked
    - Difficulty level: {difficulty}
    Return only valid JSON in this format:
    [
      {{
        "question": "...",
        "options": ["A) ...", "B) ...", "C) ...", "D) ..."],
        "correct_answer": "B"
      }}
    ]
    """
    payload = {"model": MODEL_NAME, "prompt": prompt, "stream": False}
    try:
        response = requests.post(OLLAMA_URL, json=payload)
        if response.status_code != 200:
            print("[Quiz] Ollama error:", response.text)
            return None
        result = response.json().get("response", "")
        start, end = result.find("["), result.rfind("]") + 1
        return json.loads(result[start:end])
    except Exception as e:
        print("[Quiz] Generation error:", e)
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
        return await asyncio.wait_for(future, timeout=timeout)
    except asyncio.TimeoutError:
        return ""
    finally:
        observer.stop()

# -----------------------------
# PC Microphone
# -----------------------------
def listen_pc_mic(timeout=6):
    import speech_recognition as sr
    recognizer = sr.Recognizer()
    with sr.Microphone() as source:
        recognizer.adjust_for_ambient_noise(source)
        try:
            audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=10)
            return recognizer.recognize_google(audio).strip()
        except Exception:
            return ""

# -----------------------------
# Hybrid Mic
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
# Ask Next Question
# -----------------------------
async def ask_next_question(state: QuizState, tts_state: dict):
    if state.current_index >= len(state.quiz):
        await text_to_speech("That was the last question. Quiz completed.", tts_state)
        state.active = False
        state.step = "idle"
        return

    q = state.quiz[state.current_index]
    state.awaiting_answer = True
    await text_to_speech(f"Question {state.current_index + 1}: {q['question']}", tts_state)
    await asyncio.sleep(0.5)
    await text_to_speech(" ".join(q["options"]), tts_state)
    await asyncio.sleep(0.3)
    await text_to_speech("Give your answer.", tts_state)

# -----------------------------
# Check Answer (allow repeated attempts)
# -----------------------------
async def check_answer(user_input: str, state: QuizState, tts_state: dict):
    q = state.quiz[state.current_index]
    correct_letter = q["correct_answer"].upper()
    options_texts = [opt.split(") ")[1].strip().lower() for opt in q["options"]]
    user_input_clean = user_input.lower().replace("option ", "").strip()

    # Determine if answer is correct
    if user_input_clean.upper() in ["A", "B", "C", "D"]:
        answer_correct = user_input_clean.upper() == correct_letter
    elif user_input_clean in options_texts:
        correct_index = ord(correct_letter) - ord("A")
        answer_correct = user_input_clean == options_texts[correct_index]
    else:
        answer_correct = False

    if answer_correct:
        await text_to_speech("Correct.", tts_state)
        state.current_index += 1
        state.awaiting_answer = False
        await asyncio.sleep(0.5)
        await ask_next_question(state, tts_state)
    else:
        correct_index = ord(correct_letter) - ord("A")
        await text_to_speech(f"Incorrect. The correct answer is {correct_letter}, {options_texts[correct_index].title()}. You can try again or repeat your answer.", tts_state)
        # still awaiting_answer=True to allow repeated attempts

# -----------------------------
# Handle Speech
# -----------------------------
async def handle_speech(msg_text: str, state: QuizState, tts_state: dict):
    text = msg_text.strip().lower()
    if not text:
        return

    print(f"[Heard] {text}")

    if any(cmd in text for cmd in STOP_COMMANDS):
        await text_to_speech("Stopping the quiz. Goodbye.", tts_state)
        state.active = False
        state.step = "idle"
        return

    if not state.active:
        if "start quiz" in text:
            state.active = True
            state.step = "ask_topic"
            await text_to_speech("What topic should I create the quiz for?", tts_state)
        return

    if state.step == "ask_topic":
        state.topic = text.title()
        state.step = "ask_grade"
        await text_to_speech("What is the grade level? For example, Primary 5.", tts_state)
        return

    if state.step == "ask_grade":
        grade_input = text.title()
        if grade_input in VALID_GRADES:
            state.grade = grade_input
        else:
            state.grade = "Primary 5"
            await text_to_speech(f"Invalid grade. Defaulting to {state.grade}.", tts_state)
        state.step = "ask_difficulty"
        await text_to_speech("What difficulty? Easy, Medium, or Hard?", tts_state)
        return

    if state.step == "ask_difficulty":
        state.difficulty = text.capitalize() if text in ["easy", "medium", "hard"] else "Medium"
        await text_to_speech(f"Creating a {state.difficulty} quiz on {state.topic} for {state.grade} students. Please wait.", tts_state)
        quiz = generate_quiz(state.topic, state.grade, state.difficulty)
        if not quiz:
            await text_to_speech("I could not generate a quiz. Please try again later.", tts_state)
            state.step = "idle"
            state.active = False
            return
        state.quiz = quiz
        state.step = "asking_questions"
        await ask_next_question(state, tts_state)
        return

    if state.step == "asking_questions" and state.awaiting_answer:
        await check_answer(text, state, tts_state)

# -----------------------------
# Listening Loop
# -----------------------------
async def listen_loop():
    state = QuizState()
    tts_state = {"speaking": False}
    while True:
        spoken_text = await hybrid_listen()
        await handle_speech(spoken_text, state, tts_state)

# -----------------------------
# Connection
# -----------------------------
async def find_and_connect():
    device: WiFiDevice = await MiniSdk.get_device_by_name(ROBOT_SERIAL_SUFFIX, 10)
    if not device:
        print("[ERROR] No Alpha Mini found.")
        return None
    if not await MiniSdk.connect(device):
        print("[ERROR] Connection failed.")
        return None
    await MiniSdk.enter_program()
    print("[INFO] Connected to Alpha Mini.")
    return device

async def shutdown():
    await MiniSdk.quit_program()
    await MiniSdk.release()
    print("[INFO] Disconnected from Alpha Mini.")

# -----------------------------
# Main
# -----------------------------
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
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[MAIN] Interrupted. Exiting.")
