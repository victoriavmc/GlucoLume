# Verificación de la firma de líneas (H-05) sin hardware

`verificar_firma.sh` compila `firma/firma.ino` —que usa la clase **real** `LinkOut` de `GlucoLume_MAX30100_optimizado/GlucoLumeEnlace.h` con el núcleo
oficial `arduino:avr`—, la ejecuta en un ATmega328P **simulado** (simavr) y comprueba cada línea emitida con el verificador del puente
(`acquisition/bridge/linkauth.py`). Requiere Linux o WSL con los paquetes indicados en el encabezado del script. No toca ninguna placa.

Qué demuestra: que el código compilado para AVR firma exactamente como el verificador espera (formato, SipHash-2-4, contador de arranque y de línea,
valores flotantes y negativos, líneas largas, contador cerca del límite de 32 bits, líneas sin clave y tras `KEYCLR`).

Qué NO demuestra: el comportamiento del sketch completo en la placa (sensor, LCD, tiempos reales del HC-06, EEPROM real, `SoftwareSerial`), la robustez
frente a un atacante real en el aire ni la seguridad del enlace Bluetooth (ver `docs/SEGURIDAD.md`, H-05).
