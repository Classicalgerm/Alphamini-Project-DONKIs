import speech_recognition as sr
import pyttsx3
import re
import time

# === Initialize speech engine ===
engine = pyttsx3.init()
engine.setProperty('rate', 170)

def speak(text):
    engine.say(text)
    engine.runAndWait()

def recognize_speech():
    r = sr.Recognizer()
    with sr.Microphone() as source:
        print("🎤 Listening... Speak your command (e.g., 'walk 5 steps')")
        audio = r.listen(source, phrase_time_limit=5)
    try:
        command = r.recognize_google(audio)
        print(f"🧠 You said: {command}")
        return command.lower()
    except sr.UnknownValueError:
        print("❌ Could not understand audio.")
        return ""
    except sr.RequestError:
        print("⚠️ Speech Recognition service unavailable.")
        return ""

def process_command(command):
    if "walk" in command or "step" in command:
        match = re.search(r"(\d+)", command)
        steps = int(match.group(1)) if match else 3
        speak(f"Okay, walking {steps} steps.")
        print(f"🤖 [SIMULATION] AlphaMini walks {steps} steps forward.")
    elif "turn left" in command:
        speak("Turning left.")
        print("🤖 [SIMULATION] AlphaMini turns left.")
    elif "turn right" in command:
        speak("Turning right.")
        print("🤖 [SIMULATION] AlphaMini turns right.")
    elif "stop" in command:
        speak("Stopping now.")
        print("🛑 [SIMULATION] AlphaMini stops.")
    elif "exit" in command or "goodbye" in command:
        speak("Goodbye! Shutting down voice control.")
        print("👋 Session ended.")
        exit()
    else:
        speak("Sorry, I didn’t understand that command.")
        print("❓ Unrecognized command.")

def main():
    speak("Voice command system activated.")
    time.sleep(1)
    while True:
        cmd = recognize_speech()
        if cmd:
            process_command(cmd)

if __name__ == "__main__":
    main()
