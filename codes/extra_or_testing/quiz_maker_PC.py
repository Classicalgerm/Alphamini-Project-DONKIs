import asyncio
import logging
import requests
import json
import speech_recognition as sr
import mini.mini_sdk as MiniSdk
from mini.dns.dns_browser import WiFiDevice

# -----------------------------
# Ollama Quiz Config
# -----------------------------
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "mistral"

# -----------------------------
# Connection Helpers
# -----------------------------
async def find_and_connect(serial_suffix="00213"):
    device: WiFiDevice = await MiniSdk.get_device_by_name(serial_suffix, 10)
    if not device:
        print("❌ No device found.")
        return None

    connected = await MiniSdk.connect(device)
    if not connected:
        print("❌ Could not connect to robot.")
        return None

    await MiniSdk.enter_program()
    print("✅ Connected to Alpha Mini")
    return device

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
# PC Microphone Input
# -----------------------------
def listen_pc_mic(prompt=None, timeout=6):
    r = sr.Recognizer()
    with sr.Microphone() as source:
        if prompt:
            print(prompt)
        r.adjust_for_ambient_noise(source)
        try:
            audio = r.listen(source, timeout=timeout)
            text = r.recognize_google(audio)
            print(f"🗣️ Recognized: {text}")
            return text.strip()
        except Exception as e:
            print(f"⚠️ Could not recognize speech: {e}")
            return None

# -----------------------------
# Quiz Generation
# -----------------------------
def generate_quiz(topic: str, grade: str = "Primary 5", difficulty: str = "Medium", num_questions: int = 5):
    prompt = f"""
    You are an expert Singapore educator who designs quizzes following the latest MOE syllabus.
    Create {num_questions} multiple-choice questions for {grade} students on the topic "{topic}".
    Each question should have:
    - One correct answer
    - Three plausible incorrect options
    - Indicate the correct answer clearly (A, B, C, or D)
    - Difficulty level: {difficulty}
    Output only in valid JSON array format like this:
    [
      {{
        "question": "...",
        "options": ["A) ...", "B) ...", "C) ...", "D) ..."],
        "correct_answer": "B",
        "difficulty": "Medium"
      }}
    ]
    """
    payload = {"model": MODEL_NAME, "prompt": prompt, "stream": False}

    response = requests.post(OLLAMA_URL, json=payload)
    if response.status_code != 200:
        print("❌ Error from Ollama:", response.text)
        return None

    result = response.json().get("response", "")
    try:
        quiz_data = json.loads(result)
        return quiz_data
    except json.JSONDecodeError:
        try:
            start = result.index("[")
            end = result.rindex("]") + 1
            quiz_data = json.loads(result[start:end])
            return quiz_data
        except Exception as e:
            print("⚠️ Could not parse quiz JSON:", e)
            print("Raw output:\n", result)
            return None

# -----------------------------
# Utility: Voice input with re-prompt until valid
# -----------------------------
async def get_voice_input(prompt_text, valid_options=None):
    while True:
        await say(prompt_text)
        await asyncio.sleep(0.5)
        user_input = listen_pc_mic()
        if user_input and user_input.strip():
            normalized = user_input.strip()
            if valid_options:
                # Normalize answer for options like "Option B" -> "B"
                normalized_upper = normalized.upper()
                if "OPTION" in normalized_upper:
                    normalized_upper = normalized_upper.replace("OPTION", "").strip()
                normalized_upper = normalized_upper[0]  # first letter only
                if normalized_upper in valid_options:
                    return normalized_upper
                else:
                    await say("I did not recognize a valid option. Please try again.")
            else:
                return normalized
        else:
            await say("I did not catch that. Please try again.")

# -----------------------------
# Main Logic
# -----------------------------
async def main():
    MiniSdk.set_log_level(logging.INFO)
    MiniSdk.set_robot_type(MiniSdk.RobotType.EDU)

    # 1️⃣ Connect to robot
    device = await find_and_connect()
    if not device:
        return

    try:
        # 2️⃣ Get topic, grade, difficulty via voice only
        topic = await get_voice_input("Please say the quiz topic")
        grade = await get_voice_input("Please say the grade level, for example Primary 5")
        difficulty = await get_voice_input("Please say the difficulty level: Easy, Medium, or Hard", valid_options=["EASY","MEDIUM","HARD"])

        # 3️⃣ Generate quiz
        quiz = generate_quiz(topic, grade, difficulty.capitalize())
        if not quiz:
            print("❌ No quiz generated.")
            await say("Sorry, I could not generate a quiz.")
            return

        # 4️⃣ Iterate through questions
        for i, q in enumerate(quiz, 1):
            question_text = f"Question {i}: {q['question']}"
            options_text = " ".join(q["options"])
            correct_answer = q['correct_answer'].upper()

            # Print to console (including difficulty)
            print(f"Q{i}: {q['question']}")
            for opt in q["options"]:
                print("  ", opt)
            print(f"✅ Correct Answer: {correct_answer}")
            print(f"🎯 Difficulty: {q['difficulty']}\n")

            # Speak question and options
            await say(question_text)
            await asyncio.sleep(1)
            await say(options_text)
            await asyncio.sleep(1)

            # Ask user to give answer
            user_answer = await get_voice_input("Give your answer", valid_options=["A","B","C","D"])

            if user_answer == correct_answer:
                await say("Correct!")
            else:
                await say(f"Incorrect. The correct answer is {correct_answer}.")

            await asyncio.sleep(1)  # small pause before next question

        await say("Quiz completed.")

    finally:
        await shutdown()

# -----------------------------
# Entry Point
# -----------------------------
if __name__ == "__main__":
    asyncio.run(main())
