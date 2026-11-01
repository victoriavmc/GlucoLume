# Consent - Consentimientos de la persona (prototipo académico; toma como referencia la Ley 25.326)
#
# Dos consentimientos independientes, registrados en ConsentimientoUsuario (historial de solo-agregado):
#   POLITICA_PRIVACIDAD    confirmó haber leído la Política de Privacidad. Se exige para crear una cuenta (registro local,
#                          registro con Google y activación de una cuenta invitada) y lo valida el backend.
#   DATOS_EXPERIMENTALES   autorización expresa para almacenar SUS mediciones experimentales (finalidad académica; no son
#                          historia clínica). Sin una aceptación vigente el backend no inicia ni recibe muestras de
#                          mediciones del perfil propio (measurement.startMeasurement / addSamples).
#
# El estado vigente es la fila más reciente de cada tipo; revocar agrega una fila REVOCADO y NO borra lo ya medido:
# frena nuevas recolecciones. La eliminación de la cuenta es el camino para borrar los datos personales.
#
# Si cambia el texto de un consentimiento se sube su versión. La versión aceptada queda registrada en el historial y se informa en el
# estado (versionAceptada frente a versionVigente). Un cambio de versión de la POLÍTICA NO bloquea el inicio de sesión, el refresco de
# sesión ni las mediciones: la política solo se exige al crear una cuenta (requirePolicyAccepted). Solo la autorización de datos
# experimentales bloquea mediciones, y se exige su versión vigente (isActive). Ver docs/PRIVACIDAD_Y_RETENCION.md, sección de cambios.
#
# Alcance: las mediciones de pacientes de una institución las opera personal de esa institución; su consentimiento lo
# gestiona la institución y NO lo cubre este módulo (ver docs/PRIVACIDAD.md).

import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AuthError
from app.models.consent import Consent, EstadoConsentimiento, TipoConsentimiento
from app.models.user import User
from app.utils.timeZone import nowForDb

POLICY_VERSION = "1.2"  # 1.2: IP y navegador anulados a 90 días desde el evento; extensión de hasta 90 días desde la eliminación (seguridad)
# 1.1 (19/10/2026): la auditoría guarda IP y navegador 90 días (GL-23).
EXPERIMENTAL_VERSION = "1.0"
CURRENT_VERSIONS = {
    TipoConsentimiento.POLITICA_PRIVACIDAD: POLICY_VERSION,
    TipoConsentimiento.DATOS_EXPERIMENTALES: EXPERIMENTAL_VERSION,
}

POLICY_NOT_ACCEPTED = "Para continuar tenés que confirmar que leíste la Política de Privacidad."
EXPERIMENTAL_REQUIRED = (
    "Para medir tenés que autorizar el tratamiento de tus mediciones experimentales (finalidad académica). "
    "Podés hacerlo desde la pantalla de mediciones."
)


def _latest(db: Session, idUsuario: uuid.UUID, tipo: TipoConsentimiento) -> Consent | None:
    return db.scalar(
        select(Consent).where(Consent.idUsuario == idUsuario, Consent.tipo == tipo)
        .order_by(Consent.fechaHora.desc()).limit(1)
    )


def record(db: Session, user: User, tipo: TipoConsentimiento, accepted: bool) -> Consent:
    """Agrega una fila al historial (sin commit: acompaña la transacción del llamador). Nunca modifica las anteriores."""
    previous = _latest(db, user.idUsuario, tipo)
    when: datetime = nowForDb()
    if previous is not None and when <= previous.fechaHora:
        when = previous.fechaHora + timedelta(milliseconds=1)  # el orden del historial no depende del reloj
    row = Consent(
        idUsuario=user.idUsuario, tipo=tipo.value, version=CURRENT_VERSIONS[tipo],
        estado=(EstadoConsentimiento.ACEPTADO if accepted else EstadoConsentimiento.REVOCADO).value, fechaHora=when,
    )
    db.add(row)
    db.flush()
    return row


def isActive(db: Session, user: User, tipo: TipoConsentimiento) -> bool:
    """Aceptación vigente: la última fila es ACEPTADO y de la versión actual del texto."""
    latest = _latest(db, user.idUsuario, tipo)
    return (latest is not None and latest.estado == EstadoConsentimiento.ACEPTADO
            and latest.version == CURRENT_VERSIONS[tipo])


def status(db: Session, user: User) -> dict[str, dict]:
    """Estado de cada consentimiento: aceptado vigente, versión vigente del texto y última fecha registrada."""
    result = {}
    for tipo, version in CURRENT_VERSIONS.items():
        latest = _latest(db, user.idUsuario, tipo)
        result[tipo.value] = {
            "aceptado": isActive(db, user, tipo), "versionVigente": version,
            "versionAceptada": latest.version if latest else None,
            "estado": latest.estado if latest else None, "fecha": latest.fechaHora if latest else None,
        }
    return result


def requirePolicyAccepted(accepted: bool) -> None:
    if not accepted:
        raise AuthError("POLITICA_NO_ACEPTADA", POLICY_NOT_ACCEPTED)


def requireExperimentalData(db: Session, user: User) -> None:
    """Barrera de backend (no depende del frontend): sin autorización vigente no se recolectan datos experimentales."""
    if not isActive(db, user, TipoConsentimiento.DATOS_EXPERIMENTALES):
        raise AuthError("CONSENTIMIENTO_REQUERIDO", EXPERIMENTAL_REQUIRED)


def setExperimentalConsent(db: Session, user: User, accepted: bool) -> dict[str, dict]:
    """Acepta o revoca la autorización de datos experimentales. Solo agrega una fila si cambia el estado vigente."""
    if isActive(db, user, TipoConsentimiento.DATOS_EXPERIMENTALES) != accepted:
        row = record(db, user, TipoConsentimiento.DATOS_EXPERIMENTALES, accepted)
        from app.services.audit import registerEvent  # import diferido: audit no depende de este módulo

        registerEvent(db, "PERMISO", "CONSENTIMIENTO_DATOS_EXPERIMENTALES" if accepted else "REVOCAR_CONSENTIMIENTO_DATOS_EXPERIMENTALES",
                      True, user.idUsuario, "ConsentimientoUsuario", row.idConsentimiento,
                      datosNuevos={"estado": row.estado, "version": row.version})
        db.commit()
    return status(db, user)


def acceptCurrentPolicy(db: Session, user: User) -> dict[str, dict]:
    """Acepta la versión vigente de la Política de Privacidad desde el aviso dentro de la aplicación. NO bloquea nada: sin esta aceptación
    la extensión de 90 días desde la baja no aplica a la cuenta. Solo agrega una fila si la versión vigente todavía no está aceptada."""
    if not isActive(db, user, TipoConsentimiento.POLITICA_PRIVACIDAD):
        row = record(db, user, TipoConsentimiento.POLITICA_PRIVACIDAD, True)
        from app.services.audit import registerEvent  # import diferido: audit no depende de este módulo

        registerEvent(db, "PERMISO", "CONSENTIMIENTO_POLITICA_PRIVACIDAD", True, user.idUsuario, "ConsentimientoUsuario", row.idConsentimiento,
                      datosNuevos={"estado": row.estado, "version": row.version})
        db.commit()
    return status(db, user)
