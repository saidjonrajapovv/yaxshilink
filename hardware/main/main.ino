#include <Adafruit_NeoPixel.h>
#include <Servo.h>
#include <AccelStepper.h>

///// CONFIG /////
// LED strip
#define LED_PIN 5
#define NUM_LEDS 31
Adafruit_NeoPixel strip(NUM_LEDS, LED_PIN, NEO_GRB + NEO_KHZ800);

// Servo
#define SERVO_PIN 6
Servo gateServo;
#define anglePlastic   0
#define angleAluminum  45
int currentServoAngle = -1;

// Stepper motor (DM556 driver)
#define STEP_PIN 12
#define DIR_PIN  11
AccelStepper stepper(AccelStepper::DRIVER, STEP_PIN, DIR_PIN);

// Button
#define BTN_PIN 9

// Timings
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

// Safe servo move
void moveServo(int angle) {
  if (angle != currentServoAngle) {
    gateServo.write(angle);
    currentServoAngle = angle;
  }
}

// LEDs
void setAll(uint8_t r, uint8_t g, uint8_t b) {
  for (int i = 0; i < NUM_LEDS; i++) {
    strip.setPixelColor(i, strip.Color(r, g, b));
  }
  strip.show();
}

// Rainbow animation
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

///// SETUP / LOOP /////
void setup() {
  Serial.begin(9600);

  strip.begin();
  strip.show();
  setAll(0, 0, 0);

  gateServo.attach(SERVO_PIN);
  moveServo(anglePlastic);

  // Stepper setup
  stepper.setMaxSpeed(1000);    // adjust as needed
  stepper.setAcceleration(500); // smooth acceleration
  stepper.setCurrentPosition(0);

  pinMode(BTN_PIN, INPUT_PULLUP);

  state = IDLE;
  stateStart = millis();
  startIdle();
}

///// STATE STARTERS /////
void startStart() {
  state = START;
  stateStart = millis();
  stepper.stop();
  setAll(0, 255, 0); // green
}

void startIdle() {
  state = IDLE;
  stateStart = millis();
  stepper.stop();
}

void startProcessPlastic() {
  state = PROCESS_PLASTIC;
  stateStart = millis();
  motorStart = millis();

  moveServo(anglePlastic);
  stepper.moveTo(stepper.currentPosition() + 2000); // forward
  setAll(255, 255, 0); // yellow
}

void startProcessAluminum() {
  state = PROCESS_ALUMINUM;
  stateStart = millis();
  motorStart = millis();

  moveServo(angleAluminum);
  stepper.moveTo(stepper.currentPosition() + 2000); // forward
  setAll(0, 0, 255); // blue
}

void startReject() {
  state = REJECT;
  stateStart = millis();
  motorStart = millis();

  // Rotate backward
  stepper.moveTo(stepper.currentPosition() - 2000);
  setAll(255, 0, 0); // red
}

///// SERIAL + BUTTON /////
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

void handleButton() {
  static bool lastState = HIGH;
  bool st = digitalRead(BTN_PIN);
  if (st != lastState) {
    lastState = st;
    if (st == LOW) startStart();
  }
}

///// MAIN LOOP /////
void loop() {
  unsigned long now = millis();

  handleSerial();
  handleButton();

  stepper.run(); // continuously run stepper for smooth motion

  switch (state) {
    case IDLE:
      rainbow(20);
      break;

    case START:
      // stays green until command changes state
      break;

    case PROCESS_PLASTIC:
      if (now - motorStart >= MOTOR_RUN_MS) stepper.stop();
      if (now - stateStart >= LED_PLASTIC_MS) startIdle();
      break;

    case PROCESS_ALUMINUM:
      if (now - motorStart >= MOTOR_RUN_MS) stepper.stop();
      if (now - stateStart >= LED_ALUMINUM_MS) startIdle();
      break;

    case REJECT:
      if (now - stateStart >= REJECT_RUN_MS) startIdle();
      break;
  }
}

/*
OLD CUSTOM MOTOR CODE (RELAY STYLE) — kept for reference:
void motorForward() {
  digitalWrite(DIR_PIN, HIGH);
  digitalWrite(DIR_PIN2, HIGH);
  digitalWrite(ENABLE_PIN, LOW);
}
void motorBackward() {
  digitalWrite(DIR_PIN, LOW);
  digitalWrite(DIR_PIN2, LOW);
  digitalWrite(ENABLE_PIN, LOW);
}
void motorStop() {
  digitalWrite(ENABLE_PIN, HIGH);
  digitalWrite(DIR_PIN, HIGH);
  digitalWrite(DIR_PIN2, HIGH);
}
*/



// 26.10.2025 12:18pm fandomat-1.3 
// Stepper motor edition
