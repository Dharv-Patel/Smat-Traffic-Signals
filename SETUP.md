# Rupali Canal Junction — Hardware Setup Guide

## What This Does
Replaces the simulated traffic for **Rupali Canal Junction** with real
IR sensor data from an Arduino Uno. All 29 other junctions continue
running software simulation. The dashboard shows a green **📡 LIVE** badge
on the Rupali Canal card when hardware is connected.

All features (ambulance corridor, VIP convoy, upstream blocking, ETA,
live route vehicle) work identically on hardware and simulated junctions.

---

## Hardware Required
| Component               | Qty | Notes                     |
|-------------------------|-----|---------------------------|
| Arduino Uno             | 1   | Any clone works           |
| IR Obstacle Sensor FC-51| 4   | Active-LOW output         |
| Red LED                 | 4   | 1 per direction           |
| Yellow LED              | 4   | 1 per direction           |
| Green LED               | 4   | 1 per direction           |
| 220Ω Resistor           | 12  | 1 per LED                 |
| Breadboard + Jumpers    | —   |                           |

---

## Wiring Diagram
```
ARDUINO UNO
┌─────────────────────────────────┐
│  D2 ──── IR Sensor NORTH (OUT)  │  ← Traffic from Ram Chowk
│  D3 ──── IR Sensor SOUTH (OUT)  │  ← Traffic from KP Group Circle
│  D4 ──── IR Sensor EAST  (OUT)  │  ← Traffic from Bhatar Char Rasta
│  D5 ──── IR Sensor WEST  (OUT)  │  ← Traffic from Canal-Bhatar Rd
│                                 │
│  D6 ──[220Ω]── RED    (NORTH)   │
│  D7 ──[220Ω]── YELLOW (NORTH)   │
│  D8 ──[220Ω]── GREEN  (NORTH)   │
│  D9 ──[220Ω]── RED    (SOUTH)   │
│  D10─[220Ω]── YELLOW (SOUTH)   │
│  D11─[220Ω]── GREEN  (SOUTH)   │
│  A0 ──[220Ω]── RED    (EAST)    │
│  A1 ──[220Ω]── YELLOW (EAST)    │
│  A2 ──[220Ω]── GREEN  (EAST)    │
│  A3 ──[220Ω]── RED    (WEST)    │
│  A4 ──[220Ω]── YELLOW (WEST)    │
│  A5 ──[220Ω]── GREEN  (WEST)    │
│                                 │
│  5V ──── IR VCC (all 4)         │
│  GND ─── IR GND + LED cathodes  │
└─────────────────────────────────┘
```

---

## Software Setup (3 steps)

### Step 1 — Flash the Arduino
Open `arduino/rupali_canal.ino` in Arduino IDE → Upload to Uno.
Expected serial output:
```
READY:RupaliCanal
INFO:4-way junction | NORTH/SOUTH/EAST/WEST
```

### Step 2 — Install Python dependencies
```bash
pip install flask flask-cors pyserial requests
```

### Step 3 — Run (2 terminals)

**Terminal 1 — Flask app:**
```bash
python app.py
```

**Terminal 2 — Hardware bridge:**
```bash
# Windows:
python rupali_canal_bridge.py --port COM3

# Linux / Mac:
python rupali_canal_bridge.py --port /dev/ttyUSB0
```

---

## How It Works

```
IR Sensor detects car → Arduino counts edge
        │
        ▼  every 500ms
Arduino sends "IR:5,3,8,2" over USB
        │
        ▼
rupali_canal_bridge.py receives counts
        ├── POST /api/sensor_update  →  Flask adds vehicles to queue
        └── GET  /api/state         →  reads current signal phase
                                           │
                                           ▼
                                  Sends "SIG:0:G:25" to Arduino
                                           │
                                           ▼
                                  Arduino lights LEDs
```

### Autonomous Fallback
If `rupali_canal_bridge.py` crashes or the USB disconnects, the Arduino
automatically switches to **autonomous mode** after 5 seconds — running
the same adaptive signal logic locally using its own IR sensor readings.
Serial output shows: `WARN:Python disconnected - autonomous mode`

### Signal Protocol (Python → Arduino)
| Command              | Meaning                              |
|----------------------|--------------------------------------|
| `SIG:d:G:25`         | Direction d is GREEN, 25s remaining  |
| `SIG:d:Y:3`          | Direction d is YELLOW, 3s remaining  |
| `BLINK:d:1`          | Start blinking direction d (early skip warning) |
| `BLINK:d:0`          | Stop blinking                        |
| `PING`               | Keep-alive (Arduino replies `PONG`)  |
| `RESET`              | Reset all signals to default         |

---

## Troubleshooting

| Problem                    | Fix                                             |
|----------------------------|-------------------------------------------------|
| "Cannot open COM3"         | Change `--port` to match your system            |
| LEDs don't light           | Check 220Ω resistors; measure 5V at pin         |
| Sensors not triggering     | Adjust potentiometer on FC-51; check distance   |
| Bridge runs but no IR data | Cover sensor with hand to test                  |
| All directions stay red    | Check `READY:RupaliCanal` in serial monitor     |
| Dashboard shows no LIVE badge | Bridge not running or wrong junction_id      |

---

## File Summary
```
project/
├── app.py                        ← Main Flask app (hardware-aware)
├── rupali_canal_bridge.py        ← Run this to connect Arduino ↔ Flask
├── arduino/
│   ├── rupali_canal.ino          ← Flash this to Arduino Uno (Rupali Canal)
│   └── surat_traffic.ino         ← Generic junction sketch (for future use)
├── templates/index.html          ← Dashboard (shows 📡 LIVE badge)
├── requirements.txt              ← pip dependencies
└── SETUP.md                      ← This file
```
