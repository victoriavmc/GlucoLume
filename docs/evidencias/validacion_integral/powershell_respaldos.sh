#!/usr/bin/env bash
# Ensaya los scripts REALES de database/respaldos/*.ps1 (sin modificarlos) con PowerShell 7 en Linux contra un SQL Server 2022 DESCARTABLE
# (Docker) y archivos descartables en /tmp. Datos 100 % sintéticos. Requiere: pwsh, docker, gpg, el entorno virtual del backend (schemaCheck).
# Limitaciones (no son defectos de los scripts): PowerShell en Linux no tiene DPAPI (la «protección» de la clave es solo texto codificado y
# [Marshal]::PtrToStringAuto lee la frase truncada) y sqlcmd.exe/Windows no existen: se usa un reenviador al sqlcmd del contenedor
# (powershell_shims/sqlcmd). Por eso NO se valida DPAPI, la cuenta de Windows ni la tarea programada.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"; REPO="$(cd "$HERE/../../.." && pwd)"
IMG="${MSSQL_IMAGE:-mcr.microsoft.com/mssql/server:2022-CU16-ubuntu-22.04@sha256:45a1a9d13ca5574cf8e0fe4ae73ab77248b66d9c3132ac9658fb6c16dd72a8af}"
export GL_SQL_CONTAINER=gl-mssql-bk; export GL_SQL_PW="Bk$(head -c 8 /dev/urandom | od -An -tx1 | tr -d ' \n')#Sint1"
export PATH="$HERE/powershell_shims:$PATH"; export TEMP=/tmp
BK=/tmp/gl_bk; EXT=/tmp/gl_ext; pass=0; fail=0
ok(){ echo "OK    $1"; pass=$((pass+1)); }; bad(){ echo "FALLA $1"; fail=$((fail+1)); }
rm -rf $BK $EXT; mkdir -p $BK $EXT; chmod 777 $BK $EXT
docker rm -f $GL_SQL_CONTAINER >/dev/null 2>&1
docker run -d --name $GL_SQL_CONTAINER -e ACCEPT_EULA=Y -e "MSSQL_SA_PASSWORD=$GL_SQL_PW" -e MSSQL_PID=Developer -v $BK:$BK -v $EXT:$EXT "$IMG" >/dev/null
for i in $(seq 1 60); do docker exec $GL_SQL_CONTAINER /opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -P "$GL_SQL_PW" -Q "SELECT 1" >/dev/null 2>&1 && break; sleep 2; done
SQ="docker exec $GL_SQL_CONTAINER /opt/mssql-tools18/bin/sqlcmd -C -I -S localhost -U sa -P $GL_SQL_PW -b"
iconv -f UTF-16LE -t UTF-8 "$REPO/database/reference/GlucoLume_DB_v5.sql" | sed '1s/^\xEF\xBB\xBF//' > /tmp/v5_bk.sql; docker cp /tmp/v5_bk.sql $GL_SQL_CONTAINER:/tmp/v5.sql
$SQ -Q "CREATE DATABASE GlucoLume COLLATE Modern_Spanish_CI_AS" && $SQ -i /tmp/v5.sql >/dev/null 2>&1 && $SQ -d GlucoLume -Q "INSERT INTO dbo.Auditoria (idAuditoria,tipoEvento,accion,resultado,fechaHora) VALUES (NEWID(),N'CRUD',N'SINTETICO_RESPALDO',N'EXITO',SYSDATETIME())" >/dev/null && ok "base sintética con esquema v5 y un evento" || bad "preparación"
cd "$REPO/database/respaldos"
R(){ pwsh -NoProfile -File GlucoLume_respaldo.ps1 -Instancia x -Base GlucoLume -Destino $BK -Clave $BK/clave_respaldo.dpapi -Gpg /usr/bin/gpg "$@"; }

echo "== 5. Sintaxis de los tres scripts (el [scriptblock]::Create de la lista de Windows)"
for f in GlucoLume_respaldo.ps1 GlucoLume_clave_respaldo.ps1 GlucoLume_prueba_restauracion.ps1; do
  pwsh -NoProfile -Command "[scriptblock]::Create((Get-Content -Raw ./$f)) | Out-Null; 'ok'" 2>&1 | grep -q '^ok$' && ok "sintaxis $f" || bad "sintaxis $f"; done
echo "== Clave"
pwsh -NoProfile -File GlucoLume_clave_respaldo.ps1 -Archivo $BK/clave_respaldo.dpapi | tail -1 | grep -q "Clave creada" && ok "clave creada" || bad "clave"
pwsh -NoProfile -File GlucoLume_clave_respaldo.ps1 -Archivo $BK/clave_respaldo.dpapi | grep -q "no se reemplaza" && ok "una clave existente no se reemplaza" || bad "reemplazo de clave"

echo "== 1. Respaldo con -CopiaExterna"
R -CopiaExterna $EXT; code=$?
[ $code = 0 ] && ok "código de salida 0" || bad "salida $code"
ls $BK/GlucoLume_*.bak.gpg >/dev/null 2>&1 && ok "respaldo local cifrado creado" || bad "sin respaldo local"
ls $BK/GlucoLume_*.bak >/dev/null 2>&1 && bad "quedó un .bak sin cifrar" || ok "no queda ningún .bak en claro"
[ "$(sha256sum $BK/GlucoLume_*.bak.gpg | cut -d' ' -f1)" = "$(sha256sum $EXT/GlucoLume_*.bak.gpg | cut -d' ' -f1)" ] && ok "la copia externa es idéntica (SHA-256)" || bad "copia externa distinta"
grep -q "Copia externa verificada" $BK/respaldo.log && ok "respaldo.log: «Copia externa verificada»" || bad "log"
head -c 3 $BK/GlucoLume_*.bak.gpg | od -An -tx1 | grep -qi "8c\|8d\|c3\|c9" ; file $BK/GlucoLume_*.bak.gpg | grep -qi "pgp\|gpg\|symmetric" && ok "el archivo es un contenedor OpenPGP (no un .bak legible)" || echo "   (tipo: $(file -b $BK/GlucoLume_*.bak.gpg))"
strings $BK/GlucoLume_*.bak.gpg | grep -q "SINTETICO_RESPALDO" && bad "el texto del evento aparece en claro" || ok "el contenido no es legible en el archivo cifrado"

echo "== 2. Falla de la copia externa (destino inexistente)"
sleep 1; R -CopiaExterna /tmp/gl_no_existe; code=$?
[ $code = 2 ] && ok "sale con código 2" || bad "salida $code (esperado 2)"
[ "$(ls $BK/GlucoLume_*.bak.gpg | wc -l)" = 2 ] && ok "el respaldo local igual quedó hecho" || bad "faltó el respaldo local"
grep -q "ERROR en la copia externa" $BK/respaldo.log && ok "el error de la copia queda en el log" || bad "log del error"

echo "== 3. Sin -CopiaExterna"
sleep 1; R; code=$?
[ $code = 0 ] && ok "salida 0" || bad "salida $code"
grep -q "regla 3-2-1 incompleta" $BK/respaldo.log && ok "registra el aviso de la regla 3-2-1" || bad "sin aviso 3-2-1"

echo "== Retención local (nunca el último, solo el patrón propio)"
# Hoy = 2026-10-23 (diarios: últimos 35 días; mensuales: 12 meses). Se espera conservar 20260110 y 20260201 (uno por mes), 20251220 (uno por mes) y borrar
# 20260105 y 20251215 (segundo del mes), 20250915 y 20240105 (más de 12 meses).
for d in 20260105 20260110 20260201 20251215 20251220 20250915 20240105; do : > $BK/GlucoLume_${d}_010101.bak.gpg; done
echo no_tocar > $BK/otro_archivo.txt; : > $BK/GlucoLume_manual.bak.gpg
sleep 1; R >/dev/null; code=$?
[ $code = 0 ] && ok "retención ejecutada" || bad "salida $code"
[ -f $BK/otro_archivo.txt ] && [ -f $BK/GlucoLume_manual.bak.gpg ] && ok "archivos ajenos o fuera del patrón no se tocan" || bad "borró archivos ajenos"
for d in 20260110 20260201 20251220; do [ -f $BK/GlucoLume_${d}_010101.bak.gpg ] && ok "se conserva el mensual $d" || bad "se borró el mensual $d"; done
for d in 20260105 20251215 20250915 20240105; do [ -f $BK/GlucoLume_${d}_010101.bak.gpg ] && bad "debía borrarse $d" || ok "se borró $d (segundo del mes o fuera de los 12 meses)"; done
latest=$(ls $BK/GlucoLume_2026102*.bak.gpg | tail -1); [ -s "$latest" ] && ok "el respaldo más reciente se conserva" || bad "último"
n=$(ls $BK/GlucoLume_2026102*.bak.gpg | wc -l); [ "$n" = 4 ] && ok "los 4 respaldos de hoy (diarios) siguen" || bad "diarios de hoy: $n"
grep -c "Retención: borrado" $BK/respaldo.log | sed 's/^/   borrados registrados en el log: /'

echo "== Restauración de prueba (GlucoLume_prueba_restauracion.ps1) en una instancia descartable"
VENV_BIN="$(dirname "$(command -v python)")"; export PATH="$VENV_BIN:$PATH"
archivo=$(ls $BK/GlucoLume_2026102*.bak.gpg | head -1)
pwsh -NoProfile -File GlucoLume_prueba_restauracion.ps1 -Archivo "$archivo" -Destino $BK -Clave $BK/clave_respaldo.dpapi -Gpg /usr/bin/gpg -Backend "$REPO/backend" -Imagen "$IMG" -Puerto 14399; code=$?
tail -3 $BK/restauracion.log 2>/dev/null
[ $code = 0 ] && ok "restauración de prueba: salida 0 (esquema restaurado = vigente según schemaCheck)" || bad "restauración salida $code"
docker ps -a --format '{{.Names}}' | grep -q glucolume-prueba-restauracion && bad "quedó el contenedor descartable" || ok "el contenedor descartable se elimina solo"
ls /tmp/glucolume_prueba_* >/dev/null 2>&1 && bad "quedó el .bak descifrado" || ok "el .bak descifrado se elimina solo"
echo "== Restauración con un archivo corrupto"
cp "$archivo" $BK/GlucoLume_20261231_000000.bak.gpg; printf 'basura' | dd of=$BK/GlucoLume_20261231_000000.bak.gpg bs=1 seek=100 conv=notrunc 2>/dev/null
pwsh -NoProfile -File GlucoLume_prueba_restauracion.ps1 -Archivo $BK/GlucoLume_20261231_000000.bak.gpg -Destino $BK -Clave $BK/clave_respaldo.dpapi -Gpg /usr/bin/gpg -Backend "$REPO/backend" -Imagen "$IMG" -Puerto 14399 >/dev/null 2>&1; code=$?
[ $code = 1 ] && ok "un respaldo cifrado corrupto falla la restauración (código 1) y no deja restos" || bad "corrupto: salida $code"
echo; echo "RESUMEN: $pass correctas, $fail con falla"
docker rm -f $GL_SQL_CONTAINER >/dev/null 2>&1
[ "$fail" = 0 ]
