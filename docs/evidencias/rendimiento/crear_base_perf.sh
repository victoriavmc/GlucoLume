#!/usr/bin/env bash
# Crea la base DESCARTABLE «GlucoLume_perf» dentro del contenedor SQL Server del perfil «db» (mismo servidor, otra base: no toca «GlucoLume»)
# con los scripts oficiales (esquema v5, matriz global y permisos de la cuenta de la API). Repetible: borra y vuelve a crear solo GlucoLume_perf.
# Uso (Git Bash, desde la raíz del repositorio):  bash docs/evidencias/rendimiento/crear_base_perf.sh
set -euo pipefail
export MSYS_NO_PATHCONV=1
DB=GlucoLume_perf
SA=$(grep ^SQLCMDPASSWORD docker/db.env | cut -d= -f2)
SQ=(docker exec -e SQLCMDPASSWORD="$SA" glucolume-db-1 /opt/mssql-tools18/bin/sqlcmd -C -I -S localhost -U sa -b)
T=$(cygpath -m "$(mktemp -d)")
python - "$T" <<'PY'
import sys
t = open("database/reference/GlucoLume_DB_v5.sql", encoding="utf-16").read().lstrip("﻿").replace("USE [GlucoLume]", "USE [GlucoLume_perf]", 1)
open(sys.argv[1] + "/v5.sql", "w", encoding="utf-8", newline="").write(t)
m = open("database/reference/MATRIZ.SQL", encoding="utf-8-sig").read().replace("USE [GlucoLume];", "USE [GlucoLume_perf];", 1)
open(sys.argv[1] + "/MATRIZ.SQL", "w", encoding="utf-8", newline="").write(m)
PY
docker exec glucolume-db-1 mkdir -p /tmp/sql
docker cp "$T/v5.sql" glucolume-db-1:/tmp/sql/perf_v5.sql
docker cp "$T/MATRIZ.SQL" glucolume-db-1:/tmp/sql/perf_MATRIZ.SQL
docker cp database/reference/GlucoLume_permisos.sql glucolume-db-1:/tmp/sql/GlucoLume_permisos.sql
docker cp database/reference/GlucoLume_permisos_quitar_roles_fijos.sql glucolume-db-1:/tmp/sql/GlucoLume_permisos_quitar_roles_fijos.sql
"${SQ[@]}" -Q "IF DB_ID('$DB') IS NOT NULL BEGIN ALTER DATABASE [$DB] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE [$DB]; END; CREATE DATABASE [$DB] COLLATE Modern_Spanish_CI_AS"
"${SQ[@]}" -i /tmp/sql/perf_v5.sql > /dev/null
"${SQ[@]}" -d $DB -i /tmp/sql/perf_MATRIZ.SQL > /dev/null
"${SQ[@]}" -d $DB -i /tmp/sql/GlucoLume_permisos.sql -v API_LOGIN=glucolume_app JOBS_LOGIN=glucolume_jobs CONFIRMAR=APLICAR_PERMISOS_GLUCOLUME > /dev/null
"${SQ[@]}" -d $DB -i /tmp/sql/GlucoLume_permisos_quitar_roles_fijos.sql -v API_LOGIN=glucolume_app CONFIRMAR=QUITAR_ROLES_FIJOS_GLUCOLUME > /dev/null
"${SQ[@]}" -d $DB -h -1 -W -Q "SET NOCOUNT ON; SELECT 'tablas', COUNT(*) FROM sys.tables UNION ALL SELECT 'reglas de matriz', COUNT(*) FROM dbo.ReglaMatriz"
rm -rf "$T"
