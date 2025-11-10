import asyncio
import logging
import requests
import json
import string
import mini.mini_sdk as MiniSdk
from mini.apis.api_sound import StartPlayTTS
from mini.apis.api_observe import ObserveSpeechRecognise
from mini.dns.dns_browser import WiFiDevice
from mini.pb2.codemao_speechrecognise_pb2 import SpeechRecogniseResponse

# ---- Configuration ----
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "mistral"
ROBOT_NAME = "alpha"
STOP_COMMANDS = {"stop quiz", "stop quizzing"}

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

# ---- Text-to-Speech ----
async def say(text: str):
    if not text:
        return
    tts = StartPlayTTS(text=text)
    await tts.execute()
    await asyncio.sleep(0.3)

# ---- Quiz Generation ----
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
            print("Error from Ollama:", response.text)
            return None
        result = response.json().get("response", "")
        start, end = result.find("["), result.rfind("]") + 1
        return json.loads(result[start:end])
    except Exception as e:
        print("Quiz generation error:", e)
        return None

# ---- State Management ----
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

# ---- Speech Handler ----
async def handle_speech(msg: SpeechRecogniseResponse, state: QuizState):
    text = (msg.text or "").strip()
    if not text:
        return

    cleaned = ''.join(ch for ch in text.lower() if ch not in string.punctuation)
    print(f"Heard: {cleaned}")

    if any(cmd in cleaned for cmd in STOP_COMMANDS):
        await say("Stopping the quiz. Goodbye.")
        state.active = False
        state.step = "idle"
        return

    if not state.active:
        if "quiz" in cleaned:
            state.active = True
            state.step = "ask_topic"
            await say("What topic should I create the quiz for?")
        return

    if state.step == "ask_topic":
        state.topic = cleaned.title()
        state.step = "ask_grade"
        await say("What is the grade level? For example, Primary 5.")
        return

    if state.step == "ask_grade":
        state.grade = cleaned.title()
        state.step = "ask_difficulty"
        await say("What difficulty? Easy, Medium, or Hard?")
        return

    if state.step == "ask_difficulty":
        state.difficulty = cleaned.capitalize() if cleaned in ["easy", "medium", "hard"] else "Medium"
        await say(f"Creating a {state.difficulty} quiz on {state.topic} for {state.grade} students. Please wait.")
        quiz = generate_quiz(state.topic, state.grade, state.difficulty)
        if not quiz:
            await say("I could not generate a quiz. Please try again later.")
            state.step = "idle"
            state.active = False
            return
        state.quiz = quiz
        state.step = "asking_questions"
        await ask_next_question(state)
        return

    if state.step == "asking_questions" and state.awaiting_answer:
        if cleaned in ["a", "b", "c", "d"]:
            await check_answer(cleaned.upper(), state)
        else:
            await say("Please answer with A, B, C, or D.")
        return

# ---- Quiz Flow ----
async def ask_next_question(state: QuizState):
    if state.current_index >= len(state.quiz):
        await say("That was the last question. Quiz completed.")
        state.active = False
        state.step = "idle"
        return

    q = state.quiz[state.current_index]
    question_text = q["question"]
    options = " ".join(q["options"])
    state.awaiting_answer = True

    await say(f"Question {state.current_index + 1}. {question_text}")
    await asyncio.sleep(1)
    await say(options)
    await asyncio.sleep(0.5)
    await say("Give your answer.")

async def check_answer(user_answer: str, state: QuizState):
    q = state.quiz[state.current_index]
    correct = q["correct_answer"].upper()

    if user_answer == correct:
        await say("Correct.")
    else:
        await say(f"Incorrect. The correct answer is {correct}.")

    state.current_index += 1
    state.awaiting_answer = False
    await asyncio.sleep(1)
    await ask_next_question(state)

# ---- Main Listening Loop ----
async def listen_loop():
    observer = ObserveSpeechRecognise()
    state = QuizState()

    def callback(msg: SpeechRecogniseResponse):
        asyncio.create_task(handle_speech(msg, state))

    observer.set_handler(callback)
    observer.start()
    print("Say 'quiz' to begin a voice quiz session.")
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
