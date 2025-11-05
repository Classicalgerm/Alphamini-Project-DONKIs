import asyncio
import logging
import sys
import threading
import numpy as np
from PIL import Image
import tensorflow as tf
import base64

import mini.mini_sdk as MiniSdk
from mini.dns.dns_browser import WiFiDevice
from mini.apis.api_camera import TakePhoto
from mini.apis.api_observe import ObserveInfraredDistance
from mini.apis.api_sound import StartPlayTTS
from mini.pb2.codemao_observeinfrareddistance_pb2 import ObserveInfraredDistanceResponse

# ==== SETTINGS ====
SERIAL_SUFFIX = "00213"        # last 5+ chars of AlphaMini serial
DETECTION_DISTANCE = 300       # mm = 30 cm
MODEL_PATH = "object_model.h5" # from Stage 1
LABELS = ["book", "cup", "phone", "bottle"]  # update with your model classes

# ==== INIT ====
MiniSdk.set_log_level(logging.INFO)
MiniSdk.set_robot_type(MiniSdk.RobotType.EDU)
model = tf.keras.models.load_model(MODEL_PATH)

# ==== Keyboard flag ====
stop_flag = False
def keyboard_listener():
    global stop_flag
    while True:
        key = input().strip().lower()
        if key == 'x':
            print("\n[User] Stop key 'x' pressed.")
            stop_flag = True
            break
threading.Thread(target=keyboard_listener, daemon=True).start()

# ==== Helper Functions ====
async def tts(text):
    await StartPlayTTS(text=text).execute()

async def capture_image(save_path="captured.jpg"):
    rt, photo = await TakePhoto().execute()
    if photo and photo.base64:
        with open(save_path, "wb") as f:
            f.write(base64.b64decode(photo.base64))
        return save_path
    return None

def classify_image(image_path):
    img = Image.open(image_path).resize((224, 224))
    arr = np.expand_dims(np.array(img) / 255.0, axis=0)
    preds = model.predict(arr)
    idx = np.argmax(preds)
    return LABELS[idx], float(preds[0][idx])

# ==== Main Detection Loop ====
async def detection_loop():
    print("[System] Starting continuous detection. Press 'x' + Enter to quit.")
    observer = ObserveInfraredDistance()
    detection_event = asyncio.Event()

    async def process_object(distance):
        await tts(f"Object detected at {int(distance)} millimeters. Checking object.")
        img_path = await capture_image()
        if img_path:
            label, conf = classify_image(img_path)
            await tts(f"I think this is a {label} with confidence {conf:.2f}")
        else:
            await tts("I could not capture the image properly.")
        await asyncio.sleep(2)  # short pause before resuming

    def handler(msg: ObserveInfraredDistanceResponse):
        if msg.distance <= DETECTION_DISTANCE:
            asyncio.create_task(process_object(msg.distance))

    observer.set_handler(handler)
    observer.start()

    try:
        while not stop_flag:
            await asyncio.sleep(0.5)
        observer.stop()
    finally:
        print("[System] Stopping detection loop.")

# ==== Connection Functions ====
async def connect_robot():
    device: WiFiDevice = await MiniSdk.get_device_by_name(SERIAL_SUFFIX, 10)
    if not device:
        print("[Connection] No device found.")
        return False
    connected = await MiniSdk.connect(device)
    if connected:
        print("[Connection] Connected.")
        await MiniSdk.enter_program()
        return True
    print("[Connection] Failed.")
    return False

async def disconnect_robot():
    print("[Connection] Disconnecting...")
    await MiniSdk.quit_program()
    await MiniSdk.release()

# ==== Main Entrypoint ====
async def main():
    if not await connect_robot():
        return
    try:
        await detection_loop()
    except Exception as e:
        print(f"[Error] {e}")
    finally:
        await disconnect_robot()
        print("[System] Program ended.")

if __name__ == "__main__":
    asyncio.run(main())
