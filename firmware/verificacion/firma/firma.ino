// Verificacion de la firma de lineas (H-05) en un ATmega328P SIMULADO. Compila la clase REAL (GlucoLumeEnlace.h) con el nucleo Arduino y emite lineas
// al estilo del firmware hacia un buffer en RAM; verificar_firma.sh lo ejecuta en simavr y comprueba cada linea con el puente (linkauth.py).
// NO es parte del firmware que se sube a la placa.
#include <avr/sleep.h>
#include <avr/interrupt.h>
#include "GlucoLumeEnlace.h"  // se encuentra por -I (verificar_firma.sh): el builder copia el sketch a otra carpeta

volatile uint8_t g_out[900] __attribute__((used));
volatile uint16_t g_len __attribute__((used)) = 0;
volatile uint32_t g_cycles_marker = 0;

static void sink(uint8_t c) { uint16_t n = g_len; if (n < sizeof(g_out)) { g_out[n] = c; g_len = n + 1; } }
static LinkOut out(sink);

void setup() {
  static const uint8_t KEY[16] = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15};
  out.println(F("Sistema listo."));                       // sin clave: sale tal cual

  memcpy(linkAuth.key, KEY, 16); linkAuth.magic = LINK_MAGIC; linkAuth.boot = 3; linkOn = true; lineCounter = 0;
  out.print(F("BPM:")); out.print(76.43f); out.print(F(",SpO2:")); out.print(99.65f);   // como la linea de metricas del firmware
  out.print(F(",GluExp_mgdl:")); out.print(117.0f, 1); out.print(F(",Origen:DEMO,IndiceOptico:")); out.print(2.41492f, 5);
  out.print(F(",SenalValida:")); out.print(1); out.print(F(",Dedo:")); out.print(1); out.print(F(",Muestras:")); out.println(58);
  out.print(F("PPG,")); out.print(7); out.print(','); out.print(5);                       // bloque PPG con valores negativos
  for (uint8_t k = 0; k < 10; k++) { out.print(','); out.print((int16_t)(k * 37 - 150)); }
  out.println();
  out.println("MODO:DEMO_ACTIVO");                                                          // mensaje de estado
  out.print(F("GLUCOLUME,ID=0123,SENSOR=MAX30100,FW=1.2.0,SR=")); out.println(50);
  lineCounter = 4294967290UL;                                                               // contador cerca del limite de 32 bits
  out.println(F("X"));
  linkOn = false;                                                                           // KEYCLR: vuelve a salir sin firma
  out.println(F("KEY:BORRADA"));
  cli(); sleep_enable(); sleep_cpu();
}

void loop() {}
