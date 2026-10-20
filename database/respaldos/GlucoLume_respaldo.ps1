# GlucoLume - Respaldo completo cifrado con retención (GL-07)
#
# SQL Server Express no cifra ni comprime respaldos y no tiene SQL Agent. Este script, pensado para el Programador de tareas de Windows:
#   1. BACKUP DATABASE ... WITH CHECKSUM (autenticación de Windows; la cuenta debe poder respaldar la base);
#   2. RESTORE VERIFYONLY ... WITH CHECKSUM;
#   3. cifra el .bak con GnuPG (AES-256, simétrico) usando la clave de GlucoLume_clave_respaldo.ps1 (DPAPI) y comprueba que se descifra
#      igual (SHA-256) antes de borrar el .bak en claro;
#   4. retención: conserva los diarios de los últimos -DiasDiarios días y uno por mes durante -MesesMensuales meses. Solo borra archivos
#      con el patrón de este script (GlucoLume_AAAAMMDD_HHMMSS.bak.gpg), nunca el último, y solo si el respaldo de hoy terminó bien.
# Registro en <Destino>\respaldo.log (sin claves). Sale con 1 ante cualquier error, sin borrar nada.
#
#   powershell -File GlucoLume_respaldo.ps1 [-Instancia localhost\GLUCOLUME] [-Base GlucoLume] [-Destino C:\GlucoLumeRespaldos]

param(
    [string]$Instancia = "localhost\GLUCOLUME",
    [string]$Base = "GlucoLume",
    [string]$Destino = "C:\GlucoLumeRespaldos",
    [string]$Clave = "C:\GlucoLumeRespaldos\clave_respaldo.dpapi",
    [string]$Gpg = "C:\Program Files\Git\usr\bin\gpg.exe",
    [int]$DiasDiarios = 35,
    [int]$MesesMensuales = 12
)
$ErrorActionPreference = "Stop"
$log = Join-Path $Destino "respaldo.log"
function Registrar([string]$texto) { "$(Get-Date -Format s) $texto" | Tee-Object -FilePath $log -Append }

try {
    if (-not (Test-Path $Clave)) { throw "No existe la clave de cifrado ($Clave): ejecutar GlucoLume_clave_respaldo.ps1." }
    $marca = Get-Date -Format "yyyyMMdd_HHmmss"
    $bak = Join-Path $Destino "GlucoLume_$marca.bak"
    $gpgFile = "$bak.gpg"

    & sqlcmd -S $Instancia -E -C -b -Q "BACKUP DATABASE [$Base] TO DISK = N'$bak' WITH CHECKSUM, INIT, NAME = N'GlucoLume $marca'; RESTORE VERIFYONLY FROM DISK = N'$bak' WITH CHECKSUM;" | Out-Null
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $bak)) { throw "Falló BACKUP o RESTORE VERIFYONLY (código $LASTEXITCODE)." }
    Registrar "Respaldo verificado: $(Split-Path $bak -Leaf) ($([math]::Round((Get-Item $bak).Length / 1MB, 1)) MB)"

    $frase = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR((Get-Content $Clave | ConvertTo-SecureString)))
    $frase | & $Gpg --batch --yes --quiet --pinentry-mode loopback --passphrase-fd 0 --symmetric --cipher-algo AES256 --s2k-digest-algo SHA512 --output $gpgFile $bak
    if ($LASTEXITCODE -ne 0) { throw "Falló el cifrado con GnuPG." }
    $prueba = "$bak.verificacion"
    $frase | & $Gpg --batch --yes --quiet --pinentry-mode loopback --passphrase-fd 0 --decrypt --output $prueba $gpgFile
    Remove-Variable frase
    $original = (Get-FileHash $bak -Algorithm SHA256).Hash
    $descifrado = if (Test-Path $prueba) { (Get-FileHash $prueba -Algorithm SHA256).Hash } else { "" }
    Remove-Item $prueba -ErrorAction SilentlyContinue
    if ($original -ne $descifrado) { throw "El archivo cifrado no se descifra igual al original: se conserva el .bak." }
    Remove-Item $bak
    Registrar "Cifrado AES-256 y verificado: $(Split-Path $gpgFile -Leaf) (SHA-256 del respaldo $original)"

    # Retención: solo archivos de este script; nunca el más reciente.
    $todos = Get-ChildItem $Destino -Filter "GlucoLume_*.bak.gpg" | Where-Object { $_.Name -match '^GlucoLume_(\d{8})_\d{6}\.bak\.gpg$' } |
        ForEach-Object { [pscustomobject]@{ Archivo = $_; Fecha = [datetime]::ParseExact($matches[1], "yyyyMMdd", $null) } } | Sort-Object Fecha -Descending
    $mensualesVistos = @{}
    foreach ($item in $todos | Select-Object -Skip 1) {
        $mes = $item.Fecha.ToString("yyyyMM")
        $diario = $item.Fecha -ge (Get-Date).Date.AddDays(-$DiasDiarios)
        $mensual = (-not $mensualesVistos.ContainsKey($mes)) -and $item.Fecha -ge (Get-Date).Date.AddMonths(-$MesesMensuales)
        if ($mensual) { $mensualesVistos[$mes] = $true }
        if (-not $diario -and -not $mensual) { Remove-Item $item.Archivo.FullName; Registrar "Retención: borrado $($item.Archivo.Name)" }
    }
    exit 0
} catch {
    Registrar "ERROR: $($_.Exception.Message)"
    exit 1
}
