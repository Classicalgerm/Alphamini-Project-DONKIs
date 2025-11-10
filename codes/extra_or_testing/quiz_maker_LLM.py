import requests
import json

# --- CONFIG ---
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "mistral"

def generate_quiz(topic: str, grade: str = "Primary 5", num_questions: int = 5):
    """
    Generate quiz questions using Mistral via Ollama.
    """
    prompt = f"""
    You are an expert Singapore educator who designs quizzes following the latest MOE syllabus.
    Create {num_questions} multiple-choice questions for {grade} students on the topic "{topic}".
    Each question should have:
    - One correct answer
    - Three plausible incorrect options
    - Indicate the correct answer clearly (A, B, C, or D)
    - Include a difficulty level: Easy, Medium, or Hard
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

    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False
    }

    response = requests.post(OLLAMA_URL, json=payload)
    if response.status_code != 200:
        print("❌ Error from Ollama:", response.text)
        return None

    result = response.json().get("response", "")
    try:
        # Try to parse the JSON directly
        quiz_data = json.loads(result)
        return quiz_data
    except json.JSONDecodeError:
        # Sometimes model adds extra text; try to extract JSON
        try:
            start = result.index("[")
            end = result.rindex("]") + 1
            quiz_data = json.loads(result[start:end])
            return quiz_data
        except Exception as e:
            print("⚠️ Could not parse quiz JSON:", e)
            print("Raw output:\n", result)
            return None


# --- TEST ---
if __name__ == "__main__":
    topic = input("Enter quiz topic: ")
    grade = input("Enter grade level (e.g. Primary 5, Secondary 2): ")
    quiz = generate_quiz(topic, grade)

    if quiz:
        print("\n📘 Generated Quiz:\n")
        for i, q in enumerate(quiz, 1):
            print(f"Q{i}: {q['question']}")
            for opt in q["options"]:
                print("  ", opt)
            print(f"✅ Correct Answer: {q['correct_answer']}")
            print(f"🎯 Difficulty: {q['difficulty']}\n")
    else:
        print("❌ No quiz generated.")
