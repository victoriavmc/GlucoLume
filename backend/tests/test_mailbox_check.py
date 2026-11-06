# Verificación previa del correo (app/integrations/email/mailboxCheck.py y app/services/email.py).
#
# Un servidor SMTP de prueba (127.0.0.1) responde a RCPT TO según cada escenario. Las pruebas comprueban que:
# - el buzón inexistente se rechaza (registro) y no se envía (segundo plano);
# - todo resultado dudoso (política, error temporal, catch-all, servidor caído, DNS) NO bloquea;
# - nunca se transmite DATA: la verificación no entrega ningún mensaje.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_mailbox_check.py -v

import smtplib
import socket
import socketserver
import threading

import dns.exception
import dns.resolver
import pytest
from sqlalchemy import select

from app.core.exceptions import AuthError
from app.emails.eventTypes import EmailEventType
from app.integrations.email import mailboxCheck
from app.integrations.email.mailboxCheck import ResultadoBuzon, Veredicto
from app.models.user import User
from app.schemas.auth import RegisterRequest
from app.services import auth as authService
from app.services import email as emailService
from tests.test_account_deletion import db, engine, mails  # noqa: F401 - fixtures

# Capturados al importar: la prueba reemplaza smtplib.SMTP y el DNS real (conftest), pero el servidor de prueba necesita el real.
SMTP_REAL = smtplib.SMTP
SERVIDORES_REALES = mailboxCheck._servidoresDeCorreo
REMITENTE = "noreply@glucolume.test"
NUEVA_PASSWORD = "Zorro#Lento-2027"


def conectarReal(host, puerto, timeout, nombreLocal):
    return SMTP_REAL(host, puerto, timeout=timeout, local_hostname=nombreLocal)


class ServidorSmtp:
    """Servidor SMTP de prueba. `respuestaRcpt(destino)` devuelve la línea de respuesta a RCPT TO. Guarda los comandos recibidos."""

    def __init__(self, respuestaRcpt):
        self.comandos: list[str] = []
        self.respuestaRcpt = respuestaRcpt
        servidor = self

        class Manejador(socketserver.StreamRequestHandler):
            def handle(self):
                self.wfile.write(b"220 mx.ejemplo.test ESMTP\r\n")
                while True:
                    linea = self.rfile.readline()
                    if not linea:
                        return
                    comando = linea.decode().strip()
                    servidor.comandos.append(comando)
                    verbo = comando.split(" ", 1)[0].upper()
                    if verbo in ("EHLO", "HELO"):
                        respuesta = "250 mx.ejemplo.test"
                    elif verbo == "MAIL":
                        respuesta = "250 2.1.0 OK"
                    elif verbo == "RCPT":
                        destino = comando.split(":", 1)[1].strip().strip("<>")
                        respuesta = servidor.respuestaRcpt(destino)
                    elif verbo == "RSET":
                        respuesta = "250 2.0.0 OK"
                    elif verbo == "QUIT":
                        self.wfile.write(b"221 2.0.0 bye\r\n")
                        return
                    else:
                        respuesta = "502 5.5.2 command not recognized"
                    self.wfile.write((respuesta + "\r\n").encode())

        self._server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Manejador)
        self._server.daemon_threads = True
        self.puerto = self._server.server_address[1]
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def cerrar(self):
        self._server.shutdown()
        self._server.server_close()


@pytest.fixture
def servidor():
    creados = []

    def crear(respuestaRcpt):
        nuevo = ServidorSmtp(respuestaRcpt)
        creados.append(nuevo)
        return nuevo

    yield crear
    for item in creados:
        item.cerrar()


def aceptaSolo(*buzonesValidos):
    def respuesta(destino):
        if destino in buzonesValidos:
            return "250 2.1.5 OK"
        return f"550 5.1.1 <{destino}>: Recipient address rejected: User unknown in virtual mailbox table"
    return respuesta


def verificar(correo, puerto, **kwargs):
    return mailboxCheck.verificarBuzon(
        correo,
        remitente=REMITENTE,
        timeout=3,
        puerto=puerto,
        consultarMx=lambda dominio, timeout: ["127.0.0.1"],
        conectar=conectarReal,
        **kwargs,
    )


# --- Buzón (RCPT TO) ----------------------------------------------------------------------------------------------


def test_buzon_existente_se_confirma_y_el_dominio_no_acepta_todo(servidor):
    srv = servidor(aceptaSolo("ana@ejemplo.test"))
    resultado = verificar("ana@ejemplo.test", srv.puerto)
    assert resultado == ResultadoBuzon(Veredicto.EXISTE, "BUZON_EXISTE", servidorAccesible=True)


def test_buzon_inexistente_devuelve_no_existe_con_motivo(servidor):
    srv = servidor(aceptaSolo("ana@ejemplo.test"))
    resultado = verificar("nadie@ejemplo.test", srv.puerto)
    assert resultado == ResultadoBuzon(Veredicto.NO_EXISTE, "BUZON_NO_ENCONTRADO", servidorAccesible=True)


def test_verificacion_nunca_transmite_el_mensaje(servidor):
    srv = servidor(aceptaSolo("ana@ejemplo.test"))
    verificar("ana@ejemplo.test", srv.puerto)
    verbos = [comando.split(" ", 1)[0].upper() for comando in srv.comandos]
    assert "RCPT" in verbos and "QUIT" in verbos
    assert "DATA" not in verbos  # sin DATA no sale ningún correo


def test_dominio_que_acepta_todo_no_es_concluyente(servidor):
    srv = servidor(lambda destino: "250 2.1.5 OK")
    resultado = verificar("ana@ejemplo.test", srv.puerto)
    assert resultado.veredicto is Veredicto.NO_VERIFICABLE and resultado.motivo == "DOMINIO_ACEPTA_TODO"


def test_politica_del_servidor_no_bloquea(servidor):
    srv = servidor(lambda destino: "550 5.7.1 Service unavailable; client host blocked by policy")
    resultado = verificar("ana@ejemplo.test", srv.puerto)
    assert resultado.veredicto is Veredicto.NO_VERIFICABLE and resultado.motivo == "POLITICA_SERVIDOR"


def test_error_temporal_no_bloquea(servidor):
    srv = servidor(lambda destino: "451 4.7.1 Temporary failure, try again later")
    resultado = verificar("ana@ejemplo.test", srv.puerto)
    assert resultado.veredicto is Veredicto.NO_VERIFICABLE and resultado.motivo == "RESPUESTA_TEMPORAL"


def test_rechazo_sin_codigo_mejorado_con_texto_claro_es_inexistente(servidor):
    srv = servidor(lambda destino: "550 no such user here")
    resultado = verificar("nadie@ejemplo.test", srv.puerto)
    assert resultado.veredicto is Veredicto.NO_EXISTE and resultado.motivo == "BUZON_NO_ENCONTRADO"


def test_rechazo_sin_codigo_mejorado_que_habla_de_politica_no_bloquea(servidor):
    srv = servidor(lambda destino: "550 Message blocked by policy, no such user")
    resultado = verificar("ana@ejemplo.test", srv.puerto)
    assert resultado.veredicto is Veredicto.NO_VERIFICABLE and resultado.motivo == "POLITICA_SERVIDOR"


# --- Dominio y servidor -------------------------------------------------------------------------------------------


def dnsQueResuelve(dominioInexistente):
    """DNS que responde NXDOMAIN solo para `dominioInexistente` y resuelve el resto (incluido el dominio de control)."""
    def resolver(self, qname, rdtype, *args, **kwargs):
        if str(qname).rstrip(".") == dominioInexistente:
            raise dns.resolver.NXDOMAIN()
        return []
    return resolver


def test_dominio_inexistente_se_informa_como_correo_no_encontrado(monkeypatch):
    monkeypatch.setattr(dns.resolver.Resolver, "resolve", dnsQueResuelve("gmial-typo.test"))
    resultado = mailboxCheck.verificarBuzon(
        "ana@gmial-typo.test", remitente=REMITENTE, consultarMx=SERVIDORES_REALES, conectar=conectarReal
    )
    assert resultado == ResultadoBuzon(Veredicto.NO_EXISTE, "DOMINIO_INEXISTENTE")


def test_nxdomain_con_dns_caido_no_se_cree(monkeypatch):
    """Si el DNS no resuelve ni el dominio de control, el NXDOMAIN no demuestra nada: no se rechaza el correo."""
    def todoNxdominio(self, qname, rdtype, *args, **kwargs):
        raise dns.resolver.NXDOMAIN()

    monkeypatch.setattr(dns.resolver.Resolver, "resolve", todoNxdominio)
    resultado = mailboxCheck.verificarBuzon(
        "ana@ejemplo.test", remitente=REMITENTE, consultarMx=SERVIDORES_REALES, conectar=conectarReal
    )
    assert resultado == ResultadoBuzon(Veredicto.NO_VERIFICABLE, "DNS_NO_DISPONIBLE")


def test_dominio_sin_mx_ni_a_no_tiene_correo(monkeypatch):
    def sinRegistros(self, qname, rdtype, *args, **kwargs):
        raise dns.resolver.NoAnswer()

    monkeypatch.setattr(dns.resolver.Resolver, "resolve", sinRegistros)
    resultado = mailboxCheck.verificarBuzon(
        "ana@sin-correo.test", remitente=REMITENTE, consultarMx=SERVIDORES_REALES, conectar=conectarReal
    )
    assert resultado == ResultadoBuzon(Veredicto.NO_EXISTE, "DOMINIO_SIN_CORREO")


def test_dns_sin_respuesta_no_bloquea(monkeypatch):
    def timeout(self, qname, rdtype, *args, **kwargs):
        raise dns.exception.Timeout()

    monkeypatch.setattr(dns.resolver.Resolver, "resolve", timeout)
    resultado = mailboxCheck.verificarBuzon(
        "ana@ejemplo.test", remitente=REMITENTE, consultarMx=SERVIDORES_REALES, conectar=conectarReal
    )
    assert resultado.veredicto is Veredicto.NO_VERIFICABLE and resultado.motivo == "DNS_NO_DISPONIBLE"


def puertoCerrado():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_servidor_caido_se_informa_sin_bloquear():
    resultado = verificar("ana@ejemplo.test", puertoCerrado())
    assert resultado == ResultadoBuzon(Veredicto.NO_VERIFICABLE, "SERVIDOR_NO_DISPONIBLE", servidorAccesible=False)


def test_si_el_primer_servidor_no_responde_se_prueba_el_siguiente(servidor):
    srv = servidor(aceptaSolo("ana@ejemplo.test"))

    def conectarSegunHost(host, puerto, timeout, nombreLocal):
        if host == "mx1.ejemplo.test":
            raise OSError("sin respuesta")
        return conectarReal("127.0.0.1", puerto, timeout, nombreLocal)

    resultado = mailboxCheck.verificarBuzon(
        "ana@ejemplo.test",
        remitente=REMITENTE,
        timeout=3,
        puerto=srv.puerto,
        consultarMx=lambda dominio, timeout: ["mx1.ejemplo.test", "mx2.ejemplo.test"],
        conectar=conectarSegunHost,
    )
    assert resultado == ResultadoBuzon(Veredicto.EXISTE, "BUZON_EXISTE", servidorAccesible=True)


def test_sin_remitente_configurado_no_se_consulta():
    resultado = mailboxCheck.verificarBuzon("ana@ejemplo.test", remitente=None)
    assert resultado == ResultadoBuzon(Veredicto.NO_VERIFICABLE, "REMITENTE_NO_CONFIGURADO")


def test_formato_invalido_es_correo_no_encontrado():
    resultado = mailboxCheck.verificarBuzon("sinarroba", remitente=REMITENTE)
    assert resultado == ResultadoBuzon(Veredicto.NO_EXISTE, "FORMATO_INVALIDO")


# --- Caché y servicio de correo ------------------------------------------------------------------------------------


def test_resultado_definitivo_se_guarda_y_no_se_no_verificable(monkeypatch):
    emailService._cacheBuzones.limpiar()
    llamadas = []

    def falso(correo, *, remitente, timeout):
        llamadas.append(correo)
        if correo == "ana@ejemplo.test":
            return ResultadoBuzon(Veredicto.EXISTE, "BUZON_EXISTE", True)
        return ResultadoBuzon(Veredicto.NO_VERIFICABLE, "SERVIDOR_NO_DISPONIBLE")

    monkeypatch.setattr(mailboxCheck, "verificarBuzon", falso)
    for _ in range(2):
        emailService.verificarDestinatario("ana@ejemplo.test")
        emailService.verificarDestinatario("otra@ejemplo.test")
    assert llamadas == ["ana@ejemplo.test", "otra@ejemplo.test", "otra@ejemplo.test"]
    emailService._cacheBuzones.limpiar()


def test_con_verificacion_desactivada_no_se_consulta_nada(monkeypatch):
    settings = emailService.getSettings().model_copy(update={"EMAIL_VERIFICAR_BUZON": False})
    monkeypatch.setattr(emailService, "getSettings", lambda: settings)
    monkeypatch.setattr(mailboxCheck, "verificarBuzon", lambda *a, **k: pytest.fail("no debe consultar"))
    resultado = emailService.verificarDestinatario("ana@ejemplo.test")
    assert resultado.motivo == "DESACTIVADA"


def test_requerir_buzon_lanza_correo_no_encontrado(monkeypatch):
    monkeypatch.setattr(
        emailService, "verificarDestinatario", lambda correo: ResultadoBuzon(Veredicto.NO_EXISTE, "BUZON_NO_ENCONTRADO")
    )
    with pytest.raises(AuthError) as error:
        emailService.requireMailboxExists("nadie@ejemplo.test")
    assert error.value.code == "CORREO_NO_ENCONTRADO"
    assert error.value.motivo == "BUZON_NO_ENCONTRADO"


def test_envio_en_segundo_plano_no_sale_si_el_correo_no_existe(monkeypatch):
    monkeypatch.setattr(
        emailService, "verificarDestinatario", lambda correo: ResultadoBuzon(Veredicto.NO_EXISTE, "BUZON_NO_ENCONTRADO")
    )
    enviados = []
    monkeypatch.setattr(emailService, "sendEmailEvent", lambda *a, **k: enviados.append(a) or True)
    emailService._sendSafely(EmailEventType.RECUPERACION_PASSWORD, "nadie@ejemplo.test", {}, False)
    assert enviados == []


def test_envio_en_segundo_plano_sale_si_el_correo_existe(monkeypatch):
    monkeypatch.setattr(
        emailService, "verificarDestinatario", lambda correo: ResultadoBuzon(Veredicto.EXISTE, "BUZON_EXISTE", True)
    )
    enviados = []
    monkeypatch.setattr(emailService, "sendEmailEvent", lambda *a, **k: enviados.append(a) or True)
    emailService._sendSafely(EmailEventType.RECUPERACION_PASSWORD, "ana@ejemplo.test", {}, False)
    assert enviados == [(EmailEventType.RECUPERACION_PASSWORD, "ana@ejemplo.test", {})]


# --- Registro -----------------------------------------------------------------------------------------------------


def registro(correo):
    return RegisterRequest(
        nombre="Ana", apellido="Gómez", usuario="anagomez", correoElectronico=correo,
        password=NUEVA_PASSWORD, aceptaPoliticaPrivacidad=True,
    )


def test_registro_con_correo_inexistente_no_crea_la_cuenta(db, mails, monkeypatch):  # noqa: F811
    monkeypatch.setattr(
        emailService, "verificarDestinatario", lambda correo: ResultadoBuzon(Veredicto.NO_EXISTE, "BUZON_NO_ENCONTRADO")
    )
    with pytest.raises(AuthError) as error:
        authService.registerLocal(db, registro("nadie@example.com"))
    assert error.value.code == "CORREO_NO_ENCONTRADO"
    assert db.scalar(select(User).where(User.correoElectronico == "nadie@example.com")) is None


def test_registro_con_correo_no_verificable_sigue_adelante(db, mails, monkeypatch):  # noqa: F811
    monkeypatch.setattr(
        emailService, "verificarDestinatario", lambda correo: ResultadoBuzon(Veredicto.NO_VERIFICABLE, "SERVIDOR_NO_DISPONIBLE")
    )
    user = authService.registerLocal(db, registro("ana@example.com"))
    assert user.correoElectronico == "ana@example.com"
