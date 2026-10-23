#!/usr/bin/env bash
# Prueba de ACTUALIZACIÓN SIN PÉRDIDA DE DATOS: una base instalada con el esquema v5 de `master` (antes de esta rama: sin los 31 índices, sin PuenteCredencial, sin los
# permisos nuevos) recibe sus filas sintéticas y se actualiza con los scripts de ESTA rama; se comprueba que (1) ninguna fila cambia, (2) la estructura queda
# idéntica a una instalación nueva con el v5 actual y (3) `schemaCheck` informa «Sin diferencias». Usa el contenedor de SQL Server del stack (db) y datos sintéticos.
#   STACK_SECRETS=<archivo con SA=...> DB_CONTAINER=glucolume-db-1 BACKEND_CONTAINER=glucolume-backend-1 bash actualizacion_sin_perdida.sh   (desde la raíz del repositorio)
set -u
REPO="$(git rev-parse --show-toplevel)"; cd "$REPO"
. "${STACK_SECRETS:?}"; DB="${DB_CONTAINER:-glucolume-db-1}"; BE="${BACKEND_CONTAINER:-glucolume-backend-1}"; BASE_REF="${BASE_REF:-origin/master}"
pass=0; fail=0; ok(){ echo "OK    $1"; pass=$((pass+1)); }; bad(){ echo "FALLA $1"; fail=$((fail+1)); }
sq(){ docker exec -e SQLCMDPASSWORD="$SA" "$DB" /opt/mssql-tools18/bin/sqlcmd -C -I -S localhost -U sa -b "$@"; }
val(){ sq -d "$1" -h -1 -W -Q "SET NOCOUNT ON; $2" | tr -d '\r' | sed '/^$/d' | tail -n 1; }
docker exec "$DB" mkdir -p /tmp/sql
utf8(){ iconv -f UTF-16LE -t UTF-8 | sed '1s/^\xEF\xBB\xBF//'; }
git show "$BASE_REF:database/reference/GlucoLume_DB_v5.sql" | utf8 | sed 's/\[GlucoLume\]/[GlucoLume_Antes]/' > /tmp/v5_antes.sql
utf8 < database/reference/GlucoLume_DB_v5.sql | sed 's/\[GlucoLume\]/[GlucoLume_Nueva]/' > /tmp/v5_nueva.sql
for f in /tmp/v5_antes.sql /tmp/v5_nueva.sql; do docker cp "$f" "$DB:/tmp/sql/$(basename "$f")"; done
for f in GlucoLume_actualizar_instalada GlucoLume_agregar_puente_credencial GlucoLume_permisos GlucoLume_permisos_quitar_roles_fijos; do docker cp "database/reference/$f.sql" "$DB:/tmp/sql/$f.sql"; done
for d in GlucoLume_Antes GlucoLume_Nueva; do sq -Q "IF DB_ID('$d') IS NOT NULL BEGIN ALTER DATABASE [$d] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE [$d] END; CREATE DATABASE [$d] COLLATE Modern_Spanish_CI_AS" >/dev/null; done
sq -i /tmp/sql/v5_antes.sql >/dev/null 2>&1 && ok "instalación inicial con el v5 de $BASE_REF" || bad "v5 anterior"
sq -i /tmp/sql/v5_nueva.sql >/dev/null 2>&1 && ok "instalación nueva con el v5 de esta rama (referencia)" || bad "v5 nuevo"
echo "   base anterior: $(val GlucoLume_Antes "SELECT COUNT(*) FROM sys.tables") tablas, $(val GlucoLume_Antes "SELECT COUNT(*) FROM sys.indexes WHERE name LIKE 'IX[_]%' OR name LIKE 'UX[_]%'") índices IX/UX, PuenteCredencial=$(val GlucoLume_Antes "SELECT COUNT(*) FROM sys.tables WHERE name='PuenteCredencial'")"
echo "   base nueva:    $(val GlucoLume_Nueva "SELECT COUNT(*) FROM sys.tables") tablas, $(val GlucoLume_Nueva "SELECT COUNT(*) FROM sys.indexes WHERE name LIKE 'IX[_]%' OR name LIKE 'UX[_]%'") índices IX/UX"
# Datos sintéticos
sq -d GlucoLume_Antes -Q "
INSERT INTO dbo.Usuario (nombre, apellido, correoElectronico, usuario, tipoCuenta, estado, fechaNacimiento, sexo) VALUES
 (N'Ana', N'Sintetica', N'ana.upd@example.com', N'anaupd', N'CONSUMIDOR_FINAL', N'ACTIVO', '1990-05-17', N'FEMENINO'),
 (N'Beto', N'Sintetico', N'beto.upd@example.com', N'betoupd', N'USUARIO_INSTITUCIONAL', N'ACTIVO', '1985-02-01', N'MASCULINO');
INSERT INTO dbo.Auditoria (idAuditoria, tipoEvento, accion, resultado, fechaHora) VALUES (NEWID(), N'CRUD', N'SINTETICO_A', N'EXITO', SYSDATETIME()), (NEWID(), N'CRUD', N'SINTETICO_B', N'EXITO', SYSDATETIME());
INSERT INTO dbo.Dispositivo (codigoDispositivo, modeloSensor) VALUES (N'GLUCOLUME-UPD-01', N'MAX30100');" && ok "filas sintéticas en la base anterior" || bad "datos sintéticos"
SNAP="SELECT (SELECT COUNT(*) FROM dbo.Usuario), (SELECT COUNT(*) FROM dbo.Auditoria), (SELECT COUNT(*) FROM dbo.Dispositivo), (SELECT COUNT(*) FROM dbo.ReglaMatriz), (SELECT CHECKSUM_AGG(BINARY_CHECKSUM(*)) FROM dbo.Usuario), (SELECT CHECKSUM_AGG(BINARY_CHECKSUM(*)) FROM dbo.Auditoria), (SELECT CHECKSUM_AGG(BINARY_CHECKSUM(*)) FROM dbo.Dispositivo)"
ANTES="$(val GlucoLume_Antes "$SNAP")"; echo "   instantánea antes: $ANTES"
# Cuentas existentes (las del stack): se reutilizan; si faltan se crean con contraseñas sintéticas
sq -d GlucoLume_Antes -Q "IF DATABASE_PRINCIPAL_ID('glucolume_app') IS NULL CREATE USER glucolume_app FOR LOGIN glucolume_app; ALTER ROLE db_datareader ADD MEMBER glucolume_app; ALTER ROLE db_datawriter ADD MEMBER glucolume_app;" >/dev/null 2>&1 && ok "la cuenta de la API arranca con db_datareader/db_datawriter (estado heredado de la base real)" || bad "cuenta heredada"
sq -d GlucoLume_Antes -i /tmp/sql/GlucoLume_actualizar_instalada.sql -v CONFIRMAR=ACTUALIZAR_GLUCOLUME_V5 >/tmp/upd1.out 2>&1 && ok "GlucoLume_actualizar_instalada.sql (restricciones + 31 índices)" || { bad "actualizar_instalada"; tail -5 /tmp/upd1.out; }
sq -d GlucoLume_Antes -i /tmp/sql/GlucoLume_actualizar_instalada.sql -v CONFIRMAR=ACTUALIZAR_GLUCOLUME_V5 >/dev/null 2>&1 && ok "idempotente: segunda ejecución sin errores" || bad "actualizar 2"
sq -d GlucoLume_Antes -i /tmp/sql/GlucoLume_agregar_puente_credencial.sql -v CONFIRMAR=AGREGAR_PUENTE_CREDENCIAL >/dev/null 2>&1 && ok "GlucoLume_agregar_puente_credencial.sql (H-16)" || bad "puente"
sq -d GlucoLume_Antes -i /tmp/sql/GlucoLume_permisos.sql -v API_LOGIN=glucolume_app JOBS_LOGIN=glucolume_jobs CONFIRMAR=APLICAR_PERMISOS_GLUCOLUME >/dev/null 2>&1 && ok "GlucoLume_permisos.sql (H-02) con cuentas separadas" || bad "permisos"
sq -d GlucoLume_Antes -i /tmp/sql/GlucoLume_permisos_quitar_roles_fijos.sql -v API_LOGIN=glucolume_app CONFIRMAR=QUITAR_ROLES_FIJOS_GLUCOLUME >/dev/null 2>&1 && ok "roles fijos quitados (reversible)" || bad "quitar roles"
DESPUES="$(val GlucoLume_Antes "$SNAP")"; echo "   instantánea después: $DESPUES"
[ "$ANTES" = "$DESPUES" ] && ok "NINGUNA fila cambió (conteos y checksums de Usuario, Auditoria, Dispositivo, ReglaMatriz)" || bad "los datos cambiaron"
cmp(){ [ "$(val GlucoLume_Antes "$1")" = "$(val GlucoLume_Nueva "$1")" ] ; }
q_cols="SELECT STRING_AGG(CAST(t.name+'.'+c.name+':'+TYPE_NAME(c.user_type_id)+':'+CAST(c.max_length AS varchar)+':'+CAST(c.is_nullable AS varchar) AS nvarchar(max)),'|') WITHIN GROUP (ORDER BY t.name,c.column_id) FROM sys.columns c JOIN sys.tables t ON t.object_id=c.object_id"
q_idx="SELECT STRING_AGG(CAST(t.name+'.'+i.name+':'+CAST(i.is_unique AS varchar)+':'+ISNULL(i.filter_definition,'') AS nvarchar(max)),'|') WITHIN GROUP (ORDER BY t.name,i.name) FROM sys.indexes i JOIN sys.tables t ON t.object_id=i.object_id WHERE i.name IS NOT NULL"
q_chk="SELECT STRING_AGG(CAST(OBJECT_NAME(parent_object_id)+'.'+name+':'+definition AS nvarchar(max)),'|') WITHIN GROUP (ORDER BY OBJECT_NAME(parent_object_id),name) FROM sys.check_constraints"
q_fk="SELECT STRING_AGG(CAST(OBJECT_NAME(parent_object_id)+'.'+name+'->'+OBJECT_NAME(referenced_object_id) AS nvarchar(max)),'|') WITHIN GROUP (ORDER BY OBJECT_NAME(parent_object_id),name) FROM sys.foreign_keys"
q_def="SELECT STRING_AGG(CAST(OBJECT_NAME(d.parent_object_id)+'.'+c.name+':'+d.definition AS nvarchar(max)),'|') WITHIN GROUP (ORDER BY OBJECT_NAME(d.parent_object_id),c.name) FROM sys.default_constraints d JOIN sys.columns c ON c.object_id=d.parent_object_id AND c.column_id=d.parent_column_id"  # sin el nombre: SQL Server genera sufijos distintos en cada instalación
cmp "$q_cols" && ok "columnas = instalación nueva" || bad "columnas difieren"
cmp "$q_idx" && ok "índices (nombre, unicidad, filtro) = instalación nueva" || { bad "índices difieren"; }
cmp "$q_chk" && ok "restricciones CHECK = instalación nueva" || bad "CHECK difieren"
cmp "$q_fk" && ok "claves foráneas = instalación nueva" || bad "FK difieren"
cmp "$q_def" && ok "valores por defecto = instalación nueva" || bad "DEFAULT difieren"
URL="mssql+pyodbc://sa:$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1],safe=''))" "$SA")@db:1433/GlucoLume_Antes?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"
out=$(docker exec "$BE" python -m app.cli.schemaCheck --url "$URL" 2>&1 | tail -2); echo "   schemaCheck: $out" | cut -c1-200
echo "$out" | grep -q "Sin diferencias" && ok "schemaCheck (dentro del contenedor del backend): sin diferencias" || bad "schemaCheck"
[ "${KEEP:-0}" = 1 ] || for d in GlucoLume_Antes GlucoLume_Nueva; do sq -Q "ALTER DATABASE [$d] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE [$d]" >/dev/null 2>&1; done
echo; echo "RESUMEN: $pass correctas, $fail con falla"; [ "$fail" = 0 ]
