# PatientResultEmail - Cargar, cambiar y quitar el correo del paciente para recibir sus resultados
#
# Solo el operador responsable vigente del paciente (el mismo que ve sus mediciones y puede enviarlas) administra el correo. Cargarlo exige
# que el operador declare la autorización del paciente y, además, que el PACIENTE confirme la dirección desde el enlace que recibe
# (services/resultEmailConfirmation.py, GL-08): recién entonces se guarda, por 12 meses. Cambiarlo sigue el mismo camino; quitarlo lo borra.
# La auditoría registra la acción y el vencimiento, nunca el correo. A la lectura solo se devuelve enmascarado.

import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import AuthError
from app.emails.formatting import maskEmail
from app.models.user import User
from app.schemas.measurementProfile import PatientRead, PatientResultEmailRequest
from app.services import institution as institutions
from app.services import institutionPatients as patients
from app.services import patientAccess, resultEmailStore
from app.services import resultEmailConfirmation as confirmation
from app.services.audit import registerEvent
from app.utils.timeZone import nowForDb

SCHEMA_MESSAGE = ("La base de datos instalada todavía no admite guardar el correo del paciente (faltan las columnas de correo de "
                  "resultados del esquema vigente). Consultá a la administración del sistema.")


def withResultEmail(db: Session, patient: PatientRead) -> PatientRead:
    """Agrega el correo enmascarado y su vencimiento, solo para quien administra las mediciones del paciente."""
    if not patient.medicionesAutorizadas:
        return patient
    found = resultEmailStore.stored(db, patient.idPerfilMedicion, nowForDb())
    if found is None:
        return patient
    return patient.model_copy(update={"correoResultados": maskEmail(found[0]), "correoResultadosVence": found[1]})


def _responsible(db: Session, actor: User, idInstitucion: uuid.UUID, idPerfilMedicion: uuid.UUID):
    membership = institutions.requireMembership(db, actor, idInstitucion, institutions.P_GESTIONAR_PACIENTES)
    row = patients._load(db, idInstitucion, idPerfilMedicion)
    profile = row[0]
    patients._requireModifiable(membership, profile)
    if not patientAccess.canViewMeasurements(membership, profile):
        raise AuthError("PERMISO_INSUFICIENTE", "Solo el operador responsable del paciente administra el correo de sus resultados.")
    return membership, row


def setResultEmail(db: Session, actor: User, idInstitucion: uuid.UUID, idPerfilMedicion: uuid.UUID,
                   data: PatientResultEmailRequest) -> PatientRead:
    """Pide al paciente que confirme el correo; se guarda (12 meses) cuando lo confirma. Hasta entonces sigue vigente el anterior."""
    if not resultEmailStore.ready(db):
        raise AuthError("ESQUEMA_DESACTUALIZADO", SCHEMA_MESSAGE)
    membership, row = _responsible(db, actor, idInstitucion, idPerfilMedicion)
    if not data.pacienteAutoriza:
        raise AuthError("AUTORIZACION_PACIENTE_REQUERIDA", "Confirmá que el paciente autorizó recibir sus resultados por correo.")
    if not confirmation.requestConfirmation(db, actor, idInstitucion, idPerfilMedicion, data.correo, keep=True):
        raise AuthError("ENVIO_CORREO_FALLIDO", "No pudimos enviar el correo de confirmación al paciente. Probá de nuevo en unos minutos.")
    read = withResultEmail(db, patients._read(membership, *patients._load(db, idInstitucion, idPerfilMedicion), nowForDb()))
    return read.model_copy(update={"correoResultadosPendiente": maskEmail(data.correo)})


def clearResultEmail(db: Session, actor: User, idInstitucion: uuid.UUID, idPerfilMedicion: uuid.UUID) -> PatientRead:
    """Quita el correo: el paciente deja de recibir resultados automáticos."""
    membership, row = _responsible(db, actor, idInstitucion, idPerfilMedicion)
    if resultEmailStore.stored(db, idPerfilMedicion, nowForDb()) is not None and resultEmailStore.clear(db, idPerfilMedicion):
        registerEvent(db, "CRUD", "QUITAR_CORREO_RESULTADOS_PACIENTE", True, actor.idUsuario, "PerfilMedicion", idPerfilMedicion)
        db.commit()
    return withResultEmail(db, patients._read(membership, *patients._load(db, idInstitucion, idPerfilMedicion), nowForDb()))
