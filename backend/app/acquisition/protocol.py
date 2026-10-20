# Protocol - Protocolo serie entre el Arduino y el backend (el mismo por USB y por Bluetooth HC-06)
#
# Texto ASCII, una línea por mensaje (terminada en \n). Documentado en acquisition/PROTOCOLO_SERIE.md.
#
#   Arduino → backend
#     GLUCOLUME,ID=<id>,SENSOR=<MAX30100|MAX30102>,FW=<versión>,SR=<Hz>   identificación (al arrancar y ante ID?)
#     ST,<LISTO|ADQUIRIENDO|FINALIZADA|ERROR_SENSOR>                       estado de la adquisición
#     S,<n>,<t_ms>,<red>,<ir>                                              muestra n (desde 0), tiempo relativo y canales
#     ERR,<codigo>                                                         error del dispositivo
#     PONG                                                                 respuesta a PING
#   backend → Arduino
#     ID?   identificarse        PING   probar la comunicación        START   iniciar        STOP   detener

from dataclasses import dataclass

SENSORS = ("MAX30100", "MAX30102")
STATES = ("LISTO", "ADQUIRIENDO", "FINALIZADA", "ERROR_SENSOR")


class ProtocolError(ValueError):
    pass


@dataclass(frozen=True)
class Identification:
    id: str
    sensor: str
    firmware: str
    sampleRate: int | None


@dataclass(frozen=True)
class Sample:
    number: int
    timeMs: int
    red: int
    ir: int


@dataclass(frozen=True)
class Status:
    state: str


@dataclass(frozen=True)
class DeviceError:
    code: str


@dataclass(frozen=True)
class Pong:
    pass


Message = Identification | Sample | Status | DeviceError | Pong


def parse(line: str) -> Message | None:
    """Interpreta una línea. Devuelve None si está vacía y lanza ProtocolError si no respeta el protocolo (ruido
    del enlace, línea truncada, valores fuera de rango): el llamador la descarta y la cuenta."""
    text = line.strip()
    if not text:
        return None
    parts = text.split(",")
    head = parts[0]
    try:
        if head == "S":
            if len(parts) != 5:
                raise ProtocolError("muestra con campos de más o de menos")
            number, timeMs, red, ir = (int(value) for value in parts[1:])
            if number < 0 or timeMs < 0 or red < 0 or ir < 0 or red > 262143 or ir > 262143:
                raise ProtocolError("muestra fuera de rango")
            return Sample(number, timeMs, red, ir)
        if head == "ST":
            if len(parts) != 2 or parts[1] not in STATES:
                raise ProtocolError("estado desconocido")
            return Status(parts[1])
        if head == "PONG" and len(parts) == 1:
            return Pong()
        if head == "ERR" and len(parts) == 2 and parts[1]:
            return DeviceError(parts[1][:40])
        if head == "GLUCOLUME":
            fields = dict(item.split("=", 1) for item in parts[1:] if "=" in item)
            sensor = fields.get("SENSOR", "")
            if not fields.get("ID") or sensor not in SENSORS or not fields.get("FW"):
                raise ProtocolError("identificación incompleta")
            rate = fields.get("SR")
            return Identification(fields["ID"][:100], sensor, fields["FW"][:20], int(rate) if rate else None)
    except ValueError as error:
        raise ProtocolError(str(error)) from error
    raise ProtocolError("mensaje desconocido")
