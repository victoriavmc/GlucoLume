# GlucoLume - Clave de cifrado de los respaldos (GL-07, SQL Server Express sin cifrado nativo de backups)
#
# Genera una frase de paso aleatoria (48 bytes) y la guarda protegida con DPAPI para la cuenta de Windows que la crea: solo esa cuenta,
# en este equipo, puede leerla. Los respaldos se cifran con ella (GlucoLume_respaldo.ps1). SIN UNA COPIA FUERA DEL EQUIPO, perder el
# equipo o la cuenta hace irrecuperables los respaldos: después de crearla, ejecutar con -Mostrar UNA vez y guardarla en un gestor de
# contraseñas o un sobre cerrado. Nunca se escribe en registros ni en el proyecto.
#
#   powershell -File GlucoLume_clave_respaldo.ps1                 # crea la clave si no existe
#   powershell -File GlucoLume_clave_respaldo.ps1 -Mostrar        # la muestra para copiarla a un lugar seguro (solo quien la custodia)

param(
    [string]$Archivo = "C:\GlucoLumeRespaldos\clave_respaldo.dpapi",
    [switch]$Mostrar
)
$ErrorActionPreference = "Stop"

if (Test-Path $Archivo) {
    if (-not $Mostrar) { Write-Output "La clave ya existe ($Archivo): no se reemplaza (los respaldos anteriores dependen de ella)."; exit 0 }
} else {
    $bytes = New-Object byte[] 48
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $frase = [Convert]::ToBase64String($bytes)
    $seguro = ConvertTo-SecureString $frase -AsPlainText -Force
    ConvertFrom-SecureString $seguro | Set-Content -Path $Archivo -Encoding ASCII
    Remove-Variable frase, bytes
    Write-Output "Clave creada y protegida con DPAPI en $Archivo. Guardá una copia fuera del equipo con -Mostrar."
}
if ($Mostrar) {
    $seguro = Get-Content $Archivo | ConvertTo-SecureString
    [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($seguro))
}
