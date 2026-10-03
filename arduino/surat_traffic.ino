/*
  surat_traffic.ino
  Arduino Uno — Smart Traffic Light Controller
  Hardware: 4 IR sensors + 4×3 LEDs (Red/Yellow/Green per direction)

  Wiring:
    IR Sensors (active LOW, output HIGH when no car, LOW when car detected):
      Sensor 0 (North) → D2
      Sensor 1 (South) → D3
      Sensor 2 (East)  → D4
      Sensor 3 (West)  → D5

    Traffic LEDs (one set per direction, simplified to 1 direction shown):
      North: Red→D6,  Yellow→D7,  Green→D8
      South: Red→D9,  Yellow→D10, Green→D11
      East:  Red→A0,  Yellow→A1,  Green→A2
      West:  Red→A3,  Yellow→A4,  Green→A5

  Protocol: Every 500ms, sends "IR:<n0>,<n1>,<n2>,<n3>\n" over Serial (9600 baud)
  where n = number of rising edges (cars counted) in last 500ms window.

  Also accepts commands from PC:
    "G:NS\n"  → set North-South green, East-West red
    "G:EW\n"  → set East-West green, North-South red
    "Y:NS\n"  → North-South yellow
    "Y:EW\n"  → East-West yellow
*/

// ── Pin Definitions ────────────────────────────────────────────────────────────
const int IR_PINS[4]    = {2, 3, 4, 5};  // N, S, E, W

// LED pins [direction][R=0, Y=1, G=2]
const int LED_PINS[4][3] = {
  {6,  7,  8 },   // North
  {9,  10, 11},   // South
  {A0, A1, A2},   // East
  {A3, A4, A5},   // West
};

// ── State ──────────────────────────────────────────────────────────────────────
int  carCount[4]      = {0, 0, 0, 0};
bool lastIR[4]        = {HIGH, HIGH, HIGH, HIGH};
unsigned long lastSend = 0;
String inputBuffer     = "";

// ── Setup ──────────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(9600);
  for (int i = 0; i < 4; i++) {
    pinMode(IR_PINS[i], INPUT_PULLUP);
    for (int j = 0; j < 3; j++) {
      pinMode(LED_PINS[i][j], OUTPUT);
      digitalWrite(LED_PINS[i][j], LOW);
    }
  }
  // Default: NS green, EW red
  setSignal(true);
  Serial.println("READY:SuratTraffic");
}

// ── Main Loop ──────────────────────────────────────────────────────────────────
void loop() {
  // Count cars via IR sensors
  for (int i = 0; i < 4; i++) {
    bool cur = digitalRead(IR_PINS[i]);
    if (lastIR[i] == HIGH && cur == LOW) {  // falling edge = car detected
      carCount[i]++;
    }
    lastIR[i] = cur;
  }

  // Send counts every 500ms
  if (millis() - lastSend >= 500) {
    Serial.print("IR:");
    for (int i = 0; i < 4; i++) {
      Serial.print(carCount[i]);
      if (i < 3) Serial.print(",");
      carCount[i] = 0;  // reset count
    }
    Serial.println();
    lastSend = millis();
  }

  // Receive commands from PC
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') {
      processCommand(inputBuffer);
      inputBuffer = "";
    } else {
      inputBuffer += c;
    }
  }
}

// ── Signal Control ─────────────────────────────────────────────────────────────
void setSignal(bool ns_green) {
  // NS = indices 0,1 ; EW = indices 2,3
  int nsVal = ns_green ? 2 : 0;   // 2=green pin, 0=red pin
  int ewVal = ns_green ? 0 : 2;

  for (int i = 0; i < 4; i++) {
    // Turn all off first
    for (int j = 0; j < 3; j++) digitalWrite(LED_PINS[i][j], LOW);
    // Light appropriate color
    int col = (i < 2) ? nsVal : ewVal;
    digitalWrite(LED_PINS[i][col], HIGH);
  }
}

void setYellow(bool ns_yellow) {
  int nsCol = ns_yellow ? 1 : 0;   // 1=yellow, 0=red
  int ewCol = ns_yellow ? 0 : 1;
  for (int i = 0; i < 4; i++) {
    for (int j = 0; j < 3; j++) digitalWrite(LED_PINS[i][j], LOW);
    int col = (i < 2) ? nsCol : ewCol;
    digitalWrite(LED_PINS[i][col], HIGH);
  }
}

void processCommand(String cmd) {
  cmd.trim();
  if      (cmd == "G:NS") setSignal(true);
  else if (cmd == "G:EW") setSignal(false);
  else if (cmd == "Y:NS") setYellow(true);
  else if (cmd == "Y:EW") setYellow(false);
}
