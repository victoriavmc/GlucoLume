@echo off
rem Menu del puente serie de GlucoLume (doble clic): estado, iniciar, detener, reiniciar, cambiar Bluetooth/USB o puerto,
rem diagnostico y registro, e inicio automatico. Sin argumentos abre el menu; con argumentos ejecuta ese comando
rem (por ejemplo: Puente-GlucoLume.bat start / stop / status).
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" bridge_ctl.py %*
  goto :end
)
set "PY=python"
where py >nul 2>&1 && set "PY=py -3"
%PY% bridge_ctl.py %*
:end
if not "%~1"=="" pause
