#Requires -Version 5.1
# Genera y carga los datos genéricos de demo (6 individuos, grupo con permisos distintos, 5 años de mediciones).
# Requiere la variable de entorno GLUCOLUME_PRUEBA_PASSWORD (la contraseña de prueba; no se guarda en archivos).
# Antes ejecutar 01 y 02 (matriz) y 03 (administrador).
param(
    [string]$Servidor = 'localhost\GLUCOLUME',
    [string]$Base = 'GlucoLume'
)

if (-not $env:GLUCOLUME_PRUEBA_PASSWORD) {
    Write-Error 'Definí la variable GLUCOLUME_PRUEBA_PASSWORD antes de ejecutar este script.'
    exit 1
}

Push-Location $PSScriptRoot
try {
    # 1) Genera cargar_datos.sql (contiene el hash de la contraseña de prueba: no se versiona)
    & python generar_datos.py
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    # 2) Carga en la base. -b corta ante el primer error; la transacción del script se revierte sola.
    & sqlcmd -S $Servidor -d $Base -E -C -b -f 65001 -i cargar_datos.sql
    if ($LASTEXITCODE -ne 0) {
        Write-Error 'La carga falló. Revisá el mensaje de sqlcmd; no quedó nada cargado (transacción revertida).'
        exit $LASTEXITCODE
    }
    Write-Host 'Datos demo cargados.'
}
finally {
    Pop-Location
}
