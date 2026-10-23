// GlucoLumeSipHash.h - SipHash-2-4 incremental (clave de 128 bits, etiqueta de 64 bits) para firmar las lineas del firmware (H-05).
//
// C puro (solo stdint): lo usa el firmware del Arduino UNO y se compila TAMBIEN en el equipo de desarrollo para comprobar, contra los vectores
// oficiales del paper y contra la implementacion en Python del puente (acquisition/bridge/linkauth.py), que las dos dan la misma etiqueta.
//
// Por que SipHash-2-4 y no HMAC-SHA-256: en un ATmega328P (8 bits, 2 KB de RAM, 16 MHz) SipHash firma una linea de ~110 bytes en un par de
// milisegundos con ~50 bytes de estado; HMAC-SHA-256 necesita bloques de 64 bytes, mucha mas RAM/flash y decenas de ms por linea. SipHash-2-4
// es una funcion pseudoaleatoria con clave pensada para autenticar mensajes cortos: con una clave secreta de 128 bits, falsificar una etiqueta de
// 64 bits exige adivinarla (probabilidad 2^-64 por intento, y cada intento es una linea que el puente descarta y cuenta). NO da confidencialidad
// (las lineas viajan en claro) ni es un MAC estandarizado como HMAC: es una decision de ingenieria para este hardware, documentada en
// docs/SEGURIDAD.md.
//
// Uso:  glsip_t s; glsip_init(&s, key); glsip_byte(&s, b); ...; uint64_t tag = glsip_final(&s);

#ifndef GLUCOLUME_SIPHASH_H
#define GLUCOLUME_SIPHASH_H

#include <stdint.h>

typedef struct {
  uint64_t v0, v1, v2, v3;
  uint8_t  buf[8];   // palabra parcial
  uint8_t  n;        // bytes en buf
  uint8_t  total;    // longitud total mod 256 (SipHash solo usa el byte bajo)
} glsip_t;

#define GLSIP_ROTL(x, b) (((x) << (b)) | ((x) >> (64 - (b))))

// Una sola copia de la ronda (no en linea): en el ATmega328P cada rotacion de 64 bits son llamadas a libgcc, y expandir la ronda 8 veces costaba
// ~3 KB de flash de mas.
#if defined(__GNUC__)
#define GLSIP_NOINLINE __attribute__((noinline))
#else
#define GLSIP_NOINLINE
#endif

static GLSIP_NOINLINE void glsip_round(glsip_t *s) {
  s->v0 += s->v1; s->v1 = GLSIP_ROTL(s->v1, 13); s->v1 ^= s->v0; s->v0 = GLSIP_ROTL(s->v0, 32);
  s->v2 += s->v3; s->v3 = GLSIP_ROTL(s->v3, 16); s->v3 ^= s->v2;
  s->v0 += s->v3; s->v3 = GLSIP_ROTL(s->v3, 21); s->v3 ^= s->v0;
  s->v2 += s->v1; s->v1 = GLSIP_ROTL(s->v1, 17); s->v1 ^= s->v2; s->v2 = GLSIP_ROTL(s->v2, 32);
}

static inline uint64_t glsip_le64(const uint8_t *p) {
  uint64_t x = 0;
  for (uint8_t i = 8; i > 0; i--) x = (x << 8) | p[i - 1];
  return x;
}

static GLSIP_NOINLINE void glsip_init(glsip_t *s, const uint8_t key[16]) {
  uint64_t k0 = glsip_le64(key), k1 = glsip_le64(key + 8);
  s->v0 = k0 ^ 0x736f6d6570736575ULL;
  s->v1 = k1 ^ 0x646f72616e646f6dULL;
  s->v2 = k0 ^ 0x6c7967656e657261ULL;
  s->v3 = k1 ^ 0x7465646279746573ULL;
  s->n = 0;
  s->total = 0;
}

static GLSIP_NOINLINE void glsip_byte(glsip_t *s, uint8_t b) {
  s->buf[s->n++] = b;
  s->total++;
  if (s->n == 8) {
    uint64_t m = glsip_le64(s->buf);
    s->v3 ^= m;
    glsip_round(s);
    glsip_round(s);
    s->v0 ^= m;
    s->n = 0;
  }
}

static GLSIP_NOINLINE uint64_t glsip_final(glsip_t *s) {
  uint64_t b = ((uint64_t)s->total) << 56;
  for (uint8_t i = 0; i < s->n; i++) b |= ((uint64_t)s->buf[i]) << (8 * i);
  s->v3 ^= b;
  glsip_round(s);
  glsip_round(s);
  s->v0 ^= b;
  s->v2 ^= 0xff;
  for (uint8_t i = 0; i < 4; i++) glsip_round(s);
  return s->v0 ^ s->v1 ^ s->v2 ^ s->v3;
}

#endif  // GLUCOLUME_SIPHASH_H
