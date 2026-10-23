#!/usr/bin/env bash
# Validación de H-02 y H-16 contra un SQL Server 2022 DESCARTABLE en Docker, con datos 100 % sintéticos.
# Nunca apunta a una base real: crea su propio contenedor, su propia base y lo destruye al final (salvo KEEP=1).
#   MSSQL_IMAGE=... ./sqlserver_h02_h16.sh   (ejecutar desde la raíz del repositorio)
set -u
IMG="${MSSQL_IMAGE:-mcr.microsoft.com/mssql/server:2022-CU16-ubuntu-22.04@sha256:45a1a9d13ca5574cf8e0fe4ae73ab77248b66d9c3132ac9658fb6c16dd72a8af}"
NAME=gl-mssql-h02
SA_PW="Sa#$(head -c 12 /dev/urandom | base64 | tr -dc A-Za-z0-9)x1"
API_PW="Api#$(head -c 12 /dev/urandom | base64 | tr -dc A-Za-z0-9)x1"
JOBS_PW="Job#$(head -c 12 /dev/urandom | base64 | tr -dc A-Za-z0-9)x1"
pass=0; fail=0
ok()   { echo "OK    $1"; pass=$((pass+1)); }
bad()  { echo "FALLA $1"; fail=$((fail+1)); }
sq()   { docker exec "$NAME" /opt/mssql-tools18/bin/sqlcmd -C -I -S localhost -U sa -P "$SA_PW" -b "$@"; }
sqa()  { docker exec "$NAME" /opt/mssql-tools18/bin/sqlcmd -C -I -S localhost -U glucolume_app -P "$API_PW" -d GlucoLume -b "$@"; }
sqj()  { docker exec "$NAME" /opt/mssql-tools18/bin/sqlcmd -C -I -S localhost -U glucolume_jobs -P "$JOBS_PW" -d GlucoLume -b "$@"; }
# Denegado = error de permisos de SQL Server: 229 (objeto), 230 (columna), 262 (DDL), 1088/3701 (objeto oculto por falta de VIEW DEFINITION).
expect_denied() { out=$("$@" 2>&1); if echo "$out" | grep -qE "Msg (229|230|262|1088|3701),"; then return 0; else echo "   salida: $out" | head -3; return 1; fi; }
expect_allowed() { out=$("$@" 2>&1); if echo "$out" | grep -q "Msg 229\|permission was denied\|Msg "; then echo "   salida: $out" | head -3; return 1; else return 0; fi; }

docker rm -f "$NAME" >/dev/null 2>&1
docker run -d --name "$NAME" -e ACCEPT_EULA=Y -e "MSSQL_SA_PASSWORD=$SA_PW" -e MSSQL_PID=Developer "$IMG" >/dev/null || { echo "no se pudo iniciar SQL Server"; exit 2; }
for i in $(seq 1 60); do sq -Q "SELECT 1" >/dev/null 2>&1 && break; sleep 2; done
sq -Q "SELECT @@VERSION" -h -1 | head -2
iconv -f UTF-16LE -t UTF-8 database/reference/GlucoLume_DB_v5.sql | sed '1s/^\xEF\xBB\xBF//' > /tmp/v5_utf8.sql
docker exec "$NAME" mkdir -p /tmp/sql
docker cp /tmp/v5_utf8.sql "$NAME":/tmp/sql/v5.sql
for f in database/reference/*.sql database/reference/MATRIZ.SQL; do docker cp "$f" "$NAME":/tmp/sql/"$(basename "$f")"; done

echo "== 1. Esquema v5 en una base nueva (Modern_Spanish_CI_AS)"
sq -Q "CREATE DATABASE [GlucoLume] COLLATE Modern_Spanish_CI_AS" && ok "CREATE DATABASE"
sq -i /tmp/sql/v5.sql >/tmp/v5.out 2>&1 && ok "GlucoLume_DB_v5.sql se ejecuta sin errores" || { bad "v5 falló"; tail -5 /tmp/v5.out; }
n=$(sq -d GlucoLume -h -1 -W -Q "SET NOCOUNT ON; SELECT COUNT(*) FROM sys.tables WHERE name<>'sysdiagrams'" | tr -d '[:space:]'); echo "   tablas: $n"
sq -d GlucoLume -h -1 -W -Q "SET NOCOUNT ON; SELECT COUNT(*) FROM sys.indexes WHERE name LIKE 'IX[_]%' OR name LIKE 'UX[_]%'" | tr -d ' ' | sed 's/^/   índices IX_*+UX_*: /'
[ "$(sq -d GlucoLume -h -1 -W -Q "SET NOCOUNT ON; SELECT COUNT(*) FROM sys.tables WHERE name='PuenteCredencial'" | tr -d '[:space:]')" = 1 ] && ok "v5 trae dbo.PuenteCredencial" || bad "v5 sin PuenteCredencial"
sq -d GlucoLume -i /tmp/sql/MATRIZ.SQL >/dev/null 2>&1 && ok "MATRIZ.SQL (matriz global de referencia)" || bad "MATRIZ.SQL"

echo "== 2. Estado heredado de la base real: cuenta de la API en db_datareader/db_datawriter"
sq -Q "CREATE LOGIN glucolume_app WITH PASSWORD='$API_PW', CHECK_POLICY=OFF; CREATE LOGIN glucolume_jobs WITH PASSWORD='$JOBS_PW', CHECK_POLICY=OFF;" && ok "logins sintéticos"
sq -d GlucoLume -Q "CREATE USER glucolume_app FOR LOGIN glucolume_app; ALTER ROLE db_datareader ADD MEMBER glucolume_app; ALTER ROLE db_datawriter ADD MEMBER glucolume_app; GRANT EXECUTE TO glucolume_app;" && ok "glucolume_app con roles fijos (como la base real)"
# Dato sintético de auditoría para comprobar que se puede (antes) y no se puede (después) borrar
sq -d GlucoLume -Q "INSERT INTO dbo.Auditoria (idAuditoria,tipoEvento,accion,resultado,fechaHora) VALUES (NEWID(),N'CRUD',N'SINTETICO',N'EXITO',SYSDATETIME())" && ok "evento de auditoría sintético"
expect_allowed sqa -Q "DELETE TOP (0) FROM dbo.Institucion" && ok "ANTES: la API puede borrar Institucion (riesgo H-02 reproducido)" || bad "ANTES: debía poder"
expect_allowed sqa -Q "DELETE TOP (0) FROM dbo.Auditoria" && ok "ANTES: la API puede borrar Auditoria (riesgo GL-03 reproducido)" || bad "ANTES: debía poder"

echo "== 3. Permisos de mínimo privilegio (GlucoLume_permisos.sql)"
sq -d GlucoLume -i /tmp/sql/GlucoLume_permisos.sql -v API_LOGIN=glucolume_app JOBS_LOGIN=glucolume_jobs CONFIRMAR=APLICAR_PERMISOS_GLUCOLUME >/tmp/perm.out 2>&1 && ok "permisos aplicados" || { bad "permisos"; tail -8 /tmp/perm.out; }
sq -d GlucoLume -i /tmp/sql/GlucoLume_permisos.sql -v API_LOGIN=glucolume_app JOBS_LOGIN=glucolume_jobs CONFIRMAR=APLICAR_PERMISOS_GLUCOLUME >/dev/null 2>&1 && ok "idempotente: segunda ejecución sin errores" || bad "segunda ejecución"
sq -d GlucoLume -i /tmp/sql/GlucoLume_permisos.sql -v API_LOGIN=glucolume_app JOBS_LOGIN=glucolume_jobs CONFIRMAR=NO >/dev/null 2>&1 && bad "sin CONFIRMAR exacto no debía ejecutar" || ok "sin CONFIRMAR exacto no ejecuta nada"
echo "   con db_datawriter aún presente, DELETE ajeno sigue posible (por eso existe el paso aparte):"
expect_allowed sqa -Q "DELETE TOP (0) FROM dbo.Institucion" && ok "con rol fijo todavía puede borrar Institucion (esperado antes del paso 4)" || bad "esperado permitido"
expect_denied sqa -Q "DELETE TOP (0) FROM dbo.Auditoria" && ok "el DENY sobre Auditoria prevalece incluso sobre db_datawriter" || bad "DENY Auditoria"
expect_denied sqa -Q "UPDATE TOP (0) dbo.Auditoria SET observacion=observacion" && ok "UPDATE de Auditoria rechazado (229)" || bad "UPDATE Auditoria"

echo "== 4. Quitar roles fijos (paso aparte y reversible)"
sq -d GlucoLume -i /tmp/sql/GlucoLume_permisos_quitar_roles_fijos.sql -v API_LOGIN=glucolume_app CONFIRMAR=QUITAR_ROLES_FIJOS_GLUCOLUME >/tmp/qrf.out 2>&1 && ok "roles fijos quitados" || { bad "quitar roles"; tail -5 /tmp/qrf.out; }
[ "$(sq -d GlucoLume -h -1 -W -Q "SET NOCOUNT ON; SELECT COUNT(*) FROM sys.database_role_members rm JOIN sys.database_principals r ON r.principal_id=rm.role_principal_id JOIN sys.database_principals m ON m.principal_id=rm.member_principal_id WHERE m.name='glucolume_app' AND r.name IN ('db_datareader','db_datawriter','db_owner')" | tr -d '[:space:]')" = 0 ] && ok "la API ya no es miembro de db_datareader/db_datawriter/db_owner" || bad "roles fijos siguen"
for t in Institucion PerfilMedicion Grupo Dispositivo; do
  if sq -d GlucoLume -h -1 -Q "SET NOCOUNT ON; SELECT 1 FROM sys.tables WHERE name='$t'" | grep -q 1; then
    expect_denied sqa -Q "DELETE TOP (0) FROM dbo.$t" && ok "DELETE $t rechazado (229)" || bad "DELETE $t debía rechazarse"
  fi
done
for t in AuditoriaTecnicaMedicion CodigoRecuperacionMfa ConsentimientoUsuario CredencialLocal EnvioResultado FactorMfa IdentidadExterna Medicion MedicionReferenciaCapilar MuestraSensor ReglaMatriz SesionUsuario TokenCuenta Usuario; do
  expect_allowed sqa -Q "DELETE TOP (0) FROM dbo.$t" && ok "DELETE $t permitido (el código lo necesita)" || bad "DELETE $t debía permitirse"
done
for t in Auditoria AuditoriaContexto; do
  expect_denied sqa -Q "DELETE TOP (0) FROM dbo.$t" && ok "DELETE $t rechazado" || bad "DELETE $t"
  expect_denied sqa -Q "UPDATE TOP (0) dbo.$t SET idAuditoria = idAuditoria" && ok "UPDATE $t rechazado" || bad "UPDATE $t"
done
expect_allowed sqa -Q "SELECT TOP (1) * FROM dbo.Usuario" && ok "SELECT sobre el esquema (rol_glucolume_api)" || bad "SELECT"
expect_allowed sqa -Q "BEGIN TRAN; INSERT INTO dbo.Auditoria (idAuditoria,tipoEvento,accion,resultado,fechaHora) VALUES (NEWID(),N'CRUD',N'X',N'EXITO',SYSDATETIME()); ROLLBACK" && ok "INSERT en Auditoria permitido" || bad "INSERT Auditoria"
expect_denied sqa -Q "CREATE TABLE dbo.zz(x int)" && ok "la API no puede cambiar el esquema (CREATE TABLE)" || bad "CREATE TABLE"
expect_denied sqa -Q "ALTER TABLE dbo.Usuario ADD zz int" && ok "la API no puede ALTER TABLE" || bad "ALTER TABLE"
[ "$(sq -d GlucoLume -h -1 -W -Q "SET NOCOUNT ON; SELECT COUNT(*) FROM sys.columns WHERE object_id=OBJECT_ID('dbo.Usuario') AND name='zz'" | tr -d '[:space:]')" = 0 ] && ok "el esquema no cambió" || bad "el esquema cambió"
echo "== 5. Script de verificación del proyecto"
sq -d GlucoLume -i /tmp/sql/GlucoLume_permisos_verificar.sql -v API_LOGIN=glucolume_app -W >/tmp/ver.out 2>&1; cat /tmp/ver.out
grep -q "Filas de auditoria sin cambios: SI" /tmp/ver.out && ok "verificar: auditoría sin cambios" || bad "verificar: control"
grep -q "DELETE Institucion (no debe poder).*rechazado 229" /tmp/ver.out && ok "verificar: DELETE Institucion rechazado" || bad "verificar Institucion"
grep -q "DELETE SesionUsuario (si debe poder).*permitido" /tmp/ver.out && ok "verificar: DELETE SesionUsuario permitido" || bad "verificar SesionUsuario"
echo "== 6. Cuenta de conservación"
expect_allowed sqj -Q "DELETE TOP (0) FROM dbo.Auditoria" && ok "conservación puede depurar Auditoria" || bad "jobs Auditoria"
expect_denied sqj -Q "DELETE TOP (0) FROM dbo.Institucion" && ok "conservación no puede borrar Institucion" || bad "jobs Institucion"
expect_denied sqj -Q "DROP TABLE dbo.Usuario" && ok "conservación no puede cambiar el esquema" || bad "jobs DROP"
echo "== 7. H-16: PuenteCredencial con la API"
expect_allowed sqa -Q "SELECT TOP (0) * FROM dbo.PuenteCredencial" && ok "API lee PuenteCredencial" || bad "SELECT PuenteCredencial"
expect_denied sqa -Q "DELETE TOP (0) FROM dbo.PuenteCredencial" && ok "API no puede borrar credenciales de puente" || bad "DELETE PuenteCredencial"
expect_denied sqa -Q "UPDATE TOP (0) dbo.PuenteCredencial SET tokenHash=tokenHash" && ok "API no puede cambiar tokenHash" || bad "UPDATE tokenHash"
expect_allowed sqa -Q "UPDATE TOP (0) dbo.PuenteCredencial SET fechaUltimoUso=fechaUltimoUso" && ok "API puede anotar fechaUltimoUso (GRANT de columna)" || bad "UPDATE fechaUltimoUso"
expect_denied sqa -Q "INSERT INTO dbo.PuenteCredencial (idPuenteCredencial) VALUES (NEWID())" && ok "API no puede crear credenciales" || bad "INSERT PuenteCredencial"
expect_allowed sqj -Q "UPDATE TOP (0) dbo.PuenteCredencial SET fechaRevocacion=fechaRevocacion, tokenHash=tokenHash" && ok "conservación (CLI bridgeTokens) puede revocar/rotar: UPDATE" || bad "jobs UPDATE PuenteCredencial"
expect_allowed sqj -Q "BEGIN TRAN; INSERT INTO dbo.PuenteCredencial (nombre,tokenHash,codigoDispositivo,fechaExpiracion) VALUES (N'sintetico',REPLICATE('a',64),N'DISP-SINTETICO',DATEADD(day,30,SYSDATETIME())); ROLLBACK" && ok "conservación puede crear credenciales: INSERT" || bad "jobs INSERT PuenteCredencial"
expect_denied sqj -Q "DELETE TOP (0) FROM dbo.PuenteCredencial" && ok "nadie borra credenciales: se revocan (mínimo privilegio, DELETE no concedido)" || bad "jobs DELETE PuenteCredencial"
echo "== 8. Reversión del paso 4 (restaurar roles fijos) y repetición"
sq -d GlucoLume -i /tmp/sql/GlucoLume_permisos_restaurar_roles_fijos.sql -v CONFIRMAR=RESTAURAR_ROLES_FIJOS_GLUCOLUME >/tmp/rest.out 2>&1 && ok "restaurar ejecutado" || { bad "restaurar"; tail -3 /tmp/rest.out; }
[ "$(sq -d GlucoLume -h -1 -W -Q "SET NOCOUNT ON; SELECT COUNT(*) FROM sys.database_role_members rm JOIN sys.database_principals r ON r.principal_id=rm.role_principal_id JOIN sys.database_principals m ON m.principal_id=rm.member_principal_id WHERE m.name='glucolume_app' AND r.name IN ('db_datareader','db_datawriter')" | tr -d '[:space:]')" = 2 ] && ok "restaurados db_datareader y db_datawriter" || bad "restaurar no devolvió los roles"
expect_denied sqa -Q "DELETE TOP (0) FROM dbo.Auditoria" && ok "aun restaurados, la auditoría sigue protegida por el DENY" || bad "DENY tras restaurar"
sq -d GlucoLume -i /tmp/sql/GlucoLume_permisos_quitar_roles_fijos.sql -v API_LOGIN=glucolume_app CONFIRMAR=QUITAR_ROLES_FIJOS_GLUCOLUME >/dev/null 2>&1 && ok "quitar otra vez (idempotente)" || bad "quitar 2"
echo "== 9. Reversión total de permisos"
sq -d GlucoLume -i /tmp/sql/GlucoLume_permisos_restaurar_roles_fijos.sql -v CONFIRMAR=RESTAURAR_ROLES_FIJOS_GLUCOLUME >/dev/null 2>&1
sq -d GlucoLume -i /tmp/sql/GlucoLume_permisos_revertir.sql -v CONFIRMAR=REVERTIR_PERMISOS_GLUCOLUME >/tmp/rev.out 2>&1 && ok "revertir permisos" || { bad "revertir"; tail -5 /tmp/rev.out; }
[ "$(sq -d GlucoLume -h -1 -W -Q "SET NOCOUNT ON; SELECT COUNT(*) FROM sys.database_principals WHERE name IN ('rol_glucolume_api','rol_glucolume_retencion')" | tr -d '[:space:]')" = 0 ] && ok "roles de GlucoLume eliminados" || bad "roles siguen"
expect_allowed sqa -Q "DELETE TOP (0) FROM dbo.Auditoria" && ok "estado previo recuperado (la API vuelve a poder modificar auditoría)" || bad "estado previo"
echo "== 10. Datos intactos tras todo el ciclo"
[ "$(sq -d GlucoLume -h -1 -W -Q "SET NOCOUNT ON; SELECT COUNT(*) FROM dbo.Auditoria WHERE accion=N'SINTETICO'" | tr -d '[:space:]')" = 1 ] && ok "el evento sintético sigue ahí (ningún script borra datos)" || bad "datos"
sq -d GlucoLume -i /tmp/sql/GlucoLume_permisos.sql -v API_LOGIN=glucolume_app JOBS_LOGIN=glucolume_jobs CONFIRMAR=APLICAR_PERMISOS_GLUCOLUME >/dev/null 2>&1 && ok "permisos reaplicados tras revertir" || bad "reaplicar"

echo "== 11. H-16: migración sobre una base instalada antes (sin PuenteCredencial)"
sq -d GlucoLume -Q "DROP TABLE dbo.PuenteCredencial" && ok "se simula una base anterior (tabla ausente)"
sq -d GlucoLume -i /tmp/sql/GlucoLume_agregar_puente_credencial.sql -v CONFIRMAR=NO >/dev/null 2>&1; [ "$(sq -d GlucoLume -h -1 -W -Q "SET NOCOUNT ON; SELECT COUNT(*) FROM sys.tables WHERE name='PuenteCredencial'" | tr -d '[:space:]')" = 0 ] && ok "sin CONFIRMAR exacto no crea nada" || bad "creó sin confirmar"
sq -d GlucoLume -i /tmp/sql/GlucoLume_agregar_puente_credencial.sql -v CONFIRMAR=AGREGAR_PUENTE_CREDENCIAL >/tmp/mig.out 2>&1 && ok "migración aplicada" || { bad "migración"; tail -5 /tmp/mig.out; }
sq -d GlucoLume -i /tmp/sql/GlucoLume_agregar_puente_credencial.sql -v CONFIRMAR=AGREGAR_PUENTE_CREDENCIAL >/dev/null 2>&1 && ok "migración idempotente" || bad "migración 2"
sq -d GlucoLume -i /tmp/sql/GlucoLume_permisos.sql -v API_LOGIN=glucolume_app JOBS_LOGIN=glucolume_jobs CONFIRMAR=APLICAR_PERMISOS_GLUCOLUME >/dev/null 2>&1 && ok "permisos reaplicados cubren la tabla nueva" || bad "permisos tras migración"
expect_denied sqa -Q "DELETE TOP (0) FROM dbo.PuenteCredencial" && ok "API sin DELETE en la tabla migrada" || bad "DELETE tras migración"
# Estructura idéntica a la de v5: se compara contra una base nueva con v5
sq -Q "CREATE DATABASE [GlucoLumeRef] COLLATE Modern_Spanish_CI_AS" && sed 's/\[GlucoLume\]/[GlucoLumeRef]/' /tmp/v5_utf8.sql > /tmp/v5_ref.sql && docker cp /tmp/v5_ref.sql "$NAME":/tmp/sql/v5ref.sql && sq -i /tmp/sql/v5ref.sql >/dev/null 2>&1
cols() { sq -d "$1" -h -1 -W -Q "SET NOCOUNT ON; SELECT c.name+'|'+TYPE_NAME(c.user_type_id)+'|'+CAST(c.max_length AS varchar)+'|'+CAST(c.is_nullable AS varchar) FROM sys.columns c WHERE c.object_id=OBJECT_ID('dbo.PuenteCredencial') ORDER BY c.column_id"; }
idx()  { sq -d "$1" -h -1 -W -Q "SET NOCOUNT ON; SELECT i.name+'|'+CAST(i.is_unique AS varchar)+'|'+ISNULL(i.filter_definition,'') FROM sys.indexes i WHERE i.object_id=OBJECT_ID('dbo.PuenteCredencial') AND i.name IS NOT NULL ORDER BY i.name"; }
chk()  { sq -d "$1" -h -1 -W -Q "SET NOCOUNT ON; SELECT name+'|'+definition FROM sys.check_constraints WHERE parent_object_id=OBJECT_ID('dbo.PuenteCredencial') ORDER BY name"; }
[ "$(cols GlucoLume)" = "$(cols GlucoLumeRef)" ] && ok "columnas de la tabla migrada = v5" || bad "columnas difieren"
[ "$(idx GlucoLume)" = "$(idx GlucoLumeRef)" ] && ok "índices de la tabla migrada = v5" || bad "índices difieren"
[ "$(chk GlucoLume)" = "$(chk GlucoLumeRef)" ] && ok "CHECK de la tabla migrada = v5" || bad "CHECK difieren"

echo
echo "RESUMEN: $pass correctas, $fail con falla"
[ "${KEEP:-0}" = 1 ] || docker rm -f "$NAME" >/dev/null 2>&1
[ "$fail" = 0 ]
