"""
rupali_canal_hw_test_bridge.py
==============================
Hardware Test Bridge — Rupali Canal Junction

This script connects your Arduino running rupali_canal_hardware_test.ino
to the Flask dashboard (app.py).

What it does:
  1. Reads VEH: lines from Arduino every 500ms
  2. Posts vehicle counts to Flask → software dashboard updates live
  3. Sends PING keepalive every 2 seconds so Arduino knows Python is alive
  4. If Python is NOT running → Arduino runs Rupali Canal autonomously

HOW TO USE:
  Step 1: Start Flask app:       python app.py
  Step 2: Run this bridge:       python rupali_canal_hw_test_bridge.py
  Step 3: Upload the .ino sketch to Arduino
  Step 4: Open Serial Monitor to watch sensor triggers

  Windows:  python rupali_canal_hw_test_bridge.py --port COM3
  Linux:    python rupali_canal_hw_test_bridge.py --port /dev/ttyUSB0
  Mac:      python rupali_canal_hw_test_bridge.py --port /dev/cu.usbserial-110

SERIAL MESSAGES FROM ARDUINO:
  VEH:40,0,20,10     → vehicle counts for N, S, E, W
  CAR_IN:NORTH       → car entered from North (+10)
  CAR_OUT:NORTH      → car left from North (-10)
  AUTO:GREEN:SOUTH   → autonomous mode switched to South green
  WARN:...           → Python disconnected warning

REQUIREMENTS:
  pip install pyserial requests
"""

import argparse
import sys
import time
import serial
import requests

# ── Configuration ─────────────────────────────────────────────────────────────
DEFAULT_PORT   = "COM7"                 # Windows default — change to your port
BAUD_RATE      = 9600
API_BASE       = "http://127.0.0.1:5000"
JUNCTION_ID    = "rupali_canal"
PING_INTERVAL  = 2.0                   # seconds between PINGs

# Direction mapping — matches your sensor wiring
# Index 0=NORTH, 1=SOUTH, 2=EAST, 3=WEST
DIR_NAMES = ["NORTH", "SOUTH", "EAST", "WEST"]

# ── State ─────────────────────────────────────────────────────────────────────
vehicle_counts  = [0, 0, 0, 0]
last_ping_time  = 0.0
arduino_ready   = False


# ── API call — update software dashboard ──────────────────────────────────────
def post_vehicle_counts(counts):
    """Send vehicle counts to Flask app. Dashboard updates automatically."""
    try:
        resp = requests.post(
            f"{API_BASE}/api/sensor_update",
            json={
                "junction_id":   JUNCTION_ID,
                "road_vehicles": counts,
            },
            timeout=2,
        )
        if resp.status_code == 200:
            data = resp.json()
            print(f"  [API] ✓ Dashboard updated → "
                  f"N={counts[0]} S={counts[1]} E={counts[2]} W={counts[3]}")
        else:
            print(f"  [API] ✗ Error {resp.status_code}: {resp.text[:60]}")
    except requests.ConnectionError:
        print(f"  [API] ✗ Cannot reach Flask at {API_BASE} — is app.py running?")
    except requests.Timeout:
        print("  [API] ✗ Request timed out")


# ── Parse VEH: line from Arduino ─────────────────────────────────────────────
def parse_veh_line(line):
    """
    Parse 'VEH:40,0,20,10' → [40, 0, 20, 10]
    Returns None if line is malformed.
    """
    try:
        parts = line.strip().split(":", 1)
        if len(parts) != 2:
            return None
        values = [int(x.strip()) for x in parts[1].split(",")]
        if len(values) == 4:
            return values
    except (ValueError, IndexError):
        pass
    return None


# ── Main bridge loop ──────────────────────────────────────────────────────────
def run_bridge(port):
    global vehicle_counts, last_ping_time, arduino_ready

    print(f"\n{'='*55}")
    print(f"  Rupali Canal Hardware Test Bridge")
    print(f"  Arduino port : {port}")
    print(f"  Flask app    : {API_BASE}")
    print(f"  Junction     : {JUNCTION_ID}")
    print(f"{'='*55}")
    print()
    print("  Waiting for Arduino... (may take 2-3 seconds after USB connect)")
    print()

    try:
        ser = serial.Serial(port, BAUD_RATE, timeout=1)
    except serial.SerialException as e:
        print(f"\n[ERROR] Cannot open port {port}: {e}")
        print("\nTroubleshooting:")
        print("  Windows: check Device Manager → Ports (COM & LPT)")
        print("           try COM3, COM4, COM5 etc.")
        print("  Linux:   try /dev/ttyUSB0 or /dev/ttyACM0")
        print("  Mac:     try /dev/cu.usbserial-XXXX")
        sys.exit(1)

    time.sleep(2)   # wait for Arduino to reset after Serial connect
    ser.reset_input_buffer()

    print(f"[OK] Connected to Arduino on {port}")
    print()
    print("  WHAT TO DO NOW:")
    print("  1. Open your browser → http://127.0.0.1:5000")
    print("  2. Click on Rupali Canal junction on the map")
    print("  3. Pass your hand in front of each IR sensor")
    print("  4. Watch the vehicle count change on the dashboard!")
    print()
    print("  SERIAL LOG (showing Arduino messages):")
    print(f"  {'─'*50}")

    last_ping_time = time.time()

    while True:
        now = time.time()

        # Send PING keepalive every 2 seconds
        if now - last_ping_time >= PING_INTERVAL:
            try:
                ser.write(b"PING\n")
                last_ping_time = now
            except serial.SerialException:
                print("[ERROR] Lost connection to Arduino!")
                break

        # Read one line from Arduino
        try:
            raw = ser.readline()
            if not raw:
                continue
            line = raw.decode("utf-8", errors="replace").strip()
        except serial.SerialException as e:
            print(f"[ERROR] Serial read error: {e}")
            break

        if not line:
            continue

        # ── Handle each message type ────────────────────────────────────────

        # Arduino ready message
        if line.startswith("READY:"):
            arduino_ready = True
            print(f"  [Arduino] ✓ {line}")
            print()
            continue

        # INFO and WARN messages — just display them
        if line.startswith("INFO:") or line.startswith("WARN:"):
            tag = "ℹ" if line.startswith("INFO:") else "⚠"
            print(f"  [{tag}] {line}")
            continue

        # PONG — keepalive reply
        if line == "PONG":
            # Silently received — Arduino is alive
            continue

        # Vehicle count update → post to dashboard
        if line.startswith("VEH:"):
            counts = parse_veh_line(line)
            if counts:
                vehicle_counts = counts
                post_vehicle_counts(counts)
            continue

        # Car IN event (debug)
        if line.startswith("CAR_IN:"):
            direction = line.split(":", 1)[1]
            print(f"  [🚗 +10] Car ENTERED from {direction}")
            continue

        # Car OUT event (debug)
        if line.startswith("CAR_OUT:"):
            direction = line.split(":", 1)[1]
            print(f"  [🚗 -10] Car LEFT from {direction}")
            continue

        # Autonomous mode signal change
        if line.startswith("AUTO:"):
            print(f"  [🚦 AUTO] {line}")
            continue

        # Status printout
        if line.startswith("==="):
            print(f"  {line}")
            continue

        # OK confirmations
        if line.startswith("OK:"):
            print(f"  [OK] {line}")
            continue

        # Anything else — print it for debugging
        print(f"  [Arduino] {line}")


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Rupali Canal Hardware Test Bridge"
    )
    parser.add_argument(
        "--port",
        default=DEFAULT_PORT,
        help=f"Arduino serial port (default: {DEFAULT_PORT})",
    )
    args = parser.parse_args()

    try:
        run_bridge(args.port)
    except KeyboardInterrupt:
        print("\n\n[Stopped] Bridge closed by user.")
        print("Note: Arduino will switch to autonomous mode in ~5 seconds.")
