@echo off
rem Ejecuta el puente en PRIMER PLANO con consola (para ver lo que hace, o depurar). Para el uso diario usa
rem Puente-GlucoLume.bat (segundo plano, sin ventana) o el inicio automatico. Ver README.md.
rem Lee bridge.env (junto a este archivo); si no existe, ejecuta antes Instalar-Puente.bat.
setlocal
set "HERE=%~dp0"
if not exist "%HERE%bridge.env" (
  echo Falta "%HERE%bridge.env". Ejecuta Instalar-Puente.bat primero.
  exit /b 2
)
if exist "%HERE%.venv\Scripts\python.exe" (
  "%HERE%.venv\Scripts\python.exe" "%HERE%glucolume_bridge.py" --env-file "%HERE%bridge.env" %*
) else (
  python "%HERE%glucolume_bridge.py" --env-file "%HERE%bridge.env" %*
)
exit /b %ERRORLEVEL%
