// fandomat-1.53 (Fandomat - automatic waste sorter)
// Author: Saidjon Rajapov

#include <Adafruit_NeoPixel.h>
#include <Servo.h>

///// CONFIG /////
// #################### LED strip ####################
#define LED_PIN 5
#define NUM_LEDS 64
Adafruit_NeoPixel strip(NUM_LEDS, LED_PIN, NEO_GRB + NEO_KHZ800);

// #################### Servo (SG90) ####################
#define SERVO_PIN 6
Servo gateServo;
#define anglePlastic   0
#define angleAluminum  60
int currentServoAngle = -1;

// #################### Stepper Motor (DM556) ####################
#define STEP_PIN   11   // PUL+
#define DIR_PIN    12   // DIR+
#define ENABLE_PIN 10   // ENA+
#define STEP_DELAY 500  // µs between steps (speed)

// #################### Button ####################
#define BTN_PIN 3 // non used in this version

// #################### Timings ####################
unsigned long MOTOR_RUN_MS     = 1000;
unsigned long REJECT_RUN_MS    = 5000;
unsigned long LED_PLASTIC_MS   = 5000;
unsigned long LED_ALUMINUM_MS  = 5000;

///// STATES /////
enum State {
  IDLE,
  START,
  PROCESS_PLASTIC,
  PROCESS_ALUMINUM,
  REJECT
};
State state = IDLE;

// Timers
unsigned long stateStart = 0;
unsigned long motorStart = 0;

///// HELPERS /////

// #################### Non-blocking Servo (SG90 stable) ####################
void moveServo(int targetAngle) {
  static unsigned long servoMoveStart = 0;
  static bool servoMoving = false;

  // Map logical 0–180° to SG90 safe PWM range
  int safeAngle = map(targetAngle, 0, 180, 5, 175);

  // Start move if new angle requested
  if (targetAngle != currentServoAngle && !servoMoving) {
    gateServo.attach(SERVO_PIN, 600, 2400); // MG996R pulse range
    gateServo.write(safeAngle);
    servoMoveStart = millis();
    servoMoving = true;
    currentServoAngle = targetAngle;
  }

  // Hold PWM for 600 ms to let servo stabilize, then detach
  if (servoMoving && millis() - servoMoveStart >= 600) {
    gateServo.detach();
    servoMoving = false;
  }
}

// #################### Stepper Motor ####################
void motorEnable() {
  digitalWrite(ENABLE_PIN, LOW);  // Active LOW
}

void motorDisable() {
  digitalWrite(ENABLE_PIN, HIGH); // Disable = HIGH
}

void motorMove(long steps, bool forward) {
  digitalWrite(DIR_PIN, forward ? HIGH : LOW);
  for (long i = 0; i < steps; i++) {
    digitalWrite(STEP_PIN, HIGH);
    delayMicroseconds(1750);   // DM556 min pulse width = 5 µs
    digitalWrite(STEP_PIN, LOW);
    delayMicroseconds(300);
  }
}

// #################### LEDs ####################
void setAll(uint8_t r, uint8_t g, uint8_t b) {
  for (int i = 0; i < NUM_LEDS; i++) {
    strip.setPixelColor(i, strip.Color(r, g, b));
  }
  strip.show();
}

void rainbow(uint8_t wait) {
  static uint16_t j = 0;
  for (int i = 0; i < NUM_LEDS; i++) {
    int pixelHue = (i * 256 / NUM_LEDS + j) & 255;
    strip.setPixelColor(i, strip.gamma32(strip.ColorHSV(pixelHue * 256)));
  }
  strip.show();
  j++;
  delay(wait);
}

///// #################### SETUP ####################
void setup() {
  Serial.begin(9600);

  strip.begin();
  strip.show();
  setAll(0, 0, 0);

  gateServo.attach(SERVO_PIN, 600, 2400);
  moveServo(anglePlastic); // initial stable position

  pinMode(STEP_PIN, OUTPUT);
  pinMode(DIR_PIN, OUTPUT);
  pinMode(ENABLE_PIN, OUTPUT);
  motorDisable(); // start disabled

  pinMode(BTN_PIN, INPUT_PULLUP);

  state = IDLE;
  stateStart = millis();
  startIdle();
}

///// #################### STATE STARTERS ####################
void startStart() {
  state = START;
  stateStart = millis();
  motorDisable();
  setAll(0, 255, 0); // green
}

void startIdle() {
  state = IDLE;
  stateStart = millis();
  motorDisable();
}

void startProcessPlastic() {
  state = PROCESS_PLASTIC;
  stateStart = millis();

  moveServo(anglePlastic);
  motorEnable();
  setAll(255, 255, 0); // yellow

  motorMove(2000, true); // forward rotation
  motorDisable();
}

void startProcessAluminum() {
  state = PROCESS_ALUMINUM;
  stateStart = millis();

  moveServo(angleAluminum);
  motorEnable();
  setAll(0, 0, 255); // blue

  motorMove(2000, true); // forward rotation
  motorDisable();
}

void startReject() {
  state = REJECT;
  stateStart = millis();

  motorEnable();
  setAll(255, 0, 0); // red
  motorMove(2000, false); // backward rotation
  motorDisable();
}

///// #################### SERIAL ####################
void handleSerial() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == 'S') startStart();
    else if (c == 'P') startProcessPlastic();
    else if (c == 'A') startProcessAluminum();
    else if (c == 'R') startReject();
    else if (c == 'E') startIdle();
  }
}

///// #################### MAIN LOOP ####################
void loop() {
  unsigned long now = millis();

  handleSerial();
  moveServo(currentServoAngle); // keep servo logic alive

  switch (state) {
    case IDLE:
      rainbow(20);
      break;

    case START:
      // stays green until command changes
      break;

    case PROCESS_PLASTIC:
      if (now - stateStart >= LED_PLASTIC_MS) startIdle();
      break;

    case PROCESS_ALUMINUM:
      if (now - stateStart >= LED_ALUMINUM_MS) startIdle();
      break;

    case REJECT:
      if (now - stateStart >= REJECT_RUN_MS) startIdle();
      break;
  }
}
