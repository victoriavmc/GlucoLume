#include <Wire.h>

const uint8_t PIN_SDA = A4;
const uint8_t PIN_SCL = A5;
const uint8_t MAX30100_DIR = 0x57;

void setup() {
  Serial.begin(115200);

  Wire.begin();
  Wire.setClock(100000);
  Wire.setWireTimeout(25000, true);

  Serial.println("BUSCANDO MAX30100");
}

void loop() {
  Wire.beginTransmission(MAX30100_DIR);
  byte error = Wire.endTransmission();

  Serial.print("SDA: ");
  Serial.println(digitalRead(PIN_SDA));

  Serial.print("SCL: ");
  Serial.println(digitalRead(PIN_SCL));

  switch (error) {
    case 0:
      Serial.println("MAX30100 DETECTADO - 0x57");
      break;

    case 2:
      Serial.println("ERROR 2: Sensor sin respuesta");
      break;

    case 5:
      Serial.println("ERROR 5: Timeout I2C");
      break;

    default:
      Serial.print("ERROR: ");
      Serial.println(error);
      break;
  }

  Serial.println("-----------------------");

  delay(2000);
}