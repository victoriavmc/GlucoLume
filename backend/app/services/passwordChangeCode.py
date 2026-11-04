# Cambio de contraseña con código por correo: cuenta administrativa SIN MFA activo (POST /platform/password/code).
#
#   1. requestCode(db, user, password)
#        - revalida la contraseña actual (mismo contador y bloqueo que el login);
#        - genera un código de 6 dígitos, TokenCuenta CODIGO_CAMBIO_PASSWORD (10 min, solo su HMAC) e invalida el pendiente;
#        - lo envía al correo registrado de la cuenta (nunca a uno ingresado en el formulario).
#   2. verifyCode(db, user, codigo)   (lo llama platform.reauthenticate al cambiar la contraseña)
#        - un solo intento por código: un error lo invalida y hay que pedir otro;
#        - si es correcto, lo consume en la misma transacción.
#
# Límites: un código por minuto y como máximo 3 por hora por cuenta (contados en TokenCuenta).

import hmac
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core import security
from app.core.exceptions import AuthError
from app.emails.eventTypes import EmailEventType
from app.emails.formatting import maskEmail
from app.models.accountToken import AccountToken, TipoTokenCuenta
from app.models.localCredential import LocalCredential
from app.models.user import User
from app.services import auth as authService
from app.services import email as emailService
from app.services.audit import registerEvent
from app.utils.timeZone import nowForDb

TOKEN_CODIGO_CAMBIO = TipoTokenCuenta.CODIGO_CAMBIO_PASSWORD
CODE_VALIDITY_MINUTES = 10
RESEND_COOLDOWN_SECONDS = 60
MAX_CODES_PER_HOUR = 3
ACCION_SOLICITUD = "CODIGO_CAMBIO_PASSWORD_SOLICITADO"


def _requireCodeAllowed(db: Session, idUsuario: uuid.UUID, now: datetime) -> None:
    recent = db.scalars(
        select(AccountToken.fechaCreacion).where(
            AccountToken.idUsuario == idUsuario,
            AccountToken.tipo == TOKEN_CODIGO_CAMBIO,
            AccountToken.fechaCreacion > now - timedelta(hours=1),
        )
    ).all()
    if len(recent) >= MAX_CODES_PER_HOUR:
        raise AuthError("DEMASIADAS_SOLICITUDES", "Pediste varios códigos seguidos. Probá de nuevo en una hora.")
    if recent and max(recent) > now - timedelta(seconds=RESEND_COOLDOWN_SECONDS):
        raise AuthError("DEMASIADAS_SOLICITUDES", "Esperá un minuto antes de pedir un código nuevo.")


def _pendingCode(db: Session, idUsuario: uuid.UUID) -> AccountToken | None:
    return db.scalar(
        select(AccountToken)
        .where(
            AccountToken.idUsuario == idUsuario,
            AccountToken.tipo == TOKEN_CODIGO_CAMBIO,
            AccountToken.fechaUso.is_(None),
        )
        .order_by(AccountToken.fechaCreacion.desc())
    )


def requestCode(db: Session, user: User, password: str) -> str:
    """Envía el código al correo registrado y devuelve el correo enmascarado."""
    credential = db.scalar(select(LocalCredential).where(LocalCredential.idUsuario == user.idUsuario))
    if credential is None:
        raise AuthError("CUENTA_SOLO_GOOGLE", "Tu cuenta ingresa con Google y no tiene contraseña local.")
    if not authService.verifyCurrentPassword(db, credential, password):
        registerEvent(db, "PERMISO", ACCION_SOLICITUD, False, user.idUsuario, observacion="Contraseña incorrecta",
                      motivo="PASSWORD_INCORRECTA")
        db.commit()
        raise AuthError("PASSWORD_INCORRECTA", "La contraseña ingresada no es correcta.")

    now = nowForDb()
    _requireCodeAllowed(db, user.idUsuario, now)
    # Un código nuevo invalida el pendiente anterior (queda usado: sigue contando para el límite por hora).
    db.execute(
        update(AccountToken)
        .where(
            AccountToken.idUsuario == user.idUsuario,
            AccountToken.tipo == TOKEN_CODIGO_CAMBIO,
            AccountToken.fechaUso.is_(None),
        )
        .values(fechaUso=now)
    )
    code = security.generateNumericCode()
    idToken = uuid.uuid4()
    db.add(
        AccountToken(
            idTokenCuenta=idToken,
            idUsuario=user.idUsuario,
            tipo=TOKEN_CODIGO_CAMBIO,
            tokenHash=security.hashShortCode(TOKEN_CODIGO_CAMBIO, user.idUsuario, idToken, code),
            fechaCreacion=now,
            fechaExpiracion=now + timedelta(minutes=CODE_VALIDITY_MINUTES),
        )
    )
    registerEvent(db, "PERMISO", ACCION_SOLICITUD, True, user.idUsuario, "Usuario", user.idUsuario)
    authService.commitAccountToken(db, TOKEN_CODIGO_CAMBIO)

    sent = emailService.sendEmailEvent(
        EmailEventType.CODIGO_CAMBIO_PASSWORD,
        user.correoElectronico,
        {"nombre": user.nombre, "codigoSeguridad": code, "minutosValidez": CODE_VALIDITY_MINUTES},
    )
    if not sent:
        raise AuthError("CORREO_NO_ENVIADO", "No pudimos enviarte el código. Intentá más tarde.")
    return maskEmail(user.correoElectronico)


def verifyCode(db: Session, user: User, codigo: str) -> None:
    """Consume el código pendiente. Un código incorrecto o vencido queda invalidado; el correcto se marca usado."""
    now = nowForDb()
    pending = _pendingCode(db, user.idUsuario)
    if pending is None:
        raise AuthError("CODIGO_INVALIDO", "El código no es válido. Pedí uno nuevo.")
    if pending.fechaExpiracion <= now:
        raise AuthError("CODIGO_VENCIDO", "El código venció. Pedí uno nuevo.")
    expected = security.hashShortCode(TOKEN_CODIGO_CAMBIO, user.idUsuario, pending.idTokenCuenta, codigo.strip())
    if not hmac.compare_digest(expected, pending.tokenHash):
        pending.fechaUso = now  # un solo intento por código: sin esto, 6 dígitos se probarían en serie
        db.commit()
        raise AuthError("CODIGO_INVALIDO", "El código es incorrecto. Pedí uno nuevo.")
    consumed = db.execute(
        update(AccountToken)
        .where(AccountToken.idTokenCuenta == pending.idTokenCuenta, AccountToken.fechaUso.is_(None))
        .values(fechaUso=now)
    )
    if consumed.rowcount != 1:
        db.rollback()
        raise AuthError("CODIGO_INVALIDO", "El código ingresado no es válido. Pedí uno nuevo.")
