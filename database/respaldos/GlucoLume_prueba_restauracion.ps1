# GlucoLume - Restauración de prueba de un respaldo cifrado en una instancia DESCARTABLE (GL-07)
#
# Descifra el respaldo más reciente (o -Archivo), levanta un SQL Server 2025 Developer en Docker SIN volúmenes y solo en 127.0.0.1, lo
# restaura con otro nombre, compara el esquema con `python -m app.cli.schemaCheck` y cuenta las tablas restauradas. Al terminar borra el
# contenedor y el .bak descifrado. No toca la instancia real. Mensual (o tras cambiar el procedimiento de respaldo).
#
#   powershell -File GlucoLume_prueba_restauracion.ps1 [-Archivo C:\GlucoLumeRespaldos\GlucoLume_AAAAMMDD_HHMMSS.bak.gpg]

param(
    [string]$Archivo,
    [string]$Destino = "C:\GlucoLumeRespaldos",
    [string]$Clave = "C:\GlucoLumeRespaldos\clave_respaldo.dpapi",
    [string]$Gpg = "C:\Program Files\Git\usr\bin\gpg.exe",
    [string]$Backend = (Join-Path $PSScriptRoot "..\..\backend"),
    [string]$Imagen = "mcr.microsoft.com/mssql/server:2025-latest",
    [int]$Puerto = 14399
)
$ErrorActionPreference = "Stop"
$contenedor = "glucolume-prueba-restauracion"
$log = Join-Path $Destino "restauracion.log"
function Registrar([string]$texto) { "$(Get-Date -Format s) $texto" | Tee-Object -FilePath $log -Append }
if (-not $Archivo) { $Archivo = (Get-ChildItem $Destino -Filter "GlucoLume_*.bak.gpg" | Sort-Object Name -Descending | Select-Object -First 1).FullName }
if (-not $Archivo) { Registrar "ERROR: no hay respaldos cifrados en $Destino"; exit 1 }
$bak = Join-Path $env:TEMP ("glucolume_prueba_" + [guid]::NewGuid().ToString("N") + ".bak")
$sa = "Pr1!" + [Convert]::ToBase64String((1..24 | ForEach-Object { [byte](Get-Random -Maximum 256) })).Replace("/", "x").Replace("+", "y").Replace("=", "")
try {
    $frase = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR((Get-Content $Clave | ConvertTo-SecureString)))
    $frase | & $Gpg --batch --yes --quiet --pinentry-mode loopback --passphrase-fd 0 --decrypt --output $bak $Archivo
    Remove-Variable frase
    if ($LASTEXITCODE -ne 0) { throw "No se pudo descifrar $Archivo." }

    docker rm -f $contenedor 2>$null | Out-Null
    docker run -d --name $contenedor --label descartable=true -e ACCEPT_EULA=Y -e MSSQL_PID=Developer -e "MSSQL_SA_PASSWORD=$sa" -p "127.0.0.1:${Puerto}:1433" $Imagen | Out-Null
    $listo = $false
    for ($i = 0; $i -lt 60 -and -not $listo; $i++) {
        Start-Sleep -Seconds 3
        docker exec $contenedor /opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -P $sa -Q "SELECT 1" 2>$null | Out-Null
        $listo = ($LASTEXITCODE -eq 0)
    }
    if (-not $listo) { throw "La instancia descartable no arrancó." }
    docker exec -u 0 $contenedor mkdir -p /var/opt/mssql/backup | Out-Null
    docker cp $bak "${contenedor}:/var/opt/mssql/backup/prueba.bak" | Out-Null
    docker exec -u 0 $contenedor chown mssql /var/opt/mssql/backup/prueba.bak | Out-Null
    $archivos = docker exec $contenedor /opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -P $sa -h -1 -W -Q "SET NOCOUNT ON; RESTORE FILELISTONLY FROM DISK='/var/opt/mssql/backup/prueba.bak'" |
        Where-Object { $_ -match '\S' } | ForEach-Object { ($_ -split '\s+')[0] }
    $mover = ($archivos | Select-Object -First 2 | ForEach-Object -Begin { $n = 0 } -Process { $n++; "MOVE N'$_' TO N'/var/opt/mssql/data/GlucoLume_Prueba_$n'" }) -join ", "
    docker exec $contenedor /opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -P $sa -b -Q "RESTORE DATABASE GlucoLume_Prueba FROM DISK='/var/opt/mssql/backup/prueba.bak' WITH CHECKSUM, $mover" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Falló RESTORE DATABASE." }
    $tablas = (docker exec $contenedor /opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -P $sa -h -1 -W -Q "SET NOCOUNT ON; SELECT COUNT(*) FROM GlucoLume_Prueba.sys.tables WHERE is_ms_shipped = 0") | Select-Object -First 1
    $url = "mssql+pyodbc://sa:" + [uri]::EscapeDataString($sa) + "@127.0.0.1:$Puerto/GlucoLume_Prueba?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"
    Push-Location $Backend
    $env:GLUCOLUME_ENV_FILE = Join-Path $Backend "tests\test.env"
    $esquema = & python -m app.cli.schemaCheck --url $url 2>$null | Select-Object -Last 1
    $codigo = $LASTEXITCODE
    Pop-Location
    Registrar "Restauración de prueba de $(Split-Path $Archivo -Leaf): $($tablas.Trim()) tablas; schemaCheck: $esquema"
    if ($codigo -ne 0) { throw "El esquema restaurado difiere del vigente." }
    exit 0
} catch {
    Registrar "ERROR: $($_.Exception.Message)"
    exit 1
} finally {
    docker rm -f $contenedor 2>$null | Out-Null
    Remove-Item $bak -ErrorAction SilentlyContinue
    Remove-Item Env:\GLUCOLUME_ENV_FILE -ErrorAction SilentlyContinue
}
