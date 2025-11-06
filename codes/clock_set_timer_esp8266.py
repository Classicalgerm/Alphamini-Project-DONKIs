import requests

# Replace with your ESP8266 IP printed in Serial Monitor
ESP_IP = "http://192.168.1.xx"

def set_alarm(hour, minute):
    url = f"{ESP_IP}/set_alarm?hour={hour}&minute={minute}"
    response = requests.get(url)
    print("ESP:", response.text)

def ring_now():
    response = requests.get(f"{ESP_IP}/ring_now")
    print("ESP:", response.text)

def stop_alarm():
    response = requests.get(f"{ESP_IP}/stop_alarm")
    print("ESP:", response.text)

def get_time():
    response = requests.get(f"{ESP_IP}/get_time")
    print("ESP:", response.text)

# Example use
set_alarm(8, 0)
get_time()
ring_now()
