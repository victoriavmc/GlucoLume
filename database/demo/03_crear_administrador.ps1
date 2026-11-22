#Requires -Version 5.1
# Crea la invitación del primer administrador del sistema de GlucoLume.
# Usa backend/app/cli/initAdmin.py con las credenciales de base de datos del .env del backend.
# No define contraseñas: la persona recibe un enlace de un solo uso por correo.
param(
    [Parameter(Mandatory = $true)][string]$Nombre,
    [Parameter(Mandatory = $true)][string]$Apellido,
    [Parameter(Mandatory = $true)][string]$Correo,
    [switch]$MostrarEnlace
)

$backend = Join-Path $PSScriptRoot '..\..\backend'
if (-not (Test-Path (Join-Path $backend 'app\cli\initAdmin.py'))) {
    Write-Error "No encuentro backend\app\cli\initAdmin.py desde $PSScriptRoot."
    exit 1
}

$args = @('-m', 'app.cli.initAdmin', '--nombre', $Nombre, '--apellido', $Apellido, '--correo', $Correo)
if ($MostrarEnlace) { $args += '--mostrar-enlace' }

Push-Location $backend
try {
    & python @args
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
