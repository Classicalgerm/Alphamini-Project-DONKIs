import asyncio
import logging
import sys
import time
from math import degrees, atan2, sqrt

# --- AlphaMini SDK imports (present on EDU 1.2.0) ---
import mini.mini_sdk as MiniSdk
from mini.dns.dns_browser import WiFiDevice
from mini.apis.base_api import MiniApiResultType
from mini.apis.api_action import MoveRobot, MoveRobotDirection

# Try to import sensing namespace; some EDU builds are stripped
try:
    from mini.apis import api_sence as sence
except Exception:
    sence = None

# ---- SDK setup ----
MiniSdk.set_log_level(logging.INFO)
MiniSdk.set_robot_type(MiniSdk.RobotType.EDU)

# ---- Config (adjust as you like) ----
SERIAL_SUFFIX = "00213"        # <-- put your robot's suffix here
SAFE_TILT_WARN = 10.0          # warn at |tilt| >= deg
SAFE_TILT_TRIP = 18.0          # recover at |tilt| >= deg
SAMPLE_HZ = 20                 # monitor rate
MOVE_COOLDOWN = 0.35           # seconds between step commands
MAX_STEPS = 6                  # safety clamp
DEBOUNCE = 3                   # consecutive samples to confirm warn/trip

estop_event = asyncio.Event()

# ---------- helpers ----------
def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def accel_to_pitch_roll(ax, ay, az):
    """Estimate tilt from accelerometer vector."""
    g = (ax*ax + ay*ay + az*az) ** 0.5 or 1e-9
    axn, ayn, azn = ax/g, ay/g, az/g
    pitch = degrees(atan2(-axn, (ayn*ayn + azn*azn) ** 0.5))
    roll  = degrees(atan2(ayn, azn))
    return pitch, roll

async def move_safe(direction: MoveRobotDirection, steps: int = 1):
    if estop_event.is_set():
        return
    steps = clamp(steps, 1, MAX_STEPS)
    resp = await MoveRobot(direction, steps).execute()
    if getattr(resp, "result", None) != MiniApiResultType.Success:
        print(f"[WARN] Move {direction} failed: {getattr(resp,'result',None)}")
    await asyncio.sleep(MOVE_COOLDOWN)

# ---------- posture provider (auto-detect or simulate) ----------
class PostureProvider:
    """
    Unifies posture access across different SDK variants.
    If no IMU/posture API exists, runs in SIM mode.
    """
    def _init_(self):
        self.provider_name = None
        self.cls = None
        self.sim = False
        self.sim_pitch = 0.0
        self.sim_roll = 0.0

        if sence is None:
            self.sim = True
            return

        candidates = ["GetImuData", "GetSixAxisImu", "GetPosture", "GetPostureData", "GetAttitude"]
        for name in candidates:
            if hasattr(sence, name):
                self.cls = getattr(sence, name)
                self.provider_name = name
                break
        if self.cls is None:
            self.sim = True

    async def get_pitch_roll(self):
        """Return (pitch_deg, roll_deg)."""
        if self.sim or self.cls is None:
            # SIM mode – commands via stdin in the same listener: tp/tm=±5° pitch, rp/rm=±5° roll, r0=reset
            return self.sim_pitch, self.sim_roll

        # Try to execute the SDK call and adapt to available fields.
        try:
            resp = await self.cls().execute()
        except Exception as e:
            print(f"[WARN] {self.provider_name}.execute() error: {e}. Falling back to SIM.")
            self.sim = True
            return self.sim_pitch, self.sim_roll

        if getattr(resp, "result", None) != MiniApiResultType.Success:
            print(f"[WARN] {self.provider_name} result: {getattr(resp,'result',None)}")
            return 0.0, 0.0

        # Prefer direct pitch/roll if present
        if hasattr(resp, "pitch") and hasattr(resp, "roll"):
            return float(resp.pitch), float(resp.roll)

        # Else look for accelerometer fields
        if all(hasattr(resp, a) for a in ("ax", "ay", "az")):
            return accel_to_pitch_roll(float(resp.ax), float(resp.ay), float(resp.az))

        # Unknown payload; fallback
        print(f"[WARN] {self.provider_name} returned unknown fields; using SIM.")
        self.sim = True
        return self.sim_pitch, self.sim_roll

    # SIM controls that the input listener can call:
    def sim_adjust(self, what):
        if what == "tp":
            self.sim_pitch += 5.0
        elif what == "tm":
            self.sim_pitch -= 5.0
        elif what == "rp":
            self.sim_roll += 5.0
        elif what == "rm":
            self.sim_roll -= 5.0
        elif what == "r0":
            self.sim_pitch, self.sim_roll = 0.0, 0.0

# ---------- listeners ----------
async def input_listener(posture: PostureProvider):
    """
    Accepts:
      e   -> emergency stop
      tp  -> +5° pitch, tm -> -5° pitch
      rp  -> +5° roll,  rm -> -5° roll
      r0  -> reset pitch/roll to 0
      ?   -> help
    """
    loop = asyncio.get_event_loop()
    print("[INPUT] Type 'e' + Enter for E-STOP. For SIM: tp/tm/rp/rm/r0. '?' for help.")
    while not estop_event.is_set():
        line = await loop.run_in_executor(None, sys.stdin.readline)
        cmd = line.strip().lower()
        if cmd == "e":
            print("[E-STOP] Emergency stop activated.")
            estop_event.set()
            break
        if posture.sim:
            if cmd in ("tp","tm","rp","rm","r0"):
                posture.sim_adjust(cmd)
                print(f"[SIM] pitch={posture.sim_pitch:.1f}°, roll={posture.sim_roll:.1f}°")
            elif cmd == "?":
                print("Commands: e | tp/tm (+/- pitch) | rp/rm (+/- roll) | r0 (reset)")
        else:
            if cmd == "?":
                print("Commands: e (E-STOP). SIM controls are disabled on real IMU.")

# ---------- recovery ----------
async def recovery_sequence():
    print("[RECOVERY] Excessive tilt detected -> backing off & settling...")
    await move_safe(MoveRobotDirection.BACKWARD, steps=1)
    await move_safe(MoveRobotDirection.FORWARD, steps=1)
    print("[RECOVERY] Done.")

# ---------- monitor ----------
async def posture_monitor(posture: PostureProvider):
    warn_count = 0
    trip_count = 0
    dt = 1.0 / SAMPLE_HZ
    started = time.time()

    mode = "SIMULATION" if posture.sim else f"REAL ({posture.provider_name})"
    print(f"[MONITOR] Posture monitor running @ {SAMPLE_HZ} Hz | Mode: {mode}")

    while not estop_event.is_set():
        pitch, roll = await posture.get_pitch_roll()
        t = time.time() - started

        # Debounced warn/trip logic
        if abs(pitch) >= SAFE_TILT_TRIP or abs(roll) >= SAFE_TILT_TRIP:
            trip_count += 1
            warn_count = 0
        elif abs(pitch) >= SAFE_TILT_WARN or abs(roll) >= SAFE_TILT_WARN:
            warn_count += 1
            trip_count = 0
        else:
            warn_count = 0
            trip_count = 0

        if warn_count >= DEBOUNCE:
            print("[WARN] Approaching unsafe tilt.")
            warn_count = 0

        if trip_count >= DEBOUNCE:
            print("[TRIP] Tilt beyond safe limit! Initiating recovery.")
            await recovery_sequence()
            trip_count = 0

        await asyncio.sleep(dt)

# ---------- connection ----------
async def connect_robot():
    print("[CONNECT] Trying direct connection to AlphaMini...")
    try:
        # this works on AlphaMini EDU 1.2.0+
        ok = await MiniSdk.connect()
        if ok:
            print("[CONNECTED] AlphaMini connected successfully.")
            return True
        else:
            print("[ERROR] Failed to connect to AlphaMini.")
            return False
    except Exception as e:
        print(f"[ERROR] Connection failed: {e}")
        return False

async def disconnect_robot():
    try:
        await MiniSdk.disconnect()
        print("[CONNECT] Disconnected.")
    except Exception:
        pass

# ---------- main ----------
async def main():
    connected = await connect_robot()

    posture = PostureProvider()
    if posture.sim:
        print("[INFO] IMU/posture API not found in this SDK build. Running in SIMULATION mode.")

    try:
        await asyncio.gather(
            posture_monitor(posture),
            input_listener(posture),
        )
    except asyncio.CancelledError:
        pass
    finally:
        if connected:
            await disconnect_robot()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[EXIT] Keyboard interrupt.")