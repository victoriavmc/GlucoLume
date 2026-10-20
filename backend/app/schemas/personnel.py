# Personnel - Contratos del módulo Personal de una institución (solo lectura)
#
# Una persona aparece UNA sola vez (por su cuenta), con su vínculo vigente o, si ya no lo tiene, el último; sus períodos anteriores
# (otros roles o bajas previas) van en `periodos` y en el historial. Todo sale de InstitucionUsuario y de Auditoria: no hay
# fechas ni acontecimientos inventados. El correo lo ve solo quien consulta el equipo (propietario y moderador).

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_serializer

from app.schemas.institutionUser import RolInstitucion
from app.utils.timeZone import withArgentinaZone


class _Dated(BaseModel):
    @field_serializer("*", mode="wrap", when_used="json")
    def _zone(self, value, handler):
        """Los datetime persistidos son hora de Argentina sin zona: se informan con su zona (UTC-03:00)."""
        if isinstance(value, datetime):
            return withArgentinaZone(value).isoformat()
        return handler(value)


class PersonnelItem(_Dated):
    idInstitucionUsuario: uuid.UUID  # vínculo vigente o, si no hay, el último de la persona
    nombre: str | None
    apellido: str | None
    nombreCompleto: str
    correoElectronico: str | None = None
    rolInstitucion: RolInstitucion  # rol actual (el del vínculo mostrado)
    rolesAnteriores: list[RolInstitucion] = []  # roles de períodos anteriores distintos del actual
    estadoRelacion: str
    cuentaPendiente: bool = False
    invitacionVencida: bool = False
    legajoInstitucional: str | None = None
    matriculaProfesional: str | None = None
    funcionProfesional: str | None = None
    fechaInvitacion: datetime | None = None
    fechaIncorporacion: datetime | None = None
    fechaBaja: datetime | None = None
    periodos: int = 1
    datosEliminados: bool = False  # sus datos históricos fueron eliminados: sigue el vínculo, pero ya no identifica a la persona


class PersonnelSummary(BaseModel):
    """Indicadores de TODO el personal de la institución (no dependen de los filtros). Una persona cuenta una vez."""

    totalActivos: int
    moderadoresActivos: int
    operadoresActivos: int
    propietariosActivos: int
    bajas: int  # personas cuyo vínculo más reciente es una baja (no se cuentan las reincorporadas)
    invitacionesPendientes: int  # vigentes: no incluye las vencidas ni cuenta como personal activo


class PersonnelPage(BaseModel):
    items: list[PersonnelItem]
    total: int
    pagina: int
    tamanioPagina: int
    resumen: PersonnelSummary


class PersonnelPeriod(_Dated):
    idInstitucionUsuario: uuid.UUID
    rolInstitucion: RolInstitucion
    estadoRelacion: str
    origenVinculo: str
    invitadoPor: str | None = None
    fechaInvitacion: datetime | None = None
    fechaIncorporacion: datetime | None = None
    fechaBaja: datetime | None = None
    vigente: bool = False


class PersonnelEvent(_Dated):
    """Un acontecimiento administrativo de la persona. `origen`: AUDITORIA (evento registrado, con responsable) o REGISTRO
    (surge de las fechas del vínculo cuando no existe un evento de auditoría de ese hecho)."""

    fechaHora: datetime
    tipo: str
    titulo: str
    descripcion: str | None = None
    resultado: Literal["EXITO", "FALLO"] = "EXITO"
    realizadoPor: str | None = None
    origen: Literal["AUDITORIA", "REGISTRO"] = "AUDITORIA"
    rolInstitucion: RolInstitucion | None = None


class PersonnelActions(BaseModel):
    """Qué puede hacer quien consulta con esta persona (FastAPI lo vuelve a validar en cada operación)."""

    puedeEditar: bool = False
    puedeDesvincular: bool = False
    puedeReenviar: bool = False
    puedeVerDashboard: bool = False  # dashboard operativo del operador (propietario y moderador)
    puedeEliminarDatos: bool = False  # suprimir los datos personales históricos de una persona ya desvinculada


class PersonnelProfile(PersonnelItem):
    nombreInstitucion: str
    nombreProfesionalHistorico: str | None = None
    apellidoProfesionalHistorico: str | None = None
    origenVinculo: str
    invitadoPor: str | None = None
    fechaVencimientoInvitacion: datetime | None = None
    fechaCuentaCreada: datetime | None = None  # alta de la cuenta de GlucoLume de la persona (no es la incorporación)
    fechaUltimaModificacion: datetime | None = None  # última modificación administrativa de sus datos en la institución
    periodosAnteriores: list[PersonnelPeriod] = []
    acciones: PersonnelActions = PersonnelActions()
    historial: list[PersonnelEvent] = []


class SentInvitation(_Dated):
    """Invitación emitida por la institución. Solo la ACEPTADA es (y enlaza a) personal; el resto nunca se incorporó."""
    idInstitucionUsuario: uuid.UUID
    nombreCompleto: str
    correoElectronico: str | None = None
    rolInstitucion: RolInstitucion
    estado: Literal["PENDIENTE", "ACEPTADA", "RECHAZADA", "CANCELADA", "VENCIDA"]
    cuentaPendiente: bool = False
    invitadoPor: str | None = None
    fechaInvitacion: datetime
    fechaVencimiento: datetime | None = None
    fechaRespuesta: datetime | None = None  # aceptación, rechazo o cancelación
    puedeReenviar: bool = False
    puedeCancelar: bool = False
    idPersonal: uuid.UUID | None = None  # perfil de personal de una invitación aceptada


class SentInvitationsPage(_Dated):
    items: list[SentInvitation]
    total: int
    pagina: int
    tamanioPagina: int
    resumen: dict[str, int]  # cantidad por estado, sin depender del filtro
