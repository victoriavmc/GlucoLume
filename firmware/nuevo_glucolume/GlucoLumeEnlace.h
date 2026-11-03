// GlucoLumeEnlace.h - Salida firmada de las lineas del firmware (H-05)
//
// Contiene lo que NO depende del hardware del sketch (pines, I2C, EEPROM): el estado de la clave y la clase LinkOut, que reparte cada byte a un
// "sumidero" (en el sketch: USB y Bluetooth) y, con clave, calcula la firma MIENTRAS se imprime y la agrega antes del fin de linea. Separado del
// .ino para poder compilar esta misma clase con el nucleo Arduino real y ejecutarla en un ATmega328P simulado (firmware/verificacion/firma/).
// Formato:  <linea>*<arranque>.<contador>.<etiqueta de 16 hex>   con etiqueta = SipHash-2-4("GL1|<arranque>.<contador>|<linea>").

#ifndef GLUCOLUME_ENLACE_H
#define GLUCOLUME_ENLACE_H

#include <Arduino.h>
#include "GlucoLumeSipHash.h"

#define LINK_MAGIC           0x4B4C
struct LinkAuth {
  uint16_t magic;
  uint8_t  key[16];
  uint32_t boot;                               // arranques con clave (se conserva si se borra la clave)
  uint8_t  check;                              // sobre magic y clave
};
static LinkAuth linkAuth;
static bool     linkOn = false;
static uint32_t lineCounter = 0;

static uint8_t linkCheck(const LinkAuth &a) {
  uint8_t c = 0xA7 ^ (uint8_t)(a.magic >> 8) ^ (uint8_t)a.magic;
  for (uint8_t i = 0; i < 16; i++) c = (uint8_t)((c << 1) | (c >> 7)) ^ a.key[i];
  return c;
}

// Salida unica hacia USB y Bluetooth (el sumidero). Con clave, calcula la firma MIENTRAS se imprime (sin buffer de linea: la SRAM del UNO no
// alcanza) y la agrega antes del fin de linea. Las lineas que se envian con print()/println() no cambian: solo se les suma
// "*arranque.contador.etiqueta".
class LinkOut : public Print {
public:
  explicit LinkOut(void (*sink)(uint8_t)) : sink_(sink) {}

  size_t write(uint8_t c) override {
    if (!linkOn) { sink_(c); return 1; }
    if (c == '\r') {
      if (open_) closeLine();
      sink_(c);
    } else if (c == '\n') {
      open_ = false;
      sink_(c);
    } else {
      if (!open_) openLine();
      glsip_byte(&mac_, c);
      sink_(c);
    }
    return 1;
  }

private:
  void (*sink_)(uint8_t);
  glsip_t mac_;
  bool    open_ = false;

  void putDec(uint32_t v) {
    char d[10]; uint8_t n = 0;
    do { d[n++] = (char)('0' + v % 10); v /= 10; } while (v);
    while (n) sink_((uint8_t)d[--n]);
  }
  void feedDec(uint32_t v) {
    char d[10]; uint8_t n = 0;
    do { d[n++] = (char)('0' + v % 10); v /= 10; } while (v);
    while (n) glsip_byte(&mac_, (uint8_t)d[--n]);
  }
  void openLine() {
    lineCounter++;
    glsip_init(&mac_, linkAuth.key);
    glsip_byte(&mac_, 'G'); glsip_byte(&mac_, 'L'); glsip_byte(&mac_, '1'); glsip_byte(&mac_, '|');
    feedDec(linkAuth.boot);
    glsip_byte(&mac_, '.');
    feedDec(lineCounter);
    glsip_byte(&mac_, '|');
    open_ = true;
  }
  void closeLine() {
    uint64_t tag = glsip_final(&mac_);
    open_ = false;
    sink_('*'); putDec(linkAuth.boot); sink_('.'); putDec(lineCounter); sink_('.');
    for (int8_t shift = 60; shift >= 0; shift -= 4) {
      uint8_t nibble = (uint8_t)((tag >> shift) & 0x0F);
      sink_((uint8_t)(nibble < 10 ? '0' + nibble : 'a' + nibble - 10));
    }
  }
};

#endif  // GLUCOLUME_ENLACE_H
