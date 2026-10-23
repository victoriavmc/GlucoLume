// Versión optimizada para ATmega328P/Arduino UNO: uso de PROGMEM/F() para liberar SRAM.
// Mantiene el protocolo USB/Bluetooth, el MAX30100, la señal PPG y la calibración EEPROM.
// No es una validación clínica de glucosa ni SpO2.
// GlucoLume - MODO DEMO INTEGRACION (Arduino UNO, MAX30100, LCD, USB, HC-05/HC-06).
// IMPORTANTE: GluExp_mgdl en modo DEMO es un valor sintetico, NO medido ni calculado
// con Beer-Lambert. Usarlo exclusivamente para comprobar comunicacion, API, BD y graficos.
// IndiceOptico SI proviene de muestras reales cuando SenalValida=1.
// Cuando existan referencias capilares, enviar DEMO,OFF y calibrar/validar.
// En la API/BD almacenar obligatoriamente Origen:DEMO y excluirlo de registros clinicos.
//
// Ley de Beer-Lambert:  A = log10(I0 / I) = e * c * l
//   A: absorbancia, e: coeficiente de extinción de la sustancia a esa longitud de onda,
//   c: concentración, l: camino óptico.
//
// Qué se mide aquí:
//   * El MAX30100 entrega la intensidad recibida de dos LED: rojo (~660 nm) e infrarrojo (~880 nm).
//   * La parte pulsátil (AC) de cada canal es la sangre arterial que entra con cada latido. Su absorbancia
//       dA = log10( (DC + AC/2) / (DC - AC/2) )
//     Aproximacion de variacion de absorbancia; no equivale a la absorbancia absoluta.
//   * Cociente de absorbancias pulsátiles; asumir mismo camino óptico efectivo es una simplificacion:
//       R = dA_rojo / dA_ir        ->   SpO2 aprox. = 110 - 25 * R (heuristica no validada)
//   * Indice experimental: x = dA_ir / dA_rojo (= 1/R) y una recta Gexp = a + b*x ajustada por minimos
//     cuadrados con referencias capilares (CAL). No hay sensibilidad/selectividad demostrada a glucosa.
//
// LIMITACION IMPORTANTE: los LED de 660 y 880 nm del MAX30100 no permiten aislar el efecto de la glucosa;
// el resultado Gexp es una correlacion ajustada con referencias, NO una medicion
// validada ni apta para decisiones clínicas ni de dosificación de insulina.
//
// Comandos (por USB a 115200 o por Bluetooth a 9600, terminados en salto de línea):
//   CAL,<mg/dL>   Registra un punto de calibracion con la lectura actual y valor del glucometro.
//                 Se exigen al menos 3 pares de referencia; no reemplaza validacion independiente.
//   CALCLR        Borra todos los puntos de calibración.
//   DEMO,ON       Activa el valor sintetico (solo pruebas de integracion).
//   DEMO,OFF      Desactiva el valor sintetico (GluExp_mgdl sera NA sin calibracion).
//   ID            Vuelve a informar el identificador persistente (GLUCOLUME,ID=<uuid>,...).
//   PPG,ON / PPG,OFF  Activa o desactiva el envio de la senal de pulso (ver abajo). Por defecto ON.
//   KEY,<32 hex>  (SOLO POR USB) Guarda en la EEPROM la clave de 128 bits que firma las lineas (ver "Firma de las lineas").
//   KEYCLR        (SOLO POR USB) Borra la clave: vuelve a enviar lineas sin firma.   KEY?   Informa si hay clave (nunca la muestra).
//
// Firma de las lineas (H-05, opcional): con una clave provisionada cada linea que sale por USB y Bluetooth termina en
//   *<arranque>.<contador>.<etiqueta de 16 hex>     (etiqueta = SipHash-2-4 de "GL1|<arranque>.<contador>|<linea>", 64 bits)
// y el puente (acquisition/bridge/linkauth.py) descarta lo que no verifica o repite un contador. <arranque> sube en cada reinicio (EEPROM).
// Con clave, las ordenes recibidas por Bluetooth se IGNORAN (salvo ID): el sistema solo recibe por ese canal, nunca lo usa para ordenar; asi un
// intruso emparejado no puede cambiar la calibracion ni el modo DEMO. NO cifra: las lecturas siguen viajando en claro.
//
// Senal de pulso (PPG), ademas de la linea de metricas de cada segundo:
//   PPG,<seq>,<mascara>,<v0>,<v1>,...,<v9>
//   Son muestras REALES del canal IR del MAX30100 (suavizadas y sin su componente continua), a 25 muestras/s
//   (cada 2 del muestreo de 50 Hz), en bloques de 10 (400 ms). <seq> cuenta bloques (0..255) y <mascara> marca con un
//   bit las muestras donde este firmware detecto un latido. NO es un ECG ni un valor clinico. Cada bloque ocupa
//   unos 60-80 bytes: junto con la linea de metricas cabe en un HC-06 a 9600 baudios (~25 % del enlace). El bloque
//   solo se envia con el dedo colocado y nunca en la misma vuelta del bucle que la linea de metricas.
//
// Librerias: solo LiquidCrystal I2C (externa); Wire, SoftwareSerial y EEPROM vienen con Arduino AVR.
// MAX30100 se controla por registros I2C: no incluir MAX30100.h ni PulseOximeter.

#include <Wire.h>
#include <SoftwareSerial.h>
#include <LiquidCrystal_I2C.h>
#include <EEPROM.h>
#include <math.h>
#include <avr/pgmspace.h>  // Constantes del protocolo y mensajes en Flash (SRAM libre).
#include "GlucoLumeEnlace.h"  // salida firmada de las lineas (usa GlucoLumeSipHash.h) (H-05)

// Pines Bluetooth: RX = Pin 10, TX = Pin 11
SoftwareSerial miBluetooth(10, 11);

// Objeto LCD (Dirección 0x27, 16 columnas x 2 filas)
LiquidCrystal_I2C lcd(0x27, 16, 2);

// Controlador minimo MAX30100 por I2C (direccion 0x57).
// Sin dependencia de las bibliotecas MAX30100 incompatibles entre si.
class MAX30100Raw {
public:
  bool begin() {
    Wire.begin();
    Wire.setClock(100000UL);  // Compatible con muchos adaptadores LCD PCF8574.
    uint8_t id = 0;
    if (!readRegister(0xFF, id) || id != 0x11) return false;

    if (!writeRegister(0x06, 0x40)) return false;  // Reset del dispositivo.
    delay(10);                                // Solo durante setup.
    if (!writeRegister(0x06, 0x03)) return false;  // SpO2 + HR: rojo e IR.
    if (!writeRegister(0x07, 0x43)) return false;  // Alta resolucion, 50 Hz, 1600 us.
    if (!writeRegister(0x09, 0x88)) return false;  // 27,1 mA en rojo e IR.
    return resetFIFO();
  }

  bool resetFIFO() {
    return writeRegister(0x02, 0) && writeRegister(0x03, 0) && writeRegister(0x04, 0);
  }

  // Disponibles (0..15). Si se desbordo el FIFO, reiniciar la ventana de analisis.
  bool available(uint8_t &count, bool &overflow) {
    uint8_t wr, rd, ov;
    if (!readRegister(0x02, wr) || !readRegister(0x04, rd) ||
        !readRegister(0x03, ov)) return false;
    overflow = (ov != 0);
    count = (wr - rd) & 0x0F;
    return true;
  }

  bool readRaw(uint16_t &ir, uint16_t &red) {
    Wire.beginTransmission(ADDRESS);
    Wire.write((uint8_t)0x05);
    if (Wire.endTransmission(false) != 0) return false;
    if (Wire.requestFrom(ADDRESS, (uint8_t)4) != 4) {
      while (Wire.available()) Wire.read();
      return false;
    }
    uint8_t irHi = Wire.read(), irLo = Wire.read();
    uint8_t redHi = Wire.read(), redLo = Wire.read();
    ir = ((uint16_t)irHi << 8) | irLo;
    red = ((uint16_t)redHi << 8) | redLo;
    return true;
  }

private:
  static const uint8_t ADDRESS = 0x57;

  bool writeRegister(uint8_t reg, uint8_t value) {
    Wire.beginTransmission(ADDRESS);
    Wire.write(reg);
    Wire.write(value);
    return Wire.endTransmission() == 0;
  }

  bool readRegister(uint8_t reg, uint8_t &value) {
    Wire.beginTransmission(ADDRESS);
    Wire.write(reg);
    if (Wire.endTransmission(false) != 0) return false;
    if (Wire.requestFrom(ADDRESS, (uint8_t)1) != 1) return false;
    value = Wire.read();
    return true;
  }
};

MAX30100Raw sensor;

// --- Parámetros ajustables ---------------------------------------------------------------------------------
#define REPORTING_PERIOD_MS 1000
// 1 = generar valor numerico SIMULADO cuando no hay referencia; 0 = exigir calibracion.
// Se inicia en modo DEMO solo para desarrollo y pruebas aisladas.
#define MODO_GLUCO_DEMO_INICIAL 1
static bool modoGlucoDemo = (MODO_GLUCO_DEMO_INICIAL != 0);

#define SAMPLE_RATE_HZ       50      // 50 Hz: mas margen para LCD I2C y HC-05 a 9600
#define SUBWIN_SAMPLES       50      // subventana de 1 s, coherente con 50 Hz
#define SUBWIN_PER_WINDOW    4       // ventana de análisis = 4 subventanas = 4 s
#define SMOOTH_ALPHA         0.25f   // filtro pasa-bajos exponencial de las muestras crudas
#define DC_ALPHA             0.010f  // seguidor lento del nivel DC (aprox. 2 s a 50 Hz)
#define BEAT_MIN_THR         3.0f    // umbral mínimo (cuentas) para detectar un latido

#define PPG_DECIM            2       // 50 Hz -> 25 muestras/s enviadas
#define PPG_CHUNK            10      // muestras por bloque (400 ms)
#define PPG_CLAMP            9999    // limita la muestra a +-9999 cuentas (maximo 5 caracteres)
static bool     ppgOn = true;
static int16_t  ppgBuf[PPG_CHUNK];
static uint8_t  ppgN = 0, ppgDecim = 0, ppgSeq = 0;
static uint16_t ppgMask = 0;
static bool     ppgReady = false;              // hay un bloque completo esperando ser enviado
static bool     ppgBeat = false;               // latido detectado desde la ultima muestra enviada

#define FINGER_MIN_RAW       10000   // por debajo de esto se considera que no hay dedo
#define FINGER_MAX_RAW       65000   // descartar lecturas saturadas
#define MIN_PERFUSION        0.002f  // AC/DC mínimo (0,2 %) para aceptar la ventana
#define MAX_PERFUSION        0.20f   // AC/DC máximo (20 %); por encima es movimiento
#define R_MIN                0.2f    // rango plausible de R = dA_rojo / dA_ir
#define R_MAX                3.0f

#define GLU_MIN_MGDL         20.0f   // fuera de este rango el resultado se descarta
#define GLU_MAX_MGDL         600.0f
#define CAL_MIN              3       // minimo tecnico para permitir ajuste experimental
#define CAL_MAX              8       // puntos de calibración guardados (EEPROM)
#define CAL_MAGIC            0x474C
#define CAL_FRESH_MS         8000UL  // CAL solo acepta una lectura de los últimos 8 s

// Corriente LED establecida por el registro 0x09 (0x88 = 27,1 mA en ambos canales).

// --- Estado del análisis ---------------------------------------------------------------------------------
static bool     fingerOn = false;
static uint32_t lastSampleMs = 0;
static uint16_t samplesThisReport = 0;
static bool     primed = false;
static float    fIr, fRed, dcSlow;
static float    sumIr, sumRed, minIr, maxIr, minRed, maxRed;
static uint8_t  nSub = 0, subCount = 0;
static float    winDcIr, winPpIr, winDcRed, winPpRed;
static float    lastPpIr = 0;

static uint32_t tick = 0;                      // muestras procesadas (reloj del sensor, 10 ms cada una)
static uint32_t lastBeatTick = 0;
static bool     armed = false;
static uint16_t ibi[4];                        // últimos intervalos entre latidos, en muestras
static uint8_t  ibiN = 0, ibiHead = 0;

static float    bpm = 0;
static float    spo2 = 0;
static bool     spo2Valid = false;
static float    lastX = 0;                     // x = dA_ir / dA_rojo de la última ventana válida
static uint32_t lastXMs = 0;
static bool     xValid = false;
static float    glucose = 0;
static bool     gluValid = false;

// --- Calibración (se guarda en EEPROM) ---------------------------------------------------------------------
struct CalData {
  uint16_t magic;
  uint8_t  n;
  float    x[CAL_MAX];
  float    g[CAL_MAX];
};
// Tipo del identificador propio: se define antes de la primera funcion para que el prototipo que genera Arduino lo conozca.
struct DevId {
  uint16_t magic;
  uint8_t  bytes[16];
  uint8_t  check;
};
static CalData cal;
static bool    calOk = false;                  // hay recta ajustada
static float   calA = 0, calB = 0;             // G = calA + calB * x

#define CMD_MAX_BT           23              // las ordenes por Bluetooth son cortas
#define CMD_MAX_USB          39              // KEY,<32 hex> llega solo por USB
static char pcBuf[CMD_MAX_USB + 1], btBuf[CMD_MAX_BT + 1];
static uint8_t pcLen = 0, btLen = 0;

// --- Firma de las lineas (H-05) ------------------------------------------------------------------------------
// La clave (128 bits) se provisiona UNA vez por USB (KEY,<32 hex>) y vive en la EEPROM; nunca se imprime ni se repite por Bluetooth. Sin clave todo
// funciona como antes (lineas sin firma). El contador de arranque sube en cada reinicio y se guarda: asi (arranque, contador) nunca se repite.
// La clase de salida (LinkOut) y el estado de la clave estan en GlucoLumeEnlace.h.
#define LINK_EEPROM_ADDR     130             // despues de DevId (100..118)

static void saveLinkAuth() { linkAuth.check = linkCheck(linkAuth); EEPROM.put(LINK_EEPROM_ADDR, linkAuth); }

static void loadLinkAuth() {
  EEPROM.get(LINK_EEPROM_ADDR, linkAuth);
  linkOn = (linkAuth.magic == LINK_MAGIC && linkAuth.check == linkCheck(linkAuth));
  if (!linkOn) { memset(&linkAuth, 0, sizeof(linkAuth)); return; }
  linkAuth.boot++;                             // un arranque mas: las lineas de esta sesion llevan un valor nuevo
  saveLinkAuth();
}

static void putBoth(uint8_t c) { Serial.write(c); miBluetooth.write(c); }
static LinkOut out(putBoth);                   // unica salida de lineas: firma (si hay clave) y reparte a USB y Bluetooth

// --- Utilidades ----------------------------------------------------------------------------------------------
// Respuestas dinámicas (buffer RAM) y constantes residentes en Flash.
static void say(const char *msg) {
  out.println(msg);
}
static void say(const __FlashStringHelper *msg) {
  out.println(msg);
}

static void lcdRow(uint8_t row, const char *text) {
  lcd.setCursor(0, row);
  uint8_t i = 0;
  for (; i < 16 && text[i]; i++) lcd.print(text[i]);
  for (; i < 16; i++) lcd.print(' ');
}
// Sobrecarga para textos fijos guardados en Flash; no crea buffer temporal de 17 bytes.
static void lcdRow(uint8_t row, const __FlashStringHelper *text) {
  lcd.setCursor(0, row);
  PGM_P p = reinterpret_cast<PGM_P>(text);
  uint8_t i = 0;
  for (; i < 16; i++) {
    const char c = pgm_read_byte(p + i);
    if (!c) break;
    lcd.write((uint8_t)c);
  }
  for (; i < 16; i++) lcd.write((uint8_t)' ');
}

// Absorbancia de la componente pulsátil. dc = nivel medio, pp = amplitud pico a pico.
static bool pulsatileAbsorbance(float dc, float pp, float &dA) {
  float half = pp * 0.5f;
  if (dc <= 0 || half <= 0 || half >= dc) return false;
  dA = log10((dc + half) / (dc - half));
  return true;
}

// Serie sintetica determinista: 105.0, 107.0, ... 121.0, cada 10 s.
// No usa ni afirma medir glucosa; permite evaluar persistencia/graficos temporales.
static float valorGlucosaDemo() {
  return 105.0f + 2.0f * ((millis() / 10000UL) % 9UL);
}

// --- Calibración ------------------------------------------------------------------------------------------
static void fitCalibration() {
  calOk = false;
  if (cal.n < CAL_MIN) return;
  float xm = 0, gm = 0;
  for (uint8_t i = 0; i < cal.n; i++) { xm += cal.x[i]; gm += cal.g[i]; }
  xm /= cal.n; gm /= cal.n;
  float sxx = 0, sxy = 0;
  for (uint8_t i = 0; i < cal.n; i++) {
    sxx += (cal.x[i] - xm) * (cal.x[i] - xm);
    sxy += (cal.x[i] - xm) * (cal.g[i] - gm);
  }
  if (sxx < 1e-4f) return;                     // todos los puntos casi iguales: no hay pendiente fiable
  calB = sxy / sxx;
  calA = gm - calB * xm;
  calOk = true;
}

static void loadCalibration() {
  EEPROM.get(0, cal);
  if (cal.magic != CAL_MAGIC || cal.n > CAL_MAX) {
    memset(&cal, 0, sizeof(cal));
    cal.magic = CAL_MAGIC;
  }
  for (uint8_t i = 0; i < cal.n; i++) {
    if (!isfinite(cal.x[i]) || !isfinite(cal.g[i]) || cal.g[i] < GLU_MIN_MGDL || cal.g[i] > GLU_MAX_MGDL) {
      memset(&cal, 0, sizeof(cal));
      cal.magic = CAL_MAGIC;
      break;
    }
  }
  fitCalibration();
}

static void saveCalibration() { EEPROM.put(0, cal); }

// --- Identidad persistente del dispositivo (EEPROM) ----------------------------------------------------------
// Cada Arduino genera UNA vez un identificador aleatorio (UUID v4) y lo conserva en EEPROM: no depende del puerto COM,
// del medio (USB / Bluetooth), de la computadora ni del modulo HC-05/HC-06. Lo informa con el mismo formato de
// identificacion del protocolo GlucoLume:   GLUCOLUME,ID=<uuid>,SENSOR=MAX30100,FW=<version>,SR=<Hz>
// al arrancar, ante el comando ID y cada ID_PERIOD_MS (por Bluetooth no hay reinicio al abrir el puerto). Es una linea
// aparte de la de metricas: no cambia el formato de medicion. Borrar la EEPROM o cargar un firmware que la reescriba
// genera otro identificador (otro dispositivo para el inventario).
#define FW_VERSION           "1.2.0"
#define ID_EEPROM_ADDR       100             // despues de CalData (67 bytes desde la direccion 0)
#define ID_MAGIC             0x4944
#define ID_PERIOD_MS         10000UL
static DevId devId;
static char  devIdText[37];
static uint32_t tsLastId = 0;

static uint8_t idCheck(const DevId &d) {
  uint8_t c = 0x5A;
  for (uint8_t i = 0; i < 16; i++) c = (uint8_t)((c << 1) | (c >> 7)) ^ d.bytes[i];
  return c;
}

// El UNO no tiene generador de numeros aleatorios por hardware: se mezcla el ruido de entradas analogicas sin conectar
// (A0..A3; A4/A5 son del bus I2C) con la temporizacion. Solo se usa la primera vez.
static void generateId() {
  uint32_t h = 2166136261UL ^ micros();
  for (uint8_t i = 0; i < 16; i++) {
    uint8_t acc = 0;
    for (uint8_t k = 0; k < 8; k++) {
      acc = (uint8_t)((acc << 1) | (analogRead(A0 + (k & 3)) & 1));
      delayMicroseconds(37 + (micros() & 0x1F));
    }
    h = (h ^ acc ^ (micros() & 0xFF)) * 16777619UL;
    devId.bytes[i] = (uint8_t)(h >> 11) ^ acc;
  }
  devId.bytes[6] = (devId.bytes[6] & 0x0F) | 0x40;  // UUID version 4
  devId.bytes[8] = (devId.bytes[8] & 0x3F) | 0x80;
}

static void loadIdentity() {
  EEPROM.get(ID_EEPROM_ADDR, devId);
  if (devId.magic != ID_MAGIC || devId.check != idCheck(devId)) {
    generateId();
    devId.magic = ID_MAGIC;
    devId.check = idCheck(devId);
    EEPROM.put(ID_EEPROM_ADDR, devId);
  }
  static const char HEX_DIGITS[] = "0123456789abcdef";
  uint8_t pos = 0;
  for (uint8_t i = 0; i < 16; i++) {
    if (i == 4 || i == 6 || i == 8 || i == 10) devIdText[pos++] = '-';
    devIdText[pos++] = HEX_DIGITS[devId.bytes[i] >> 4];
    devIdText[pos++] = HEX_DIGITS[devId.bytes[i] & 0x0F];
  }
  devIdText[pos] = 0;
}

static void sendIdentity() {
  Print *ports[1] = { &out };  // una sola salida: firma (si hay clave) y reparte a USB y Bluetooth
  for (uint8_t i = 0; i < 1; i++) {
    ports[i]->print(F("GLUCOLUME,ID="));
    ports[i]->print(devIdText);
    ports[i]->print(F(",SENSOR=MAX30100,FW="));
    ports[i]->print(F(FW_VERSION));
    ports[i]->print(F(",SR="));
    ports[i]->println(SAMPLE_RATE_HZ);
  }
  tsLastId = millis();
}

static bool hexByte(const char *p, uint8_t &out8) {
  uint8_t v = 0;
  for (uint8_t i = 0; i < 2; i++) {
    char c = p[i]; uint8_t n;
    if (c >= '0' && c <= '9') n = c - '0';
    else if (c >= 'a' && c <= 'f') n = c - 'a' + 10;
    else if (c >= 'A' && c <= 'F') n = c - 'A' + 10;
    else return false;
    v = (uint8_t)((v << 4) | n);
  }
  out8 = v;
  return true;
}

static void handleCommand(char *line, bool fromUsb) {
  if (strcmp_P(line, PSTR("ID")) == 0) { sendIdentity(); return; }   // vuelve a informar el identificador
  // Con clave, el canal Bluetooth solo SALE (H-05): una orden recibida por ahi no la envia nadie legitimo, asi que se ignora.
  if (linkOn && !fromUsb) { say(F("CMD:SOLO_POR_USB")); return; }
  // Provision de la clave: solo por USB (acceso fisico). Nunca se muestra, ni se devuelve, ni se reenvia por Bluetooth.
  if (strncmp_P(line, PSTR("KEY,"), 4) == 0) {
    uint8_t key[16]; bool good = fromUsb && strlen(line) == 36;
    for (uint8_t i = 0; good && i < 16; i++) good = hexByte(line + 4 + 2 * i, key[i]);
    memset(line, 0, strlen(line));                                    // la clave no queda en el buffer de ordenes
    if (!good) { memset(key, 0, sizeof(key)); say(F("KEY:ERROR,se espera KEY,<32 hex> por USB")); return; }
    memcpy(linkAuth.key, key, 16); memset(key, 0, sizeof(key));
    linkAuth.magic = LINK_MAGIC;
    linkAuth.boot++;                                                  // epoca nueva: el puente ve un (arranque, contador) mayor
    lineCounter = 0;
    saveLinkAuth();
    linkOn = true;
    say(F("KEY:OK"));
    return;
  }
  if (strcmp_P(line, PSTR("KEYCLR")) == 0) {
    if (!fromUsb) { say(F("KEY:SOLO_POR_USB")); return; }
    say(F("KEY:BORRADA"));                                            // se avisa firmada, y recien despues se apaga la firma
    memset(linkAuth.key, 0, sizeof(linkAuth.key));
    linkAuth.magic = 0;
    saveLinkAuth();
    linkOn = false;
    return;
  }
  if (strcmp_P(line, PSTR("KEY?")) == 0) {
    if (linkOn) { out.print(F("KEY:ACTIVA,ARRANQUE=")); out.println(linkAuth.boot); }
    else say(F("KEY:SIN_CLAVE"));
    return;
  }
  char msg[48];
  if (strcmp_P(line, PSTR("DEMO,ON")) == 0) {
    modoGlucoDemo = true;
    say(F("MODO:DEMO_ACTIVO"));
  } else if (strcmp_P(line, PSTR("DEMO,OFF")) == 0) {
    modoGlucoDemo = false;
    say(F("MODO:DEMO_DESACTIVADO"));
  } else if (strcmp_P(line, PSTR("PPG,ON")) == 0) {
    ppgOn = true;
    say(F("MODO:PPG_ACTIVO"));
  } else if (strcmp_P(line, PSTR("PPG,OFF")) == 0) {
    ppgOn = false;
    ppgN = 0; ppgMask = 0; ppgReady = false;
    say(F("MODO:PPG_DESACTIVADO"));
  } else if (strcmp_P(line, PSTR("CALCLR")) == 0) {
    memset(&cal, 0, sizeof(cal));
    cal.magic = CAL_MAGIC;
    saveCalibration();
    fitCalibration();
    say(F("CAL:BORRADA"));
  } else if (strncmp_P(line, PSTR("CAL,"), 4) == 0) {
    float ref = atof(line + 4);
    if (ref < GLU_MIN_MGDL || ref > GLU_MAX_MGDL) {
      say(F("CAL:ERROR,valor fuera de rango"));
    } else if (!fingerOn || !xValid || millis() - lastXMs > CAL_FRESH_MS) {
      say(F("CAL:ERROR,sin lectura valida reciente (dedo quieto)"));
    } else {
      if (cal.n == CAL_MAX) {                  // lleno: descarta el más antiguo
        for (uint8_t i = 1; i < CAL_MAX; i++) { cal.x[i - 1] = cal.x[i]; cal.g[i - 1] = cal.g[i]; }
        cal.n--;
      }
      cal.x[cal.n] = lastX;
      cal.g[cal.n] = ref;
      cal.n++;
      saveCalibration();
      fitCalibration();
      snprintf_P(msg, sizeof(msg), PSTR("CAL:OK,puntos=%u,ajuste=%s"), cal.n, calOk ? "SI" : "NO");
      say(msg);
    }
  }
}

// Acumula bytes de una línea; al recibir '\n' ejecuta el comando si lo es. No consume el byte: el puente
// serial de abajo sigue reenviando todo igual que antes (para configurar el HC-06 con comandos AT).
static void feedCommandByte(char c, char *buf, uint8_t &len, uint8_t maxLen, bool fromUsb) {
  if (c == '\n' || c == '\r') {
    if (len > 0) { buf[len] = 0; handleCommand(buf, fromUsb); }
    len = 0;
  } else if (len < maxLen) {
    buf[len++] = c;
  } else {
    len = 0;                                   // línea demasiado larga: no es un comando
  }
}

// --- Procesamiento de señal --------------------------------------------------------------------------------
static void resetAnalysis() {
  primed = false;
  nSub = 0; subCount = 0;
  winDcIr = winPpIr = winDcRed = winPpRed = 0;
  lastPpIr = 0;
  armed = false; lastBeatTick = 0; ibiN = 0; ibiHead = 0;
  bpm = 0; spo2Valid = false; xValid = false; gluValid = false;
  ppgN = 0; ppgMask = 0; ppgDecim = 0; ppgReady = false; ppgBeat = false;  // sin dedo no hay senal: no se arrastra un bloque a medias
}

// Guarda 1 de cada PPG_DECIM muestras de la senal IR sin continua. El bloque completo lo envia loop() (no se transmite aqui
// para no demorar la lectura del FIFO del sensor).
static void ppgPush(float ac) {
  if (!ppgOn || ppgReady) return;
  if (++ppgDecim < PPG_DECIM) return;
  ppgDecim = 0;
  long v = lroundf(ac);
  if (v > PPG_CLAMP) v = PPG_CLAMP;
  if (v < -PPG_CLAMP) v = -PPG_CLAMP;
  ppgBuf[ppgN] = (int16_t)v;
  if (ppgBeat) { ppgMask |= (uint16_t)(1u << ppgN); ppgBeat = false; }
  if (++ppgN >= PPG_CHUNK) ppgReady = true;
}

static void sendPpg() {
  Print *ports[1] = { &out };  // una sola salida: firma (si hay clave) y reparte a USB y Bluetooth
  for (uint8_t i = 0; i < 1; i++) {
    ports[i]->print(F("PPG,"));
    ports[i]->print(ppgSeq);
    ports[i]->print(',');
    ports[i]->print(ppgMask);
    for (uint8_t k = 0; k < PPG_CHUNK; k++) {
      ports[i]->print(',');
      ports[i]->print(ppgBuf[k]);
    }
    ports[i]->println();
  }
  ppgSeq++;
  ppgN = 0; ppgMask = 0; ppgReady = false;
}

static void detectBeat(float ac) {
  float h = 0.2f * lastPpIr;
  if (h < BEAT_MIN_THR) h = BEAT_MIN_THR;
  if (ac < -h) {
    armed = true;
  } else if (armed && ac > h) {
    armed = false;
    uint32_t dt = tick - lastBeatTick;
    if (lastBeatTick == 0 || dt >= (SAMPLE_RATE_HZ * 3UL / 10UL)) {  // >=300 ms (max. 200 lpm)
      if (lastBeatTick != 0 && dt <= (SAMPLE_RATE_HZ * 3UL / 2UL)) { // <=1500 ms (min. 40 lpm)
        ibi[ibiHead] = (uint16_t)dt;
        ibiHead = (ibiHead + 1) & 3;
        if (ibiN < 4) ibiN++;
        uint32_t sum = 0;
        for (uint8_t i = 0; i < ibiN; i++) sum += ibi[i];
        bpm = 60.0f * SAMPLE_RATE_HZ * ibiN / sum;
      }
      lastBeatTick = tick;
      ppgBeat = true;                            // el latido queda marcado en el bloque PPG que se esta armando
    }
  }
}

static void closeWindow() {
  float dcIr = winDcIr / SUBWIN_PER_WINDOW, ppIr = winPpIr / SUBWIN_PER_WINDOW;
  float dcRed = winDcRed / SUBWIN_PER_WINDOW, ppRed = winPpRed / SUBWIN_PER_WINDOW;
  winDcIr = winPpIr = winDcRed = winPpRed = 0;
  subCount = 0;

  if (dcIr <= 0 || dcRed <= 0) {
    spo2Valid = false; xValid = false; gluValid = false;
    return;
  }
  float pIr = ppIr / dcIr, pRed = ppRed / dcRed;
  float dAir, dAred;
  spo2Valid = false; xValid = false; gluValid = false;
  if (pIr < MIN_PERFUSION || pIr > MAX_PERFUSION || pRed < MIN_PERFUSION || pRed > MAX_PERFUSION) return;
  if (!pulsatileAbsorbance(dcIr, ppIr, dAir) || !pulsatileAbsorbance(dcRed, ppRed, dAred)) return;

  float R = dAred / dAir;
  if (R < R_MIN || R > R_MAX) return;

  spo2 = 110.0f - 25.0f * R;
  if (spo2 > 100.0f) spo2 = 100.0f;
  if (spo2 < 0.0f) spo2 = 0.0f;
  spo2Valid = true;

  lastX = dAir / dAred;
  lastXMs = millis();
  xValid = true;

  if (calOk) {
    float g = calA + calB * lastX;
    if (isfinite(g) && g >= GLU_MIN_MGDL && g <= GLU_MAX_MGDL) { glucose = g; gluValid = true; }
  }
}

static void closeSubWindow() {
  float dcIr = sumIr / SUBWIN_SAMPLES, dcRed = sumRed / SUBWIN_SAMPLES;
  float ppIr = maxIr - minIr, ppRed = maxRed - minRed;
  winDcIr += dcIr; winPpIr += ppIr;
  winDcRed += dcRed; winPpRed += ppRed;
  lastPpIr = ppIr;
  nSub = 0;
  if (++subCount >= SUBWIN_PER_WINDOW) closeWindow();
}

static void processSample(uint16_t rawIr, uint16_t rawRed) {
  tick++;
  if (samplesThisReport < 65535U) samplesThisReport++;
  lastSampleMs = millis();
  if (rawIr < FINGER_MIN_RAW || rawIr > FINGER_MAX_RAW || rawRed > FINGER_MAX_RAW) {
    if (fingerOn) resetAnalysis();
    fingerOn = false;
    return;
  }
  fingerOn = true;

  if (!primed) {
    fIr = rawIr; fRed = rawRed; dcSlow = rawIr;
    sumIr = sumRed = 0;
    minIr = minRed = 65535.0f; maxIr = maxRed = 0;
    nSub = 0; subCount = 0;
    primed = true;
  }
  fIr  += SMOOTH_ALPHA * (rawIr  - fIr);
  fRed += SMOOTH_ALPHA * (rawRed - fRed);
  dcSlow += DC_ALPHA * (fIr - dcSlow);
  detectBeat(fIr - dcSlow);
  ppgPush(fIr - dcSlow);

  if (nSub == 0) {
    sumIr = sumRed = 0;
    minIr = minRed = 65535.0f; maxIr = maxRed = 0;
  }
  sumIr += fIr; sumRed += fRed;
  if (fIr < minIr) minIr = fIr;
  if (fIr > maxIr) maxIr = fIr;
  if (fRed < minRed) minRed = fRed;
  if (fRed > maxRed) maxRed = fRed;
  if (++nSub >= SUBWIN_SAMPLES) closeSubWindow();
}

// --- Programa ------------------------------------------------------------------------------------------------
uint32_t tsLastReport = 0;

void setup() {
  // Comunicación con PC a 115200 para fluidez del MAX30100
  Serial.begin(115200);

  // Comunicación con Bluetooth a 9600
  miBluetooth.begin(9600);

  // Inicializar LCD
  lcd.init();
  lcd.backlight();
  lcd.setCursor(0, 0);
  lcd.print(F("Iniciando..."));

  // Inicializar sensor (lectura cruda de rojo e infrarrojo)
  if (!sensor.begin()) {
    lcd.clear();
    lcd.print(F("Error MAX30100"));
    Serial.println(F("ERROR: MAX30100 no detectado por I2C (0x57). Revisar cableado/alimentacion."));
    for (;;); // Se detiene aqui si falla el sensor.
  }
  loadCalibration();
  loadIdentity();
  loadLinkAuth();

  lcd.clear();
  Serial.println(F("Sistema listo."));
  Serial.println(F("Comandos: DEMO,ON | DEMO,OFF | CAL,<mg/dL> | CALCLR"));
  if (modoGlucoDemo) Serial.println(F("AVISO: GLUCOSA DEMO SINTETICA. NO ES MEDICION."));
  if (!calOk) Serial.println(F("Indice experimental SIN CALIBRAR: use CAL con glucometro (minimo 3 puntos)."));
  Serial.println(F("ADVERTENCIA: Gexp NO es un valor clinico de glucosa."));
  Serial.println(linkOn ? F("Enlace FIRMADO (SipHash-2-4). KEY? informa el estado; la clave no se muestra.")
                        : F("AVISO: enlace SIN firmar (sin clave). Provisionar con KEY,<32 hex> por USB."));
  sendIdentity();
}

void loop() {
  // 1. Lectura de FIFO MAX30100 (16 muestras = 320 ms a 50 Hz)
  uint8_t n = 0;
  bool overflow = false;
  if (!sensor.available(n, overflow) || overflow) {
    sensor.resetFIFO();  // Perdida de muestras o problema I2C: evitar procesar datos incoherentes.
    fingerOn = false;
    resetAnalysis();
  } else {
    for (uint8_t i = 0; i < n; ++i) {
      uint16_t ir, red;
      if (!sensor.readRaw(ir, red)) {
        fingerOn = false;
        resetAnalysis();
        sensor.resetFIFO();
        break;
      }
      processSample(ir, red);
    }
  }

  // 2. Transmisión de datos cada 1 segundo (sin bloquear la lectura I2C)
  bool reportedNow = false;
  if (millis() - tsLastReport > REPORTING_PERIOD_MS) {
    reportedNow = true;
    if (lastSampleMs == 0 || millis() - lastSampleMs > 1000UL) {
      fingerOn = false;
      resetAnalysis();
    }
    if (lastBeatTick != 0 && tick - lastBeatTick > 3UL * SAMPLE_RATE_HZ) bpm = 0;  // sin latidos hace 3 s
    float outBpm = fingerOn ? bpm : 0;
    float outSpo2 = (fingerOn && spo2Valid) ? spo2 : 0;
    bool outGlu = fingerOn && gluValid;
    bool outGluDemo = modoGlucoDemo;
    // En modo DEMO el numero es deliberadamente sintetico incluso si falta el dedo.
    // BPM y SpO2 siguen dependiendo del sensor. La API DEBE registrar Origen=DEMO.
    float outGlucosa = outGluDemo ? valorGlucosaDemo() : glucose;

    // --- Envío por Serial USB (PC / Serial Plotter) y Bluetooth (Celular / App) ---
    Print *ports[1] = { &out };  // una sola salida: firma (si hay clave) y reparte a USB y Bluetooth
    for (uint8_t i = 0; i < 1; i++) {
      ports[i]->print(F("BPM:"));
      ports[i]->print(outBpm);
      ports[i]->print(F(",SpO2:"));
      ports[i]->print(outSpo2);
      ports[i]->print(F(",GluExp_mgdl:"));
      if (outGluDemo)      ports[i]->print(outGlucosa, 1);
      else if (outGlu)     ports[i]->print(outGlucosa, 1);
      else                 ports[i]->print(F("NA"));
      ports[i]->print(F(",Origen:"));
      if (outGluDemo)      ports[i]->print(F("DEMO"));
      else if (outGlu)     ports[i]->print(F("EXPERIMENTAL"));
      else                 ports[i]->print(F("SIN_CALIBRAR"));
      ports[i]->print(F(",IndiceOptico:"));
      if (fingerOn && xValid) ports[i]->print(lastX, 5);
      else ports[i]->print(F("NA"));
      ports[i]->print(F(",SenalValida:"));
      ports[i]->print((fingerOn && xValid) ? 1 : 0);
      ports[i]->print(F(",Dedo:"));
      ports[i]->print(fingerOn ? 1 : 0);
      ports[i]->print(F(",Muestras:"));
      ports[i]->println(samplesThisReport);
    }

    // --- Actualización Pantalla LCD ---
    char row[17];
    if (!fingerOn) {
      lcdRow(0, F("Coloque el dedo"));
      if (outGluDemo) {
        snprintf_P(row, sizeof(row), PSTR("DEMO:%d mg/dL"), (int)(outGlucosa + 0.5f));
        lcdRow(1, row);
      } else lcdRow(1, calOk ? F("Gexp: --") : F("Sin calibracion"));
    } else {
      char b[6], s[6];
      if (outBpm > 0)   snprintf(b, sizeof(b), "%d", (int)(outBpm + 0.5f));  else { b[0] = '-'; b[1] = '-'; b[2] = 0; }
      if (outSpo2 > 0)  snprintf(s, sizeof(s), "%d", (int)(outSpo2 + 0.5f)); else { s[0] = '-'; s[1] = '-'; s[2] = 0; }
      snprintf_P(row, sizeof(row), PSTR("BPM:%s SpO2:%s%%"), b, s);
      lcdRow(0, row);
      if (outGluDemo) {
        snprintf_P(row, sizeof(row), PSTR("DEMO:%d mg/dL"), (int)(outGlucosa + 0.5f));
        lcdRow(1, row);
      } else if (!calOk) lcdRow(1, F("Sin calibracion"));
      else if (outGlu) {
        snprintf_P(row, sizeof(row), PSTR("Gexp~%d mg/dL"), (int)(glucose + 0.5f));
        lcdRow(1, row);
      } else lcdRow(1, F("Gexp: midiendo"));
    }

    samplesThisReport = 0;
    tsLastReport = millis();
  }

  // 2b. Bloque de senal PPG (solo con dedo, y nunca en la misma vuelta que la linea de metricas: evita desbordar el FIFO)
  if (ppgReady && !reportedNow) {
    if (fingerOn) sendPpg();
    else { ppgN = 0; ppgMask = 0; ppgReady = false; }
  } else if (!reportedNow && millis() - tsLastId >= ID_PERIOD_MS) {
    sendIdentity();  // linea de identificacion aparte de la de metricas
  }

  // 3. Puente Serial bidireccional (Comandos manuales PC <-> Bluetooth) + interpretación de CAL / CALCLR
  while (miBluetooth.available() > 0) {
    char c = miBluetooth.read();
    Serial.write(c);
    feedCommandByte(c, btBuf, btLen, CMD_MAX_BT, false);
  }

  while (Serial.available() > 0) {
    char c = Serial.read();
    feedCommandByte(c, pcBuf, pcLen, CMD_MAX_USB, true);
    // La linea KEY,<clave> no se reenvia por Bluetooth: ya se ejecuto y el buffer quedo en cero (pcLen = 0), o aun se esta acumulando y empieza
    // con "KEY,". Todo lo demas se reenvia como siempre (configuracion AT del HC-06 desde la PC).
    bool secret = pcLen >= 4 && memcmp_P(pcBuf, PSTR("KEY,"), 4) == 0;
    if (!secret) miBluetooth.write(c);
  }
}
