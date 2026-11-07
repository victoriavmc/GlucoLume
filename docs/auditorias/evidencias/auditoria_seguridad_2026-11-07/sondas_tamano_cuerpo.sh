#!/usr/bin/env bash
# Límites de tamaño del cuerpo por operación (B-1, auditoría 07/11/2026). Solo lectura. No usar contra producción.
#
# Uso: sondas_tamano_cuerpo.sh [URL_BASE] [HOST]
#
# Para cada caso envía un cuerpo de tamaño exacto y registra: código HTTP, Content-Type y si nginx lo rechazó (413). Un código distinto de
# 413 significa que nginx lo dejó pasar al backend (la validación del backend responde después: 401, 422, etc.).
# Límites esperados tras la corrección (bytes = KiB x 1024): general 163840 (160k), autenticación 16384 (16k),
# ingesta del puente y navegador 786432 (768k), muestras 393216 (384k), offboarding 393216 (384k).
set -u
BASE="${1:-http://127.0.0.1:8080}"
HOST_PUBLICO="${2:-glucolume-server.tailb27487.ts.net}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Genera un cuerpo JSON de N bytes exactos: {"relleno":"aaa...."} (válido, con un campo que el backend rechazará después: no importa,
# solo medimos si nginx lo corta).
cuerpo() {  # tamano_bytes archivo
  local n="$1" archivo="$2"
  local prefijo='{"relleno":"'
  local sufijo='"}'
  local base=$(( ${#prefijo} + ${#sufijo} ))
  local relleno=$(( n - base ))
  { printf '%s' "$prefijo"; head -c "$relleno" /dev/zero | tr '\0' 'a'; printf '%s' "$sufijo"; } > "$archivo"
}

caso() {  # etiqueta ruta tamano_bytes
  local etiqueta="$1" ruta="$2" n="$3"
  cuerpo "$n" "$TMP/c.json"
  local salida
  salida=$(curl -s -m 60 -D "$TMP/h" -o "$TMP/b" -w '%{http_code}' -X POST -H "Host: $HOST_PUBLICO" \
    -H "Content-Type: application/json" --data-binary "@$TMP/c.json" "$BASE$ruta")
  local tipo
  tipo=$(tr -d '\r' < "$TMP/h" | awk 'tolower($1)=="content-type:"{print $2}' | head -1)
  local rechazo="no (llega al backend)"
  [ "$salida" = "413" ] && rechazo="SI (nginx 413)"
  printf '%-40s %-30s %9s %-18s %-22s %s\n' "$etiqueta" "$ruta" "$n" "$salida" "${tipo:-?}" "$rechazo"
}

printf '%-40s %-30s %9s %-18s %-22s %s\n' OPERACION RUTA BYTES CODIGO CONTENT-TYPE "RECHAZADO POR NGINX"
caso "General (contacto), justo bajo 160k" /api/v1/contact 163840
caso "General (contacto), 160k + 1 byte"   /api/v1/contact 163841
caso "General (contacto), 1 MB (antes aceptado)" /api/v1/contact 1000000
caso "Autenticación login, justo bajo 16k" /api/v1/auth/login 16384
caso "Autenticación login, 16k + 1 byte"   /api/v1/auth/login 16385
caso "Ingesta puente, justo bajo 768k"     /api/v1/acquisition/bridge/ingest 786432
caso "Ingesta puente, 768k + 1 byte"       /api/v1/acquisition/bridge/ingest 786433
caso "Ingesta navegador, 700 KB"           /api/v1/acquisition/browser/ingest 716800
caso "Muestras, justo bajo 384k"           /api/v1/measurements/00000000-0000-0000-0000-000000000000/samples 393216
caso "Muestras, 384k + 1 byte"             /api/v1/measurements/00000000-0000-0000-0000-000000000000/samples 393217
caso "Offboarding, justo bajo 384k"        /api/v1/institutions/00000000-0000-0000-0000-000000000000/operators/00000000-0000-0000-0000-000000000000/offboard 393216
caso "Offboarding, 384k + 1 byte"          /api/v1/institutions/00000000-0000-0000-0000-000000000000/operators/00000000-0000-0000-0000-000000000000/offboard 393217
caso "Matrices (reglas, peor caso 96 KB)"  /api/v1/matrices 98304
caso "Exportación (peor caso 123 KB)"      /api/v1/institutions/00000000-0000-0000-0000-000000000000/patients/export 125952
