# MailboxCheck - Verificación previa de un correo, sin enviar mensajes
#
# 1. Dominio y servidor: consulta los registros MX del dominio (o el A, si no hay MX) y abre una conexión SMTP al puerto 25 de
#    los primeros servidores. Si ninguno responde, el servidor no es accesible y el resultado no puede afirmar nada.
# 2. Buzón: pide RCPT TO con el destinatario y corta ahí (nunca se transmite DATA, así que no sale ningún mensaje).
#    - Si el servidor rechaza el buzón con un código de «destinatario inexistente» (5.1.x o texto equivalente), el correo no existe.
#    - Si lo acepta, prueba con una dirección aleatoria del mismo dominio: si también la acepta, el dominio acepta todo (catch-all)
#      y la respuesta no sirve para nada: queda NO_VERIFICABLE.
#
# Un resultado dudoso (política anti-spam, error temporal, servidor caído, DNS sin respuesta, catch-all) nunca bloquea:
# se devuelve NO_VERIFICABLE y quien llama decide. Solo NO_EXISTE justifica rechazar un correo.
#
# Las consultas salen desde este servidor: muchos proveedores bloquean o limitan las conexiones SMTP desde IP de centros de datos,
# por eso lo habitual es obtener NO_VERIFICABLE con motivo SERVIDOR_NO_DISPONIBLE o POLITICA_SERVIDOR.

import re
import secrets
import smtplib
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

import dns.exception
import dns.resolver

PUERTO_SMTP = 25
# Servidores de correo del dominio que se prueban como máximo (por preferencia de MX).
MAX_SERVIDORES = 2
# Dominio que siempre existe: sirve para comprobar que el DNS funciona antes de creer en un NXDOMAIN.
DOMINIO_DE_CONTROL = "example.com"
# Dominio que siempre existe: sirve para comprobar que el DNS funciona antes de creer en un NXDOMAIN.
DOMINIO_DE_CONTROL = "example.com"
# Códigos de estado mejorados (RFC 3463) que significan «el buzón o la dirección no existe».
SUBCODIGOS_BUZON_INEXISTENTE = frozenset({"5.1.0", "5.1.1", "5.1.2", "5.1.10"})
CODIGOS_RECHAZO_BUZON = frozenset({550, 551, 553})

_POLITICA = re.compile(
    r"blocked|blacklist|block list|reputation|policy|spam|rate limit|too many|listed|denied|"
    r"bloquead|pol[ií]tica|lista negra|reputaci[oó]n",
    re.IGNORECASE,
)
_BUZON_INEXISTENTE = re.compile(
    r"user unknown|no such user|unknown user|no such (mailbox|recipient|address|user)|"
    r"mailbox (not found|does not exist|doesn't exist)|recipient (address )?rejected|"
    r"does not exist|doesn't exist|no existe|usuario desconocido",
    re.IGNORECASE,
)
_CODIGO_MEJORADO = re.compile(r"\b5\.(\d{1,3})\.(\d{1,3})\b")


class Veredicto(StrEnum):
    EXISTE = "EXISTE"
    NO_EXISTE = "NO_EXISTE"
    NO_VERIFICABLE = "NO_VERIFICABLE"


@dataclass(frozen=True)
class ResultadoBuzon:
    veredicto: Veredicto
    # Código estable que explica el veredicto (nunca texto libre del servidor).
    motivo: str
    # Validación del servidor SMTP: True si al menos un servidor del dominio respondió por SMTP.
    servidorAccesible: bool = False


class _DominioInexistente(Exception):
    """NXDOMAIN: el dominio no existe."""


class _DominioSinCorreo(Exception):
    """El dominio existe pero no tiene MX ni A (o tiene MX nulo, RFC 7505)."""


def _comprobarResolver(resolver: dns.resolver.Resolver) -> None:
    """Un NXDOMAIN solo prueba que el dominio no existe si el DNS funciona. Si el resolver tampoco resuelve un dominio conocido
    (DNS caído, bloqueado o mal configurado), el NXDOMAIN no prueba nada y se informa como error de DNS."""
    try:
        resolver.resolve(DOMINIO_DE_CONTROL, "A")
    except dns.exception.DNSException as error:
        raise dns.exception.DNSException("El DNS no resuelve el dominio de control.") from error


def _servidoresDeCorreo(dominio: str, timeout: float) -> list[str]:
    """Hosts SMTP del dominio por preferencia. Lanza _DominioInexistente, _DominioSinCorreo o un error de DNS (dns.exception)."""
    resolver = dns.resolver.Resolver()
    resolver.lifetime = timeout
    try:
        registros = sorted(resolver.resolve(dominio, "MX"), key=lambda registro: registro.preference)
    except dns.resolver.NXDOMAIN as error:
        _comprobarResolver(resolver)
        raise _DominioInexistente from error
    except dns.resolver.NoAnswer:
        registros = []
    hosts = [str(registro.exchange).rstrip(".") for registro in registros]
    if hosts == [""]:
        raise _DominioSinCorreo  # MX nulo: el dominio declara que no recibe correo
    if hosts:
        return hosts
    # Sin MX, SMTP usa el registro A del propio dominio (RFC 5321, §5.1).
    try:
        resolver.resolve(dominio, "A")
    except dns.resolver.NXDOMAIN as error:
        _comprobarResolver(resolver)
        raise _DominioSinCorreo from error
    except dns.resolver.NoAnswer as error:
        raise _DominioSinCorreo from error
    return [dominio]


def _conectarPorDefecto(host: str, puerto: int, timeout: float, nombreLocal: str) -> smtplib.SMTP:
    return smtplib.SMTP(host, puerto, timeout=timeout, local_hostname=nombreLocal)


def _clasificarRespuesta(codigo: int, texto: str) -> tuple[Veredicto, str]:
    """Interpreta la respuesta a RCPT TO. Devuelve (veredicto, motivo); EXISTE con motivo ACEPTADO significa «el servidor aceptó»."""
    if codigo in (250, 251):
        return Veredicto.EXISTE, "ACEPTADO"
    if 400 <= codigo < 500:
        return Veredicto.NO_VERIFICABLE, "RESPUESTA_TEMPORAL"
    if codigo not in CODIGOS_RECHAZO_BUZON:
        return Veredicto.NO_VERIFICABLE, "RESPUESTA_NO_CONCLUYENTE"
    mejorado = _CODIGO_MEJORADO.search(texto)
    if mejorado is not None:
        subcodigo = f"5.{mejorado.group(1)}.{mejorado.group(2)}"
        if subcodigo in SUBCODIGOS_BUZON_INEXISTENTE:
            return Veredicto.NO_EXISTE, "BUZON_NO_ENCONTRADO"
        if subcodigo.startswith("5.7."):
            return Veredicto.NO_VERIFICABLE, "POLITICA_SERVIDOR"
        return Veredicto.NO_VERIFICABLE, "RECHAZO_NO_CONCLUYENTE"
    # Sin código mejorado: solo se acepta el rechazo si el texto dice claramente que el buzón no existe, y nunca si habla de políticas.
    if _POLITICA.search(texto):
        return Veredicto.NO_VERIFICABLE, "POLITICA_SERVIDOR"
    if _BUZON_INEXISTENTE.search(texto):
        return Veredicto.NO_EXISTE, "BUZON_NO_ENCONTRADO"
    return Veredicto.NO_VERIFICABLE, "RECHAZO_NO_CONCLUYENTE"


def _rcpt(servidor: smtplib.SMTP, remitente: str, destinatario: str) -> tuple[Veredicto, str]:
    codigo, _ = servidor.mail(remitente)
    if codigo >= 400:
        raise _RemitenteRechazado
    codigo, respuesta = servidor.rcpt(destinatario)
    texto = respuesta.decode("utf-8", errors="replace") if isinstance(respuesta, bytes) else str(respuesta)
    return _clasificarRespuesta(codigo, texto)


class _RemitenteRechazado(Exception):
    """El servidor no acepta MAIL FROM: no se puede preguntar por ningún buzón."""


def _cerrar(servidor: smtplib.SMTP) -> None:
    try:
        servidor.quit()
    except Exception:  # noqa: BLE001 - cerrar nunca cambia el resultado de la consulta
        servidor.close()


def _consultarServidor(
    host: str, correo: str, dominio: str, remitente: str, *, puerto: int, timeout: float,
    conectar: Callable[[str, int, float, str], smtplib.SMTP],
) -> ResultadoBuzon:
    """Pregunta a un servidor. Los errores de conexión suben para que se pruebe el siguiente MX; cualquier fallo posterior
    ya es parte de una conversación real y se informa como resultado no concluyente."""
    dominioRemitente = remitente.rsplit("@", 1)[-1]
    servidor = conectar(host, puerto, timeout, dominioRemitente)
    try:
        servidor.ehlo_or_helo_if_needed()
        veredicto, motivo = _rcpt(servidor, remitente, correo)
        if veredicto is Veredicto.NO_EXISTE:
            return ResultadoBuzon(Veredicto.NO_EXISTE, motivo, servidorAccesible=True)
        if veredicto is Veredicto.NO_VERIFICABLE:
            return ResultadoBuzon(Veredicto.NO_VERIFICABLE, motivo, servidorAccesible=True)
        # Aceptado: comprobar que el dominio no acepte cualquier dirección.
        servidor.rset()
        azar = f"glucolume-{secrets.token_hex(8)}@{dominio}"
        veredictoAzar, _ = _rcpt(servidor, remitente, azar)
        if veredictoAzar is Veredicto.EXISTE:
            return ResultadoBuzon(Veredicto.NO_VERIFICABLE, "DOMINIO_ACEPTA_TODO", servidorAccesible=True)
        if veredictoAzar is Veredicto.NO_EXISTE:
            return ResultadoBuzon(Veredicto.EXISTE, "BUZON_EXISTE", servidorAccesible=True)
        return ResultadoBuzon(Veredicto.NO_VERIFICABLE, "RESPUESTA_NO_CONCLUYENTE", servidorAccesible=True)
    except _RemitenteRechazado:
        return ResultadoBuzon(Veredicto.NO_VERIFICABLE, "REMITENTE_RECHAZADO", servidorAccesible=True)
    except (OSError, smtplib.SMTPException):
        return ResultadoBuzon(Veredicto.NO_VERIFICABLE, "CONVERSACION_INTERRUMPIDA", servidorAccesible=True)
    finally:
        _cerrar(servidor)


def verificarBuzon(
    correo: str,
    *,
    remitente: str | None,
    timeout: float = 5.0,
    puerto: int = PUERTO_SMTP,
    consultarMx: Callable[[str, float], list[str]] | None = None,
    conectar: Callable[[str, int, float, str], smtplib.SMTP] | None = None,
) -> ResultadoBuzon:
    """Verifica un correo sin enviarle mensajes. `remitente` es la dirección de GlucoLume usada en MAIL FROM.

    `consultarMx` y `conectar` se pueden reemplazar (pruebas); por defecto usan DNS y SMTP reales.
    """
    if not remitente or "@" not in remitente:
        return ResultadoBuzon(Veredicto.NO_VERIFICABLE, "REMITENTE_NO_CONFIGURADO")
    partes = correo.split("@")
    if len(partes) != 2 or not partes[0] or not partes[1]:
        return ResultadoBuzon(Veredicto.NO_EXISTE, "FORMATO_INVALIDO")
    dominioDestino = partes[1].lower()
    consultar = consultarMx or _servidoresDeCorreo
    try:
        hosts = consultar(dominioDestino, timeout)
    except _DominioInexistente:
        return ResultadoBuzon(Veredicto.NO_EXISTE, "DOMINIO_INEXISTENTE")
    except _DominioSinCorreo:
        return ResultadoBuzon(Veredicto.NO_EXISTE, "DOMINIO_SIN_CORREO")
    except (dns.exception.DNSException, OSError):
        return ResultadoBuzon(Veredicto.NO_VERIFICABLE, "DNS_NO_DISPONIBLE")

    abrir = conectar or _conectarPorDefecto
    for host in hosts[:MAX_SERVIDORES]:
        try:
            return _consultarServidor(
                host, correo, dominioDestino, remitente, puerto=puerto, timeout=timeout, conectar=abrir
            )
        except (OSError, smtplib.SMTPException):
            continue  # este servidor no responde por SMTP: se prueba el siguiente
    return ResultadoBuzon(Veredicto.NO_VERIFICABLE, "SERVIDOR_NO_DISPONIBLE", servidorAccesible=False)


class CacheVeredictos:
    """Memoria de resultados definitivos (EXISTE / NO_EXISTE) para no repetir la consulta a un mismo correo en poco tiempo.
    Los NO_VERIFICABLE no se guardan: un fallo transitorio no debe fijarse durante horas."""

    def __init__(self, ttlSegundos: float = 3600.0, maxEntradas: int = 5000) -> None:
        self._ttl = ttlSegundos
        self._max = maxEntradas
        self._datos: dict[str, tuple[float, ResultadoBuzon]] = {}
        self._lock = threading.Lock()

    def obtener(self, correo: str) -> ResultadoBuzon | None:
        with self._lock:
            entrada = self._datos.get(correo)
            if entrada is None:
                return None
            vence, resultado = entrada
            if time.monotonic() >= vence:
                del self._datos[correo]
                return None
            return resultado

    def guardar(self, correo: str, resultado: ResultadoBuzon) -> None:
        if resultado.veredicto is Veredicto.NO_VERIFICABLE:
            return
        with self._lock:
            if len(self._datos) >= self._max:
                self._datos.clear()  # tope simple: el caché se reconstruye con las siguientes consultas
            self._datos[correo] = (time.monotonic() + self._ttl, resultado)

    def limpiar(self) -> None:
        with self._lock:
            self._datos.clear()
