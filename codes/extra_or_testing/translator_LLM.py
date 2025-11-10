import requests
import json

# --- CONFIGURATION ---
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "mistral"  # you can also try 'gemma:2b' or 'llama3:8b'

def translate_text(text, target_language="Chinese"):
    """
    Translate text into the target language using a local LLM.
    """
    prompt = f"Translate the following sentence into {target_language}:\n\n{text}"
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False
    }

    try:
        response = requests.post(OLLAMA_URL, json=payload)
        if response.status_code == 200:
            result = response.json()
            return result.get("response", "").strip()
        else:
            print("Error:", response.text)
            return None
    except Exception as e:
        print("LLM Error:", e)
        return None


# --- TEST TRANSLATION ---
if __name__ == "__main__":
    source_text = "Hello, how are you today?"
    translated = translate_text(source_text, target_language="Japanese")
    if translated:
        print(f"\nOriginal: {source_text}\nTranslated: {translated}")
