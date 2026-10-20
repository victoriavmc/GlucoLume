# Audit - Servicio central de registro de eventos de auditoría
#
# Todos los módulos registran sus eventos con registerEvent: no hay otra forma de escribir en Auditoria. El servicio
# completa solo lo que cada llamador no debería repetir:
#   - modulo: módulo funcional del evento (a partir de la entidad afectada);
#   - idInstitucion: institución DONDE OCURRIÓ el evento, resuelta desde la entidad afectada (la institución del
#     paciente, de la matriz, del vínculo…), nunca desde el usuario: una cuenta puede pertenecer a varias
#     instituciones. Los eventos de cuenta y autenticación no tienen institución y quedan en la auditoría global.
#   - fecha y hora: hora de Argentina (la fija el backend; ver app/db/base.py y app/utils/timeZone.py).
# Nunca se guardan secretos: las claves sensibles de datosPrevios/datosNuevos se descartan antes de persistir.
#
# Transacciones: registerEvent agrega el evento a la sesión y lo confirma quien llama junto con la operación. Para los
# intentos rechazados o fallidos de operaciones críticas, registerFailure deshace el trabajo pendiente de la operación y
# confirma SOLO el evento, de modo que el rechazo queda registrado aunque la operación principal no se aplique.
#
# La consulta de la auditoría vive en app/services/auditQuery.py y no se audita a sí misma (salvo los intentos no
# autorizados, que son un único alta sin recursión). Los registros son de solo lectura: ningún endpoint los modifica ni
# los elimina.

import hashlib
import hmac
import json
import re
import uuid
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import requestContext
from app.core.config import getSettings
from app.models.audit import Audit
from app.models.auditContext import AuditContext
from app.models.device import Device
from app.models.institutionUser import InstitutionUser
from app.models.user import User
from app.models.matrix import Matrix
from app.models.measurement import Measurement
from app.models.measurementProfile import MeasurementProfile
from app.models.profileTransfer import ProfileTransfer
from app.services import schemaCompat

TipoEvento = Literal["LOGIN", "CRUD", "PERMISO", "ACCESO"]

MODULOS = (
    "CUENTA", "GRUPOS", "INSTITUCIONES", "PERFILES", "MEDICIONES", "DISPOSITIVOS", "MATRICES", "PLATAFORMA", "AUDITORIA",
    "SEGURIDAD", "SISTEMA",
)
MODULO_POR_TABLA = {
    "Usuario": "CUENTA", "CredencialLocal": "CUENTA", "IdentidadExterna": "CUENTA", "FactorMfa": "CUENTA",
    "SesionUsuario": "CUENTA", "TokenCuenta": "CUENTA",
    "Grupo": "GRUPOS", "GrupoUsuario": "GRUPOS",
    "Institucion": "INSTITUCIONES", "InstitucionUsuario": "INSTITUCIONES",
    "PerfilMedicion": "PERFILES", "TransferenciaPerfil": "PERFILES",
    "Medicion": "MEDICIONES", "MedicionReferenciaCapilar": "MEDICIONES",
    "Dispositivo": "DISPOSITIVOS", "Matriz": "MATRICES", "ReglaMatriz": "MATRICES",
}
# Operaciones críticas: las que cambian accesos, responsabilidades, configuración o datos de forma difícil de revertir.
ACCIONES_CRITICAS = frozenset({
    "ELIMINACION_CUENTA", "ELIMINAR_INSTITUCION", "REABRIR_INSTITUCION", "REVOCAR_MIEMBRO_INSTITUCION",
    "ELIMINAR_INSTITUCION_ADMINISTRATIVA", "PAUSAR_INSTITUCION", "REACTIVAR_INSTITUCION", "MODIFICAR_CUPOS_INSTITUCION",
    "MODIFICAR_MIEMBRO_INSTITUCION", "ELIMINAR_GRUPO", "TRANSFERIR_ADMINISTRACION_GRUPO", "DESVINCULAR_INTEGRANTE_GRUPO",
    "BAJA_PACIENTE", "CAMBIAR_RESPONSABLE_PERFIL", "ASIGNAR_RESPONSABLE_PACIENTE", "ACEPTAR_TRANSFERENCIA_PERFIL",
    "ACTIVAR_MATRIZ", "DESACTIVAR_MATRIZ", "ARCHIVAR_MATRIZ", "MFA_DESHABILITADO", "MFA_DESHABILITADO_POR_RECUPERACION",
    "REFRESH_REUTILIZADO", "DEPURAR_DATOS_PACIENTES", "CONSULTAR_AUDITORIA", "DESCOMISIONAR_DISPOSITIVO",
    "DESVINCULAR_DISPOSITIVO", "ASIGNAR_DISPOSITIVO",
    "ELIMINACION_AUTOMATICA_CUENTA", "INICIAR_PERIODO_GRACIA", "PACIENTES_PENDIENTES_REASIGNACION", "MINIMIZAR_DATOS_PERSONAL_HISTORICO",
    "ELIMINAR_DATOS_PERSONAL_HISTORICO", "ANONIMIZAR_PACIENTES", "DEPURAR_MEDICIONES_RETENCION",
})
_SENSITIVE_KEY = re.compile(r"pass|token|secret|hash|clave|otp|totp|credencial|^codigo$|^codigoRecuperacion$|^codigoMfa$",
                            re.IGNORECASE)


def moduleFor(tipoEvento: str, tablaAfectada: str | None) -> str:
    if tablaAfectada in MODULO_POR_TABLA:
        return MODULO_POR_TABLA[tablaAfectada]
    return "CUENTA" if tipoEvento == "LOGIN" else "SISTEMA"


def sanitize(data):
    """Descarta valores de claves sensibles (contraseñas, tokens, secretos, códigos) de forma recursiva."""
    if isinstance(data, dict):
        return {key: "[omitido]" if _SENSITIVE_KEY.search(str(key)) else sanitize(value) for key, value in data.items()}
    if isinstance(data, list):
        return [sanitize(item) for item in data]
    return data


def resolveInstitution(db: Session, tabla: str | None, idRegistro: uuid.UUID | None) -> uuid.UUID | None:
    """Institución donde ocurrió el evento, según la entidad afectada. None si la entidad no es institucional."""
    if tabla is None or idRegistro is None:
        return None
    if tabla == "Institucion":
        return idRegistro
    if tabla == "InstitucionUsuario":
        relation = db.get(InstitutionUser, idRegistro)
        return relation.idInstitucion if relation else None
    if tabla == "Matriz":
        matrix = db.get(Matrix, idRegistro)
        return matrix.idInstitucion if matrix else None
    if tabla == "Dispositivo":
        device = db.get(Device, idRegistro)
        return device.idInstitucionAsignada if device else None
    if tabla == "TransferenciaPerfil":
        transfer = db.get(ProfileTransfer, idRegistro)
        relation = db.get(InstitutionUser, transfer.idOperadorDestino) if transfer else None
        return relation.idInstitucion if relation else None
    profile = None
    if tabla == "PerfilMedicion":
        profile = db.get(MeasurementProfile, idRegistro)
    elif tabla == "Medicion":
        measurement = db.get(Measurement, idRegistro)
        profile = db.get(MeasurementProfile, measurement.idPerfilMedicion) if measurement else None
    if profile is not None and profile.idInstitucionUsuarioResponsable is not None:
        relation = db.get(InstitutionUser, profile.idInstitucionUsuarioResponsable)
        return relation.idInstitucion if relation else None
    return None


# Campos de datosPrevios/datosNuevos que referencian una relación institucional (InstitucionUsuario). Solo estos se
# resuelven a una persona: no se convierte en nombre cualquier UUID.
RELATION_FIELDS = {
    "idInstitucionUsuarioResponsable": "Responsable institucional",
    "idInstitucionUsuarioRegistrante": "Registrado por",
    "idOperadorDestino": "Operador destinatario",
    "idResponsable": "Responsable del dispositivo",
}
PLATFORM_ACCOUNTS = ("MODERADOR_PLATAFORMA", "ADMINISTRADOR_PLATAFORMA")


def _asUuid(value) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value)) if value else None
    except ValueError:
        return None


def personName(relation: InstitutionUser | None, user: User | None) -> str | None:
    """Nombre con el que se identifica a la persona de una relación institucional: primero la identidad registrada en el
    vínculo (nombre/apellido profesional histórico, que sobrevive a bajas y a la eliminación de la cuenta) y, si no hay,
    el de la cuenta mientras siga vigente. Nunca incluye documento, matrícula ni otros datos."""
    parts = []
    if relation is not None:
        if relation.fechaMinimizacionDatos is not None:
            return None  # vencido el plazo de conservación: ni siquiera el nombre de la cuenta vigente identifica a la persona en ese vínculo
        parts = [relation.nombreProfesionalHistorico, relation.apellidoProfesionalHistorico]
    if not any(parts) and user is not None and user.estado != "ELIMINADO":
        parts = [user.nombre, user.apellido]
    name = " ".join(part.strip() for part in parts if part and part.strip())
    return name or None


def _referencedRelations(tabla, idRegistro, tablaRelacionada, idRelacionado, *blobs) -> set[uuid.UUID]:
    ids: set[uuid.UUID] = set()
    for blob in blobs:
        for key in RELATION_FIELDS:
            found = _asUuid((blob or {}).get(key))
            if found:
                ids.add(found)
    if tabla == "InstitucionUsuario" and idRegistro:
        ids.add(idRegistro)
    if tablaRelacionada == "InstitucionUsuario" and idRelacionado:
        ids.add(idRelacionado)
    return ids


def _identitySnapshot(db: Session, relationIds: set[uuid.UUID], idUsuario, idInstitucion) -> dict | None:
    """Referencia histórica mínima del evento: nombre (y rol) de las personas involucradas AL MOMENTO de la operación y
    de quien la ejecutó. Se guarda en `detalle` para que la auditoría siga siendo comprensible aunque la persona cambie
    de nombre, sea desvinculada o elimine su cuenta. Solo nombre completo y rol; los UUID siguen siendo la referencia."""
    people = {}
    for relationId in relationIds:
        relation = db.get(InstitutionUser, relationId)
        if relation is None or relation.idInstitucion != idInstitucion:
            continue  # un UUID de otra institución no se resuelve ni se guarda
        name = personName(relation, db.get(User, relation.idUsuarioInvitado))
        if name:
            people[str(relationId)] = {"nombreCompleto": name, "rol": relation.rolInstitucion}
    actor = None
    if idUsuario is not None and idInstitucion is not None:
        row = db.scalar(select(InstitutionUser).where(
            InstitutionUser.idInstitucion == idInstitucion, InstitutionUser.idUsuarioInvitado == idUsuario,
        ).order_by(InstitutionUser.fechaInvitacion.desc()))
        user = db.get(User, idUsuario)
        if row is not None:
            name = personName(row, user)
            actor = {"nombreCompleto": name, "rol": row.rolInstitucion} if name else None
        elif user is not None and user.tipoCuenta in PLATFORM_ACCOUNTS:
            actor = {"nombreCompleto": None, "rol": "PLATAFORMA"}
    if not people and not actor:
        return None
    snapshot = {}
    if people:
        snapshot["personas"] = people
    if actor:
        snapshot["actor"] = actor
    return snapshot


def hashIdentifier(identifier: str) -> str:
    """HMAC (clave del servidor) del identificador escrito en un intento de acceso sobre una cuenta inexistente. Permite ver que el mismo
    identificador se probó varias veces, o desde cuántos orígenes, sin guardar lo que la persona escribió (a veces es una contraseña pegada
    en el campo equivocado). Se normaliza como se normalizan los correos y usuarios: sin espacios y en minúsculas."""
    key = hashlib.sha256(b"glucolume.audit.identifier:" + getSettings().JWT_SECRET.get_secret_value().encode()).digest()
    return hmac.new(key, identifier.strip().lower().encode(), hashlib.sha256).hexdigest()[:32]


def singleInstitutionOf(db: Session, idUsuario: uuid.UUID | None) -> uuid.UUID | None:
    """Institución de una cuenta que pertenece a UNA sola (vínculo activo). Con varias, ninguna: un intento de acceso a la cuenta no ocurre en
    una institución en particular y no debe aparecer en la auditoría de todas. Se usa solo para los accesos fallidos de personal institucional."""
    if idUsuario is None:
        return None
    ids = db.scalars(select(InstitutionUser.idInstitucion).where(
        InstitutionUser.idUsuarioInvitado == idUsuario, InstitutionUser.estadoRelacion == "ACTIVO").distinct().limit(2)).all()
    return ids[0] if len(ids) == 1 else None


def _requestContextRow(db: Session, motivo: str | None, identificadorHash: str | None) -> AuditContext | None:
    """Contexto de seguridad del evento: lo que la solicitud HTTP en curso aporta (correlación, IP, cliente) más el motivo normalizado. Nada
    si no hay nada que guardar o si la base instalada todavía no tiene la tabla AuditoriaContexto."""
    context = requestContext.current()
    if context is None and motivo is None and identificadorHash is None:
        return None
    if not schemaCompat.auditContextReady(db):
        return None
    return AuditContext(
        idCorrelacion=context.correlationId if context else None, ipOrigen=context.ip if context else None,
        agenteUsuario=context.agent if context else None, motivo=motivo[:40] if motivo else None, identificadorHash=identificadorHash,
    )


def registerEvent(
    db: Session,
    tipoEvento: TipoEvento,
    accion: str,
    exito: bool,
    idUsuario: uuid.UUID | None = None,
    tablaAfectada: str | None = None,
    idRegistro: uuid.UUID | None = None,
    observacion: str | None = None,
    datosPrevios: dict | None = None,
    datosNuevos: dict | None = None,
    tablaRelacionada: str | None = None,
    idRelacionado: uuid.UUID | None = None,
    idInstitucion: uuid.UUID | None = None,
    modulo: str | None = None,
    motivo: str | None = None,
    identificadorHash: str | None = None,
) -> None:
    """datosPrevios/datosNuevos se guardan como JSON (CK_Auditoria_*Json): solo identificadores y nombres de campos,
    nunca secretos ni datos personales o clínicos innecesarios. `idInstitucion` y `modulo` se resuelven solos.
    `motivo`: motivo técnico normalizado (código estable, p. ej. PASSWORD_INCORRECTA), nunca texto libre. La IP, el cliente y el identificador
    de correlación salen de la solicitud en curso (core/requestContext.py)."""
    if idInstitucion is None:
        idInstitucion = resolveInstitution(db, tablaAfectada, idRegistro)
    snapshot = None
    if idInstitucion is not None:
        snapshot = _identitySnapshot(
            db, _referencedRelations(tablaAfectada, idRegistro, tablaRelacionada, idRelacionado, datosPrevios, datosNuevos),
            idUsuario, idInstitucion)
    audit = Audit(
        idUsuario=idUsuario,
        tipoEvento=tipoEvento,
        modulo=modulo or moduleFor(tipoEvento, tablaAfectada),
        idInstitucion=idInstitucion,
        accion=accion[:50],
        resultado="EXITO" if exito else "FALLO",
        tablaAfectada=tablaAfectada,
        idRegistro=idRegistro,
        tablaRelacionada=tablaRelacionada,
        idRelacionado=idRelacionado,
        observacion=observacion[:1000] if observacion else None,
        detalle=json.dumps(snapshot, ensure_ascii=False) if snapshot else None,
        datosPrevios=json.dumps(sanitize(datosPrevios), ensure_ascii=False) if datosPrevios is not None else None,
        datosNuevos=json.dumps(sanitize(datosNuevos), ensure_ascii=False) if datosNuevos is not None else None,
    )
    if tipoEvento == "LOGIN" and idUsuario is not None and schemaCompat.auditAccountTypeReady(db):
        # Evidencia propia del evento: el tipo de la cuenta que se autenticó, tal como es ahora (la cuenta puede cambiar de tipo después).
        actor = db.get(User, idUsuario)
        if actor is not None:
            audit.tipoCuentaActor = actor.tipoCuenta  # en el mismo INSERT del evento, sin UPDATE posterior (GL-02)
    contexto = _requestContextRow(db, motivo, identificadorHash)
    if contexto is not None:
        audit.contexto = contexto
    db.add(audit)


def registerFailure(db: Session, tipoEvento: TipoEvento, accion: str, idUsuario: uuid.UUID | None = None,
                    tablaAfectada: str | None = None, idRegistro: uuid.UUID | None = None, observacion: str | None = None,
                    **kwargs) -> None:
    """Deja constancia de un intento rechazado o fallido aunque la operación principal no se aplique: descarta lo
    pendiente de la operación y confirma solo el evento (con su resultado FALLO)."""
    db.rollback()
    registerEvent(db, tipoEvento, accion, False, idUsuario, tablaAfectada, idRegistro, observacion, **kwargs)
    db.commit()
