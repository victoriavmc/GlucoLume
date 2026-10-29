# KnownAccess - Criterio para avisar de un inicio de sesión desde un equipo nuevo
#
# El inicio de sesión se audita SIEMPRE (LOGIN_*, services/auth.py); eso no cambia. Lo que se decide aquí es si además merece un aviso
# visible en «Notificaciones». Criterio (RN-NOT-03), verificable y sin adivinar:
#   - se reconoce el acceso por la combinación navegador + sistema operativo + tipo de equipo (nunca por IP, que cambia con la red);
#   - es NUEVO si esa combinación no figura en AccesoConocido para la cuenta Y la cuenta ya tenía al menos un acceso conocido;
#   - el primer acceso de una cuenta (sin historia) solo se registra: no hay contra qué compararlo, así que no se afirma nada;
#   - sin datos del cliente (ninguno de los tres rótulos) no se registra ni se avisa.
# Una combinación se avisa una sola vez: queda registrada y, además, el aviso lleva una clave de unicidad por equipo.
# Todo error se registra y se ignora: el inicio de sesión nunca falla ni se demora por esto.

import hashlib
import logging
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.knownAccess import KnownAccess
from app.models.user import User
from app.services import schemaCompat
from app.utils.timeZone import nowForDb
from app.utils.userAgent import ClientInfo

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NewAccess:
    huella: str
    navegador: str | None
    sistemaOperativo: str | None
    dispositivo: str | None

    @property
    def description(self) -> str:
        base = " en ".join(part for part in (self.navegador, self.sistemaOperativo) if part)
        if not self.dispositivo:
            return base
        return f"{base} ({self.dispositivo})" if base else self.dispositivo


def fingerprint(client: ClientInfo) -> str | None:
    labels = (client.navegador, client.sistemaOperativo, client.dispositivo)
    if not any(labels):
        return None
    return hashlib.sha256("|".join(label or "" for label in labels).encode("utf-8")).hexdigest()


def registerAccess(db: Session, user: User, client: ClientInfo | None) -> NewAccess | None:
    """Registra el acceso y devuelve un NewAccess si viene de un equipo nuevo para una cuenta con historia; si no, None."""
    try:
        huella = fingerprint(client) if client is not None else None
        if huella is None or not schemaCompat.hasTable(db, "AccesoConocido"):
            return None
        now = nowForDb()
        known = db.scalar(select(KnownAccess).where(KnownAccess.idUsuario == user.idUsuario, KnownAccess.huella == huella))
        if known is not None:
            known.ultimoAcceso = now
            db.commit()
            return None
        hadHistory = (db.scalar(select(func.count(KnownAccess.idAccesoConocido)).where(
            KnownAccess.idUsuario == user.idUsuario)) or 0) > 0
        db.add(KnownAccess(idUsuario=user.idUsuario, huella=huella, navegador=client.navegador,
                           sistemaOperativo=client.sistemaOperativo, dispositivo=client.dispositivo,
                           primerAcceso=now, ultimoAcceso=now))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()  # dos inicios de sesión simultáneos desde el mismo equipo: el otro lo registró primero
            return None
        return NewAccess(huella, client.navegador, client.sistemaOperativo, client.dispositivo) if hadHistory else None
    except Exception as error:  # noqa: BLE001 - detectar un equipo nuevo nunca debe impedir iniciar sesión
        db.rollback()
        logger.error("No se pudo registrar el acceso conocido (%s).", type(error).__name__)
        return None
