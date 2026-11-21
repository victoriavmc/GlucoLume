#include <LiquidCrystal_I2C.h>
#include "MAX30100_PulseOximeter.h"

// Crear el objeto LCD con dirección 0x27, 16 columnas y 2 filas
LiquidCrystal_I2C lcd(0x27, 16, 2);

#define REPORTING_PERIOD_MS 1000

PulseOximeter pox;
uint32_t tsLastReport = 0;

// Pines del semáforo
const int verde = 8;
const int amarillo = 9;
const int rojo = 12;

void onBeatDetected() {
    Serial.println("¡Latido detectado!");
}

void setup() {
    // Iniciar comunicación serial
    Serial.begin(115200);
    Serial.println("Inicializando sistema...");

    // Configurar pines del semáforo como salida
    pinMode(verde, OUTPUT);
    pinMode(amarillo, OUTPUT);
    pinMode(rojo, OUTPUT);

    digitalWrite(verde, LOW);
    digitalWrite(amarillo, LOW);
    digitalWrite(rojo, LOW);

    // Inicializar LCD
    lcd.init();
    lcd.backlight();
    lcd.print("Iniciando...");
    delay(3000);
    lcd.clear();

    // Inicializar el oxímetro MAX30100
    if (!pox.begin()) {
        Serial.println("ERROR: Fallo al iniciar MAX30100");
        lcd.setCursor(0, 0);
        lcd.print("Error MAX30100");
        while (1);
    } else {
        Serial.println("SUCCESS: MAX30100 iniciado correctamente");
    }

    // Configurar corriente del LED infrarrojo
    pox.setIRLedCurrent(MAX30100_LED_CURR_7_6MA);

    // Registrar callback de detección de latidos
    pox.setOnBeatDetectedCallback(onBeatDetected);
}

void loop() {
    // Actualizar el sensor tan rápido como sea posible
    pox.update();

    float bpm = pox.getHeartRate();
    float spO2 = pox.getSpO2();

    // Control del semáforo basado en los BPM (si hay lectura válida)
    if (bpm > 0) {
        if (bpm <= 110) {
            digitalWrite(verde, HIGH);
            digitalWrite(amarillo, LOW);
            digitalWrite(rojo, LOW);
        } else if (bpm <= 150) {
            digitalWrite(verde, LOW);
            digitalWrite(amarillo, HIGH);
            digitalWrite(rojo, LOW);
        } else {
            digitalWrite(verde, LOW);
            digitalWrite(amarillo, LOW);
            digitalWrite(rojo, HIGH);
        }
    } else {
        // Si no hay dedo o lectura válida, apagar semáforo
        digitalWrite(verde, LOW);
        digitalWrite(amarillo, LOW);
        digitalWrite(rojo, LOW);
    }

    // Reportar cada 1 segundo en el monitor serie y actualizar LCD
    if (millis() - tsLastReport > REPORTING_PERIOD_MS) {
        Serial.print("Heart rate: ");
        Serial.print(bpm);
        Serial.print(" bpm / SpO2: ");
        Serial.print(spO2);
        Serial.println("%");

        // Mostrar datos en la pantalla LCD I2C
        lcd.clear();
        lcd.setCursor(0, 0);
        lcd.print("BPM : ");
        lcd.print(bpm);
        
        lcd.setCursor(0, 1);
        lcd.print("SpO2: ");
        lcd.print(spO2);
        lcd.print("%");

        tsLastReport = millis();
    }
}

