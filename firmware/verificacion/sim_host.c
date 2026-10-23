/* Ejecuta un .elf de ATmega328P en simavr hasta que duerme con interrupciones apagadas y vuelca, en hexadecimal, g_len bytes de g_out (direcciones
   en hex como argumentos) y los ciclos usados. Uso: sim_host firma.elf <dir g_len> <dir g_out> */
#include <stdio.h>
#include <stdlib.h>
#include <simavr/sim_avr.h>
#include <simavr/sim_elf.h>
int main(int argc, char **argv) {
  if (argc < 4) return 2;
  elf_firmware_t f;
  if (elf_read_firmware(argv[1], &f) != 0) return 3;
  avr_t *avr = avr_make_mcu_by_name("atmega328p");
  avr_init(avr); avr_load_firmware(avr, &f); avr->frequency = 16000000;
  unsigned lenAddr = (unsigned)strtoul(argv[2], NULL, 16) & 0xFFFF, outAddr = (unsigned)strtoul(argv[3], NULL, 16) & 0xFFFF;
  int state = cpu_Running; unsigned long long guard = 0;
  while (state != cpu_Done && state != cpu_Crashed && guard < 400000000ULL) { state = avr_run(avr); guard++; }
  unsigned len = avr->data[lenAddr] | (avr->data[lenAddr + 1] << 8);
  fprintf(stderr, "estado=%d ciclos=%llu bytes=%u\n", state, (unsigned long long)avr->cycle, len);
  for (unsigned i = 0; i < len; i++) printf("%02x", avr->data[outAddr + i]);
  printf("\n");
  return state == cpu_Done ? 0 : 1;
}
