# GlucoLume - Copia de la base de Docker en la instancia de Windows (localhost\GLUCOLUME)
#
# La base principal es la del contenedor (la que usa el backend); esta copia la replica en Windows, en un solo sentido. Pensado para el
# Programador de tareas (tarea «GlucoLume - Copia desde Docker», cada 5 minutos):
#   1. BACKUP DATABASE ... WITH COPY_ONLY, CHECKSUM dentro del contenedor (sa con la contraseña que ya tiene el contenedor: no pasa por
#      Windows) y RESTORE VERIFYONLY;
#   2. docker cp del .bak a <Destino>\copia_docker (carpeta con acceso para el servicio MSSQL$GLUCOLUME) y se borra del contenedor;
#   3. RESTORE ... WITH REPLACE sobre la base de Windows (autenticación de Windows), moviendo los archivos a los que ya usaba;
#   4. la deja en READ_ONLY: es una copia, lo que se escriba ahí se perdería en la próxima copia;
#   5. borra el .bak en claro.
# COPY_ONLY: no altera la cadena de respaldos del contenedor. La copia puede ir hasta un intervalo atrasada respecto de Docker.
# Registro en <Destino>\copia_docker.log (sin claves). Sale con 1 ante cualquier error; la base de Windows queda como estaba salvo que falle
# el RESTORE mismo (en ese caso la próxima ejecución la vuelve a restaurar, y está el respaldo diario cifrado).
#
#   powershell -File GlucoLume_copia_docker.ps1 [-Contenedor glucolume-db-1] [-Instancia localhost\GLUCOLUME] [-Base GlucoLume]
#                                               [-Destino C:\GlucoLumeRespaldos]

param(
    [string]$Contenedor = "glucolume-db-1",
    [string]$Instancia = "localhost\GLUCOLUME",
    [string]$Base = "GlucoLume",
    [string]$Destino = "C:\GlucoLumeRespaldos"
)
$ErrorActionPreference = "Stop"
$log = Join-Path $Destino "copia_docker.log"
function Registrar([string]$texto) { "$(Get-Date -Format s) $texto" | Out-File -FilePath $log -Append -Encoding utf8; $texto }

$carpeta = Join-Path $Destino "copia_docker"
$bakContenedor = "/var/opt/mssql/backup/copia_windows.bak"
$bak = Join-Path $carpeta "copia_windows.bak"

try {
    $salud = & docker inspect -f "{{.State.Health.Status}}" $Contenedor 2>$null
    if ($LASTEXITCODE -ne 0 -or $salud -ne "healthy") { throw "El contenedor $Contenedor no está en marcha y sano (estado: '$salud')." }
    New-Item -ItemType Directory -Force $carpeta | Out-Null

    # 1. Respaldo dentro del contenedor.
    $sql = "BACKUP DATABASE [$Base] TO DISK = N'$bakContenedor' WITH COPY_ONLY, CHECKSUM, INIT; RESTORE VERIFYONLY FROM DISK = N'$bakContenedor' WITH CHECKSUM;"
    # El SQL viaja en base64 y la clave por SQLCMDPASSWORD: PowerShell 5.1 rompe las comillas dobles anidadas al llamar a docker y, por
    # la entrada estándar, antepone un BOM que sqlcmd toma como parte del SQL.
    $sql64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($sql))
    & docker exec $Contenedor bash -c 'mkdir -p /var/opt/mssql/backup && echo $1 | base64 -d | SQLCMDPASSWORD=$MSSQL_SA_PASSWORD /opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -b -i /dev/stdin' _ $sql64 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Falló BACKUP o RESTORE VERIFYONLY en el contenedor (código $LASTEXITCODE)." }

    # 2. Traerlo a Windows.
    & docker cp "${Contenedor}:$bakContenedor" $bak | Out-Null
    $copiado = $LASTEXITCODE
    & docker exec $Contenedor rm -f $bakContenedor | Out-Null
    if ($copiado -ne 0 -or -not (Test-Path $bak)) { throw "Falló docker cp del respaldo." }

    # 3. Restaurar sobre la base de Windows, en los mismos archivos que ya usa (o en la carpeta de datos por defecto si no existe).
    $archivos = & sqlcmd -S $Instancia -E -C -b -h -1 -W -s "|" -Q "SET NOCOUNT ON; RESTORE FILELISTONLY FROM DISK = N'$bak';"
    if ($LASTEXITCODE -ne 0) { throw "No se pudo leer el contenido del respaldo (RESTORE FILELISTONLY)." }
    $actuales = & sqlcmd -S $Instancia -E -C -b -h -1 -W -s "|" -Q "SET NOCOUNT ON; SELECT type_desc, physical_name FROM sys.master_files WHERE database_id = DB_ID(N'$Base');"
    $datos = & sqlcmd -S $Instancia -E -C -b -h -1 -W -Q "SET NOCOUNT ON; SELECT CAST(SERVERPROPERTY('InstanceDefaultDataPath') AS nvarchar(400));"
    $carpetaDatos = ($datos | Where-Object { $_ } | Select-Object -First 1).Trim()
    $mover = @()
    foreach ($linea in $archivos | Where-Object { $_ -match '\|' }) {
        $campos = $linea.Split("|")
        $logico = $campos[0]; $tipo = $campos[2]   # LogicalName | PhysicalName | Type (D datos, L registro) | ...
        $tipoActual = if ($tipo -eq "L") { "LOG" } else { "ROWS" }
        $existente = $actuales | Where-Object { $_ -like "$tipoActual|*" } | Select-Object -First 1
        $fisico = if ($existente) { $existente.Split("|")[1] } else { Join-Path $carpetaDatos ($(if ($tipo -eq "L") { "${Base}_log.ldf" } else { "$Base.mdf" })) }
        $mover += "MOVE N'$logico' TO N'$fisico'"
    }
    if ($mover.Count -lt 2) { throw "El respaldo no trae los archivos esperados (datos y registro)." }

    $restaurar = "IF DB_ID(N'$Base') IS NOT NULL ALTER DATABASE [$Base] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; " +
                 "RESTORE DATABASE [$Base] FROM DISK = N'$bak' WITH REPLACE, CHECKSUM, $($mover -join ', '); " +
                 "ALTER DATABASE [$Base] SET MULTI_USER; ALTER DATABASE [$Base] SET READ_ONLY WITH ROLLBACK IMMEDIATE;"
    & sqlcmd -S $Instancia -E -C -b -Q $restaurar | Out-Null
    $restaurado = $LASTEXITCODE
    if ($restaurado -ne 0) {
        & sqlcmd -S $Instancia -E -C -Q "IF DB_ID(N'$Base') IS NOT NULL ALTER DATABASE [$Base] SET MULTI_USER;" | Out-Null
        throw "Falló el RESTORE en $Instancia (código $restaurado)."
    }
    Registrar "Copia actualizada: $Contenedor -> $Instancia\$Base ($([math]::Round((Get-Item $bak).Length / 1MB, 1)) MB, solo lectura)"
    exit 0
} catch {
    Registrar "ERROR: $($_.Exception.Message)"
    exit 1
} finally {
    # 5. El .bak en claro no se conserva.
    Remove-Item $bak -ErrorAction SilentlyContinue
}
