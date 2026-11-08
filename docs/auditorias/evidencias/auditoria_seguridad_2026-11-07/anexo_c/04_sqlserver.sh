#!/usr/bin/env bash
# Anexo C (auditoría 07/11/2026). DIAGNÓSTICO DE SOLO LECTURA de SQL Server.
# Solo consultas de catálogo (sys.*). No lee datos de pacientes, no crea ni modifica nada.
# Caso A: SQL Server en el contenedor "db" (perfil db de Compose). Usa MSSQL_SA_PASSWORD que ya está en el contenedor; no se imprime.
# Caso B: SQL Server externo (Windows u otro host). Ejecutar las mismas consultas allí con SSMS o sqlcmd -E; ver la sección B.
#
# Uso (caso A, desde el directorio del repo):   bash 04_sqlserver.sh A 2>&1 | tee "$HOME/diag_04_sql.txt"
#       (caso B, desde Ubuntu: solo prueba de alcance de red) bash 04_sqlserver.sh B HOST_O_IP [PUERTO=1433]
sec() { printf '\n===== %s =====\n' "$1"; }
MODO="${1:-A}"

if [ "$MODO" = "B" ]; then
  HOST="${2:?Indicar el host o IP de SQL Server}"; PUERTO="${3:-1433}"
  sec "11. Alcance de red desde el servidor Ubuntu hacia SQL Server externo"
  if timeout 5 bash -c "</dev/tcp/$HOST/$PUERTO" 2>/dev/null; then echo "TCP $HOST:$PUERTO: ALCANZABLE desde este equipo"; else echo "TCP $HOST:$PUERTO: no alcanzable (bien si la base solo debe ser accesible desde el backend o el host Docker)"; fi
  echo "MANUAL (en el equipo Windows): el puerto $PUERTO debe estar permitido solo desde la IP del servidor Ubuntu en el firewall de Windows, no desde toda la red."
  exit 0
fi

SQL_BASE='
SET NOCOUNT ON;
SELECT SERVERPROPERTY('ProductVersion') AS version, SERVERPROPERTY('Edition') AS edicion, SERVERPROPERTY('ProductLevel') AS nivel;
SELECT name, is_disabled FROM sys.server_principals WHERE name = N'sa';
SELECT COUNT(*) AS miembros_sysadmin FROM sys.server_role_members rm JOIN sys.server_principals r ON r.principal_id = rm.role_principal_id AND r.name = N'sysadmin';
SELECT name, value_in_use FROM sys.configurations WHERE name IN (N'xp_cmdshell', N'clr enabled', N'Ole Automation Procedures', N'remote admin connections', N'Database Mail XPs');
SELECT name, type_desc, is_disabled FROM sys.server_principals WHERE type IN ('S','U','G') AND name NOT LIKE '##%' ORDER BY name;
SELECT name, state_desc, recovery_model_desc FROM sys.databases;
SELECT auth_scheme, encrypt_option FROM sys.dm_exec_connections WHERE session_id = @@SPID;
'
# La contraseña va por la variable de entorno SQLCMDPASSWORD y no por -P: así no aparece en la lista de procesos (argv).
SQLCMD='SQLCMDPASSWORD="$MSSQL_SA_PASSWORD" /opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -b -W -s "|" -i /dev/stdin'
sec "11. SQL Server en el contenedor db (caso A)"
printf '%s' "$SQL_BASE" | docker compose exec -T db sh -c "$SQLCMD" 2>&1
echo "--- último respaldo registrado por base (fecha y tipo de cifrado):"
printf '%s' "SET NOCOUNT ON; SELECT d.name, MAX(b.backup_finish_date) AS ultimo, MAX(b.encryptor_type) AS cifrado FROM sys.databases d LEFT JOIN msdb.dbo.backupset b ON b.database_name = d.name GROUP BY d.name;" | docker compose exec -T db sh -c "$SQLCMD" 2>&1
echo "--- logins de la aplicación: ¿alguno es sysadmin?"
printf '%s' "SET NOCOUNT ON; SELECT name, IS_SRVROLEMEMBER('sysadmin', name) AS es_sysadmin FROM sys.server_principals WHERE name LIKE N'glucolume%';" | docker compose exec -T db sh -c "$SQLCMD" 2>&1
echo "(fin)"
