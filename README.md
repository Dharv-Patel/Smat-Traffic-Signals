# 🚦 Surat Smart Traffic Management System

A college-level IoT + ML demonstration project for smart traffic management
across real Surat City junctions.

---

## 📁 Project Structure

```
surat_traffic/
├── app.py                  ← Flask backend (main server)
├── traffic_graph.py        ← Dijkstra shortest-path graph
├── serial_bridge.py        ← Arduino ↔ Python serial reader
├── requirements.txt
├── ml/
│   └── traffic_predictor.py ← ML model (adaptive green times)
├── arduino/
│   └── surat_traffic.ino   ← Arduino sketch
└── templates/
    └── index.html          ← Web dashboard (Leaflet.js)
```

---

## 🚀 Quick Start (Software Only)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the dashboard
python app.py

# 3. Open in browser
#    http://127.0.0.1:5000
```

---

## 🔌 Hardware Setup (Rupali Canal Smart Traffic Physical Model)

> Full hardware guide from: **Rupali_Canal_Hardware_Guide.docx**
> Arduino Uno | IR Sensors | Traffic LEDs | Sound Detection | Street & Building Lights

---

### SECTION 1: Complete Hardware List

#### 1.1 Main Controller

| Component | Qty | Purpose | Approx. Price (INR) |
|-----------|-----|---------|---------------------|
| Arduino Uno R3 | 1 | Main brain — controls all sensors, LEDs, and logic | ₹400–600 |
| USB A to B Cable | 1 | Connect Arduino to laptop (power + serial data) | ₹80–120 |
| 9V Battery + Snap Connector | 1 | Portable power if laptop not available | ₹50–80 |

#### 1.2 IR Sensors — Traffic Detection (4 per road side × 4 sides = 16 total)

| Component | Qty | Spec / Notes | Approx. Price (INR) |
|-----------|-----|-------------|---------------------|
| IR Obstacle Sensor Module (FC-51) | 16 | Active LOW output; 3-pin module (VCC, GND, OUT). Adjustable sensitivity via onboard potentiometer | ₹25–40 each (~₹500 total) |

> ⚠ **Note:** Arduino Uno only has 14 digital + 6 analog pins. With 16 IR sensors + 12 LEDs, you WILL run out of pins. Use an I2C port expander (PCF8574 or MCP23017) for extra sensors. See Section 3.3.

#### 1.3 Traffic Signal LEDs — 3 per direction × 4 directions = 12 LEDs

| Component | Qty | Color | Purpose |
|-----------|-----|-------|---------|
| 5mm LED | 4 | RED | One per direction — STOP signal |
| 5mm LED | 4 | YELLOW | One per direction — SLOW DOWN signal |
| 5mm LED | 4 | GREEN | One per direction — GO signal |
| 220Ω Resistor (1/4W) | 12 | — | One in series per LED to limit current |

> ✔ **Tip:** Buy pre-packaged LED assorted kits (100 pcs ₹80) — includes all colors.

#### 1.4 Ambulance / Sound Detection

| Component | Qty | Notes | Approx. Price (INR) |
|-----------|-----|-------|---------------------|
| KY-038 Sound Sensor Module | 1 | Detects loud sound (siren). Has digital OUT pin. Sensitivity adjustable by onboard potentiometer | ₹30–60 |

> ⚠ **Note:** KY-038 only detects if sound is above a threshold — it does NOT identify ambulance siren frequency specifically. For a physical model demo, this is sufficient. Set sensitivity so only loud claps/sirens trigger it.

#### 1.5 Street Lights (Roads) — Turn ON when dark + vehicle detected

| Component | Qty | Notes | Approx. Price (INR) |
|-----------|-----|-------|---------------------|
| LDR (Light Dependent Resistor) | 4 | One per road side — detects darkness | ₹5–10 each |
| 10kΩ Resistor | 4 | Voltage divider with LDR (pull-down) | ₹1–2 each |
| White/Yellow LED 5mm | 8–12 | Street lights (2–3 per road side) | ₹2–5 each |
| 220Ω Resistor | 8–12 | Current limiter for each street LED | ₹1–2 each |
| NPN Transistor (2N2222 or BC547) | 4 | Switch for driving multiple street LEDs | ₹5–10 each |

#### 1.6 Building Lights — Turn ON when dark + vehicle nearby

| Component | Qty | Notes | Approx. Price (INR) |
|-----------|-----|-------|---------------------|
| Yellow/Warm White LED 5mm | 8–16 | 2–4 per building (~4 buildings) | ₹2–5 each |
| 220Ω Resistor | 8–16 | One per LED | ₹1–2 each |
| LDR (shared with street lights) | — | Reuse same LDR reading per road side | Already counted above |

#### 1.7 Pin Expander (Critical for Physical Model)

| Component | Qty | Notes | Approx. Price (INR) |
|-----------|-----|-------|---------------------|
| PCF8574 I2C Port Expander | 2 | Adds 8 digital I/O pins per chip via I2C (2-wire). 2 chips = 16 extra pins for the 12 extra IR sensors | ₹40–80 each |

#### 1.8 Wires & Connectors

| Component | Qty | Notes |
|-----------|-----|-------|
| Jumper Wires Male-to-Male | 40+ | For breadboard connections |
| Jumper Wires Male-to-Female | 20+ | For sensor modules to breadboard |
| Breadboard (830 points) | 1–2 | Main circuit assembly |
| Mini Breadboard (400 points) | 1 | Optional — for sensor cluster |

#### 1.9 Summary Shopping List

| Item | Quantity | Est. Total Cost |
|------|----------|----------------|
| Arduino Uno R3 | 1 | ₹500 |
| IR Sensor Module FC-51 | 16 | ₹500 |
| Red LED 5mm | 4 | ₹20 |
| Yellow LED 5mm | 4 | ₹20 |
| Green LED 5mm | 4 | ₹20 |
| White/Yellow LED (street+building) | 20–28 | ₹80 |
| 220Ω Resistor | 40 | ₹40 |
| 10kΩ Resistor | 4 | ₹10 |
| LDR | 4 | ₹40 |
| KY-038 Sound Sensor | 1 | ₹50 |
| PCF8574 I2C Port Expander | 2 | ₹120 |
| NPN Transistor BC547 | 4 | ₹30 |
| Jumper Wires (bundle) | 1 bundle | ₹100 |
| Breadboard 830pt | 1 | ₹80 |
| USB Cable for Arduino | 1 | ₹100 |
| **TOTAL** | | **~₹1,700–2,000** |

---

### SECTION 2: Arduino Pin Mapping

Based on `rupali_canal.ino` — exact pin numbers used in the program.

#### 2.1 IR Sensors (Vehicle Detection) — Direct Arduino Pins

| Direction | Road Side | Arduino Pin | Wire Color Suggested |
|-----------|-----------|-------------|----------------------|
| NORTH | Ram Chowk side | D2 | Yellow |
| SOUTH | KP Group Circle side | D3 | Orange |
| EAST | Bhatar Char Rasta side | D4 | Blue |
| WEST | Canal-Bhatar Rd Circle side | D5 | Purple |

> ⚠ **Note:** This is only 4 pins for 4 sensors (1 per side). The model uses 4 IR sensors per side = 16 sensors total. The extra 12 sensors need the PCF8574 expander (see Section 3.3).

#### 2.2 Traffic Signal LEDs — Direct Arduino Pins

| Direction | LED Color | Arduino Pin | Wire Color |
|-----------|-----------|-------------|------------|
| NORTH | RED | D6 | Red wire |
| NORTH | YELLOW | D7 | Yellow wire |
| NORTH | GREEN | D8 | Green wire |
| SOUTH | RED | D9 | Red wire |
| SOUTH | YELLOW | D10 | Yellow wire |
| SOUTH | GREEN | D11 | Green wire |
| EAST | RED | A0 | Red wire |
| EAST | YELLOW | A1 | Yellow wire |
| EAST | GREEN | A2 | Green wire |
| WEST | RED | A3 | Red wire |
| WEST | YELLOW | A4 | Yellow wire |
| WEST | GREEN | A5 | Green wire |

#### 2.3 Sound Sensor (Ambulance Detection)

| Signal | Arduino Pin | Notes |
|--------|-------------|-------|
| OUT (Digital) | D12 (recommended) | Goes HIGH or LOW on loud sound |
| VCC | 5V | Power supply |
| GND | GND | Ground |

> ⚠ **Note:** D12 and D13 are free in the current code — add sound sensor code to use D12.

#### 2.4 LDR (Darkness Sensor) for Street & Building Lights

| LDR Position | Arduino Pin | Notes |
|-------------|-------------|-------|
| LDR North Road | A0 (conflict!) → use A6 or expander | Conflict with EAST RED LED — plan carefully |
| LDR All Sides | Use analog reads via expander or separate Arduino | Recommended: use one LDR for whole model |

> ⚠ **Note:** Since analog pins A0–A5 are all used for LEDs, use a second small Arduino Nano (₹180) or a separate transistor circuit for the LDR-triggered lights.

---

### SECTION 3: Detailed Wire Connections

#### 3.1 How to Connect Each IR Sensor (FC-51 Module)

```
IR Sensor VCC  →  Arduino 5V (breadboard red rail)
IR Sensor GND  →  Arduino GND (breadboard blue rail)
IR Sensor OUT  →  Arduino Digital Pin (D2/D3/D4/D5)
```

#### 3.2 LED Wiring (Each Traffic LED)

```
Arduino Pin  →  220Ω Resistor  →  LED Anode (+, long leg)
LED Cathode (−, short leg / flat side)  →  GND
```

#### 3.3 PCF8574 I2C Port Expander (For Extra 12 IR Sensors)

| PCF8574 Pin | Connect To | Notes |
|-------------|-----------|-------|
| VCC | Arduino 5V | Power |
| GND | Arduino GND | Ground |
| SDA | Arduino A4 (SDA) | I2C Data — shared between chips |
| SCL | Arduino A5 (SCL) | I2C Clock — shared between chips |
| A0, A1, A2 | GND or VCC to set address | Chip 1: A0=GND,A1=GND,A2=GND (addr 0x20); Chip 2: A0=VCC (addr 0x21) |
| P0–P7 | One IR sensor OUT per pin | 8 sensors per chip × 2 chips = 16 sensors |

> ⚠ **CONFLICT ALERT:** A4 and A5 are also used for EAST/WEST YELLOW LEDs. You must reassign those LED pins or use a second Arduino Nano just for the extra sensors.

#### 3.4 Sound Sensor (KY-038) Wiring — Ambulance Detection

| KY-038 Pin | Connect To | Notes |
|-----------|-----------|-------|
| VCC (+) | Arduino 5V | Power supply |
| GND (−) | Arduino GND | Ground |
| D0 (Digital Out) | Arduino D12 | Sends HIGH/LOW based on sound threshold |
| A0 (Analog Out) | Not needed | Ignore for basic use |

**Calibration:**
- Rotate the potentiometer on KY-038 slowly clockwise to increase sensitivity.
- In normal room: onboard LED should be OFF. Clap hands — it should turn ON briefly.
- Set so only loud sounds (like sirens) trigger it, not normal talking.

#### 3.5 Street Light & Building Light Wiring

LDR voltage divider:
```
5V → LDR → Junction Point (→ Analog Pin) → 10kΩ Resistor → GND
```

Transistor switch for multiple LEDs:
```
Arduino Pin → 1kΩ Resistor → BC547 Base (B)
BC547 Collector (C) → All street LEDs (+) via 220Ω each
BC547 Emitter (E) → GND
LED other end (−) → GND
```

| Light Group | Control Method | ON Condition | Arduino Pin (suggestion) |
|-------------|---------------|-------------|--------------------------|
| NORTH Street Lights | BC547 transistor | Dark (LDR) AND NORTH IR detects car | D13 |
| SOUTH Street Lights | BC547 transistor | Dark AND SOUTH IR detects car | Second Arduino or expander |
| EAST Street Lights | BC547 transistor | Dark AND EAST IR detects car | Second Arduino or expander |
| WEST Street Lights | BC547 transistor | Dark AND WEST IR detects car | Second Arduino or expander |
| Building Lights | BC547 transistor | Dark (LDR) — always ON when dark | Single shared pin |

---

### SECTION 4: Physical Model Wiring Tips

#### 4.1 Power Rails — Most Important Rule
- Arduino 5V pin → breadboard RED (+) rail
- Arduino GND pin → breadboard BLUE (−) rail
- EVERY sensor and LED cathode must connect to GND rail
- EVERY sensor VCC must connect to 5V rail

> ⚠ If your breadboard has two separate halves (gap in middle), connect both halves' power rails with a short wire.

#### 4.2 Wire Color Coding — Use Consistently

| Wire Color | Always Use For |
|-----------|---------------|
| RED | 5V Power (VCC) |
| BLACK | Ground (GND) |
| YELLOW | Sensor signal wires |
| GREEN | Green LED connections |
| Orange/Brown | Yellow LED connections |
| Blue/Purple | Red LED connections |
| White | Data signals (SDA, SCL, etc.) |

#### 4.3 Testing Order (Step by Step)

1. Connect only Arduino + USB. Upload basic 'Blink' sketch. LED on pin 13 should blink.
2. Add all 12 traffic LEDs + resistors. Test each one lights up.
3. Add 4 IR sensors (one per side). Open Serial Monitor. Wave hand — check IR count increases.
4. Upload `rupali_canal.ino`. Traffic lights should cycle automatically.
5. Add sound sensor. Clap near it — ambulance override should activate.
6. Add LDR + street/building LEDs. Cover LDR to simulate darkness — lights should turn ON.
7. If adding extra 12 IR sensors, wire PCF8574 expanders and test I2C communication.

#### 4.4 Common Mistakes to Avoid

- **Never** connect LED directly to Arduino pin without 220Ω resistor — it will burn the pin.
- Do not reverse LED polarity — flat side / short leg must go to GND.
- IR sensors must face downward/forward toward road, not upward.
- KY-038 potentiometer — turn slowly. Too sensitive = constant false triggers.
- Check that ALL ground wires connect to SAME GND. Multiple disconnected grounds = erratic behavior.
- When using I2C: SDA and SCL each need a 4.7kΩ pull-up resistor to 5V if connecting long wires.

---

### SECTION 5: Quick Reference Card

| What | Where | How Many |
|------|-------|----------|
| Arduino Uno | Centre of junction model | 1 |
| IR Sensors (per side) | Road entry points, 4 sensors in a row | 4 per side × 4 sides = 16 |
| Traffic LEDs (per side) | Above road on signal pole | 3 per side (R/Y/G) × 4 = 12 |
| Sound Sensor (KY-038) | Any central location | 1 total |
| LDR (dark sensor) | Open area, exposed to ambient light | 1–4 |
| Street Light LEDs | Along road edges | 2–3 per side (8–12 total) |
| Building Light LEDs | Inside model buildings | 2–4 per building |
| PCF8574 Expander | On breadboard | 2 (for extra IR sensors) |
| BC547 Transistors | On breadboard | 4 (one per road side for lights) |
| 220Ω Resistors | In series with every LED | 40+ total |
| 10kΩ Resistors | With each LDR (voltage divider) | 4 |

### Upload Arduino Code
1. Open `arduino/rupali_canal.ino` in Arduino IDE
2. Select Board: **Arduino Uno**
3. Select correct COM port
4. Upload

### Run Serial Bridge
```bash
# Edit SERIAL_PORT in serial_bridge.py first (COM3 / /dev/ttyUSB0)
python serial_bridge.py
```

---

## 🤖 ML Model

The `TrafficPredictor` class in `ml/traffic_predictor.py` uses a
**weighted linear regression** model to compute adaptive green light durations:

```
green_time = base + (density_weight × density)
           + (peak_am_weight × am_peak × density)
           + (peak_pm_weight × pm_peak × density)
```

- Base green time: **18 seconds**
- Range: **10 – 60 seconds**
- Peak hours: 8–10 AM and 5–8 PM get extra weight
- NS and EW directions get inverse proportions

---

## 🗺 Junctions Covered

| Junction | Location |
|----------|----------|
| Athwa Gate | Central Surat |
| Majura Gate | North |
| Vesu Point | West Surat |
| Ring Road Circle | Central |
| Adajan Patia | West |
| Piplod Circle | Southwest |
| Katargam | North-East |
| Varachha Road | North-East |
| Udhna Darwaja | East |
| Sachin Circle | South |
| Althan Tenament | West |
| Bhatar Road | Central-West |

---

## 🌐 API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /` | Web dashboard |
| `GET /api/state` | All junction states (density, phase, countdown) |
| `GET /api/route?from=X&to=Y` | Shortest path avoiding congestion |
| `GET /api/junctions` | Junction coordinates |
| `GET /api/arduino_data` | Live sensor simulation/hardware data |

---

## 📊 Features

- **Live Traffic Simulation** — densities update every second
- **Adaptive Signal Timing** — ML adjusts green times per density
- **4-Phase Signal Cycling** — NS Green → NS Yellow → EW Green → EW Yellow
- **Interactive Map** — Leaflet.js dark map with colored roads
- **Route Finder** — Dijkstra's algorithm avoiding congested roads
- **Arduino Integration** — Real IR sensor data via serial bridge
- **Countdown Timers** — Live per-junction phase countdowns

---

## 🎓 Presentation Tips

1. Show the **live map** with color-coded roads changing in real-time
2. Demonstrate **route finding** between two distant junctions
3. Explain the **ML model** weights and how peak hours affect timing
4. If hardware available: show IR sensor triggering signal change
5. Show the **API endpoints** in browser to prove backend integration

---

*Built for final-year engineering demonstration — Surat, Gujarat*
