# Prepara la base AISLADA de la prueba de concurrencia (ver README.md). Lo ejecuta un DBA una sola vez con una cuenta de administración.
# NO usa la cuenta de la API. Rechaza las bases reales y cualquier nombre que no termine en _Concurrencia_Prueba.
#
#   .\preparar_base_prueba.ps1 -Servidor localhost -Puerto 1435 -Base GlucoLume_Concurrencia_Prueba
#   (autenticación de Windows: -E; con usuario: -Usuario <admin> y la contraseña se pide al ejecutar)

param(
    [Parameter(Mandatory = $true)] [string] $Servidor,
    [Parameter(Mandatory = $true)] [int] $Puerto,
    [Parameter(Mandatory = $true)] [string] $Base,
    [string] $Usuario,
    [switch] $E
)

$ErrorActionPreference = 'Stop'
$prohibidas = @('GlucoLume', 'GlucoLume_Copia')
if ($prohibidas -contains $Base -or -not $Base.EndsWith('_Concurrencia_Prueba')) {
    throw "Base no permitida: '$Base'. Debe terminar en _Concurrencia_Prueba y no puede ser una base real."
}
$scripts = @(
    (Join-Path $PSScriptRoot '..\..\..\database\reference\GlucoLume_DB_v5.sql'),
    (Join-Path $PSScriptRoot '..\..\..\database\reference\GlucoLume_vinculo_cuenta_dispositivo.sql')
) | ForEach-Object { (Resolve-Path $_).Path }

$auth = if ($E) { @('-E') } else { @('-U', $Usuario, '-P', (Read-Host -Prompt 'Contraseña del administrador' -AsSecureString | ForEach-Object { [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($_)) })) }
$comun = @('-S', "$Servidor,$Puerto", '-b') + $auth

# 1) Base nueva (vacía). Si ya existe, el script no la borra: hay que eliminarla a mano (no se hace aquí).
& sqlcmd @comun -Q "IF DB_ID(N'$Base') IS NOT NULL THROW 50000, 'La base ya existe: elegí otro nombre o borrala a mano.', 1; CREATE DATABASE [$Base];"

# 2) Esquema: los scripts dicen USE [GlucoLume]; se apuntan a la base de prueba en una copia temporal (la original no se modifica).
foreach ($script in $scripts) {
    $texto = Get-Content -Raw -Encoding Unicode -LiteralPath $script
    $texto = $texto -replace '\[GlucoLume\]', "[$Base]"
    $temporal = Join-Path $env:TEMP ("glucolume_" + [IO.Path]::GetFileName($script))
    Set-Content -LiteralPath $temporal -Value $texto -Encoding Unicode
    & sqlcmd @comun -d $Base -i $temporal
    Remove-Item -LiteralPath $temporal
}
Write-Host "Base '$Base' lista. Ahora creá el login de ejecución (solo db_datareader y db_datawriter sobre esta base)."
