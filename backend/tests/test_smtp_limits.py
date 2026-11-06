# Límite de conexiones SMTP simultáneas y tiempo total por envío (app/integrations/email/sender.py).
#
# Los envíos sincrónicos bloquean un hilo de la API mientras dura la conexión. Estas pruebas fijan que (1) nunca hay más conexiones
# abiertas que SMTP_MAX_CONCURRENT, (2) sin lugar libre el envío falla sin conectar, (3) un servidor que no responde se corta al
# vencer el tiempo total, y (4) el camino normal sigue igual.

import smtplib
import socket
import threading
import time
from email.message import EmailMessage
from types import SimpleNamespace

import pytest

from app.integrations.email import sender

# conftest.py reemplaza smtplib.SMTP por un bloqueo (ningún correo real). Esta referencia conserva la clase verdadera para la
# prueba que conecta solo a un socket local que no responde.
_SMTP_REAL = smtplib.SMTP


def _message() -> EmailMessage:
    return sender.buildHtmlMessage("destino@example.com", "Asunto", "<p>hola</p>", "hola")


def _settings(port: int = 587):
    return SimpleNamespace(
        SMTP_HOST="127.0.0.1",
        SMTP_PORT=port,
        SMTP_USERNAME="cuenta",
        SMTP_PASSWORD=SimpleNamespace(get_secret_value=lambda: "clave"),
        SMTP_FROM="no-reply@example.com",
        SMTP_FROM_NAME="GlucoLume",
        smtpEnabled=True,
    )


def test_nunca_hay_mas_conexiones_que_el_limite(monkeypatch):
    monkeypatch.setattr(sender, "SMTP_SLOT_WAIT_SECONDS", 30)
    lock = threading.Lock()
    estado = {"abiertas": 0, "maximo": 0}

    class ServidorLento:
        def send_message(self, message):
            with lock:
                estado["abiertas"] += 1
                estado["maximo"] = max(estado["maximo"], estado["abiertas"])
            time.sleep(0.05)
            with lock:
                estado["abiertas"] -= 1

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return None

    monkeypatch.setattr(sender, "_connect", lambda deadline: ServidorLento())
    message = _message()
    errores = []

    def enviar():
        try:
            sender._send(message)
        except Exception as error:  # noqa: BLE001 - la prueba recoge cualquier fallo
            errores.append(error)

    hilos = [threading.Thread(target=enviar) for _ in range(12)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()

    assert errores == []
    assert 2 <= estado["maximo"] <= sender.SMTP_MAX_CONCURRENT


def test_sin_lugar_en_el_limite_el_envio_falla_sin_conectar(monkeypatch):
    monkeypatch.setattr(sender, "SMTP_SLOT_WAIT_SECONDS", 0.05)
    conexiones = []
    monkeypatch.setattr(sender, "_connect", lambda deadline: conexiones.append(deadline))
    ocupados = 0
    try:
        for _ in range(sender.SMTP_MAX_CONCURRENT):
            assert sender._slots.acquire(blocking=False)
            ocupados += 1
        with pytest.raises(sender.SmtpBusyError):
            sender._send(_message())
    finally:
        for _ in range(ocupados):
            sender._slots.release()
    assert conexiones == []


def test_tiempo_total_corta_un_servidor_que_no_responde(monkeypatch):
    servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    servidor.bind(("127.0.0.1", 0))
    servidor.listen(1)
    puerto = servidor.getsockname()[1]
    aceptadas = []

    def aceptar():
        conexion, _ = servidor.accept()
        conexion.sendall(b"220 servidor de prueba listo\r\n")  # saluda, y después no responde a EHLO/STARTTLS
        aceptadas.append(conexion)

    hilo = threading.Thread(target=aceptar, daemon=True)
    hilo.start()
    monkeypatch.setattr(sender.smtplib, "SMTP", _SMTP_REAL)  # solo 127.0.0.1
    monkeypatch.setattr(sender, "getSettings", lambda: _settings(puerto))
    monkeypatch.setattr(sender, "SMTP_TOTAL_TIMEOUT_SECONDS", 0.5)
    monkeypatch.setattr(sender, "SMTP_TIMEOUT_SECONDS", 60)  # solo el total debe cortar la espera
    inicio = time.monotonic()
    try:
        with pytest.raises(sender.SmtpDeadlineError):
            sender._send(_message())
        assert time.monotonic() - inicio < 5
    finally:
        for conexion in aceptadas:
            conexion.close()
        servidor.close()


def test_envio_normal_conecta_autentica_envia_y_cierra(monkeypatch):
    registro = []

    class ServidorFalso:
        sock = None

        def __init__(self, host, port, timeout):  # como smtplib: el constructor conecta y lee el saludo
            registro.append(("conexion", host, port, timeout))

        def starttls(self, context):
            registro.append(("starttls",))

        def login(self, usuario, clave):
            registro.append(("login", usuario))

        def send_message(self, message):
            registro.append(("send", message["To"]))

        def quit(self):
            registro.append(("quit",))

        def close(self):
            registro.append(("close",))

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):  # como smtplib: QUIT y cierre al salir del bloque
            self.quit()
            self.close()

    monkeypatch.setattr(sender, "getSettings", lambda: _settings(2525))
    monkeypatch.setattr(sender.smtplib, "SMTP", ServidorFalso)

    sender._send(_message())

    assert registro == [
        ("conexion", "127.0.0.1", 2525, sender.SMTP_TIMEOUT_SECONDS),
        ("starttls",),
        ("login", "cuenta"),
        ("send", "destino@example.com"),
        ("quit",),
        ("close",),
    ]
    assert sender._slots._value == sender.SMTP_MAX_CONCURRENT  # el lugar vuelve a quedar libre


def test_causas_nuevas_se_registran_con_su_categoria(monkeypatch):
    monkeypatch.setattr(sender, "getSettings", lambda: _settings())

    ocupado = sender.describeSmtpError(sender.SmtpBusyError("sin lugar"))
    assert "demasiados envíos SMTP" in ocupado
    assert "configuración" not in ocupado

    agotado = sender.describeSmtpError(sender.SmtpDeadlineError("vencido"))
    assert "tiempo total del envío agotado" in agotado
    assert "conectando" not in agotado


def test_vencimiento_durante_la_transmision_se_informa_como_tiempo_total():
    class ServidorCortado:
        sock = None

        def send_message(self, message):
            deadline._expire()  # el plazo vence mientras el servidor no responde
            raise OSError("socket cerrado por el plazo")

    deadline = sender._Deadline(60)
    with pytest.raises(sender.SmtpDeadlineError) as info:
        sender._deliver(ServidorCortado(), _message(), deadline)
    assert isinstance(info.value.__cause__, OSError)
