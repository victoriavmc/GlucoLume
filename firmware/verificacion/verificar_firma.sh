#!/usr/bin/env bash
# Verifica la firma de lineas del firmware (H-05) en un ATmega328P simulado, sin hardware. Linux o WSL (Ubuntu/Debian).
#
#   sudo apt-get install -y gcc-avr avr-libc binutils-avr simavr libsimavr-dev libelf-dev arduino-builder arduino-core-avr arduino-ctags build-essential python3
#   git clone --depth 1 https://github.com/johnrickman/LiquidCrystal_I2C   # NO hace falta para esta prueba (solo para compilar el sketch completo)
#   bash firmware/verificacion/verificar_firma.sh
#
# Compila firma/firma.ino (que usa la clase REAL de GlucoLumeEnlace.h con el nucleo oficial arduino:avr), la ejecuta en simavr, y comprueba CADA linea
# emitida con acquisition/bridge/linkauth.py: payloads exactos, firmas validas, contadores crecientes, lo anterior a la clave sin firma y lo posterior
# a KEYCLR sin firma. Imprime ciclos y bytes. Nada de esto toca la placa ni sube nada.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
WORK="$(mktemp -d)"
trap '[ -n "${GL_KEEP:-}" ] || rm -rf "$WORK"' EXIT
mkdir -p "$WORK/hw" "$WORK/tools/avr" "$WORK/build" "$WORK/libs"
ln -sfn /usr/bin "$WORK/tools/avr/bin"
cat > "$WORK/hw/platform.txt" <<'PLAT'
tools.ctags.path=/usr/bin
tools.ctags.cmd.path={path}/arduino-ctags
tools.ctags.pattern="{cmd.path}" -u --language-force=c++ -f - --c++-kinds=svpf --fields=KSTtzns --line-directives "{source_file}"
preproc.includes.flags=-w -x c++ -M -MG -MP
recipe.preproc.includes="{compiler.path}{compiler.cpp.cmd}" {compiler.cpp.flags} {preproc.includes.flags} -mmcu={build.mcu} -DF_CPU={build.f_cpu} -DARDUINO={runtime.ide.version} -DARDUINO_{build.board} -DARDUINO_ARCH_{build.arch} {compiler.cpp.extra_flags} {build.extra_flags} {includes} "{source_file}"
preproc.macros.flags=-w -x c++ -E -CC
recipe.preproc.macros="{compiler.path}{compiler.cpp.cmd}" {compiler.cpp.flags} {preproc.macros.flags} -mmcu={build.mcu} -DF_CPU={build.f_cpu} -DARDUINO={runtime.ide.version} -DARDUINO_{build.board} -DARDUINO_ARCH_{build.arch} {compiler.cpp.extra_flags} {build.extra_flags} {includes} "{source_file}" -o "{preprocessed_file_path}"
PLAT
cp -r "$ROOT/firmware/verificacion/firma" "$WORK/sketch"
# El encabezado de la clase se busca con -I (el builder copia el sketch a otra carpeta, una ruta relativa no serviria).
arduino-builder -compile -hardware /usr/share/arduino/hardware -hardware "$WORK/hw" -tools "$WORK/tools" -fqbn arduino:avr:uno \
  -prefs="build.extra_flags=-I$ROOT/firmware/GlucoLume_MAX30100_optimizado" -libraries "$WORK/libs" -build-path "$WORK/build" \
  "$WORK/sketch/firma.ino" 2>&1 | grep -E "Sketch uses|Global variables|error" || true
ELF="$WORK/build/firma.ino.elf"
LEN="$(avr-nm "$ELF" | awk '$3 == "g_len" {print $1}')"; OUT="$(avr-nm "$ELF" | awk '$3 == "g_out" {print $1}')"; [ -n "$LEN" ] && [ -n "$OUT" ] || { echo 'no se encontraron g_len/g_out en el ELF' >&2; exit 1; }
gcc -o "$WORK/sim_host" "$ROOT/firmware/verificacion/sim_host.c" -lsimavr -lelf
"$WORK/sim_host" "$ELF" "$LEN" "$OUT" | tail -n 1 > "$WORK/salida.hex"  # simavr escribe otras lineas informativas antes
python3 -I "$ROOT/firmware/verificacion/comprobar_salida.py" "$WORK/salida.hex" "$ROOT/acquisition/bridge"
