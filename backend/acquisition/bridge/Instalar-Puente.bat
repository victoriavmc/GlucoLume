@echo off
rem Instalacion UNICA del puente serie de GlucoLume (doble clic).
rem Crea el entorno Python del puente, instala pyserial y abre el asistente: elegir Bluetooth o USB, elegir el puerto COM,
rem validar el servidor y el dispositivo, y (solo si lo pedis) activar el inicio automatico.
setlocal
cd /d "%~dp0"
set "PY=python"
where py >nul 2>&1 && set "PY=py -3"
%PY% --version >nul 2>&1
if errorlevel 1 (
  echo No se encontro Python 3.10 o superior. Instalalo desde https://www.python.org/downloads/ y volve a ejecutar este archivo.
  pause
  exit /b 1
)
%PY% bridge_ctl.py install %*
echo.
pause
