"""
rupali_canal_bridge.py  — v3
=============================

Fixes in this version
---------------------
  FIX 1 — Zero-on-connect
      On startup, bridge calls POST /api/hardware_connect which immediately
      zeros all vehicle counts in the dashboard. Dashboard starts at 0,0,0,0
      the moment hardware takes over.

  FIX 2 — Arduino autonomous blink eliminated
      The old bridge let Arduino run its own internal green/yellow timer AND
      sent SIG: commands, causing both to fight. Now the bridge sends SIG:
      every second, and Arduino obeys it (resets its internal phaseStart).
      Arduino's autonomous loop only fires if PING stops for 5 s (failsafe).

  FIX 3 — VEH: counts pushed to dashboard as absolute values
      Old bridge printed VEH: lines but never sent them to the dashboard.
      Now every VEH:N,S,E,W message is immediately POSTed to /api/sensor_set
      as absolute vehicle counts. Dashboard shows exactly what IR sensors see.

Flow
----
  CONNECT  →  POST /api/hardware_connect  (zeros dashboard, disables sim)
  Every 500ms: Arduino VEH:40,10,0,20
               →  POST /api/sensor_set {road_vehicles:[40,10,0,20], ...}
               →  Dashboard shows 40/10/0/20 instantly
  Every 1s:   GET /api/state  →  SIG:dir:G/Y:countdown  →  Arduino LEDs
  Every 2s:   PING  (Arduino watchdog, keeps autonomous mode suppressed)

Run:
    python rupali_canal_bridge.py
    python rupali_canal_bridge.py --port /dev/ttyUSB0   (Linux/Pi)
    python rupali_canal_bridge.py --port COM7            (Windows)

Flask app (app.py) must be running at http://127.0.0.1:5000
"""

import argparse
import serial
import requests
import time
import threading
import sys

# ── Configuration ──────────────────────────────────────────────────────────────
DEFAULT_PORT  = "COM8"
BAUD_RATE     = 9600
API_BASE      = "http://127.0.0.1:5000"
JUNCTION_ID   = "rupali_canal"
PING_INTERVAL = 2.0    # seconds — Arduino watchdog keepalive
CMD_INTERVAL  = 1.0    # seconds — send SIG: command to Arduino
POST_INTERVAL = 0.2    # FIX: was 0.5s — now 0.2s to match Arduino's faster 200ms send rate

# Arduino DIR_NAMES order: NORTH=0 SOUTH=1 EAST=2 WEST=3
DIRECTION_NAMES = ["NORTH", "SOUTH", "EAST", "WEST"]

# ── Shared state ───────────────────────────────────────────────────────────────
# Latest absolute vehicle counts from Arduino VEH: message
hw_vehicle_counts = [0, 0, 0, 0]   # [N, S, E, W] — ground truth
hw_active_dir     = 0              # direction index currently active on Arduino
hw_phase          = "green"        # "green" / "yellow"
veh_dirty         = False          # True when new VEH: arrived and not yet POSTed
last_state        = {}             # last /api/state response
lock              = threading.Lock()
running           = True


# ── Serial reader thread ───────────────────────────────────────────────────────
def serial_reader(ser):
    global hw_vehicle_counts, hw_active_dir, hw_phase, veh_dirty, running

    print("[Serial] Reader thread started")

    while running:
        try:
            raw = ser.readline().decode("utf-8", errors="ignore").strip()
            if not raw:
                continue

            # ── VEH:40,10,0,20  — absolute vehicle counts (ground truth) ──────
            if raw.startswith("VEH:"):
                try:
                    parts = list(map(int, raw[4:].split(",")))
                    with lock:
                        for i in range(min(len(parts), 4)):
                            hw_vehicle_counts[i] = parts[i]
                        veh_dirty = True   # flag: push to dashboard immediately
                    veh_str = "  ".join(
                        f"{DIRECTION_NAMES[i]}={parts[i]}"
                        for i in range(min(len(parts), 4))
                    )
                    print(f"[HW Sensors]   VEH: {veh_str}")
                except ValueError:
                    pass

            # ── AUTO:GREEN:SOUTH — Arduino switched direction autonomously ─────
            elif raw.startswith("AUTO:GREEN:"):
                dir_name = raw[11:].strip()
                if dir_name in DIRECTION_NAMES:
                    with lock:
                        hw_active_dir = DIRECTION_NAMES.index(dir_name)
                        hw_phase      = "green"
                print(f"[HW Signal]    AUTO GREEN -> {dir_name}")

            # ── AUTO:YELLOW:SOUTH — Arduino autonomous yellow ──────────────────
            elif raw.startswith("AUTO:YELLOW:"):
                dir_name = raw[12:].strip()
                if dir_name in DIRECTION_NAMES:
                    with lock:
                        hw_phase = "yellow"
                print(f"[HW Signal]    AUTO YELLOW -> {dir_name}")

            # ── CAR_IN / CAR_OUT — single sensor event (log only) ─────────────
            elif raw.startswith("CAR_IN:") or raw.startswith("CAR_OUT:"):
                print(f"[HW Sensor]    {raw}")

            elif raw == "PONG":
                pass   # watchdog reply — silent

            elif raw.startswith("READY:"):
                print(f"[Arduino]      {raw}")

            elif raw.startswith("WARN:") or raw.startswith("INFO:"):
                print(f"[Arduino]      {raw}")

            else:
                if raw:
                    print(f"[Arduino]      {raw}")

        except serial.SerialException as e:
            print(f"[Serial] Read error: {e}")
            running = False
            break
        except Exception as e:
            print(f"[Reader] Error: {e}")
            time.sleep(0.1)


# ── Dashboard API calls ────────────────────────────────────────────────────────
def call_hardware_connect():
    """
    Called ONCE at startup. Zeros the dashboard vehicle counts and disables
    software simulation for rupali_canal.
    """
    for attempt in range(5):
        try:
            r = requests.post(
                f"{API_BASE}/api/hardware_connect",
                json={"junction_id": JUNCTION_ID},
                timeout=2,
            )
            if r.status_code == 200:
                print(f"[Connect]      Dashboard zeroed — hardware is now in control")
                return True
            else:
                print(f"[Connect]      /api/hardware_connect {r.status_code}: {r.text[:60]}")
        except requests.RequestException as e:
            print(f"[Connect]      Attempt {attempt+1}/5 failed: {e}")
        time.sleep(1)
    return False


def post_sensor_set(counts, active_dir, phase):
    """
    Push absolute vehicle counts + signal state to dashboard.
    FIX: countdown is intentionally NOT sent — app.py's ML-based compute_green_time
    calculates the correct adaptive green time from the vehicle count.
    Sending our own estimate was overriding the adaptive signal logic.
    """
    try:
        r = requests.post(
            f"{API_BASE}/api/sensor_set",
            json={
                "junction_id":   JUNCTION_ID,
                "road_vehicles": counts,      # [N,S,E,W] absolute
                "active_dir":    active_dir,  # 0-3
                "phase":         phase,       # "green"/"yellow"
                # countdown intentionally omitted — app.py computes it adaptively
            },
            timeout=1,
        )
        if r.status_code == 200:
            return r.json()
        else:
            print(f"[API]          sensor_set {r.status_code}: {r.text[:60]}")
    except requests.RequestException as e:
        print(f"[API]          sensor_set error: {e}")
    return None


def get_junction_state():
    """GET current signal state for rupali_canal from dashboard."""
    try:
        r = requests.get(f"{API_BASE}/api/state", timeout=1)
        if r.status_code == 200:
            return r.json().get(JUNCTION_ID, {})
    except requests.RequestException:
        pass
    return {}


# ── Build SIG command from dashboard state ─────────────────────────────────────
def build_sig_command(state):
    """
    Translate dashboard signal state into a SIG:dir:phase:countdown command.

    Format:  SIG:1:G:22   (direction 1, Green, 22 seconds remaining)
             SIG:2:Y:3    (direction 2, Yellow, 3 seconds)
             SIG:0:R:0    (all red — VIP/upstream override)

    The Arduino processes this in processCommand() and calls setSignalLEDs().
    This is how the dashboard controls the physical LEDs exactly.
    """
    if not state:
        return None

    road_signals = state.get("road_signals", [])
    if not road_signals:
        return None

    # Ambulance corridor override
    if state.get("ambulance"):
        amb_toward = state.get("amb_toward")
        roads = [rs["road_to"] for rs in road_signals]
        if amb_toward and amb_toward in roads:
            idx = roads.index(amb_toward)
            return f"SIG:{idx}:G:6"
        return "SIG:0:R:0"

    # VIP or upstream block — all red
    if state.get("vip") or state.get("upstream_blocked"):
        return "SIG:0:R:0"

    # Normal: find active direction
    for idx, rs in enumerate(road_signals):
        if rs["phase"] in ("green", "yellow"):
            ph  = "G" if rs["phase"] == "green" else "Y"
            cntd = max(1, rs.get("countdown", 1))
            return f"SIG:{idx}:{ph}:{cntd}"

    return None


# ── Main loop ──────────────────────────────────────────────────────────────────
def main(port):
    global last_state, running, veh_dirty

    print("+---------------------------------------------------------+")
    print("|  Rupali Canal Junction  -  Hardware <-> Dashboard v3    |")
    print("+---------------------------------------------------------+")
    print(f"  Port      : {port} @ {BAUD_RATE} baud")
    print(f"  Dashboard : {API_BASE}")
    print(f"  Junction  : {JUNCTION_ID}")
    print()
    print("  On connect  : Dashboard vehicle counts ZEROED")
    print("  Every 200ms : VEH: counts -> dashboard (absolute)")
    print("  Every 1s    : Dashboard signal -> SIG: -> Arduino LEDs")
    print("  Every 2s    : PING keepalive (suppresses Arduino autonomous mode)")
    print("  Green time  : Computed adaptively by app.py ML from vehicle count")
    print()

    # Open serial port
    try:
        ser = serial.Serial(port, BAUD_RATE, timeout=2)
        time.sleep(2)   # wait for Arduino to finish resetting
        print(f"[Serial]       Connected to {port}")
    except serial.SerialException as e:
        print(f"[ERROR]        Cannot open {port}: {e}")
        print("  Linux  : try /dev/ttyUSB0 or /dev/ttyACM0")
        print("  Windows: try COM3, COM4, COM7 ...")
        sys.exit(1)

    # ── FIX 1: Zero dashboard counts on connect ────────────────────────────────
    print("[Connect]      Zeroing dashboard vehicle counts...")
    if not call_hardware_connect():
        print("[WARNING]      Could not reach dashboard to zero counts.")
        print("               Is app.py running at http://127.0.0.1:5000 ?")
        print("               Continuing anyway — counts will sync on first VEH:")

    # Start serial reader thread
    reader = threading.Thread(target=serial_reader, args=(ser,), daemon=True)
    reader.start()

    last_post_time = 0.0
    last_cmd_time  = 0.0
    last_ping_time = 0.0

    print("[Bridge]       Running — press Ctrl+C to stop.\n")

    try:
        while running:
            now = time.time()

            # ── Every 200ms push VEH: counts to dashboard ────────────────────
            if now - last_post_time >= POST_INTERVAL:
                last_post_time = now

                with lock:
                    counts    = list(hw_vehicle_counts)
                    a_dir     = hw_active_dir
                    a_phase   = hw_phase
                    dirty     = veh_dirty
                    veh_dirty = False   # consumed

                result = post_sensor_set(counts, a_dir, a_phase)
                if result and dirty:
                    # Only print when there was actually new sensor data
                    veh_str = "  ".join(
                        f"{DIRECTION_NAMES[i]}={counts[i]}" for i in range(4)
                    )
                    print(f"[-> Dashboard] {veh_str}  phase={a_phase}  dir={DIRECTION_NAMES[a_dir]}")

            # ── FIX 2: Every 1s send SIG: so Arduino obeys dashboard ──────────
            if now - last_cmd_time >= CMD_INTERVAL:
                last_cmd_time = now

                state = get_junction_state()
                if state:
                    last_state = state

                sig = build_sig_command(last_state)
                if sig:
                    ser.write((sig + "\n").encode())
                    phase_d = last_state.get("phase", "?")
                    cntd_d  = last_state.get("countdown", 0)
                    print(f"[-> Arduino]   {sig}  (dashboard phase={phase_d} cntd={cntd_d}s)")
                else:
                    # No valid state yet — just keep watchdog alive
                    ser.write(b"PING\n")

            # ── Every 2s: PING keeps Arduino out of autonomous mode ────────────
            if now - last_ping_time >= PING_INTERVAL:
                last_ping_time = now
                ser.write(b"PING\n")

            time.sleep(0.05)

    except KeyboardInterrupt:
        print("\n[Bridge]       Stopped by user.")
    finally:
        running = False
        try:
            ser.write(b"PING\n")   # one last ping; Arduino will go autonomous ~5s later
            time.sleep(0.15)
        except Exception:
            pass
        ser.close()
        print("[Bridge]       Port closed.")
        print("[Bridge]       Arduino will enter autonomous mode in ~5 seconds.")


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Rupali Canal Hardware <-> Dashboard Bridge v3"
    )
    parser.add_argument(
        "--port",
        default=DEFAULT_PORT,
        help=f"Serial port (default: {DEFAULT_PORT})",
    )
    args = parser.parse_args()
    main(args.port)