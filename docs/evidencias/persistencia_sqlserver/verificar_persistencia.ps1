# Verificación de persistencia de SQL Server (GlucoLume) para las capturas del TIF. SOLO LECTURA.
# No reinicia ni recrea contenedores, no borra volúmenes, no modifica datos ni esquema y no muestra secretos
# (las contraseñas se enmascaran; sqlcmd toma la de sa de la variable SQLCMDPASSWORD del propio contenedor).
#
#   powershell -ExecutionPolicy Bypass -File docs\evidencias\persistencia_sqlserver\verificar_persistencia.ps1          # todo
#   powershell -ExecutionPolicy Bypass -File docs\evidencias\persistencia_sqlserver\verificar_persistencia.ps1 -Seccion 3  # una captura
param([int]$Seccion = 0)

$ErrorActionPreference = 'Continue'
$repo = Resolve-Path (Join-Path $PSScriptRoot '..\..\..')
$sqlcmd = '/opt/mssql-tools18/bin/sqlcmd'

function Titulo($n, $texto) { Write-Host ""; Write-Host "== $n. $texto" -ForegroundColor Cyan; Write-Host ("   " + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')) }
function Sql($consulta, $base = 'master') { docker exec glucolume-db-1 $sqlcmd -S localhost -U sa -C -W -s '|' -d $base -Q "SET NOCOUNT ON; $consulta" }
function Mostrar($n) { return ($Seccion -eq 0 -or $Seccion -eq $n) }

if (Mostrar 1) {
    Titulo 1 'Contenedores activos'
    docker ps --filter 'name=glucolume-' --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.CreatedAt}}'
}

if (Mostrar 2) {
    Titulo 2 'Conexión backend -> SQL Server (sin secretos)'
    docker exec glucolume-backend-1 env | Select-String '^DB_' | ForEach-Object {
        $l = $_.Line; if ($l -match '^(DB_[A-Z_]*PASSWORD)=') { "$($matches[1])=***" } else { $l } }
    Write-Host '-- Sesiones abiertas en SQL Server por el backend (login de aplicación, no sa):'
    Sql "SELECT s.login_name, DB_NAME(s.database_id) AS base, c.client_net_address, s.program_name, COUNT(*) AS sesiones FROM sys.dm_exec_sessions s JOIN sys.dm_exec_connections c ON c.session_id = s.session_id WHERE s.is_user_process = 1 AND s.login_name <> 'sa' GROUP BY s.login_name, s.database_id, c.client_net_address, s.program_name"
    Write-Host '-- IP del backend en la red de datos:'
    docker inspect glucolume-backend-1 --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{$v.IPAddress}}{{println}}{{end}}'
    Write-Host '-- Rol y permisos efectivos de glucolume_app:'
    Sql "SELECT r.name AS rol, m.name AS miembro FROM sys.database_role_members rm JOIN sys.database_principals r ON r.principal_id = rm.role_principal_id JOIN sys.database_principals m ON m.principal_id = rm.member_principal_id WHERE m.name = 'glucolume_app'" 'GlucoLume'
    Sql "EXECUTE AS USER = 'glucolume_app'; SELECT USER_NAME() AS usuario, HAS_PERMS_BY_NAME('dbo.Medicion','OBJECT','SELECT') AS select_Medicion, HAS_PERMS_BY_NAME('dbo.Medicion','OBJECT','INSERT') AS insert_Medicion, HAS_PERMS_BY_NAME('dbo.Dispositivo','OBJECT','SELECT') AS select_Dispositivo, HAS_PERMS_BY_NAME('dbo.Auditoria','OBJECT','UPDATE') AS update_Auditoria, HAS_PERMS_BY_NAME(DB_NAME(),'DATABASE','CREATE TABLE') AS create_table, IS_ROLEMEMBER('db_owner') AS db_owner; REVERT;" 'GlucoLume'
}

if (Mostrar 3) {
    Titulo 3 'Volumen persistente de SQL Server'
    docker inspect glucolume-db-1 --format '{{range .Mounts}}tipo={{.Type}} volumen={{.Name}} destino={{.Destination}} escritura={{.RW}}{{println}}{{end}}'
    docker volume inspect glucolume_mssql-data --format 'volumen={{.Name}} driver={{.Driver}} creado={{.CreatedAt}} etiquetas={{json .Labels}}'
    docker inspect glucolume-db-1 --format 'contenedor={{.Name}} id={{slice .Id 0 12}} creado={{.Created}} iniciado={{.State.StartedAt}}'
    Write-Host '-- Archivos físicos de GlucoLume según SQL Server y en el disco del volumen:'
    Sql "SELECT name, type_desc, physical_name, size * 8 / 1024 AS size_mb FROM sys.master_files WHERE DB_NAME(database_id) = 'GlucoLume'"
    docker exec glucolume-db-1 sh -c 'df -h /var/opt/mssql | tail -1; ls -l /var/opt/mssql/data/GlucoLume*'
    Write-Host '-- Identidad persistida en master (nombre del contenedor original) frente al contenedor actual:'
    Sql "SELECT @@SERVERNAME AS servername_guardado_en_master, SERVERPROPERTY('MachineName') AS contenedor_actual, SERVERPROPERTY('Edition') AS edicion, SERVERPROPERTY('ProductUpdateLevel') AS cu"
}

if (Mostrar 4) {
    Titulo 4 'Base GlucoLume y sus tablas'
    Sql "SELECT name, state_desc, recovery_model_desc, create_date FROM sys.databases WHERE name = 'GlucoLume'"
    Sql "SELECT s.name + '.' + t.name AS tabla, SUM(p.rows) AS filas FROM sys.tables t JOIN sys.schemas s ON s.schema_id = t.schema_id JOIN sys.partitions p ON p.object_id = t.object_id AND p.index_id IN (0, 1) GROUP BY s.name, t.name ORDER BY 1" 'GlucoLume'
}

if (Mostrar 5) {
    Titulo 5 'Mediciones registradas (consulta de solo lectura, sin datos personales)'
    # Se copia el .sql al contenedor (el pipe de PowerShell 5.1 altera la codificación) y se borra al terminar.
    docker cp (Join-Path $PSScriptRoot 'consulta_mediciones.sql') glucolume-db-1:/tmp/consulta_mediciones.sql | Out-Null
    docker exec glucolume-db-1 $sqlcmd -S localhost -U sa -C -W -s '|' -d GlucoLume -i /tmp/consulta_mediciones.sql
    docker exec -u 0 glucolume-db-1 rm -f /tmp/consulta_mediciones.sql
}

if (Mostrar 7) {
    Titulo 7 'Copia de seguridad externa (.bak) y su verificación'
    $bak = Get-ChildItem (Join-Path $repo 'respaldos\sqlserver\*.bak') -ErrorAction SilentlyContinue | Sort-Object LastWriteTime | Select-Object -Last 1
    if (-not $bak) { Write-Host 'No hay .bak en respaldos\sqlserver.'; return }
    $bak | Select-Object Name, Length, LastWriteTime | Format-Table -AutoSize | Out-String | Write-Host
    Write-Host ('SHA-256: ' + (Get-FileHash $bak.FullName -Algorithm SHA256).Hash)
    Write-Host ('Excluido de Git: ' + (git -C $repo check-ignore -v ("respaldos/sqlserver/" + $bak.Name)))
    # Se copia a /tmp del contenedor (fuera del volumen), se verifica y se borra la copia temporal.
    $tmp = '/tmp/verificar_' + $bak.Name
    docker cp $bak.FullName ("glucolume-db-1:" + $tmp) | Out-Null
    Sql "RESTORE VERIFYONLY FROM DISK = N'$tmp' WITH CHECKSUM"
    Sql "RESTORE FILELISTONLY FROM DISK = N'$tmp'" | ForEach-Object { ($_ -split '\|')[0..2] -join '|' }
    docker exec -u 0 glucolume-db-1 rm -f $tmp
}

if (Mostrar 8) {
    Titulo 8 'Origen físico de la medición (puente serie Bluetooth en este equipo)'
    Write-Host '-- Configuración del puente (bridge.env; el token se enmascara):'
    Get-Content (Join-Path $repo 'backend\acquisition\bridge\bridge.env') | ForEach-Object {
        if ($_ -match '^\s*([A-Z_]+)\s*=') { $clave = $matches[1]; if ($clave -match 'TOKEN|KEY|SECRET|PASS') { "$clave=***" } else { $_ } } }
    Write-Host '-- Puertos serie Bluetooth (SPP) emparejados; el prefijo de la MAC 98D331 es el habitual de los módulos HC-05/HC-06:'
    Get-CimInstance Win32_PnPEntity | Where-Object { $_.Name -match 'Bluetooth.*\(COM\d+\)' } | ForEach-Object {
        $mac = if ($_.PNPDeviceID -match '&([0-9A-F]{12})_') { $matches[1] } else { '' }
        '{0}  estado={1}  MAC remota={2}' -f $_.Name, $_.Status, $mac }
    Write-Host '-- Proceso del puente en ejecución:'
    Get-CimInstance Win32_Process -Filter "Name like 'python%'" | Where-Object { $_.CommandLine -match 'glucolume_bridge' } |
        ForEach-Object { 'PID {0}  iniciado {1}  {2}' -f $_.ProcessId, $_.CreationDate, ($_.CommandLine -replace '.*\\', '') }
    Write-Host '-- Pedidos del backend desde el arranque del contenedor (solo recuento por ruta; sin parámetros ni cabeceras):'
    docker logs glucolume-backend-1 2>&1 | Select-String '"(POST) (/api/v1/acquisition/[^ ?]+)' | ForEach-Object { $_.Matches[0].Groups[2].Value } |
        Group-Object | Select-Object Count, Name | Format-Table -AutoSize | Out-String | Write-Host
}