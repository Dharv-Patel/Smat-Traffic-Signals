/*
  ============================================================
  rupali_canal.ino
  Rupali Canal Junction — Smart Adaptive Traffic Controller
  Arduino Uno + 16 IR Sensors + 12 Traffic LEDs + Sound Sensor
  + LDR + Street Lights + Building Lights
  ============================================================

  JUNCTION LAYOUT (Rupali Canal, Surat):
  ┌─────────────────────────────────────────────────────────┐
  │  Direction 0 = NORTH  (towards Ram Chowk)               │
  │  Direction 1 = SOUTH  (towards KP Group Circle)         │
  │  Direction 2 = EAST   (towards Bhatar Char Rasta)       │
  │  Direction 3 = WEST   (towards Canal-Bhatar Rd Circle)  │
  └─────────────────────────────────────────────────────────┘

  ═══════════════════════════════════════════════════════════
  WIRING GUIDE
  ═══════════════════════════════════════════════════════════

  ── DIRECT IR SENSORS (1 per side, Active LOW) ──
    NORTH → D2   SOUTH → D3   EAST → D4   WEST → D5
    Each: VCC→5V, GND→GND, OUT→pin (INPUT_PULLUP)

  ── TRAFFIC SIGNAL LEDs (3 per direction = 12 total) ──
    NORTH: RED→D6   YELLOW→D7   GREEN→D8
    SOUTH: RED→D9   YELLOW→D10  GREEN→D11
    EAST:  RED→A0   YELLOW→A1   GREEN→A2
    WEST:  Controlled via PCF8574 #2 (P4=RED, P5=YELLOW, P6=GREEN)
    Each LED needs 220Ω resistor in series.

  ── SOUND SENSOR KY-038 (Ambulance Detection) ──
    VCC→5V, GND→GND, D0→D12
    Adjust potentiometer so only loud sirens/claps trigger it.

  ── LDR (Darkness Detection) ──
    Circuit: 5V → LDR → A6 → 10kΩ → GND
    A6 reads LOW when dark, HIGH when bright.
    (A6 is analog-only on Uno — safe from I2C conflict)

  ── NORTH STREET LIGHTS (direct via BC547 transistor) ──
    D13 → 1kΩ → BC547 Base
    BC547 Collector → Street LEDs(+) via 220Ω each
    BC547 Emitter → GND
    ON when: dark AND NORTH IR detects vehicle

  ── PCF8574 I2C EXPANDERS ──
    Both chips: VCC→5V, GND→GND, SDA→A4, SCL→A5
    Add 4.7kΩ pull-up resistors on SDA and SCL to 5V.
    ⚠ A3 (WEST RED in original) is freed — WEST LEDs now on Chip #2.

    CHIP #1 addr 0x20 (A0=GND, A1=GND, A2=GND) — all inputs:
      P0 → NORTH IR extra #2    P1 → NORTH IR extra #3
      P2 → NORTH IR extra #4    P3 → SOUTH IR extra #2
      P4 → SOUTH IR extra #3    P5 → SOUTH IR extra #4
      P6 → EAST  IR extra #2    P7 → EAST  IR extra #3

    CHIP #2 addr 0x21 (A0=VCC, A1=GND, A2=GND) — mixed:
      P0 → EAST  IR extra #4  (input)
      P1 → WEST  IR extra #2  (input)
      P2 → WEST  IR extra #3  (input)
      P3 → WEST  IR extra #4  (input)
      P4 → WEST RED LED       (output, LOW=ON via 220Ω)
      P5 → WEST YELLOW LED    (output, LOW=ON via 220Ω)
      P6 → WEST GREEN LED     (output, LOW=ON via 220Ω)
      P7 → Building Lights    (output, HIGH=ON via BC547)

  ── S/E/W STREET LIGHTS ──
    Recommended: second Arduino Nano listens to "STLIGHT:DIR:1/0"
    Serial messages from this sketch to control those lights.
  ═══════════════════════════════════════════════════════════
*/

#include <Wire.h>

// ── Constants ────────────────────────────────────────────────────────────────
#define NUM_DIRS            4
#define YELLOW_SECS         3
#define MIN_GREEN_SECS      18
#define MAX_GREEN_SECS      60
#define ZERO_BLINK_SECS     4
#define SEND_INTERVAL       200    // FIX: was 500ms — now 200ms for faster dashboard updates
#define IR_DEBOUNCE_MS      80     // FIX: ignore re-triggers within 80ms (same vehicle)
#define CMD_TIMEOUT_MS      5000
#define AMBULANCE_GREEN_SECS 15
#define LDR_DARK_THRESHOLD  400     // analogRead below this = dark (0–1023)
#define SOUND_DEBOUNCE_MS   500

#define PCF_ADDR_1  0x20
#define PCF_ADDR_2  0x21

// ── Pin Definitions ──────────────────────────────────────────────────────────
const int IR_PINS[NUM_DIRS]    = {2, 3, 4, 5};   // N, S, E, W

// NORTH/SOUTH/EAST direct LED pins [dir][R=0,Y=1,G=2]
// WEST (dir 3) → PCF8574 #2
const int LED_PINS[3][3] = {
  {6,  7,  8 },   // NORTH
  {9,  10, 11},   // SOUTH
  {A0, A1, A2},   // EAST
};

#define SOUND_PIN         12
#define LDR_PIN           A6
#define STREET_NORTH_PIN  13

// PCF8574 #1 bit positions (all inputs)
#define PCF1_IR_N2  0
#define PCF1_IR_N3  1
#define PCF1_IR_N4  2
#define PCF1_IR_S2  3
#define PCF1_IR_S3  4
#define PCF1_IR_S4  5
#define PCF1_IR_E2  6
#define PCF1_IR_E3  7

// PCF8574 #2 bit positions
#define PCF2_IR_E4       0   // input
#define PCF2_IR_W2       1   // input
#define PCF2_IR_W3       2   // input
#define PCF2_IR_W4       3   // input
#define PCF2_LED_W_RED   4   // output, LOW=ON
#define PCF2_LED_W_YEL   5   // output, LOW=ON
#define PCF2_LED_W_GRN   6   // output, LOW=ON
#define PCF2_BLDG_LIGHT  7   // output, HIGH=ON (via BC547)

// ── State ─────────────────────────────────────────────────────────────────────
int  vehicleCount[NUM_DIRS]     = {0,0,0,0};
bool lastIR[NUM_DIRS]           = {HIGH,HIGH,HIGH,HIGH};
bool lastIR_exp1[8]             = {HIGH,HIGH,HIGH,HIGH,HIGH,HIGH,HIGH,HIGH};
bool lastIR_exp2[4]             = {HIGH,HIGH,HIGH,HIGH};
int  edgeCount[NUM_DIRS]        = {0,0,0,0};

// FIX: debounce timestamps — one per sensor beam to prevent multi-count
unsigned long irDebounce[NUM_DIRS]      = {0,0,0,0};
unsigned long irDebounceExp1[8]         = {0,0,0,0,0,0,0,0};
unsigned long irDebounceExp2[4]         = {0,0,0,0};

int  activeDir      = 0;
int  currentPhase   = 0;
int  countdown      = MIN_GREEN_SECS;
bool isBlinking     = false;
bool blinkState     = false;
unsigned long blinkTimer = 0;

// Ambulance
bool ambulanceActive     = false;
int  ambulanceDir        = -1;
int  ambulanceCountdown  = 0;
bool lastSoundState      = HIGH;
unsigned long soundDebounce   = 0;
unsigned long lastAmbulanceTick = 0;

// Autonomous
bool autonomousMode  = false;
unsigned long lastCmdTime  = 0;
unsigned long lastTickTime = 0;
int  autoCountdown   = MIN_GREEN_SECS;
int  autoPhase       = 0;
int  autoActiveDir   = 0;
int  zeroSince       = -1;

// Lighting
bool isDark                       = false;
bool streetLight[NUM_DIRS]        = {false,false,false,false};
bool buildingLight                = false;
unsigned long lastLightCheck      = 0;
#define LIGHT_CHECK_INTERVAL      1000

// PCF8574
bool    pcf1Available = false;
bool    pcf2Available = false;
uint8_t pcf2Output    = 0xFF;   // P4–P6 HIGH=LED OFF; P7 LOW=light OFF initially

unsigned long lastSendTime = 0;
const char* DIR_NAMES[NUM_DIRS] = {"NORTH","SOUTH","EAST","WEST"};
String inputBuf = "";

// ═══════════════════════════════════════════════════════════════════════════════
void setup() {
  Serial.begin(9600);

  for (int i = 0; i < NUM_DIRS; i++) pinMode(IR_PINS[i], INPUT_PULLUP);

  for (int d = 0; d < 3; d++)
    for (int c = 0; c < 3; c++) {
      pinMode(LED_PINS[d][c], OUTPUT);
      digitalWrite(LED_PINS[d][c], LOW);
    }

  pinMode(SOUND_PIN, INPUT);
  pinMode(STREET_NORTH_PIN, OUTPUT);
  digitalWrite(STREET_NORTH_PIN, LOW);

  Wire.begin();
  pcf1Available = pcfPing(PCF_ADDR_1);
  pcf2Available = pcfPing(PCF_ADDR_2);

  if (pcf1Available) { pcfWrite(PCF_ADDR_1, 0xFF); Serial.println("INFO:PCF8574#1 OK"); }
  else               { Serial.println("WARN:PCF8574#1 not found - 1 IR sensor per side only"); }

  if (pcf2Available) {
    // P0-P3 inputs (high), P4-P6 outputs HIGH (LEDs OFF), P7 output LOW (lights OFF)
    pcf2Output = 0x7F;   // 0111 1111: P7=0(light off), P6/P5/P4=1(LEDs off), P3-P0=1(IR inputs)
    pcfWrite(PCF_ADDR_2, pcf2Output);
    Serial.println("INFO:PCF8574#2 OK");
  } else {
    Serial.println("WARN:PCF8574#2 not found - WEST LEDs + building lights unavailable");
  }

  setSignalLEDs(0, 0);
  lastCmdTime  = millis();
  lastTickTime = millis();
  Serial.println("READY:RupaliCanal");
  Serial.println("INFO:16xIR|12xLED|KY038|LDR|StreetLights|BuildingLights");
}

// ═══════════════════════════════════════════════════════════════════════════════
void loop() {
  unsigned long now = millis();

  readDirectIR();
  if (pcf1Available) readExpanderIR1();
  if (pcf2Available) readExpanderIR2();

  handleSoundSensor(now);

  if (now - lastLightCheck >= LIGHT_CHECK_INTERVAL) {
    lastLightCheck = now;
    updateLighting();
  }

  if (now - lastSendTime >= SEND_INTERVAL) {
    sendIRCounts();
    lastSendTime = now;
  }

  readSerial();

  if (now - lastCmdTime > CMD_TIMEOUT_MS) {
    if (!autonomousMode) {
      autonomousMode = true;
      Serial.println("WARN:Python disconnected - autonomous mode");
      autoActiveDir = 0; autoPhase = 0;
      autoCountdown = computeGreenTime(vehicleCount[0]);
      zeroSince = -1;
    }
    if (!ambulanceActive) runAutonomous(now);
  } else {
    autonomousMode = false;
  }

  if (ambulanceActive) runAmbulanceTimer(now);

  if (isBlinking && (now - blinkTimer >= 500)) {
    blinkTimer = now;
    blinkState = !blinkState;
    int dir = autonomousMode ? autoActiveDir : activeDir;
    setGreenPin(dir, blinkState);
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// IR READING
// ═══════════════════════════════════════════════════════════════════════════════
void readDirectIR() {
  unsigned long now = millis();
  for (int i = 0; i < NUM_DIRS; i++) {
    bool cur = digitalRead(IR_PINS[i]);
    // FIX: only count a new vehicle on falling edge AND debounce period has passed
    if (lastIR[i] == HIGH && cur == LOW) {
      if (now - irDebounce[i] >= IR_DEBOUNCE_MS) {
        irDebounce[i] = now;
        edgeCount[i]++;
        vehicleCount[i] = min(vehicleCount[i] + 1, 99);
        Serial.print("CAR_IN:"); Serial.println(i);
      }
    }
    lastIR[i] = cur;
  }
}

void readExpanderIR1() {
  unsigned long now = millis();
  uint8_t data = pcfRead(PCF_ADDR_1);
  // NORTH: bits 0,1,2 | SOUTH: bits 3,4,5 | EAST: bits 6,7
  int dirMap[8] = {0,0,0,1,1,1,2,2};
  for (int i = 0; i < 8; i++) {
    bool cur = !((data >> i) & 0x01);  // active LOW
    if (!lastIR_exp1[i] && cur) {
      // FIX: debounce — only count if debounce window has passed for this direction
      if (now - irDebounceExp1[i] >= IR_DEBOUNCE_MS) {
        irDebounceExp1[i] = now;
        edgeCount[dirMap[i]]++;
        vehicleCount[dirMap[i]] = min(vehicleCount[dirMap[i]] + 1, 99);
      }
    }
    lastIR_exp1[i] = cur;
  }
}

void readExpanderIR2() {
  unsigned long now = millis();
  uint8_t data = pcfRead(PCF_ADDR_2);
  // P0=EAST#4, P1=WEST#2, P2=WEST#3, P3=WEST#4
  int dirMap[4] = {2,3,3,3};
  for (int i = 0; i < 4; i++) {
    bool cur = !((data >> i) & 0x01);
    if (!lastIR_exp2[i] && cur) {
      // FIX: debounce per sensor beam
      if (now - irDebounceExp2[i] >= IR_DEBOUNCE_MS) {
        irDebounceExp2[i] = now;
        edgeCount[dirMap[i]]++;
        vehicleCount[dirMap[i]] = min(vehicleCount[dirMap[i]] + 1, 99);
      }
    }
    lastIR_exp2[i] = cur;
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// AMBULANCE
// ═══════════════════════════════════════════════════════════════════════════════
void handleSoundSensor(unsigned long now) {
  bool soundNow = (digitalRead(SOUND_PIN) == LOW);  // KY-038 D0 goes LOW on sound
  if (soundNow && !lastSoundState && (now - soundDebounce > SOUND_DEBOUNCE_MS)) {
    soundDebounce  = now;
    lastSoundState = true;
    if (!ambulanceActive) {
      ambulanceActive    = true;
      ambulanceDir       = activeDir;
      ambulanceCountdown = AMBULANCE_GREEN_SECS;
      lastAmbulanceTick  = now;
      setSignalLEDs(ambulanceDir, 0);
      Serial.print("AMBULANCE:DETECTED:");
      Serial.print(DIR_NAMES[ambulanceDir]);
      Serial.print(",green_for:"); Serial.println(AMBULANCE_GREEN_SECS);
    }
  }
  if (!soundNow) lastSoundState = false;
}

void runAmbulanceTimer(unsigned long now) {
  if (now - lastAmbulanceTick < 1000) return;
  lastAmbulanceTick = now;
  ambulanceCountdown--;
  Serial.print("AMBULANCE:COUNTDOWN:"); Serial.println(ambulanceCountdown);
  if (ambulanceCountdown <= 0) {
    ambulanceActive = false;
    ambulanceDir    = -1;
    Serial.println("AMBULANCE:CLEARED");
    setSignalLEDs(activeDir, currentPhase < 2 ? currentPhase : 0);
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// LIGHTING (LDR + Street + Building)
// ═══════════════════════════════════════════════════════════════════════════════
void updateLighting() {
  int ldrValue = analogRead(LDR_PIN);
  isDark = (ldrValue < LDR_DARK_THRESHOLD);

  // NORTH street light — direct pin D13
  bool northOn = isDark && (vehicleCount[0] > 0);
  if (northOn != streetLight[0]) {
    streetLight[0] = northOn;
    digitalWrite(STREET_NORTH_PIN, northOn ? HIGH : LOW);
  }

  // Building lights — PCF8574 #2, P7, via BC547 (HIGH = ON)
  if (pcf2Available) {
    if (isDark != buildingLight) {
      buildingLight = isDark;
      // P7 HIGH = transistor ON = building lights ON
      if (buildingLight) pcf2Output |=  (1 << PCF2_BLDG_LIGHT);
      else               pcf2Output &= ~(1 << PCF2_BLDG_LIGHT);
      pcfWrite(PCF_ADDR_2, pcf2Output);
    }
  }

  // Report LDR + NORTH light status
  Serial.print("LDR:"); Serial.print(ldrValue);
  Serial.print(",DARK:"); Serial.print(isDark ? "1":"0");
  Serial.print(",STLIGHT_N:"); Serial.print(streetLight[0] ? "1":"0");
  Serial.print(",BLDG:"); Serial.println(buildingLight ? "1":"0");

  // Notify Python/second Nano for S/E/W street lights
  for (int d = 1; d < NUM_DIRS; d++) {
    bool shouldOn = isDark && (vehicleCount[d] > 0);
    if (shouldOn != streetLight[d]) {
      streetLight[d] = shouldOn;
      Serial.print("STLIGHT:"); Serial.print(DIR_NAMES[d]);
      Serial.print(":"); Serial.println(shouldOn ? "1":"0");
    }
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// LED CONTROL
// ═══════════════════════════════════════════════════════════════════════════════
void setSignalLEDs(int activeD, int phase) {
  isBlinking = false;
  blinkState = false;

  for (int d = 0; d < NUM_DIRS; d++) {
    if (d == 3) {
      // WEST via PCF8574 #2 (LOW = LED ON for P4/P5/P6)
      if (!pcf2Available) continue;
      bool r = (d != activeD);
      bool y = (d == activeD && phase == 1);
      bool g = (d == activeD && phase == 0);
      // LOW = ON, so clear bit to turn ON, set bit to turn OFF
      if (r) pcf2Output |=  (1 << PCF2_LED_W_RED); else pcf2Output &= ~(1 << PCF2_LED_W_RED);
      if (!r) pcf2Output |= (1 << PCF2_LED_W_RED); // ensure off if not red — re-handle below
      // Cleaner logic:
      // RED on  → P4 LOW
      // YEL on  → P5 LOW
      // GRN on  → P6 LOW
      // Turn all WEST LEDs off first
      pcf2Output |= (1 << PCF2_LED_W_RED) | (1 << PCF2_LED_W_YEL) | (1 << PCF2_LED_W_GRN);
      if (d == activeD) {
        int pin = (phase == 0) ? PCF2_LED_W_GRN : PCF2_LED_W_YEL;
        pcf2Output &= ~(1 << pin);  // pull LOW = turn ON
      } else {
        pcf2Output &= ~(1 << PCF2_LED_W_RED);  // RED on for inactive
      }
      pcfWrite(PCF_ADDR_2, pcf2Output);
    } else {
      for (int c = 0; c < 3; c++) digitalWrite(LED_PINS[d][c], LOW);
      if (d == activeD) {
        digitalWrite(LED_PINS[d][(phase == 0) ? 2 : 1], HIGH);
      } else {
        digitalWrite(LED_PINS[d][0], HIGH);  // RED
      }
    }
  }
}

void setGreenPin(int dir, bool state) {
  if (dir == 3 && pcf2Available) {
    if (state) pcf2Output &= ~(1 << PCF2_LED_W_GRN);  // LOW = ON
    else       pcf2Output |=  (1 << PCF2_LED_W_GRN);  // HIGH = OFF
    pcfWrite(PCF_ADDR_2, pcf2Output);
  } else if (dir < 3) {
    digitalWrite(LED_PINS[dir][2], state ? HIGH : LOW);
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// PCF8574 HELPERS
// ═══════════════════════════════════════════════════════════════════════════════
bool pcfPing(uint8_t addr) {
  Wire.beginTransmission(addr);
  return (Wire.endTransmission() == 0);
}
void pcfWrite(uint8_t addr, uint8_t data) {
  Wire.beginTransmission(addr);
  Wire.write(data);
  Wire.endTransmission();
}
uint8_t pcfRead(uint8_t addr) {
  Wire.requestFrom(addr, (uint8_t)1);
  return Wire.available() ? Wire.read() : 0xFF;
}

// ═══════════════════════════════════════════════════════════════════════════════
// SERIAL
// ═══════════════════════════════════════════════════════════════════════════════
void sendIRCounts() {
  Serial.print("IR:");
  for (int i = 0; i < NUM_DIRS; i++) {
    Serial.print(edgeCount[i]);
    if (i < NUM_DIRS-1) Serial.print(",");
    edgeCount[i] = 0;
  }
  Serial.println();
  Serial.print("VEH:");
  for (int i = 0; i < NUM_DIRS; i++) {
    Serial.print(vehicleCount[i]);
    if (i < NUM_DIRS-1) Serial.print(",");
  }
  Serial.println();
}

void readSerial() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') { processCommand(inputBuf); inputBuf = ""; }
    else if (c != '\r') inputBuf += c;
  }
}

void processCommand(String cmd) {
  cmd.trim();
  if (cmd.length() == 0) return;
  lastCmdTime = millis();

  if (cmd == "PING") { Serial.println("PONG"); return; }

  if (cmd == "RESET") {
    activeDir = 0; currentPhase = 0; countdown = MIN_GREEN_SECS;
    isBlinking = false; ambulanceActive = false;
    for (int i = 0; i < NUM_DIRS; i++) vehicleCount[i] = 0;
    setSignalLEDs(0, 0);
    Serial.println("OK:RESET"); return;
  }

  // SIG:d:phase:countdown
  if (cmd.startsWith("SIG:")) {
    int p1 = cmd.indexOf(':', 4), p2 = cmd.indexOf(':', p1+1);
    if (p1<0||p2<0) return;
    int d = cmd.substring(4,p1).toInt();
    char ph = cmd.charAt(p1+1);
    int cntd = cmd.substring(p2+1).toInt();
    if (d<0||d>=NUM_DIRS) return;
    activeDir = d; countdown = cntd;
    int phIdx = (ph=='G')?0:(ph=='Y')?1:2;
    currentPhase = phIdx;
    if (!ambulanceActive && phIdx<2) setSignalLEDs(d, phIdx);
    return;
  }

  // BLINK:d:state
  if (cmd.startsWith("BLINK:")) {
    int p1 = cmd.indexOf(':',6); if (p1<0) return;
    int d = cmd.substring(6,p1).toInt();
    int st = cmd.substring(p1+1).toInt();
    if (d<0||d>=NUM_DIRS) return;
    isBlinking = (st==1);
    if (!isBlinking) setGreenPin(d, true);
    blinkTimer = millis(); return;
  }

  // AMBDIR:d — Python specifies ambulance direction
  if (cmd.startsWith("AMBDIR:")) {
    int d = cmd.substring(7).toInt();
    if (d>=0&&d<NUM_DIRS) {
      ambulanceActive = true; ambulanceDir = d;
      ambulanceCountdown = AMBULANCE_GREEN_SECS;
      lastAmbulanceTick = millis();
      setSignalLEDs(d, 0);
      Serial.print("AMBULANCE:PYOVERRIDE:"); Serial.println(DIR_NAMES[d]);
    } return;
  }

  // VEHDEC:d — Python confirms vehicles cleared
  if (cmd.startsWith("VEHDEC:")) {
    int d = cmd.substring(7).toInt();
    if (d>=0&&d<NUM_DIRS) vehicleCount[d] = max(0, vehicleCount[d]-5);
    return;
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// AUTONOMOUS MODE
// ═══════════════════════════════════════════════════════════════════════════════
void runAutonomous(unsigned long now) {
  if (now - lastTickTime < 1000) return;
  lastTickTime = now;

  int aDir = autoActiveDir, aVeh = vehicleCount[aDir];
  int greenElapsed = computeGreenTime(aVeh) - autoCountdown;

  if (autoPhase==0 && aVeh==0 && greenElapsed>=MIN_GREEN_SECS) {
    if (zeroSince<0) { zeroSince=ZERO_BLINK_SECS; isBlinking=true; blinkTimer=now; }
    else {
      zeroSince--;
      if (zeroSince<=0) {
        autoPhase=1; autoCountdown=YELLOW_SECS;
        isBlinking=false; zeroSince=-1;
        setSignalLEDs(aDir,1); return;
      }
    }
  } else if (aVeh>0) { zeroSince=-1; isBlinking=false; }

  autoCountdown--;
  if (autoCountdown<=0) {
    if (autoPhase==0) {
      autoPhase=1; autoCountdown=YELLOW_SECS;
      isBlinking=false; setSignalLEDs(aDir,1);
    } else {
      autoActiveDir=(aDir+1)%NUM_DIRS;
      autoPhase=0; autoCountdown=computeGreenTime(vehicleCount[autoActiveDir]);
      isBlinking=false; zeroSince=-1;
      vehicleCount[aDir]=max(0,vehicleCount[aDir]-5);
      setSignalLEDs(autoActiveDir,0);
      Serial.print("AUTO:GREEN:"); Serial.print(DIR_NAMES[autoActiveDir]);
      Serial.print(",dur:"); Serial.println(autoCountdown);
    }
  }
}

int computeGreenTime(int vehicles) {
  return max(MIN_GREEN_SECS, min(MAX_GREEN_SECS, MIN_GREEN_SECS + vehicles/2));
}
