import speech_recognition as sr
import pyttsx3
import re
import time
import requests

# === ESP8266 IP ===
ESP_IP = "http://10.51.232.238"  # ← replace with your ESP IP (no trailing slash)

# === Initialize TTS ===
engine = pyttsx3.init()
engine.setProperty('rate', 170)

def speak(text):
    print(f"🗣️ {text}")
    engine.say(text)
    engine.runAndWait()

# === Speech Recognition ===
def recognize_speech(prompt="Speak your command."):
    r = sr.Recognizer()
    with sr.Microphone() as source:
        speak(prompt)
        print("🎤 Listening...")
        audio = r.listen(source, phrase_time_limit=5)
    try:
        command = r.recognize_google(audio)
        print(f"🧠 You said: {command}")
        return command.lower()
    except sr.UnknownValueError:
        speak("Sorry, I didn’t catch that.")
        return ""
    except sr.RequestError:
        speak("Speech recognition service unavailable.")
        return ""

# === ESP Communication ===
def send_request(endpoint, params=None):
    try:
        url = f"{ESP_IP}/{endpoint}"
        response = requests.get(url, params=params, timeout=5)
        print(f"ESP: {response.text}")
        return response.text
    except requests.exceptions.RequestException:
        speak("Failed to reach the ESP clock. Check Wi-Fi connection.")
        return None

def set_alarm(hour, minute):
    send_request("set_alarm", {"hour": hour, "minute": minute})
    speak(f"Alarm set to {hour:02d}:{minute:02d}.")

def set_timer(minutes):
    send_request("set_timer", {"minutes": minutes})
    speak(f"Timer started for {minutes} minutes.")

def stop_alarm():
    send_request("stop_alarm")
    speak("Alarm and timer cleared.")

def ring_now():
    send_request("ring_now")
    speak("Alarm triggered manually.")

def get_time():
    result = send_request("get_time")
    if result:
        speak(f"The current time is {result}.")

# Additional digital clock features
def get_alarm_status():
    result = send_request("get_alarm")  # You need to implement this endpoint in ESP
    if result:
        speak(f"The current alarm is set to {result}.")

def pause_timer():
    send_request("pause_timer")  # Requires ESP endpoint
    speak("Timer paused.")

def resume_timer():
    send_request("resume_timer")  # Requires ESP endpoint
    speak("Timer resumed.")

def reset_timer():
    send_request("reset_timer")  # Requires ESP endpoint
    speak("Timer reset.")

def get_timer_remaining():
    result = send_request("get_timer_remaining")  # Requires ESP endpoint
    if result:
        speak(f"Remaining time on timer is {result}.")

# === Command Processing ===
def process_command(command):
    # --- Set alarm ---
    if "set alarm" in command:
        match = re.findall(r"(\d+)", command)
        if len(match) >= 2:
            hour, minute = int(match[0]), int(match[1])
        elif len(match) == 1:
            hour, minute = int(match[0]), 0
        else:
            speak("Please say the time, for example, set alarm for eight thirty.")
            return
        set_alarm(hour, minute)

    # --- Timer / Countdown ---
    elif "timer" in command or "countdown" in command:
        match = re.search(r"(\d+)", command)
        minutes = int(match.group(1)) if match else 1
        set_timer(minutes)

    # --- Stop / Clear ---
    elif "stop alarm" in command or "turn off alarm" in command or "stop timer" in command:
        stop_alarm()

    # --- Pause / Resume / Reset timer ---
    elif "pause timer" in command:
        pause_timer()
    elif "resume timer" in command:
        resume_timer()
    elif "reset timer" in command:
        reset_timer()
    elif "remaining time" in command or "timer remaining" in command:
        get_timer_remaining()

    # --- Ring alarm immediately ---
    elif "ring now" in command or "start alarm" in command:
        ring_now()

    # --- Ask for current time ---
    elif "what time" in command or "current time" in command:
        get_time()

    # --- Ask for current alarm ---
    elif "current alarm" in command or "show alarm" in command:
        get_alarm_status()

    # --- Exit voice control ---
    elif "exit" in command or "goodbye" in command or "shut down" in command:
        speak("Goodbye! Shutting down voice control.")
        print("👋 Session ended.")
        exit()

    else:
        speak("Sorry, I didn’t understand that command.")

# === Main Loop ===
def main():
    speak("Voice clock control activated.")
    time.sleep(1)
    while True:
        cmd = recognize_speech("Say a command like set alarm, start timer, stop timer, or ask time.")
        if cmd:
            process_command(cmd)

if __name__ == "__main__":
    main()
