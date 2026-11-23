#Requires -Version 5.1
# Demo de GlucoLume: carga, verificación y limpieza de las 9 cuentas individuales sintéticas, con el seeder del backend
# (backend/app/cli/demoSeed.py). Corre desde la raíz del repositorio en el servidor, con Docker levantado y la base creada.
#
# Sin -Aplicar no escribe nada (simulación). Las contraseñas nunca van a la consola: quedan en el archivo privado
# CarpetaCredenciales\credenciales-demo.txt, fuera del repositorio.
#
#   .\database\demo\03_demo.ps1 -Accion cargar                                  # simulación
#   .\database\demo\03_demo.ps1 -Accion cargar -Aplicar -AutorizarProduccion    # carga (regenera contraseñas)
#   .\database\demo\03_demo.ps1 -Accion verificar                               # comprueba cuentas y contraseñas
#   .\database\demo\03_demo.ps1 -Accion limpiar -Aplicar -AutorizarProduccion   # borra solo los datos demo

param(
    [ValidateSet('cargar', 'verificar', 'limpiar')][string]$Accion = 'cargar',
    [switch]$Aplicar,
    [switch]$AutorizarProduccion,
    [string]$Base = 'GlucoLume',
    [string]$CarpetaCredenciales = (Join-Path $HOME 'GlucoLumeDemo')
)

$ErrorActionPreference = 'Stop'
$raiz = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

# Argumentos de la CLI según la acción.
$cli = @()
switch ($Accion) {
    'cargar' {
        if ($Aplicar) { $cli += '--aplicar', '--regenerar-contrasenas' }
    }
    'verificar' {
        $cli += '--verificar'
    }
    'limpiar' {
        $cli += '--limpiar'
        if ($Aplicar) { $cli += '--aplicar' }
    }
}
if ($AutorizarProduccion) { $cli += '--autorizar-produccion', '--confirmar-base', $Base }

# La carpeta de credenciales debe existir y ser escribible por el usuario del contenedor backend (uid 10001).
New-Item -ItemType Directory -Force -Path $CarpetaCredenciales | Out-Null
if (($IsLinux) -and $Aplicar -and $Accion -eq 'cargar') {
    & sudo chown 10001:10001 $CarpetaCredenciales
}

$docker = @(
    'compose', 'run', '--rm',
    '-v', "${CarpetaCredenciales}:/demo-secrets",
    '-e', 'GLUCOLUME_DEMO_CREDENCIALES=/demo-secrets/credenciales-demo.txt'
)
# Contraseña común para todas las cuentas demo (si se define en el entorno, se pasa al contenedor sin mostrarla).
if ($env:GLUCOLUME_DEMO_PASSWORD) { $docker += '-e', 'GLUCOLUME_DEMO_PASSWORD' }
$docker += 'backend', 'python', '-m', 'app.cli.demoSeed'
$docker += $cli

Push-Location $raiz
try {
    & docker @docker
    if ($LASTEXITCODE -ne 0) { throw "demoSeed terminó con código $LASTEXITCODE. Revisá el mensaje de arriba." }
}
finally {
    Pop-Location
}
