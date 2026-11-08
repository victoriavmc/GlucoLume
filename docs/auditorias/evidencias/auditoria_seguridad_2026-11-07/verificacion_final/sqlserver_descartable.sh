#!/usr/bin/env bash
# Ejecuta las pruebas *_sqlserver (las que la suite normal omite) contra SQL Server 2022 CU16 DESCARTABLE.
#
# Qué hace: levanta un contenedor propio con la imagen fijada del proyecto (docker/mssql/Dockerfile), sin volúmenes y publicado solo en
# 127.0.0.1; crea la base GlucoLume_Descartable; aplica database/reference/GlucoLume_DB_v5.sql (en una COPIA, con el USE apuntado a la base
# descartable), crea las cuentas de prueba, aplica GlucoLume_permisos.sql y GlucoLume_retencion_ip_tecnica.sql; corre las pruebas en
# secuencia (no en paralelo: cada una vacía la base); y elimina el contenedor al terminar. Nunca usa la base GlucoLume ni otro servidor.
#
# Requisitos en el equipo que ejecuta: Docker, openssl, iconv, y un Python con el backend instalado (pyodbc) y el driver
# «ODBC Driver 18 for SQL Server» (msodbcsql18 + unixODBC). Sin el driver, pyodbc no carga y las pruebas no pueden correr.
#
# Uso, desde la raíz del repo:
#   PY=backend/.venv/bin/python bash docs/auditorias/evidencias/auditoria_seguridad_2026-11-07/verificacion_final/sqlserver_descartable.sh
# Variables opcionales: PY (intérprete con pyodbc, por defecto python3), PUERTO (por defecto 14333), SALIDA (carpeta del informe),
# KEEP=1 (conserva el contenedor para diagnóstico; por defecto se elimina).
# Los secretos se generan en cada corrida, viajan por archivos temporales con permisos 600 y no se imprimen ni quedan en el informe.
set -euo pipefail

RAIZ="$(cd "$(dirname "$0")/../../../../.." && pwd)"
IMG="mcr.microsoft.com/mssql/server:2022-CU16-ubuntu-22.04@sha256:45a1a9d13ca5574cf8e0fe4ae73ab77248b66d9c3132ac9658fb6c16dd72a8af"
PY="${PY:-python3}"
PUERTO="${PUERTO:-14333}"
SALIDA="${SALIDA:-$(mktemp -d "${TMPDIR:-/tmp}/glucolume-sqlserver-XXXX")}"
NOMBRE="glucolume-prueba-mssql-$$"
BASE="GlucoLume_Descartable"
TMP="$(mktemp -d)"
chmod 700 "$TMP"
cleanup() {
  if [ "${KEEP:-0}" = 1 ]; then echo "KEEP=1: contenedor $NOMBRE conservado para diagnóstico"; else docker rm -f "$NOMBRE" >/dev/null 2>&1 || true; fi
  rm -rf "$TMP"
}
trap cleanup EXIT

gen() { openssl rand -base64 30 | tr -dc 'A-Za-z0-9' | head -c 18; }
SA="Aa1!$(gen)"; APP="Aa1!$(gen)"; RET="Aa1!$(gen)"
printf '%s' "$SA" > "$TMP/sa"; printf '%s' "$APP" > "$TMP/app"; printf '%s' "$RET" > "$TMP/ret"
printf 'ACCEPT_EULA=Y\nMSSQL_PID=Express\nMSSQL_SA_PASSWORD=%s\n' "$SA" > "$TMP/entorno"

echo "Contenedor descartable: $NOMBRE (127.0.0.1:$PUERTO)"
docker run -d --name "$NOMBRE" -p "127.0.0.1:$PUERTO:1433" --env-file "$TMP/entorno" "$IMG" >/dev/null
docker cp "$TMP/sa" "$NOMBRE:/tmp/.sa"

# Ejecuta sqlcmd dentro del contenedor leyendo la clave de un archivo (nunca en la línea de comandos).
sq() {
  docker exec "$NOMBRE" sh -c 'SQLCMDPASSWORD="$(cat /tmp/.sa)"; export SQLCMDPASSWORD; exec /opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -b "$@"' sh "$@"
}
for _ in $(seq 1 60); do sq -Q "SELECT 1" >/dev/null 2>&1 && break; sleep 3; done
sq -Q "SELECT 'motor listo: ' + CAST(SERVERPROPERTY('ProductVersion') AS varchar(40))" -h -1

sq -Q "CREATE DATABASE [$BASE]" >/dev/null

# Esquema vigente: v5 en una copia con el USE apuntado a la base descartable (el archivo del repo no se modifica).
iconv -f UTF-16 -t UTF-8 "$RAIZ/database/reference/GlucoLume_DB_v5.sql" | sed "s/USE \[GlucoLume\]/USE [$BASE]/" > "$TMP/v5.sql"
docker cp "$TMP/v5.sql" "$NOMBRE:/tmp/v5.sql"
sq -d "$BASE" -I -i /tmp/v5.sql >/dev/null

# Cuentas de prueba (CREATE LOGIN con la clave dentro de un archivo temporal que se borra enseguida).
{
  echo "CREATE LOGIN [glucolume_app] WITH PASSWORD = N'$APP', CHECK_POLICY = OFF;"
  echo "CREATE LOGIN [glu_ret_test] WITH PASSWORD = N'$RET', CHECK_POLICY = OFF;"
  echo "USE [$BASE];"
  echo "CREATE USER [glucolume_app] FOR LOGIN [glucolume_app];"
  echo "CREATE USER [glu_ret_test] FOR LOGIN [glu_ret_test];"
} > "$TMP/cuentas.sql"
docker cp "$TMP/cuentas.sql" "$NOMBRE:/tmp/cuentas.sql"
sq -I -i /tmp/cuentas.sql >/dev/null
# El archivo con las claves de las cuentas queda solo dentro del contenedor descartable, que se elimina al terminar.

# Permisos de mínimo privilegio: la API no puede modificar ni borrar la auditoría; la cuenta de retención solo anula IP y agente.
docker cp "$RAIZ/database/reference/GlucoLume_permisos.sql" "$NOMBRE:/tmp/permisos.sql"
sq -d "$BASE" -I -i /tmp/permisos.sql -v API_LOGIN="glucolume_app" JOBS_LOGIN="NINGUNA" CONFIRMAR="APLICAR_PERMISOS_GLUCOLUME" >/dev/null
docker cp "$RAIZ/database/reference/GlucoLume_retencion_ip_tecnica.sql" "$NOMBRE:/tmp/retencion.sql"
sq -d "$BASE" -I -i /tmp/retencion.sql -v RET_LOGIN="glu_ret_test" CONFIRMAR="APLICAR_RETENCION_IP_TECNICA" >/dev/null
echo "Esquema v5 y permisos aplicados en $BASE."

# Corrida de pruebas. Las URL se arman dentro de Python leyendo los archivos temporales: las claves no pasan por argv ni por el entorno del shell.
cat > "$TMP/correr.py" <<'PYEOF'
import os, re, sys, urllib.parse
sys.path.insert(0, os.getcwd())  # el backend (cwd) para importar app y tests
import pytest
tmp, puerto, salida = sys.argv[1], sys.argv[2], sys.argv[3]
leer = lambda n: open(os.path.join(tmp, n), encoding="utf-8").read()
base = "GlucoLume_Descartable?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"
os.environ["TEST_SQLSERVER_CONFIRM"] = "DESCARTABLE"
os.environ["TEST_SQLSERVER_URL"] = f"mssql+pyodbc://sa:{urllib.parse.quote_plus(leer('sa'))}@127.0.0.1:{puerto}/{base}"
os.environ["TEST_SQLSERVER_RET_URL"] = f"mssql+pyodbc://glu_ret_test:{urllib.parse.quote_plus(leer('ret'))}@127.0.0.1:{puerto}/{base}"
secretos = [leer("sa"), leer("app"), leer("ret")]
pruebas = ["tests/test_device_connection_sqlserver.py", "tests/test_platform_sqlserver.py", "tests/test_telemetry_sqlserver.py",
           "tests/test_user_notifications_sqlserver.py", "tests/test_technical_retention_sqlserver.py", "tests/test_reautenticacion_sqlserver.py"]
informe = os.path.join(salida, "pytest_sqlserver.txt")
with open(informe, "w", encoding="utf-8") as f:
    old = sys.stdout
    sys.stdout = f
    try:
        codigo = pytest.main(["-p", "no:cacheprovider", "-q", "-rs", "-v"] + pruebas)
    finally:
        sys.stdout = old
texto = open(informe, encoding="utf-8").read()
for s in secretos:
    texto = texto.replace(s, "***")
texto = re.sub(r"mssql\+pyodbc://[^ '\"]+", "mssql+pyodbc://***", texto)
open(informe, "w", encoding="utf-8").write(texto)
print("pytest código de salida:", codigo, "| informe:", informe)
sys.exit(codigo)
PYEOF
mkdir -p "$SALIDA"
cd "$RAIZ/backend"
"$PY" "$TMP/correr.py" "$TMP" "$PUERTO" "$SALIDA"
