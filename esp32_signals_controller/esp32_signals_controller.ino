#include <WiFi.h>
#include <PubSubClient.h>
#include <cstring>
#include <cstdlib>
#include <esp32-hal-ledc.h>
// --------------- User configuration ----------------
const char* WIFI_SSID = "YOUR_SSID";
const char* WIFI_PASS = "YOUR_PASSWORD";

const char* MQTT_HOST = "broker.emqx.io";
const uint16_t MQTT_PORT = 1883;
const char* MQTT_CLIENT_ID = "esp32_signals_controller";
const char* TOPIC_CYCLE = "signals/cycle";

// Pin mapping for each signal head (two per direction group)
struct SignalPins {
  uint8_t red;
  uint8_t yellow;
  uint8_t green;
};

SignalPins NS_SIGNALS[] = {
  {21, 22, 23},  // North
  {19, 18, 5}    // South
};

SignalPins EW_SIGNALS[] = {
  {25, 26, 27},  // East
  {32, 33, 4}    // West
};

// Timing defaults / fail-safe
const uint32_t DEFAULT_NS_GREEN = 9000;
const uint32_t DEFAULT_EW_GREEN = 9000;
const uint32_t DEFAULT_AMBER = 2000;
const uint32_t DEFAULT_ALL_RED = 1000;
const uint32_t FAILSAFE_MS = 15000;

WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);

struct CycleSpec {
  bool nsFirst;
  uint32_t nsGreen;
  uint32_t ewGreen;
  uint32_t amber;
  uint32_t allRed;
};

enum Phase {
  PHASE_NS_GREEN,
  PHASE_NS_AMBER,
  PHASE_ALL_RED_TO_EW,
  PHASE_EW_GREEN,
  PHASE_EW_AMBER,
  PHASE_ALL_RED_TO_NS
};

CycleSpec activeCycle = {true, DEFAULT_NS_GREEN, DEFAULT_EW_GREEN, DEFAULT_AMBER, DEFAULT_ALL_RED};
CycleSpec pendingCycle;
bool hasPendingCycle = false;

Phase currentPhase = PHASE_NS_GREEN;
unsigned long phaseStarted = 0;
uint32_t phaseDuration = DEFAULT_NS_GREEN;
unsigned long lastCycleRx = 0;

// ---------------- Helper routines ----------------

void setSignalPins(const SignalPins& pins, bool redOn, bool yellowOn, bool greenOn) {
  digitalWrite(pins.red, redOn ? HIGH : LOW);
  digitalWrite(pins.yellow, yellowOn ? HIGH : LOW);
  digitalWrite(pins.green, greenOn ? HIGH : LOW);
}

void setGroup(SignalPins* group, size_t count, bool redOn, bool yellowOn, bool greenOn) {
  for (size_t i = 0; i < count; ++i) {
    setSignalPins(group[i], redOn, yellowOn, greenOn);
  }
}

void allRed() {
  setGroup(NS_SIGNALS, 2, true, false, false);
  setGroup(EW_SIGNALS, 2, true, false, false);
}

uint32_t durationForPhase(const CycleSpec& spec, Phase phase) {
  switch (phase) {
    case PHASE_NS_GREEN: return spec.nsGreen;
    case PHASE_NS_AMBER: return spec.amber;
    case PHASE_ALL_RED_TO_EW: return spec.allRed;
    case PHASE_EW_GREEN: return spec.ewGreen;
    case PHASE_EW_AMBER: return spec.amber;
    case PHASE_ALL_RED_TO_NS: return spec.allRed;
  }
  return DEFAULT_NS_GREEN;
}

Phase nextPhase(Phase phase) {
  switch (phase) {
    case PHASE_NS_GREEN: return PHASE_NS_AMBER;
    case PHASE_NS_AMBER: return PHASE_ALL_RED_TO_EW;
    case PHASE_ALL_RED_TO_EW: return PHASE_EW_GREEN;
    case PHASE_EW_GREEN: return PHASE_EW_AMBER;
    case PHASE_EW_AMBER: return PHASE_ALL_RED_TO_NS;
    case PHASE_ALL_RED_TO_NS: return PHASE_NS_GREEN;
  }
  return PHASE_NS_GREEN;
}

void applyOutputsForPhase(Phase phase) {
  switch (phase) {
    case PHASE_NS_GREEN:
      setGroup(NS_SIGNALS, 2, false, false, true);
      setGroup(EW_SIGNALS, 2, true, false, false);
      break;
    case PHASE_NS_AMBER:
      setGroup(NS_SIGNALS, 2, false, true, false);
      setGroup(EW_SIGNALS, 2, true, false, false);
      break;
    case PHASE_ALL_RED_TO_EW:
    case PHASE_ALL_RED_TO_NS:
      allRed();
      break;
    case PHASE_EW_GREEN:
      setGroup(EW_SIGNALS, 2, false, false, true);
      setGroup(NS_SIGNALS, 2, true, false, false);
      break;
    case PHASE_EW_AMBER:
      setGroup(EW_SIGNALS, 2, false, true, false);
      setGroup(NS_SIGNALS, 2, true, false, false);
      break;
  }
}

void beginPhase(Phase phase, const CycleSpec& spec) {
  currentPhase = phase;
  phaseDuration = durationForPhase(spec, phase);
  phaseStarted = millis();
  applyOutputsForPhase(phase);
}

void activateCycle(const CycleSpec& spec) {
  activeCycle = spec;
  Phase startPhase = spec.nsFirst ? PHASE_NS_GREEN : PHASE_EW_GREEN;
  beginPhase(startPhase, activeCycle);
  lastCycleRx = millis();
  hasPendingCycle = false;
}

CycleSpec defaultCycle() {
  CycleSpec spec;
  spec.nsFirst = true;
  spec.nsGreen = DEFAULT_NS_GREEN;
  spec.ewGreen = DEFAULT_EW_GREEN;
  spec.amber = DEFAULT_AMBER;
  spec.allRed = DEFAULT_ALL_RED;
  return spec;
}

// ---------------- Networking ----------------

void ensureWifi() {
  if (WiFi.status() == WL_CONNECTED) {
    return;
  }
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println(" connected");
}

void ensureMqtt() {
  while (!mqtt.connected()) {
    Serial.print("Connecting to MQTT...");
    if (mqtt.connect(MQTT_CLIENT_ID)) {
      Serial.println("connected");
      mqtt.subscribe(TOPIC_CYCLE);
    } else {
      Serial.print("failed, rc=");
      Serial.print(mqtt.state());
      Serial.println(" retrying in 2s");
      delay(2000);
    }
  }
}

void handleCycleMessage(const char* payload) {
  char order[4] = {0};
  unsigned long nsMs = 0, ewMs = 0, amberMs = 0, allredMs = 0;
  int parsed = sscanf(payload, "CYCLE %3s %lu %lu %lu %lu", order, &nsMs, &ewMs, &amberMs, &allredMs);
  if (parsed != 5) {
    Serial.print("Invalid cycle payload: ");
    Serial.println(payload);
    return;
  }
  CycleSpec spec;
  spec.nsFirst = (strncmp(order, "NS", 2) == 0);
  spec.nsGreen = (uint32_t)nsMs;
  spec.ewGreen = (uint32_t)ewMs;
  spec.amber = (uint32_t)amberMs;
  spec.allRed = (uint32_t)allredMs;
  pendingCycle = spec;
  hasPendingCycle = true;
  lastCycleRx = millis();
  Serial.printf("Queued cycle: order=%s NS=%lu EW=%lu amber=%lu allred=%lu\n", order, nsMs, ewMs, amberMs, allredMs);
}

void mqttCallback(char* topic, byte* payload, unsigned int length) {
  if (strcmp(topic, TOPIC_CYCLE) != 0) {
    return;
  }
  static char buffer[96];
  size_t copyLen = length;
  if (copyLen >= sizeof(buffer)) {
    copyLen = sizeof(buffer) - 1;
  }
  memcpy(buffer, payload, copyLen);
  buffer[copyLen] = '\0';
  handleCycleMessage(buffer);
}

// ---------------- FSM update ----------------

void updatePhases() {
  unsigned long now = millis();
  if (now - phaseStarted < phaseDuration) {
    return;
  }
  if ((currentPhase == PHASE_ALL_RED_TO_NS || currentPhase == PHASE_ALL_RED_TO_EW) && hasPendingCycle) {
    activateCycle(pendingCycle);
    return;
  }
  currentPhase = nextPhase(currentPhase);
  if ((currentPhase == PHASE_NS_GREEN || currentPhase == PHASE_EW_GREEN) && hasPendingCycle) {
    activateCycle(pendingCycle);
    return;
  }
  beginPhase(currentPhase, activeCycle);
}

void checkFailsafe() {
  unsigned long now = millis();
  if (now - lastCycleRx > FAILSAFE_MS) {
    Serial.println("Failsafe: reverting to default cycle");
    activateCycle(defaultCycle());
  }
}

// ---------------- Arduino entry points ----------------

void setup() {
  Serial.begin(115200);
  for (SignalPins pins : NS_SIGNALS) {
    pinMode(pins.red, OUTPUT);
    pinMode(pins.yellow, OUTPUT);
    pinMode(pins.green, OUTPUT);
  }
  for (SignalPins pins : EW_SIGNALS) {
    pinMode(pins.red, OUTPUT);
    pinMode(pins.yellow, OUTPUT);
    pinMode(pins.green, OUTPUT);
  }
  allRed();

  ensureWifi();
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(mqttCallback);
  ensureMqtt();
  activateCycle(activeCycle);
}

void loop() {
  ensureWifi();
  ensureMqtt();
  mqtt.loop();
  updatePhases();
  checkFailsafe();
  delay(5);
}
