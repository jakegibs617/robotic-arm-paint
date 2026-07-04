// Minimal Arduino PWM-servo bridge for painterbot's ascii_servo protocol.
//
// Python sends one command per line:
//   S <channel> <angle>
//
// Example:
//   S 0 90
//
// This sketch is intentionally small and boring: the Python software remains the
// source of truth for safe per-joint limits; the Arduino only clamps to Servo.h's
// absolute 0..180 degree range before writing the PWM pulse.

#include <Servo.h>

const long BAUD_RATE = 115200;
const byte SERVO_COUNT = 6;

// Edit these pins to match the actual wiring.
const byte SERVO_PINS[SERVO_COUNT] = {3, 5, 6, 9, 10, 11};

Servo servos[SERVO_COUNT];
int positions[SERVO_COUNT] = {90, 90, 90, 90, 90, 30};

void setup() {
  Serial.begin(BAUD_RATE);

  for (byte ch = 0; ch < SERVO_COUNT; ch++) {
    servos[ch].attach(SERVO_PINS[ch]);
    servos[ch].write(positions[ch]);
  }

  Serial.println("READY painterbot ascii_servo");
}

void loop() {
  if (!Serial.available()) {
    return;
  }

  char cmd = Serial.read();
  if (cmd == '\n' || cmd == '\r' || cmd == ' ') {
    return;
  }

  if (cmd == 'S' || cmd == 's') {
    handleServoCommand();
  } else if (cmd == '?') {
    printPositions();
  } else {
    discardLine();
    Serial.println("ERR unknown command");
  }
}

void handleServoCommand() {
  int channel = Serial.parseInt();
  float angle = Serial.parseFloat();
  discardLine();

  if (channel < 0 || channel >= SERVO_COUNT) {
    Serial.println("ERR channel");
    return;
  }

  int clamped = constrain((int)round(angle), 0, 180);
  positions[channel] = clamped;
  servos[channel].write(clamped);

  Serial.print("OK ");
  Serial.print(channel);
  Serial.print(" ");
  Serial.println(clamped);
}

void printPositions() {
  Serial.print("POS");
  for (byte ch = 0; ch < SERVO_COUNT; ch++) {
    Serial.print(" ");
    Serial.print(positions[ch]);
  }
  Serial.println();
}

void discardLine() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      break;
    }
  }
}
