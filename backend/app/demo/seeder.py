# Demo - Carga y verificación de los datos de demostración (dry-run y aplicación)
#
# Flujo:
#   1. buildPlan() LEE la base (nunca escribe). Decide, registro por registro, si se CREA o YA EXISTE y detecta colisiones
#      (correo, CUIT, código de dispositivo, documento de paciente) con datos que no son demo. Con colisiones, no se aplica nada.
#   2. apply() escribe el plan en UNA transacción por etapas (usuarios → instituciones/grupo/dispositivos/credenciales → vínculos
#      → perfiles → mediciones). Cualquier error deshace todo. Las cuentas se crean con el mecanismo real de la aplicación: hash de
#      contraseña de security.py, credencial local, consentimientos del servicio de consentimientos y estado ACTIVO (el correo queda
#      verificado por este proceso autorizado). No se configura MFA.
#   3. Ninguna función de este módulo envía correo: no usa services/email ni services/notifications.
#
# Lo que verifican las pruebas (tests/test_demo_seed.py): idempotencia, aislamiento, cantidades, autenticación real, permisos por
# configuración de privacidad, aislamiento de pacientes entre operadores e instituciones, y que el administrador de plataforma
# existente no se modifica.

from __future__ import annotations

import os
import secrets
import string
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import getSettings
from app.demo import catalog as C
from app.models.consent import TipoConsentimiento
from app.models.device import Device
from app.models.group import Group
from app.models.groupUser import GroupUser
from app.models.institution import Institution
from app.models.institutionUser import InstitutionUser
from app.models.localCredential import LocalCredential
from app.models.measurement import Measurement
from app.models.measurementProfile import MeasurementProfile
from app.models.mfaFactor import MfaFactor
from app.models.user import User
from app.schemas.institution import normalizeLegalId
from app.services import consent as consentService
from app.services import matrix as matrixService
from app.services import measurementRetention
from app.services.measurementProfile import calculateAge
from app.utils.timeZone import nowForDb

ESTADO_ACTIVO = "ACTIVO"
PASSWORD_ALPHABET = string.ascii_letters + string.digits + "!#%&*+-=?@"
PASSWORD_LENGTH = 20
ETAPAS = 5  # 1 usuarios · 2 instituciones, grupo, dispositivos y credenciales · 3 vínculos · 4 perfiles · 5 mediciones


class SeedError(Exception):
    """Carga rechazada: nada se escribió. El mensaje es apto para mostrar al operador (nunca contiene contraseñas)."""


@dataclass
class PlanItem:
    entidad: str
    clave: str
    accion: str  # CREAR | YA_EXISTE | REGENERAR_CONTRASENA
    detalle: str = ""


@dataclass
class Plan:
    anchor: datetime
    items: list[PlanItem] = field(default_factory=list)
    bloqueos: list[str] = field(default_factory=list)
    advertencias: list[str] = field(default_factory=list)
    etapas: list[list[object]] = field(default_factory=lambda: [[] for _ in range(ETAPAS)])
    pacientesAFijarInstitucion: list[tuple[uuid.UUID, uuid.UUID]] = field(default_factory=list)
    cuentasACrear: list[str] = field(default_factory=list)
    cuentasARegenerar: list[str] = field(default_factory=list)

    @property
    def bloqueado(self) -> bool:
        return bool(self.bloqueos)

    def conteo(self) -> dict[str, dict[str, int]]:
        out: dict[str, dict[str, int]] = {}
        for item in self.items:
            bucket = out.setdefault(item.entidad, {})
            bucket[item.accion] = bucket.get(item.accion, 0) + 1
        return out


@dataclass
class CheckResult:
    cuenta: str
    correo: str
    ok: bool
    detalle: str


# --- Autorización, entorno y rutas -----------------------------------------------------------------------------------


def assertAllowed(*, autorizarProduccion: bool = False, confirmarBase: str | None = None) -> None:
    """En API_ENV=production la carga solo corre con --autorizar-produccion Y --confirmar-base igual al nombre de la base."""
    settings = getSettings()
    if settings.API_ENV != "production":
        return
    if not autorizarProduccion or confirmarBase is None or confirmarBase != settings.DB_NAME:
        raise SeedError("API_ENV=production: la carga demo está bloqueada. Solo se ejecuta con --autorizar-produccion y "
                        "--confirmar-base <nombre exacto de la base>, decisión explícita del responsable del sistema.")


def defaultAnchor() -> datetime:
    """Medianoche (hora de Argentina, naive) del día de ejecución: el mismo día produce los mismos datos."""
    return datetime.combine(nowForDb().date(), time(0, 0))


def repoRoots() -> list[Path]:
    """Carpetas que nunca pueden contener el archivo de credenciales: el paquete backend (también dentro de la imagen Docker, donde
    no hay .git) y, si existe, la raíz del repositorio git que lo contiene."""
    backend = Path(__file__).resolve().parents[2]
    roots = [backend]
    for candidate in (backend, *backend.parents):
        if (candidate / ".git").exists():
            roots.append(candidate)
            break
    return roots


def assertOutsideRepo(path: str | Path) -> None:
    """El archivo con contraseñas nunca se escribe dentro del repositorio (ni en su contexto de build de Docker)."""
    resolved = Path(path).expanduser().resolve()
    for root in repoRoots():
        if resolved == root or root in resolved.parents:
            raise SeedError("El archivo de credenciales no puede estar dentro del repositorio: elegí una carpeta privada fuera de él.")


def defaultCredentialsPath() -> Path:
    override = os.environ.get("GLUCOLUME_DEMO_CREDENCIALES")
    if override:
        return Path(override).expanduser()
    return Path.home() / "GlucoLumeDemo" / "credenciales-demo.txt"


# --- Contraseñas ------------------------------------------------------------------------------------------------------


def generatePassword(account: C.Account) -> str:
    """Contraseña temporal de demostración: cumple la política real (security.passwordPolicyErrors), no es común y no contiene el
    correo ni el nombre de la cuenta. Solo se escribe en el archivo privado de credenciales; nunca en logs ni reportes."""
    identifiers = (account.key, account.correo.split("@", 1)[0], account.nombre, account.apellido)
    while True:
        candidate = "".join(secrets.choice(PASSWORD_ALPHABET) for _ in range(PASSWORD_LENGTH))
        if security.passwordPolicyErrors(candidate):
            continue
        if security.isCommonPassword(candidate) or security.passwordContainsPersonalData(candidate, *identifiers):
            continue
        return candidate


# --- Plan (solo lectura) ---------------------------------------------------------------------------------------------


def _exists(db: Session, model, key) -> bool:
    return db.get(model, key) is not None


def _existingIds(db: Session, column, ids: list[uuid.UUID]) -> set[uuid.UUID]:
    found: set[uuid.UUID] = set()
    for start in range(0, len(ids), 500):
        found.update(db.scalars(select(column).where(column.in_(ids[start:start + 500]))).all())
    return found


def _collisions(db: Session, plan: Plan) -> None:
    for account in C.ACCOUNTS:
        other = db.scalar(select(User.idUsuario).where(User.correoElectronico == account.correo))
        if other is not None and other != account.id:
            plan.bloqueos.append(f"Ya existe una cuenta con el correo {account.correo} que no es demo.")
    for institution in C.INSTITUTIONS:
        digits = normalizeLegalId("CUIT", institution.cuit)
        other = db.scalar(select(Institution.idInstitucion).where(Institution.identificadorLegal == digits))
        if other is not None and other != institution.id:
            plan.bloqueos.append(f"Ya existe una institución con el CUIT sintético {digits} que no es demo.")
    for device in C.DEVICES:
        other = db.scalar(select(Device.idDispositivo).where(Device.codigoDispositivo == device.codigo))
        if other is not None and other != device.id:
            plan.bloqueos.append(f"Ya existe un dispositivo con el código {device.codigo} que no es demo.")
    for patient in C.PATIENTS:
        if patient.dni is None:
            continue
        other = db.scalar(select(MeasurementProfile.idPerfilMedicion).where(
            MeasurementProfile.dni == patient.dni, MeasurementProfile.tipoPerfil == C.PERFIL_INSTITUCIONAL))
        if other is not None and other != patient.id:
            plan.bloqueos.append(f"Ya existe un paciente con el documento sintético {patient.dni} que no es demo.")


def buildPlan(db: Session, *, anchor: datetime | None = None, passwords: dict[str, str] | None = None,
              regenerarContrasenas: bool = False) -> Plan:
    """Calcula qué se crearía. Solo lee la base. Con `passwords` (modo aplicar) arma también los registros a insertar: cada cuenta
    que se crea o se regenera debe tener su contraseña en ese diccionario."""
    anchor = anchor or defaultAnchor()
    plan = Plan(anchor=anchor)
    _collisions(db, plan)
    if plan.bloqueado:
        return plan
    building = passwords is not None
    now = nowForDb()
    accounts = {account.key: account for account in C.ACCOUNTS}

    # Etapa 1 — usuarios; etapa 2 — credenciales.
    for account in C.ACCOUNTS:
        if _exists(db, User, account.id):
            plan.items.append(PlanItem("Usuario", account.key, "YA_EXISTE"))
            credential = db.get(LocalCredential, C.demoId("credencial", account.key))
            if regenerarContrasenas and credential is not None:
                plan.cuentasARegenerar.append(account.key)
                plan.items.append(PlanItem("Credencial", account.key, "REGENERAR_CONTRASENA"))
                if building:
                    credential.passwordHash = security.hashPassword(passwords[account.key])
                    credential.fechaUltimoCambioPassword = now
                    credential.fechaActualizacion = now
                    credential.intentosFallidosConsecutivos = 0
            else:
                plan.items.append(PlanItem("Credencial", account.key, "YA_EXISTE"))
            continue
        plan.cuentasACrear.append(account.key)
        plan.items.append(PlanItem("Usuario", account.key, "CREAR", account.rol))
        plan.items.append(PlanItem("Credencial", account.key, "CREAR"))
        if building:
            plan.etapas[0].append(User(
                idUsuario=account.id, nombre=account.nombre, apellido=account.apellido, correoElectronico=account.correo,
                usuario=None, tipoCuenta=account.tipoCuenta, estado=ESTADO_ACTIVO, fechaCreacion=now, fechaActualizacion=now,
                fechaEliminacion=None, fechaNacimiento=account.fechaNacimiento, sexo=account.sexo,
                notificarNuevoInicioSesion=False, fechaInicioGracia=None, fechaVencimientoGracia=None,
            ))
            plan.etapas[1].append(LocalCredential(
                idCredencialLocal=C.demoId("credencial", account.key), idUsuario=account.id,
                passwordHash=security.hashPassword(passwords[account.key]), requiereCambioPassword=False,
                intentosFallidosConsecutivos=0, fechaUltimoCambioPassword=now, fechaCreacion=now, fechaActualizacion=now,
            ))

    # Etapa 1 — instituciones (los dispositivos y vínculos dependen de ellas).
    for institution in C.INSTITUTIONS:
        if _exists(db, Institution, institution.id):
            plan.items.append(PlanItem("Institucion", institution.key, "YA_EXISTE"))
            continue
        plan.items.append(PlanItem("Institucion", institution.key, "CREAR", f"{institution.nombre} ({institution.tipoInstitucion})"))
        if building:
            plan.etapas[0].append(Institution(
                idInstitucion=institution.id, tipoIdentificadorLegal="CUIT",
                identificadorLegal=normalizeLegalId("CUIT", institution.cuit), nombre=institution.nombre,
                tipoInstitucion=institution.tipoInstitucion, descripcion=C.NOTA_INSTITUCION, estado="ACTIVA",
                fechaCreacion=now, fechaActualizacion=now, cantidadReaperturas=0,
            ))

    # Etapa 2 — grupo familiar y dispositivos.
    groupId = C.demoId("grupo", C.GROUP_KEY)
    if _exists(db, Group, groupId):
        plan.items.append(PlanItem("Grupo", C.GROUP_KEY, "YA_EXISTE"))
    else:
        plan.items.append(PlanItem("Grupo", C.GROUP_KEY, "CREAR", C.GROUP_NAME))
        if building:
            plan.etapas[1].append(Group(idGrupo=groupId, nombre=C.GROUP_NAME, descripcion=C.NOTA_GRUPO, estado="ACTIVO",
                                        fechaCreacion=anchor - timedelta(days=70), fechaActualizacion=now))
    for device in C.DEVICES:
        if _exists(db, Device, device.id):
            plan.items.append(PlanItem("Dispositivo", device.key, "YA_EXISTE"))
            continue
        plan.items.append(PlanItem("Dispositivo", device.key, "CREAR", device.codigo))
        if building:
            plan.etapas[1].append(Device(
                idDispositivo=device.id, codigoDispositivo=device.codigo, nombre=f"Dispositivo DEMO {device.key} (sintético)",
                modelo="GlucoLume DEMO", modeloSensor=C.SENSOR_DEMO, versionFirmware=C.VERSION_FIRMWARE_DEMO, estado="OPERATIVO",
                idInstitucionAsignada=C.INSTITUTIONS_BY_KEY[device.institution].id if device.institution else None,
                idInstitucionUsuarioResponsable=None, fechaRegistro=anchor - timedelta(days=60),
            ))

    # Etapa 3 — vínculos institucionales y del grupo.
    for link in C.STAFF:
        if _exists(db, InstitutionUser, link.id):
            plan.items.append(PlanItem("VinculoInstitucional", f"{link.institution}/{link.account}", "YA_EXISTE"))
            continue
        plan.items.append(PlanItem("VinculoInstitucional", f"{link.institution}/{link.account}", "CREAR", link.rol))
        if building:
            owner = link.rol == C.ROL_PROPIETARIO
            plan.etapas[2].append(InstitutionUser(
                idInstitucionUsuario=link.id, idInstitucion=C.INSTITUTIONS_BY_KEY[link.institution].id,
                idUsuarioInvitado=accounts[link.account].id, rolInstitucion=link.rol, matriculaProfesional=link.matricula,
                legajoInstitucional=link.legajo, funcionProfesional=link.funcionProfesional, estadoRelacion="ACTIVO",
                origenVinculo="CREACION_INSTITUCION" if owner else "INVITACION",
                idUsuarioInvitador=accounts[link.invitadoPor].id if link.invitadoPor else None,
                fechaInvitacion=anchor - timedelta(days=30), fechaIncorporacion=anchor - timedelta(days=29),
            ))
    memberships = [("grupo-admin", "PROPIETARIO", (False, False, False, False))]
    memberships += [(key, "MIEMBRO", flags) for key, flags, _ in C.GROUP_MEMBERS]
    for key, role, flags in memberships:
        linkId = C.demoId("vinculo-grupo", key)
        if _exists(db, GroupUser, linkId):
            plan.items.append(PlanItem("VinculoGrupo", key, "YA_EXISTE"))
            continue
        plan.items.append(PlanItem("VinculoGrupo", key, "CREAR", role))
        if building:
            perfil, ultima, historial, avisos = flags
            plan.etapas[2].append(GroupUser(
                idGrupoUsuario=linkId, idGrupo=groupId, idUsuario=accounts[key].id, rolGrupo=role, estadoRelacion="ACTIVO",
                nivelComparticion="NINGUNA", fechaInvitacion=anchor - timedelta(days=60),
                fechaIncorporacion=anchor - timedelta(days=59), visualiza=True, compartePerfil=perfil,
                comparteUltimaMedicion=ultima, comparteHistorial=historial, notificaMedicion=avisos,
            ))

    # Etapas 4 y 5 — perfiles de medición y mediciones.
    _profilesAndMeasurements(db, plan, building, now)
    return plan


def _profilesAndMeasurements(db: Session, plan: Plan, building: bool, now: datetime) -> None:
    accounts = {account.key: account for account in C.ACCOUNTS}
    individuals = C.individualMeasurements()
    patients = C.patientMeasurements()
    today = plan.anchor.date()
    # Como la aplicación al iniciar una medición: la matriz de la institución si tiene una activa; si no, la global. Solo se referencia
    # (las mediciones demo no reciben estimación del servidor, así que la matriz solo clasifica la glucosa informada).
    globalMatrix = matrixService.resolveMatrix(db, None, today)
    if globalMatrix is None:
        plan.advertencias.append("No hay una matriz global activa y vigente: la clasificación de glucosa de la demo mostrará SIN_MATRIZ.")
    matrixByInstitution = {inst: matrixService.resolveMatrix(db, C.INSTITUTIONS_BY_KEY[inst].id, today) for inst in C.MAIN_INSTITUTIONS}
    existingMeasurements = _existingIds(db, Measurement.idMedicion,
                                        [spec.id for _, specs in individuals for spec in specs]
                                        + [spec.id for _, specs in patients for spec in specs])

    for accountKey, specs in individuals:
        account = accounts[accountKey]
        profileId = C.demoId("perfil", accountKey)
        _profileItem(db, plan, building, accountKey, profileId, lambda pid, a=account, s=specs: MeasurementProfile(
            idPerfilMedicion=pid, tipoPerfil=C.PERFIL_CONSUMIDOR, idUsuario=a.id, nombre=a.nombre, apellido=a.apellido,
            fechaNacimiento=a.fechaNacimiento, sexoModelo=a.sexo, fechaCreacion=now - timedelta(days=60),
            fechaUltimaMedicion=_lastCompletedEnd(s, plan.anchor)))
        _measurements(plan, building, specs, profileId, accountKey, account.fechaNacimiento, account.sexo,
                      existingMeasurements, C.deviceKeyForIndividual(accountKey),
                      globalMatrix.idMatriz if globalMatrix else None)

    for patient, specs in patients:
        profileId = patient.id
        created = _profileItem(db, plan, building, patient.key, profileId, lambda pid, p=patient, s=specs: MeasurementProfile(
            idPerfilMedicion=pid, tipoPerfil=C.PERFIL_INSTITUCIONAL,
            idInstitucionUsuarioResponsable=C.demoId("vinculo-institucional", patient.relationKey),
            identificadorPseudonimo=patient.pseudonimo, nombre=patient.nombre, apellido=patient.apellido, dni=patient.dni,
            fechaNacimiento=patient.fechaNacimiento, sexoModelo=patient.sexoModelo, fechaCreacion=now - timedelta(days=50),
            fechaUltimaMedicion=_lastCompletedEnd(s, plan.anchor)))
        if created and building:
            # Índice de documento único por institución: se fija después de insertar el perfil (ver apply).
            plan.pacientesAFijarInstitucion.append((profileId, C.INSTITUTIONS_BY_KEY[patient.institution].id))
        matrix = matrixByInstitution[patient.institution] or globalMatrix
        _measurements(plan, building, specs, profileId, patient.key, patient.fechaNacimiento, patient.sexoModelo,
                      existingMeasurements, C.patientDeviceKey(patient), matrix.idMatriz if matrix else None)


def _profileItem(db: Session, plan: Plan, building: bool, key: str, profileId: uuid.UUID, factory) -> bool:
    """Devuelve True si el perfil se crea en esta ejecución."""
    if _exists(db, MeasurementProfile, profileId):
        plan.items.append(PlanItem("PerfilMedicion", key, "YA_EXISTE"))
        return False
    plan.items.append(PlanItem("PerfilMedicion", key, "CREAR"))
    if building:
        plan.etapas[3].append(factory(profileId))
    return True


def _lastCompletedEnd(specs, anchor: datetime) -> datetime | None:
    """Como en la aplicación: la última medición completada fija fechaUltimaMedicion del perfil."""
    completed = [spec.start(anchor) for spec in specs if spec.estado == C.ESTADO_COMPLETADA]
    return max(completed) + timedelta(minutes=2) if completed else None


def _measurements(plan: Plan, building: bool, specs, profileId, key, birth, sex, existing, deviceKey: str,
                  matrixId: uuid.UUID | None) -> None:
    pending = [spec for spec in specs if spec.id not in existing]
    plan.items.append(PlanItem("Medicion", key, "CREAR" if pending else "YA_EXISTE", f"{len(pending)} de {len(specs)}"))
    if building:
        for spec in pending:
            plan.etapas[4].append(_measurementRecord(spec, profileId, birth, sex, plan.anchor, deviceKey, matrixId))


def _measurementRecord(spec: C.MeasurementSpec, profileId, birth: date | None, sex: str | None, anchor: datetime,
                       deviceKey: str, matrixId: uuid.UUID | None) -> Measurement:
    start = spec.start(anchor)
    completed = spec.estado == C.ESTADO_COMPLETADA
    glucose = spec.glucosa  # solo en mediciones de glucosa completadas (DEMO); la oximetría no informa glucosa
    lastMeal = start - timedelta(minutes=spec.minutosDesdeComida) if spec.minutosDesdeComida is not None else None
    deviceId = next(device.id for device in C.DEVICES if device.key == deviceKey)
    return Measurement(
        idMedicion=spec.id, idPerfilMedicion=profileId, idDispositivo=deviceId,
        idMatriz=matrixId if glucose is not None else None,
        modoMedicion=spec.modo, estadoMedicion=spec.estado, fechaHoraInicio=start, fechaHoraFin=start + timedelta(minutes=2),
        fechaHoraUltimaComida=lastMeal, condicionComida=spec.condicion,
        edadAlMomento=calculateAge(birth, start.date()) if birth else None, sexoModelo=sex,
        versionFirmwareAlMomento=C.VERSION_FIRMWARE_DEMO if completed else None, modeloSensorAlMomento=C.SENSOR_DEMO,
        versionAlgoritmo=C.ALGORITMO_DEMO if completed else None, calidadSenal=spec.calidadSenal, spo2=spec.spo2,
        frecuenciaCardiaca=spec.frecuenciaCardiaca, glucosaEstimada=None, observacion=C.NOTA_MEDICION,
        origenGlucosa=C.ORIGEN_DEMO if glucose is not None else None, glucosaDispositivo=glucose,
        unidadGlucosa="mg/dL" if glucose is not None else None, indiceOptico=spec.indiceOptico,
        lecturasEstabilizadas=spec.lecturas,
    )


# --- Aplicación ------------------------------------------------------------------------------------------------------


def apply(db: Session, plan: Plan) -> dict[str, int]:
    """Escribe el plan en una sola transacción por etapas. Devuelve lo creado por entidad. Ante cualquier error, deshace todo."""
    if plan.bloqueado:
        raise SeedError("La carga está bloqueada por colisiones con datos que no son demo:\n- " + "\n- ".join(plan.bloqueos))
    try:
        for index, records in enumerate(plan.etapas):
            if index == 1:
                _consents(db, plan)  # usuarios ya insertados: consentimientos del servicio real
            if records:
                db.add_all(records)
                db.flush()
            if index == 3:  # perfiles insertados: fijar la institución de cada paciente nuevo
                for profileId, institutionId in plan.pacientesAFijarInstitucion:
                    measurementRetention.stampInstitution(db, profileId, institutionId)
                db.flush()
        db.commit()
    except Exception:
        db.rollback()
        raise
    created: dict[str, int] = {}
    for item in plan.items:
        if item.accion == "CREAR":
            created[item.entidad] = created.get(item.entidad, 0) + 1
    return created


def _consents(db: Session, plan: Plan) -> None:
    for key in plan.cuentasACrear:
        account = C.ACCOUNTS_BY_KEY[key]
        if account.individual:
            user = db.get(User, account.id)
            consentService.record(db, user, TipoConsentimiento.POLITICA_PRIVACIDAD, True)
            consentService.record(db, user, TipoConsentimiento.DATOS_EXPERIMENTALES, True)


# --- Verificación sin sesión -----------------------------------------------------------------------------------------


def verifyAccounts(db: Session, passwords: dict[str, str]) -> list[CheckResult]:
    """Por cuenta: existe, estado ACTIVO, tipo correcto, credencial que verifica con la contraseña del archivo privado, sin MFA
    habilitado y con su perfil o vínculo. No abre sesión ni escribe auditoría."""
    results: list[CheckResult] = []
    for account in C.ACCOUNTS:
        user = db.get(User, account.id)
        if user is None:
            results.append(CheckResult(account.key, account.correo, False, "la cuenta no existe"))
            continue
        problems: list[str] = []
        if user.estado != ESTADO_ACTIVO:
            problems.append(f"estado {user.estado}")
        if user.tipoCuenta != account.tipoCuenta:
            problems.append(f"tipoCuenta {user.tipoCuenta}")
        credential = db.get(LocalCredential, C.demoId("credencial", account.key))
        if credential is None:
            problems.append("sin credencial local")
        elif account.key not in passwords:
            problems.append("contraseña no disponible en el archivo privado (usar --regenerar-contrasenas)")
        elif not security.verifyPassword(passwords[account.key], credential.passwordHash)[0]:
            problems.append("la contraseña del archivo privado no coincide con la base")
        factor = db.scalar(select(MfaFactor).where(MfaFactor.idUsuario == user.idUsuario, MfaFactor.habilitado == True))
        if factor is not None:
            problems.append("MFA habilitado (la demo no lo configura)")
        if account.individual:
            if db.get(MeasurementProfile, C.demoId("perfil", account.key)) is None:
                problems.append("sin perfil de medición")
        else:
            link = next(s for s in C.STAFF if s.account == account.key)
            if db.get(InstitutionUser, link.id) is None:
                problems.append("sin vínculo institucional")
        results.append(CheckResult(account.key, account.correo, not problems, "OK" if not problems else "; ".join(problems)))
    return results


def countDemoRows(db: Session) -> dict[str, int]:
    """Cuántos registros demo hay (solo lectura), por entidad: la fuente de la verificación posterior a la carga."""
    ids = {
        "Usuario": (User.idUsuario, [a.id for a in C.ACCOUNTS]),
        "Institucion": (Institution.idInstitucion, [i.id for i in C.INSTITUTIONS]),
        "Grupo": (Group.idGrupo, [C.demoId("grupo", C.GROUP_KEY)]),
        "Dispositivo": (Device.idDispositivo, [d.id for d in C.DEVICES]),
        "PerfilMedicion": (MeasurementProfile.idPerfilMedicion,
                           [C.demoId("perfil", a.key) for a in C.ACCOUNTS if a.individual] + [p.id for p in C.PATIENTS]),
        "Medicion": (Measurement.idMedicion, [s.id for _, specs in C.individualMeasurements() for s in specs]
                     + [s.id for _, specs in C.patientMeasurements() for s in specs]),
    }
    return {entidad: len(_existingIds(db, column, values)) for entidad, (column, values) in ids.items()}


__all__ = ["Plan", "PlanItem", "SeedError", "CheckResult", "assertAllowed", "defaultAnchor", "defaultCredentialsPath",
           "assertOutsideRepo", "generatePassword", "buildPlan", "apply", "verifyAccounts", "countDemoRows"]
