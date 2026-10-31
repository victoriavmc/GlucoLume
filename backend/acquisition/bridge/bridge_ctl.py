#!/usr/bin/env python3
"""GlucoLume - Administrador local del puente serie (Windows).

Una sola herramienta para NO repetir comandos de PowerShell:

  install     Prepara el entorno Python (venv + pyserial con hashes) y ejecuta `setup`. Se hace una sola vez.
  setup       Asistente: elegir Bluetooth o USB, elegir el puerto COM entre los que Windows muestra, velocidad automática
              (Bluetooth 9600 / USB 115200), URL y token del backend, código del dispositivo. Valida el backend, el token y
              que el dispositivo esté registrado. Escribe bridge.env protegido (solo tu usuario). Pregunta, sin activarlo por
              su cuenta, si querés el inicio automático.
  start/stop/restart   Inicia el puente SIN ventana (pythonw), lo detiene liberando el COM, o ambos.
  status      ¿Instalado? ¿ejecutándose? ¿conectado al puerto? ¿enviando datos al backend? (--json para scripts)
  ports       Puertos que ve Windows (Bluetooth/Arduino) y su estado, sin asumir ninguno.
  logs        Últimas líneas del registro (sin secretos).
  doctor      Diagnóstico completo con la solución de cada problema.
  autostart   enable | disable | status: tarea programada al iniciar sesión (opcional; nunca se activa sola).
  uninstall   Detiene el puente y quita el inicio automático (y, si lo pedís, la configuración y el entorno).
  (sin comando) menú interactivo.

El navegador NO puede ejecutar programas locales ni abrir puertos COM: lo que sí puede hacer GlucoLume (elegir puerto entre los
que el propio puente informa, pausar, detener, reiniciar) pasa por el backend autenticado y lo aplica este puente. Iniciar el
puente desde cero es una acción local: se hace aquí, con el acceso directo o con el inicio automático.

Solo biblioteca estándar (usa pyserial a través de glucolume_bridge.py, dentro del entorno virtual).
"""

import argparse
import ctypes
import getpass
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import glucolume_bridge as bridge  # noqa: E402

ENV_PATH = HERE / "bridge.env"
VENV_DIR = HERE / ".venv"
REQUIREMENTS = HERE.parent / "requirements.txt"
SCRIPT = HERE / "glucolume_bridge.py"
PROJECT_ENV = HERE.parent.parent / ".env"
TASK_NAME = "GlucoLume Puente"
RUN_KEY = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "GlucoLumePuente"
DEFAULT_API = "http://localhost"
DEFAULT_CODE = "GL-0001"
FRESH_SECONDS = 15.0  # un estado más viejo que esto = el puente no está escribiendo (detenido o colgado)
NO_WINDOW, DETACHED, NEW_GROUP = 0x08000000, 0x00000008, 0x00000200


# --- Utilidades --------------------------------------------------------------------------------------------------------------


def out(text: str = "") -> None:
    print(text, flush=True)


def pythonExe(windowed: bool = False) -> str:
    """Intérprete del entorno virtual del puente; pythonw (sin ventana) para el segundo plano."""
    scripts = VENV_DIR / ("Scripts" if os.name == "nt" else "bin")
    names = ("pythonw.exe", "python.exe") if os.name == "nt" and windowed else (("python.exe",) if os.name == "nt" else ("python",))
    for name in names:
        if (scripts / name).exists():
            return str(scripts / name)
    base = Path(sys.executable)
    if os.name == "nt" and windowed and (base.with_name("pythonw.exe")).exists():
        return str(base.with_name("pythonw.exe"))
    return str(base)


def venvReady() -> bool:
    return (VENV_DIR / ("Scripts" if os.name == "nt" else "bin")).exists()


def pidAlive(pid) -> bool:
    """¿Existe ese proceso? (En Windows `os.kill(pid, 0)` lo TERMINARÍA: se consulta con la API de procesos.)"""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return False
    try:
        code = ctypes.c_ulong()
        return bool(kernel32.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259  # STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def statusPath() -> Path:
    return bridge.dataDir() / "status.json"


def readStatus() -> dict | None:
    try:
        return json.loads(statusPath().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def ageSeconds(status: dict | None) -> float | None:
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(status["actualizado"])).total_seconds()
    except (TypeError, KeyError, ValueError):
        return None


def protectFile(path: Path) -> bool:
    """Deja el archivo legible solo por el usuario actual (contiene el token del puente). Mejor esfuerzo."""
    if os.name != "nt":
        try:
            path.chmod(0o600)
            return True
        except OSError:
            return False
    user = os.environ.get("USERNAME")
    if not user:
        return False
    done = subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r", f"{user}:(R,W)"], capture_output=True, text=True,
                          creationflags=NO_WINDOW)
    return done.returncode == 0


# --- Configuración ---------------------------------------------------------------------------------------------------------------


def readEnv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            text = raw.strip()
            if text and not text.startswith("#") and "=" in text:
                key, _, value = text.partition("=")
                values[key.strip()] = value.strip().strip('"').strip("'")
    except OSError:
        pass
    return values


def renderEnv(values: dict[str, str], previous: dict[str, str] | None = None) -> str:
    """Contenido de bridge.env: las claves del puente + las que el usuario ya tenía (p. ej. BRIDGE_LOCK_PORT)."""
    keep = {k: v for k, v in (previous or {}).items() if k in bridge.ENV_KEYS and k not in values and v}
    merged = {**keep, **{k: v for k, v in values.items() if v}}
    order = ["SERIAL_PORT", "SERIAL_MEDIUM", "BRIDGE_API_URL", "BRIDGE_TOKEN", "BRIDGE_DEVICE_CODE", "BRIDGE_DEVICE_KEY"]
    lines = ["# Puente serie de GlucoLume (Windows). Generado por bridge_ctl.py. NO se versiona ni se comparte: contiene el token.",
             "# Se puede cambiar el puerto o el medio ejecutando de nuevo `bridge_ctl.py setup` o desde GlucoLume."]
    lines += [f"{key}={merged[key]}" for key in order if key in merged]
    lines += [f"{key}={value}" for key, value in merged.items() if key not in order]
    return "\n".join(lines) + "\n"


def projectToken(path: Path = PROJECT_ENV) -> str | None:
    token = readEnv(path).get("BRIDGE_TOKEN", "")
    return token if len(token) >= 32 else None


# --- Backend ----------------------------------------------------------------------------------------------------------------------


def post(url: str, token: str, payload: dict, timeout: float = 6.0) -> tuple[int, dict]:
    return bridge.httpPost(url, token, payload, timeout)


def interpretCheck(status: int, body: dict, code: str) -> tuple[str, str]:
    """(nivel, mensaje) de la respuesta de POST /acquisition/bridge/check. Nivel: ok | warn | error."""
    if status == 403:
        if body.get("codigo") == "PUENTE_FUERA_DE_ALCANCE":
            return "error", f"La credencial de este puente no corresponde al dispositivo «{code}»."
        return "error", ("El backend rechazó el token (distinto del vigente, revocado o vencido). Pedí uno nuevo a quien administra GlucoLume "
                         "(python -m app.cli.bridgeTokens) o, con el token compartido, copiá el valor de BRIDGE_TOKEN del .env del proyecto.")
    if status == 503:
        return "error", "El backend no tiene BRIDGE_TOKEN configurado. Agregalo al .env del proyecto y ejecutá: docker compose up -d backend"
    if status in (404, 405):
        return "error", "El backend es anterior a esta versión del puente. Reconstruilo: docker compose up -d --build"
    if status != 200:
        return "error", f"El backend respondió {status}."
    if not body.get("registrado"):
        return "ok", (f"El dispositivo «{code}» todavía no figura en el inventario: GlucoLume lo registra solo la primera vez que el "
                      "puente se conecta (queda operativo y disponible para las cuentas individuales).")
    if not body.get("operativo"):
        return "warn", f"El dispositivo «{code}» está registrado pero no operativo (mantenimiento o fuera de servicio)."
    return "ok", f"El dispositivo «{code}» está registrado y operativo ({body.get('sensor')})."


def checkBackend(apiUrl: str, token: str, code: str) -> tuple[str, str]:
    url = apiUrl.rstrip("/") + "/api/v1/acquisition/bridge/check"
    try:
        status, body = post(url, token, {"codigoDispositivo": code})
    except Exception as error:  # noqa: BLE001 - red, DNS, rechazo de conexión
        return "error", f"No se pudo conectar con {apiUrl} ({type(error).__name__}). ¿Está levantado Docker? Probá: docker compose up -d"
    return interpretCheck(status, body, code)


# --- Estado ---------------------------------------------------------------------------------------------------------------------


def interpretStatus(configured: bool, status: dict | None, age: float | None) -> dict:
    """Traduce status.json a un estado legible: no instalado, detenido, ejecutándose, reconectando, conectado, transmitiendo."""
    if not configured:
        return {"estado": "NO_CONFIGURADO", "titulo": "No instalado", "detalle": "Falta la configuración. Ejecutá la instalación (Instalar-Puente.bat)."}
    alive = bool(status) and pidAlive(status.get("pid")) and age is not None and age <= FRESH_SECONDS
    if not alive or status.get("estado") in ("DETENIDO", "REINICIANDO"):
        return {"estado": "DETENIDO", "titulo": "Detenido", "detalle": "El puente no está ejecutándose. Iniciarlo: bridge_ctl.py start (o el acceso directo)."}
    if status.get("estado") == "ERROR":
        return {"estado": "ERROR", "titulo": "Error", "detalle": status.get("error") or "El puente terminó con un error."}
    link = status.get("estadoEnlace")
    if status.get("pausado") or link == "PAUSADO":
        return {"estado": "PAUSADO", "titulo": "Pausado", "detalle": "La lectura está pausada: el puerto está libre."}
    if link == bridge.NO_DEVICE:
        return {"estado": "SIN_DISPOSITIVO", "titulo": "Sin dispositivo GlucoLume conectado",
                "detalle": "Modo automático: el puente busca el Arduino por USB y Bluetooth y se conectará cuando aparezca."}
    if link != "CONECTADO":
        cause = status.get("error") or "Sin conexión con el puerto."
        return {"estado": "RECONECTANDO", "titulo": "Intentando reconectar", "detalle": cause}
    if not status.get("backendOk", True):
        return {"estado": "SIN_BACKEND", "titulo": "Conectado al puerto, backend sin respuesta",
                "detalle": status.get("errorBackend") or "Reintentando con el servidor; las lecturas se conservan."}
    return {"estado": "TRANSMITIENDO", "titulo": "Conectado y transmitiendo", "detalle": f"Puerto {status.get('puerto')} abierto; enviando datos al backend."}


def showStatus(asJson: bool = False) -> int:
    configured = ENV_PATH.exists()
    status = readStatus()
    age = ageSeconds(status)
    result = interpretStatus(configured, status, age)
    task = autostartState()
    if asJson:
        out(json.dumps({**result, "instalado": configured, "inicioAutomatico": task, "estadoLocal": status}, ensure_ascii=False))
        return 0 if result["estado"] in ("TRANSMITIENDO", "PAUSADO") else 1
    out(f"Puente GlucoLume: {result['titulo']}")
    out(f"  {result['detalle']}")
    out(f"  Instalado:           {'sí' if configured else 'no'}")
    out(f"  Inicio automático:   {task}")
    if status and result["estado"] not in ("NO_CONFIGURADO", "DETENIDO"):
        out(f"  Medio y velocidad:   {status.get('medio')} · {status.get('baudios')} baudios")
        out(f"  Puerto:              {status.get('puerto')}")
        out(f"  Dispositivo (código): {status.get('dispositivo')}")
        out(f"  Última lectura del Arduino: {status.get('ultimaLinea') or 'ninguna todavía'}")
        out(f"  Líneas enviadas / en cola:  {status.get('lineasEnviadas')} / {status.get('lineasEnCola')}")
    out(f"  Registro:            {bridge.dataDir() / 'bridge.log'}")
    return 0 if result["estado"] in ("TRANSMITIENDO", "PAUSADO") else 1


# --- Inicio / detención -------------------------------------------------------------------------------------------------------------


def isRunning() -> bool:
    status = readStatus()
    age = ageSeconds(status)
    return bool(status) and pidAlive(status.get("pid")) and age is not None and age <= FRESH_SECONDS and status.get("estado") == "EJECUTANDO"


def commandLine() -> list[str]:
    return [pythonExe(True), str(SCRIPT), "--service", "--env-file", str(ENV_PATH)]


def startBridge(wait: float = 15.0) -> int:
    if not ENV_PATH.exists():
        out("Todavía no está configurado. Ejecutá la instalación primero (Instalar-Puente.bat o: bridge_ctl.py install).")
        return 2
    if isRunning():
        out("El puente ya está ejecutándose.")
        return showStatus()
    before = (readStatus() or {}).get("iniciado")
    flags = (DETACHED | NEW_GROUP | NO_WINDOW) if os.name == "nt" else 0
    subprocess.Popen(commandLine(), cwd=str(HERE), creationflags=flags, close_fds=True, stdin=subprocess.DEVNULL,  # noqa: S603
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=os.name != "nt")
    out("Iniciando el puente (sin ventana)…")
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        time.sleep(0.5)
        status = readStatus()
        if status and status.get("iniciado") != before and status.get("estado") in ("EJECUTANDO", "ERROR") and pidAlive(status.get("pid")):
            break
    else:
        out("El puente no respondió a tiempo. Revisá el registro con: bridge_ctl.py logs")
        return 1
    time.sleep(1.5)  # deja que el primer latido y la apertura del puerto se reflejen en el estado
    return showStatus()


def stopBridge(wait: float = 12.0) -> int:
    status = readStatus()
    if not status or not pidAlive(status.get("pid")):
        out("El puente ya está detenido.")
        return 0
    pid = status["pid"]
    flag = bridge.dataDir() / "stop.flag"
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.write_text("stop", encoding="utf-8")
    out("Deteniendo el puente (libera el puerto COM)…")
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline and pidAlive(pid):
        time.sleep(0.3)
    if pidAlive(pid):
        out("No se detuvo a tiempo: se fuerza el cierre.")
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, creationflags=NO_WINDOW if os.name == "nt" else 0)
        flag.unlink(missing_ok=True)
    out("El puente se detuvo.")
    return 0


# --- Inicio automático (opcional) ---------------------------------------------------------------------------------------------------


def taskXml(user: str, python: str, script: str, envFile: str, workdir: str) -> str:
    """Tarea de usuario al iniciar sesión: sin privilegios elevados, sin ventana, sin límite de tiempo, aunque funcione a batería,
    una sola instancia y con reintentos si el proceso termina con error."""
    arguments = f'"{script}" --service --env-file "{envFile}"'
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>GlucoLume: puente serie Arduino a backend. Solo se crea si el usuario lo habilita.</Description></RegistrationInfo>
  <Triggers><LogonTrigger><Enabled>true</Enabled><UserId>{escape(user)}</UserId><Delay>PT15S</Delay></LogonTrigger></Triggers>
  <Principals><Principal id="Author"><UserId>{escape(user)}</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>7</Priority>
    <RestartOnFailure><Interval>PT1M</Interval><Count>5</Count></RestartOnFailure>
  </Settings>
  <Actions Context="Author"><Exec><Command>{escape(python)}</Command><Arguments>{escape(arguments)}</Arguments><WorkingDirectory>{escape(workdir)}</WorkingDirectory></Exec></Actions>
</Task>
"""


def _run(command: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, text=True, creationflags=NO_WINDOW if os.name == "nt" else 0)


def autostartState() -> str:
    if os.name != "nt":
        return "no disponible (solo Windows)"
    if _run(["schtasks", "/Query", "/TN", TASK_NAME]).returncode == 0:
        return "habilitado (tarea programada al iniciar sesión)"
    if _run(["reg", "query", RUN_KEY, "/v", RUN_VALUE]).returncode == 0:
        return "habilitado (clave Run del usuario)"
    return "desactivado"


def enableAutostart() -> int:
    if os.name != "nt":
        out("El inicio automático solo está disponible en Windows.")
        return 2
    if not ENV_PATH.exists():
        out("Configurá el puente antes de activar el inicio automático.")
        return 2
    user = f"{os.environ.get('USERDOMAIN', '')}\\{os.environ.get('USERNAME', '')}".strip("\\")
    xml = taskXml(user, pythonExe(True), str(SCRIPT), str(ENV_PATH), str(HERE))
    with tempfile.NamedTemporaryFile("wb", suffix=".xml", delete=False) as handle:
        handle.write(b"\xff\xfe" + xml.encode("utf-16-le"))
        temp = handle.name
    try:
        done = _run(["schtasks", "/Create", "/TN", TASK_NAME, "/XML", temp, "/F"])
    finally:
        Path(temp).unlink(missing_ok=True)
    if done.returncode == 0:
        out(f"Inicio automático habilitado: tarea «{TASK_NAME}» al iniciar sesión (sin permisos de administrador, sin ventana).")
        return 0
    detail = (done.stderr or done.stdout).strip().splitlines()[-1:] or ["sin detalle"]
    out(f"No se pudo crear la tarea programada ({detail[0]}).")
    # Alternativa que nunca exige administrador: la clave Run del propio usuario. Solo con consentimiento explícito.
    if confirm("¿Usar en su lugar la clave de inicio del usuario (Run)? Hace lo mismo, sin Programador de tareas", default=False):
        command = " ".join(f'"{part}"' if " " in part else part for part in commandLine())
        run = _run(["reg", "add", RUN_KEY, "/v", RUN_VALUE, "/t", "REG_SZ", "/d", command, "/f"])
        out("Inicio automático habilitado (clave Run del usuario)." if run.returncode == 0 else "Tampoco se pudo crear la clave Run.")
        return run.returncode
    return 1


def disableAutostart() -> int:
    if os.name != "nt":
        return 0
    _run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"])
    _run(["reg", "delete", RUN_KEY, "/v", RUN_VALUE, "/f"])
    out("Inicio automático desactivado.")
    return 0


# --- Preguntas ---------------------------------------------------------------------------------------------------------------------

NON_INTERACTIVE = False


def ask(question: str, default: str | None = None, secret: bool = False) -> str:
    if NON_INTERACTIVE or not sys.stdin or not sys.stdin.isatty():
        if default is not None:
            return default
        raise SystemExit(f"Falta un dato y no hay modo interactivo: {question}")
    suffix = f" [{default}]" if default else ""
    answer = (getpass.getpass(f"{question}{suffix}: ") if secret else input(f"{question}{suffix}: ")).strip()
    return answer or (default or "")


def confirm(question: str, default: bool = False) -> bool:
    if NON_INTERACTIVE or not sys.stdin or not sys.stdin.isatty():
        return default
    answer = input(f"{question} [{'S/n' if default else 's/N'}]: ").strip().lower()
    return default if not answer else answer.startswith(("s", "y"))


# --- Instalación / configuración -------------------------------------------------------------------------------------------------------


def discoverPorts() -> list[dict]:
    scanner = bridge.PortScanner(windows=bridge.readWindowsPorts)
    try:
        return scanner.scan()
    except Exception:  # noqa: BLE001
        return []


def describePort(port: dict) -> str:
    tags = [tag for tag, on in (("Bluetooth", port["esBluetooth"]), ("Arduino/USB-serial", port["esArduino"])) if on]
    state = port.get("estadoWindows")
    warn = f"  ⚠ Windows informa estado «{state}»" if state and state != "OK" else ""
    return f"{port['puerto']:<7} {port.get('descripcion') or 'sin descripción'}{' [' + ', '.join(tags) + ']' if tags else ''}{warn}"


def suggestedPorts(ports: list[dict], medium: str) -> list[dict]:
    flag = "esBluetooth" if medium == "BLUETOOTH" else "esArduino"
    return [p for p in ports if p[flag]] or ports


def choosePort(medium: str, requested: str | None, previous: str | None) -> str:
    if requested:
        return requested.upper()
    ports = discoverPorts()
    candidates = suggestedPorts(ports, medium)
    out(f"\nPuertos que ve Windows ({'Bluetooth' if medium == 'BLUETOOTH' else 'USB'}):")
    if not ports:
        out("  (ninguno). " + ("Emparejá el HC-05/HC-06 en Configuración → Bluetooth y volvé a intentar." if medium == "BLUETOOTH"
                               else "Conectá el Arduino con un cable USB de datos e instalá el controlador CH340 si hace falta."))
    for index, port in enumerate(candidates, 1):
        out(f"  {index}. {describePort(port)}")
    if medium == "BLUETOOTH":
        out("  Elegí el puerto COM SALIENTE del HC-05 (Configuración → Bluetooth → Más opciones → Puertos COM).")
    default = candidates[0]["puerto"] if len(candidates) == 1 else (previous if previous and any(p["puerto"] == previous for p in ports) else None)
    answer = ask("Número de la lista o nombre del puerto (por ejemplo COM5)", default)
    if answer.isdigit() and 1 <= int(answer) <= len(candidates):
        return candidates[int(answer) - 1]["puerto"]
    if not answer:
        raise SystemExit("No se eligió ningún puerto.")
    return answer.upper()


def cmdSetup(args) -> int:
    global NON_INTERACTIVE
    NON_INTERACTIVE = bool(args.yes)
    previous = readEnv(ENV_PATH)
    out("Configuración del puente GlucoLume (Arduino → Windows → backend)\n")
    medium = (args.medium or "").upper()
    if medium not in (*bridge.BAUD, bridge.AUTO):
        default = previous.get("SERIAL_MEDIUM", "BLUETOOTH")
        out("¿Cómo está conectado el Arduino?\n  1. Bluetooth (HC-05/HC-06, 9600 baudios)\n  2. USB (cable al Arduino UNO, 115200 baudios)\n"
            "  3. Automático: el puente busca el GlucoLume por USB y Bluetooth y se conecta solo (no hace falta elegir COM)")
        choice = ask("Opción", {"USB": "2", "AUTO": "3"}.get(default, "1"))
        medium = {"2": "USB", "usb": "USB", "USB": "USB", "3": bridge.AUTO, "auto": bridge.AUTO, "AUTO": bridge.AUTO}.get(choice.strip(), "BLUETOOTH")
    if medium == bridge.AUTO:
        out("Medio: automático (USB y Bluetooth). El puerto se detecta solo al identificar el GlucoLume.")
        port = ""
    else:
        baud = bridge.BAUD[medium]
        out(f"Medio: {medium.title()} · velocidad automática: {baud} baudios (la del firmware).")
        port = choosePort(medium, args.port, previous.get("SERIAL_PORT") if not previous.get("SERIAL_PORT", "").startswith("<") else None)
    apiUrl = args.api_url or ask("URL de GlucoLume (el backend en Docker)", previous.get("BRIDGE_API_URL", DEFAULT_API))
    token = ""
    if args.token_file:
        token = readEnv(Path(args.token_file)).get("BRIDGE_TOKEN", "")
    token = token or os.environ.get("BRIDGE_TOKEN", "") or previous.get("BRIDGE_TOKEN", "")
    found = projectToken()
    if not token and found:
        if confirm("Se encontró BRIDGE_TOKEN en el .env del proyecto. ¿Usarlo?", default=True):
            token = found
    if not token:
        token = ask("BRIDGE_TOKEN (el mismo del .env del proyecto; no se muestra al escribir)", secret=True)
    if len(token) < 32:
        out("El token debe tener al menos 32 caracteres.")
        return 2
    code = args.device_code or ask("Código del dispositivo en el inventario de GlucoLume", previous.get("BRIDGE_DEVICE_CODE", DEFAULT_CODE))
    try:
        bridge.readConfig({"SERIAL_PORT": port, "SERIAL_MEDIUM": medium, "BRIDGE_API_URL": apiUrl, "BRIDGE_TOKEN": token,
                           "BRIDGE_DEVICE_CODE": code})  # en AUTO el puerto va vacío y no es obligatorio
    except bridge.ConfigError as error:
        out(f"Configuración inválida: {error}")
        return 2
    if not args.no_check:
        level, message = checkBackend(apiUrl, token, code)
        out(f"\nBackend: {message}")
        if level == "error":
            if not confirm("¿Guardar la configuración de todos modos?", default=False):
                return 1
        elif level == "warn" and not confirm("¿Continuar igual? Podés registrar el dispositivo después.", default=True):
            return 1
    ENV_PATH.write_text(renderEnv({"SERIAL_PORT": port, "SERIAL_MEDIUM": medium, "BRIDGE_API_URL": apiUrl, "BRIDGE_TOKEN": token,
                                   "BRIDGE_DEVICE_CODE": code}, previous), encoding="utf-8")
    out(f"\nConfiguración guardada en {ENV_PATH}" + (" (acceso restringido a tu usuario)." if protectFile(ENV_PATH) else
                                                       " (no se pudo restringir el acceso: protegé el archivo)."))
    if args.autostart == "yes" or (args.autostart is None and confirm(
            "¿Querés que el puente se inicie solo al abrir sesión en Windows? (podés cambiarlo cuando quieras)", default=False)):
        enableAutostart()
    elif args.autostart == "no":
        disableAutostart()
    if isRunning():
        out("El puente está ejecutándose: para aplicar el cambio reinicialo (bridge_ctl.py restart).")
    elif args.start or (args.start is None and confirm("¿Iniciar el puente ahora?", default=True)):
        startBridge()
    return 0


def cmdGenKey(args) -> int:
    """Genera la clave de 128 bits que firma las líneas del Arduino (H-05) y explica cómo cargarla. Con --save la deja en bridge.env (nunca en el repositorio)."""
    import secrets

    key = secrets.token_hex(16)
    out("Clave nueva (128 bits). Se muestra UNA vez: no la guardes en el repositorio, en un chat ni en un correo.\n")
    out(f"  {key}\n")
    out("Para activarla en el Arduino (firmware GlucoLume_MAX30100_optimizado, por USB, con el Monitor Serie a 115200 y fin de línea «Nueva línea»):")
    out(f"  KEY,{key}")
    out("Debe responder KEY:OK. Después, `KEY?` informa si hay clave (nunca la muestra).")
    if args.save:
        previous = readEnv(ENV_PATH)
        if not previous:
            out("\nNo hay bridge.env: ejecutá primero `bridge_ctl.py setup`.")
            return 2
        ENV_PATH.write_text(renderEnv({**previous, "BRIDGE_DEVICE_KEY": key}, previous), encoding="utf-8")
        protectFile(ENV_PATH)
        out(f"\nBRIDGE_DEVICE_KEY guardada en {ENV_PATH}. Reiniciá el puente (`bridge_ctl.py restart`). Con clave, el puente descarta lo que no esté firmado.")
    else:
        out("\nEn el equipo del puente, agregá a bridge.env:  BRIDGE_DEVICE_KEY=<la clave>   (o repetí el comando con --save).")
    return 0


def cmdAuthReset(_args) -> int:
    """Olvida el último contador aceptado (linkauth.json). Necesario si se borró la EEPROM del Arduino o se cargó otro con la misma clave."""
    state = bridge.dataDir() / "linkauth.json"
    try:
        state.unlink()
        out(f"Se olvidó el último contador aceptado ({state}). La próxima línea firmada válida fija el nuevo punto de partida.")
    except FileNotFoundError:
        out("No había contador guardado: nada que olvidar.")
    out("Aviso: mientras no haya un contador guardado, una línea firmada capturada antes se aceptaría una vez. Hacelo solo si reprovisionaste el Arduino.")
    return 0


def cmdInstall(args) -> int:
    out("Instalación del puente GlucoLume (una sola vez)\n")
    if not venvReady():
        out("Creando el entorno Python del puente (.venv)…")
        if subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)]).returncode != 0:
            out("No se pudo crear el entorno virtual. ¿Está instalado Python 3.10 o superior?")
            return 1
    out("Instalando dependencias (pyserial, con verificación de hashes)…")
    flags = ["--require-hashes", "-r", str(REQUIREMENTS)]
    if subprocess.run([pythonExe(False), "-m", "pip", "install", "--disable-pip-version-check", *flags]).returncode != 0:
        out("No se pudieron instalar las dependencias. Revisá la conexión a internet y volvé a ejecutar la instalación.")
        return 1
    passthrough = [a for a in sys.argv[2:]]
    return subprocess.call([pythonExe(False), str(Path(__file__).resolve()), "setup", *passthrough])


# --- Diagnóstico -------------------------------------------------------------------------------------------------------------------------


def cmdPorts(_args) -> int:
    ports = discoverPorts()
    if not ports:
        out("Windows no muestra ningún puerto COM. Emparejá el Bluetooth o conectá el Arduino por USB.")
        return 1
    for port in ports:
        out(describePort(port))
    return 0


def cmdLogs(args) -> int:
    logFile = bridge.dataDir() / "bridge.log"
    if not logFile.exists():
        out("Todavía no hay registro.")
        return 1
    for line in logFile.read_text(encoding="utf-8", errors="replace").splitlines()[-args.lines:]:
        out(line)
    return 0


def cmdDoctor(_args) -> int:
    problems = 0

    def report(level: str, text: str) -> None:
        nonlocal problems
        problems += level == "error"
        out(f"  [{ {'ok': 'OK', 'warn': '!!', 'error': 'XX'}[level] }] {text}")

    out("Diagnóstico del puente GlucoLume\n")
    report("ok" if sys.version_info >= (3, 10) else "error", f"Python {sys.version.split()[0]}")
    report("ok" if venvReady() else "warn", "Entorno virtual del puente" + ("" if venvReady() else ": no existe (ejecutá la instalación)"))
    try:
        import serial  # noqa: F401

        report("ok", "pyserial instalado")
    except Exception:  # noqa: BLE001
        report("error", "pyserial no está instalado en este Python (ejecutá la instalación)")
    if not ENV_PATH.exists():
        report("error", "Falta bridge.env: ejecutá la instalación o `bridge_ctl.py setup`")
        return 1
    env = readEnv(ENV_PATH)
    try:
        cfg = bridge.readConfig(env)
        described = "búsqueda automática (USB y Bluetooth)" if cfg.medium == bridge.AUTO else f"{cfg.medium.title()} · {cfg.port} · {cfg.baud} baudios"
        report("ok", f"Configuración válida: {described} · dispositivo {cfg.deviceCode}")
    except bridge.ConfigError as error:
        report("error", str(error))
        return 1
    level, message = checkBackend(cfg.apiUrl, cfg.token, cfg.deviceCode)
    report(level, message)
    if cfg.deviceKey is not None:
        report("ok", "Enlace con el dispositivo AUTENTICADO (BRIDGE_DEVICE_KEY): se descartan las líneas sin firma válida o repetidas. No cifra el enlace.")
    else:
        report("warn", "Enlace con el dispositivo SIN autenticar (falta BRIDGE_DEVICE_KEY): quien esté al alcance del Bluetooth podría falsificar o repetir "
                       "lecturas. `bridge_ctl.py genkey` genera la clave; requiere el firmware optimizado con firma.")
    ports = discoverPorts()
    match = next((p for p in ports if p["puerto"].upper() == cfg.port.upper()), None)
    if cfg.medium == bridge.AUTO:
        report("ok", f"Puertos candidatos (USB/Bluetooth): {', '.join(p['puerto'] for p in ports if p['esArduino'] or p['esBluetooth']) or 'ninguno todavía'}. "
                     "Se identifica el GlucoLume por su línea GLUCOLUME,ID=; ninguno se asume válido.")
    elif match is None:
        report("error", f"Windows no muestra el puerto {cfg.port}. Mostrados: {', '.join(p['puerto'] for p in ports) or 'ninguno'}. "
               "Si es Bluetooth, comprobá el emparejamiento; si es USB, el cable y el controlador (CH340).")
    elif match.get("estadoWindows") not in (None, "OK"):
        report("warn", f"{cfg.port} existe pero Windows informa estado «{match['estadoWindows']}»: reinstalá el controlador del adaptador.")
    else:
        report("ok", f"Windows muestra {describePort(match)}")
    status = readStatus()
    result = interpretStatus(True, status, ageSeconds(status))
    report("ok" if result["estado"] in ("TRANSMITIENDO", "PAUSADO") else "warn", f"Puente: {result['titulo']}. {result['detalle']}")
    if result["estado"] == "DETENIDO" and match is not None:
        try:
            import serial

            handle = serial.Serial(cfg.port, cfg.baud, timeout=0.5)
            handle.close()
            report("ok", f"{cfg.port} se puede abrir (libre)")
        except Exception as error:  # noqa: BLE001
            code, message = bridge.classifyError(error)
            hint = {"PUERTO_OCUPADO": " Cerrá el Monitor Serie del Arduino IDE, PuTTY u otra aplicación que lo use.",
                    "DISPOSITIVO_SIN_RESPUESTA": " Encendé el Arduino y comprobá que el módulo Bluetooth tenga alimentación y esté en alcance.",
                    "PUERTO_INEXISTENTE": " Reconectá el dispositivo y revisá el controlador."}.get(code, "")
            report("error", f"{cfg.port}: {message}{hint}")
    report("ok", f"Inicio automático: {autostartState()}")
    return 1 if problems else 0


def cmdUninstall(args) -> int:
    stopBridge()
    disableAutostart()
    if args.purge:
        ENV_PATH.unlink(missing_ok=True)
        import shutil

        shutil.rmtree(VENV_DIR, ignore_errors=True)
        out("Se eliminó la configuración (bridge.env) y el entorno virtual.")
    return 0


# --- Menú ---------------------------------------------------------------------------------------------------------------------------


def menu() -> int:
    options = [
        ("Ver estado", lambda: showStatus()), ("Iniciar el puente", lambda: startBridge()), ("Detener el puente", lambda: stopBridge()),
        ("Reiniciar el puente", lambda: (stopBridge(), startBridge())[1]),
        ("Cambiar medio (Bluetooth/USB) o puerto", lambda: cmdSetup(argparse.Namespace(
            yes=False, medium=None, port=None, api_url=None, token_file=None, device_code=None, no_check=False, autostart=None, start=False))),
        ("Ver puertos de Windows", lambda: cmdPorts(None)), ("Ver registro", lambda: cmdLogs(argparse.Namespace(lines=40))),
        ("Diagnóstico completo", lambda: cmdDoctor(None)), ("Activar inicio automático", lambda: enableAutostart()),
        ("Desactivar inicio automático", lambda: disableAutostart()),
    ]
    while True:
        out("\n=== Puente GlucoLume ===")
        showStatus()
        out("")
        for index, (label, _) in enumerate(options, 1):
            out(f"  {index}. {label}")
        out("  0. Salir")
        choice = input("Opción: ").strip()
        if choice in ("0", "", "q"):
            return 0
        if choice.isdigit() and 1 <= int(choice) <= len(options):
            out("")
            options[int(choice) - 1][1]()
            input("\nEnter para continuar…")


def buildParser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Administrador local del puente serie de GlucoLume.")
    sub = parser.add_subparsers(dest="command")
    for name in ("install", "setup"):
        item = sub.add_parser(name, help="instalación (install) o asistente de configuración (setup)")
        item.add_argument("--medium", choices=["BLUETOOTH", "USB", "AUTO", "bluetooth", "usb", "auto"])
        item.add_argument("--port")
        item.add_argument("--api-url")
        item.add_argument("--token-file", help="archivo (p. ej. el .env del proyecto) del que leer BRIDGE_TOKEN")
        item.add_argument("--device-code")
        item.add_argument("--no-check", action="store_true", help="no consultar al backend")
        item.add_argument("--autostart", choices=["yes", "no"], help="habilitar/deshabilitar el inicio automático sin preguntar")
        item.add_argument("--start", action=argparse.BooleanOptionalAction, default=None)
        item.add_argument("--yes", action="store_true", help="sin preguntas: usa valores por defecto o los indicados")
    for name in ("start", "stop", "restart", "ports", "doctor"):
        sub.add_parser(name)
    genkey = sub.add_parser("genkey", help="genera la clave que firma las líneas del Arduino (H-05)")
    genkey.add_argument("--save", action="store_true", help="la guarda como BRIDGE_DEVICE_KEY en bridge.env")
    sub.add_parser("auth-reset", help="olvida el último contador aceptado (tras reprovisionar el Arduino)")
    status = sub.add_parser("status")
    status.add_argument("--json", action="store_true")
    logs = sub.add_parser("logs")
    logs.add_argument("-n", "--lines", type=int, default=40)
    auto = sub.add_parser("autostart")
    auto.add_argument("action", choices=["enable", "disable", "status"])
    uninstall = sub.add_parser("uninstall")
    uninstall.add_argument("--purge", action="store_true", help="borra también bridge.env y el entorno virtual")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = buildParser().parse_args(argv)
    if args.command is None:
        return menu()
    table = {
        "install": cmdInstall, "setup": cmdSetup, "start": lambda a: startBridge(), "stop": lambda a: stopBridge(),
        "restart": lambda a: (stopBridge(), startBridge())[1], "status": lambda a: showStatus(a.json), "ports": cmdPorts,
        "logs": cmdLogs, "doctor": cmdDoctor, "uninstall": cmdUninstall, "genkey": cmdGenKey, "auth-reset": cmdAuthReset,
        "autostart": lambda a: {"enable": enableAutostart, "disable": disableAutostart,
                                "status": lambda: (out(f"Inicio automático: {autostartState()}"), 0)[1]}[a.action](),
    }
    return table[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
