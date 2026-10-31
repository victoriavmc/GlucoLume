# Pruebas de datos institucionales completos, pacientes institucionales, asignación de operadores, retención de
# 12 meses tras el cierre y reautenticación de cuentas solo Google.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_institution_patients.py -v
#
# Usan el esquema SQLite temporal de test_account_deletion.py y el escenario `team` de test_institutions.py
# (propietaria, moderador y operadora activos, incorporados por invitación aceptada).

import uuid
from datetime import date, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select, update

from app.core.exceptions import AuthError
from app.models.audit import Audit
from app.models.device import Device
from app.models.institution import Institution
from app.models.institutionUser import InstitutionUser
from app.models.user import User
from app.models.measurement import Measurement
from app.models.measurementProfile import MeasurementProfile
from app.models.profileTransfer import ProfileTransfer
from app.schemas.institution import InstitutionCreateRequest, InstitutionDeletionRequest, InstitutionUpdateRequest
from app.schemas.measurementProfile import PatientCreateRequest, PatientUpdateRequest
from app.services import institution as institutions
from app.services import institutionPatients as patients
from app.services import measurement as measurementService
from app.services.institutionalRetention import purgeExpiredPatientData
from app.utils.timeZone import nowForDb
from tests.legacy_offboarding import legacyRevoke
from tests.test_account_deletion import (  # noqa: F401 - fixtures
    PASSWORD,
    audits,
    db,
    enableMfa,
    engine,
    mails,
    makeUser,
    reload,
    totpCode,
)
from tests.test_institutions import (  # noqa: F401 - fixtures
    cuit,
    expectError,
    freshLookupLimiter,
    institutional,
    newInstitution,
    relationOf,
    team,
)


def patientData(**overrides) -> PatientCreateRequest:
    data = {"nombre": "juan", "apellido": "pérez", "dni": "20.111.222", "fechaNacimiento": "1980-01-02",
            "sexoModelo": "masculino"}
    return PatientCreateRequest(**{**data, **overrides})


def addOperator(db, team, email="segundo@example.com", usuario="segundo") -> InstitutionUser:
    user = institutional(db, email, usuario)
    invitation = institutions.invite(db, team.moderator, team.id, "OPERADOR", email)
    institutions.respondInvitation(db, user, invitation.idInstitucionUsuario, accept=True)
    return relationOf(db, team, user)


def otherInstitution(db):
    """Otra institución con su propia operadora activa."""
    owner = institutional(db, "otra-duenia@example.com", "otraduenia")
    moderator = institutional(db, "otro-moderador@example.com", "otromoderador")
    operator = institutional(db, "otra-operadora@example.com", "otraoperadora")
    institution = newInstitution(db, owner, "87654321", "Laboratorio Norte")
    invitation = institutions.invite(db, owner, institution.idInstitucion, "MODERADOR", moderator.correoElectronico)
    institutions.respondInvitation(db, moderator, invitation.idInstitucionUsuario, accept=True)
    invitation = institutions.invite(db, moderator, institution.idInstitucion, "OPERADOR", operator.correoElectronico)
    institutions.respondInvitation(db, operator, invitation.idInstitucionUsuario, accept=True)
    relation = db.scalar(select(InstitutionUser).where(InstitutionUser.idUsuarioInvitado == operator.idUsuario))
    return institution, operator, relation


# --- Datos institucionales completos --------------------------------------------------------


def test_detalle_completo_con_los_datos_reales_del_modelo(db, mails):
    owner = institutional(db, "duenia@example.com", "duenia")
    data = InstitutionCreateRequest(nombre="Centro Médico San José", tipoInstitucion="CLINICA",
                                    identificadorLegal="30-71234567-1", descripcion="Sede central")
    created = institutions.createInstitution(db, owner, data)
    detail = institutions.getDetail(db, owner, created.idInstitucion)
    assert (detail.nombre, detail.tipoInstitucion, detail.descripcion) == ("Centro Médico San José", "CLINICA", "Sede central")
    assert (detail.tipoIdentificadorLegal, detail.identificadorLegal, detail.estado) == ("CUIT", "30712345671", "ACTIVA")
    assert detail.propietario.model_dump() == {"nombre": "Victoria", "apellido": "Cortés"}
    assert detail.fechaCreacion is not None and detail.fechaActualizacion is not None
    assert (detail.cantidadModeradores, detail.cantidadOperadores, detail.cantidadPacientes) == (0, 0, 0)


def test_no_acepta_campos_que_el_modelo_no_almacena():
    with pytest.raises(ValidationError):
        InstitutionCreateRequest(nombre="Hospital X", tipoInstitucion="HOSPITAL", identificadorLegal=cuit(),
                                 correoContacto="x@example.com")
    with pytest.raises(ValidationError):
        InstitutionUpdateRequest(telefonoContacto="011 4567-8900")


def test_modificar_y_volver_a_consultar(db, mails, team):
    institutions.updateInstitution(db, team.owner, team.id, InstitutionUpdateRequest(
        nombre="Hospital Central", tipoInstitucion="CLINICA", descripcion="Sede"))
    again = institutions.getDetail(db, team.moderator, team.id)
    assert (again.nombre, again.tipoInstitucion, again.descripcion) == ("Hospital Central", "CLINICA", "Sede")
    assert reload(db, Institution, team.id).nombre == "Hospital Central"


# --- Pacientes: caso C ----------------------------------------------------------------------


def test_operador_registra_consulta_y_modifica_un_paciente(db, mails, team):
    created = patients.createPatient(db, team.operator, team.id, patientData())
    operatorRelation = relationOf(db, team, team.operator)
    # Normalizados y asociados a la institución mediante su responsable (la operadora que lo creó).
    assert (created.nombre, created.apellido, created.dni, created.sexoModelo) == ("Juan", "Pérez", "20111222", "MASCULINO")
    assert created.responsable.idInstitucionUsuario == operatorRelation.idInstitucionUsuario
    assert created.identificadorPseudonimo.startswith("PAC-") and created.estado == "ACTIVO"
    profile = reload(db, MeasurementProfile, created.idPerfilMedicion)
    assert profile.tipoPerfil == "INSTITUCIONAL" and profile.idUsuario is None
    assert db.get(InstitutionUser, profile.idInstitucionUsuarioResponsable).idInstitucion == team.id

    detail = patients.getPatient(db, team.operator, team.id, created.idPerfilMedicion)
    assert detail.puedeModificar is True and detail.edad >= 45
    assert audits(db, "CONSULTAR_PACIENTE")[0].idUsuario == team.operator.idUsuario

    updated = patients.updatePatient(db, team.operator, team.id, created.idPerfilMedicion,
                                     PatientUpdateRequest(apellido="pérez gómez", fechaNacimiento="1981-03-04"))
    assert (updated.apellido, str(updated.fechaNacimiento)) == ("Pérez Gómez", "1981-03-04")
    [audit] = audits(db, "MODIFICAR_PACIENTE")
    assert "Pérez" not in (audit.datosNuevos or "")  # la auditoría no guarda datos personales
    assert institutions.getDetail(db, team.owner, team.id).cantidadPacientes == 1


def managerReassign(db, team, manager, idPerfilMedicion, target):
    """Reasignación de un paciente con responsable ACTIVO: el gestor la propone y el operador destino la acepta (no hay cambio unilateral)."""
    from app.models.profileTransfer import ProfileTransfer
    from app.services import profileTransfers

    patients.assignResponsible(db, manager, team.id, idPerfilMedicion, target.idInstitucionUsuario)
    pending = db.scalar(select(ProfileTransfer).where(ProfileTransfer.idPerfilMedicion == idPerfilMedicion, ProfileTransfer.estado == "PENDIENTE"))
    assert pending is not None, "la propuesta del gestor debe quedar pendiente"
    profileTransfers.acceptTransfer(db, db.get(User, target.idUsuarioInvitado), team.id, pending.idTransferenciaPerfil)


def test_operadores_disponibles_y_asignacion_persistida(db, mails, team):
    second = addOperator(db, team)
    created = patients.createPatient(db, team.operator, team.id, patientData())

    options = patients.assignableOperators(db, team.operator, team.id)
    assert {(o.nombre, o.apellido) for o in options} == {("Victoria", "Cortés")}
    assert {o.idInstitucionUsuario for o in options} == {relationOf(db, team, team.operator).idInstitucionUsuario,
                                                       second.idInstitucionUsuario}
    assert set(options[0].model_dump()) == {"idInstitucionUsuario", "nombre", "apellido"}  # sin datos sensibles

    # El operador no reasigna: para eso existe la transferencia con aceptación del otro operador.
    expectError("PERMISO_INSUFICIENTE", patients.assignResponsible, db, team.operator, team.id,
                created.idPerfilMedicion, second.idInstitucionUsuario)
    assert reload(db, MeasurementProfile, created.idPerfilMedicion).idInstitucionUsuarioResponsable ==         relationOf(db, team, team.operator).idInstitucionUsuario
    managerReassign(db, team, team.moderator, created.idPerfilMedicion, second)
    assert reload(db, MeasurementProfile, created.idPerfilMedicion).idInstitucionUsuarioResponsable == second.idInstitucionUsuario
    transfer = db.scalar(select(ProfileTransfer).where(ProfileTransfer.idPerfilMedicion == created.idPerfilMedicion))
    assert transfer.estado == "ACEPTADA" and transfer.idOperadorDestino == second.idInstitucionUsuario
    # Ya no está a su cargo: la operadora original solo ve su identificación administrativa (sin documento ni salud) y no lo modifica.
    seen = patients.getPatient(db, team.operator, team.id, created.idPerfilMedicion)
    assert (seen.nombre, seen.dni, seen.sexoModelo, seen.fechaNacimiento, seen.edad) == ("Juan", None, None, None, None)
    assert seen.esMio is False and seen.medicionesAutorizadas is False and seen.puedeModificar is False
    assert patients.listPatients(db, team.operator, team.id).total == 1  # lo sigue viendo en el listado de la institución
    newer = patients.getPatient(db, db.get(User, second.idUsuarioInvitado), team.id, created.idPerfilMedicion)
    assert newer.puedeModificar is True and newer.esMio and newer.medicionesAutorizadas and newer.dni
    expectError("PERMISO_INSUFICIENTE", patients.updatePatient, db, team.operator, team.id, created.idPerfilMedicion,
                PatientUpdateRequest(nombre="Otro"))
    patients.updatePatient(db, team.moderator, team.id, created.idPerfilMedicion, PatientUpdateRequest(nombre="Juan Carlos"))


def test_el_operador_no_administra_personal_por_ver_operadores(db, mails, team):
    patients.assignableOperators(db, team.operator, team.id)
    institutional(db, "nueva@example.com", "nueva")
    expectError("PERMISO_INSUFICIENTE", institutions.invite, db, team.operator, team.id, "OPERADOR", "nueva@example.com")
    expectError("PERMISO_INSUFICIENTE", institutions.listMembers, db, team.operator, team.id)
    expectError("PERMISO_INSUFICIENTE", institutions.revokeMember, db, team.operator, team.id, "OPERADOR",
                relationOf(db, team, team.operator).idInstitucionUsuario)


def test_responsable_debe_ser_operador_activo_de_la_institucion(db, mails, team):
    created = patients.createPatient(db, team.operator, team.id, patientData())
    moderatorRelation = relationOf(db, team, team.moderator)
    expectError("OPERADOR_NO_DISPONIBLE", patients.assignResponsible, db, team.moderator, team.id,
                created.idPerfilMedicion, moderatorRelation.idInstitucionUsuario)
    expectError("OPERADOR_NO_DISPONIBLE", patients.assignResponsible, db, team.moderator, team.id,
                created.idPerfilMedicion, uuid.uuid4())
    # El moderador que crea un paciente tiene que elegir un responsable.
    expectError("RESPONSABLE_REQUERIDO", patients.createPatient, db, team.moderator, team.id, patientData(dni="30111222"))
    other = patients.createPatient(db, team.moderator, team.id, patientData(
        dni="30111222", idInstitucionUsuarioResponsable=relationOf(db, team, team.operator).idInstitucionUsuario))
    assert other.responsable.nombre == "Victoria"


def test_documento_duplicado_en_la_institucion(db, mails, team):
    patients.createPatient(db, team.operator, team.id, patientData())
    error = expectError("PACIENTE_REGISTRADO", patients.createPatient, db, team.operator, team.id, patientData(dni="20111222"))
    assert error.message == "Ya hay un paciente activo con ese documento en la institución."


def test_listado_con_busqueda_filtros_y_paginacion(db, mails, team):
    second = addOperator(db, team)
    for index, (nombre, apellido) in enumerate([("Ana", "Zapata"), ("Bruno", "Alvarez"), ("Carla", "Mendez")]):
        patients.createPatient(db, team.operator, team.id, patientData(nombre=nombre, apellido=apellido, dni=f"4000000{index}"))
    patients.createPatient(db, team.moderator, team.id, patientData(
        nombre="Dario", apellido="Benitez", dni="40000009", idInstitucionUsuarioResponsable=second.idInstitucionUsuario))

    page = patients.listPatients(db, team.owner, team.id, tamanioPagina=3)
    assert page.total == 4 and [p.apellido for p in page.items] == ["Alvarez", "Benitez", "Mendez"]
    assert [p.apellido for p in patients.listPatients(db, team.owner, team.id, tamanioPagina=3, pagina=2).items] == ["Zapata"]
    assert [p.nombre for p in patients.listPatients(db, team.owner, team.id, busqueda="MEN").items] == ["Carla"]
    assert [p.nombre for p in patients.listPatients(db, team.owner, team.id, busqueda="40000009").items] == ["Dario"]
    assert patients.listPatients(db, team.owner, team.id, busqueda="%").total == 0  # comodines escapados
    assert patients.listPatients(db, team.operator, team.id, soloMios=True).total == 3
    assert patients.listPatients(db, team.owner, team.id, idResponsable=second.idInstitucionUsuario).total == 1


def test_filtros_de_estado_vencimiento_y_anonimizados(db, mails, team):
    """Dados de baja ordenados por vencimiento (los que antes pierden sus datos, primero), filtro por plazo, anonimizados y todos."""
    def create(apellido, dni):
        return patients.createPatient(db, team.operator, team.id, patientData(apellido=apellido, dni=dni))

    def setExpiration(profile, when):  # un paciente dado de baja con su identidad todavía presente
        db.execute(update(MeasurementProfile).where(MeasurementProfile.idPerfilMedicion == profile.idPerfilMedicion)
                   .values(fechaExpiracionDatosPersonales=when))
        db.commit()

    now = nowForDb()
    create("Activa", "41000001")
    overdue = create("Vencida", "41000002")
    soon = create("Pronto", "41000003")
    later = create("Despues", "41000004")
    gone = create("Borrado", "41000005")
    setExpiration(overdue, now - timedelta(days=1, hours=12))
    setExpiration(soon, now + timedelta(days=5, hours=12))
    setExpiration(later, now + timedelta(days=200, hours=12))
    patients.dischargePatient(db, team.moderator, team.id, gone.idPerfilMedicion)  # anonimizado en el acto

    lastNames = lambda page: [p.apellido for p in page.items]  # noqa: E731
    assert lastNames(patients.listPatients(db, team.owner, team.id)) == ["Activa"]
    bajas = patients.listPatients(db, team.owner, team.id, estado="BAJA")
    assert lastNames(bajas) == ["Vencida", "Pronto", "Despues"]  # menos días primero
    assert [p.diasRestantesDatos for p in bajas.items] == [-2, 5, 200]
    assert lastNames(patients.listPatients(db, team.owner, team.id, estado="BAJA", venceEnDias=30)) == ["Vencida", "Pronto"]
    assert lastNames(patients.listPatients(db, team.owner, team.id, estado="BAJA", venceEnDias=3)) == ["Vencida"]

    anonymized = patients.listPatients(db, team.owner, team.id, estado="ANONIMIZADO")
    assert [(p.estado, p.anonimizado, p.apellido, p.diasRestantesDatos) for p in anonymized.items] == [("BAJA", True, None, None)]
    everyone = patients.listPatients(db, team.owner, team.id, estado="TODOS")
    assert everyone.total == 5 and sorted((p.estado, p.anonimizado) for p in everyone.items) == [
        ("ACTIVO", False), ("BAJA", False), ("BAJA", False), ("BAJA", False), ("BAJA", True)]

    content, _ = patients.exportPatients(db, team.owner, team.id, alcance="TODOS", estado="BAJA", venceEnDias=30)
    assert b"Pronto" in content and b"Despues" not in content and b"Borrado" not in content


# --- Baja de pacientes ----------------------------------------------------------------------


def test_baja_de_paciente_lo_anonimiza_en_el_acto(db, mails, team):
    created = patients.createPatient(db, team.operator, team.id, patientData())
    addMeasurementTo(db, created.idPerfilMedicion, 3, 95)
    expectError("PERMISO_INSUFICIENTE", patients.dischargePatient, db, team.operator, team.id, created.idPerfilMedicion)
    discharged = patients.dischargePatient(db, team.moderator, team.id, created.idPerfilMedicion)
    assert discharged.estado == "BAJA"
    # Con la migración 031 la baja anonimiza: no queda ningún dato personal ni el seudónimo que conocía el operador.
    assert (discharged.nombre, discharged.apellido, discharged.dni, discharged.fechaNacimiento, discharged.sexoModelo) == (None,) * 5
    assert discharged.identificadorPseudonimo != created.identificadorPseudonimo
    [audit] = audits(db, "BAJA_PACIENTE")
    assert audit.idUsuario == team.moderator.idUsuario  # fecha exacta y responsable de la baja
    assert audits(db, "ANONIMIZAR_PACIENTES")
    # Ya no es un paciente: no figura en ningún listado ni se puede modificar. Sus mediciones siguen, sin persona, en la cohorte anónima.
    expectError("PACIENTE_NO_ENCONTRADO", patients.updatePatient, db, team.moderator, team.id, created.idPerfilMedicion,
                PatientUpdateRequest(nombre="Otro"))
    assert patients.listPatients(db, team.owner, team.id).total == 0
    assert patients.listPatients(db, team.owner, team.id, estado="BAJA").total == 0
    assert db.scalar(select(func.count()).select_from(Measurement)) == 1
    assert db.scalar(select(func.count()).select_from(Measurement).where(Measurement.idPerfilMedicion == created.idPerfilMedicion)) == 0
    # Un documento dado de baja puede volver a registrarse.
    patients.createPatient(db, team.operator, team.id, patientData())


# --- Seguridad: caso D ----------------------------------------------------------------------


def test_aislamiento_entre_instituciones(db, mails, team):
    created = patients.createPatient(db, team.operator, team.id, patientData())
    other, otherOperator, otherRelation = otherInstitution(db)

    # No se ven ni se modifican pacientes de otra institución, aunque se conozca el identificador.
    expectError("PACIENTE_NO_ENCONTRADO", patients.getPatient, db, team.owner, team.id, uuid.uuid4())
    expectError("INSTITUCION_NO_ENCONTRADA", patients.getPatient, db, otherOperator, team.id, created.idPerfilMedicion)
    expectError("PACIENTE_NO_ENCONTRADO", patients.getPatient, db, otherOperator, other.idInstitucion, created.idPerfilMedicion)
    assert patients.listPatients(db, otherOperator, other.idInstitucion).total == 0
    # No se asigna a un operador de otra institución.
    expectError("OPERADOR_NO_DISPONIBLE", patients.assignResponsible, db, team.moderator, team.id,
                created.idPerfilMedicion, otherRelation.idInstitucionUsuario)
    expectError("OPERADOR_NO_DISPONIBLE", patients.createPatient, db, team.moderator, team.id,
                patientData(dni="30111222", idInstitucionUsuarioResponsable=otherRelation.idInstitucionUsuario))
    assert reload(db, MeasurementProfile, created.idPerfilMedicion).idInstitucionUsuarioResponsable == \
        relationOf(db, team, team.operator).idInstitucionUsuario


def test_operador_desvinculado_pierde_acceso_aunque_tenga_sesion(db, mails, team):
    created = patients.createPatient(db, team.operator, team.id, patientData())
    operatorRelation = relationOf(db, team, team.operator)
    legacyRevoke(db, team.moderator, team.id, operatorRelation.idInstitucionUsuario)
    expectError("INSTITUCION_NO_ENCONTRADA", patients.listPatients, db, team.operator, team.id)
    expectError("INSTITUCION_NO_ENCONTRADA", patients.getPatient, db, team.operator, team.id, created.idPerfilMedicion)
    # El paciente sigue en la institución, con su responsable marcado como inactivo hasta reasignarlo.
    detail = patients.getPatient(db, team.owner, team.id, created.idPerfilMedicion)
    assert detail.responsable.activo is False


def test_cuenta_individual_no_accede_a_pacientes(db, mails, team):
    expectError("PERMISO_INSUFICIENTE", patients.listPatients, db, makeUser(db), team.id)


# --- Eliminación y retención: caso E --------------------------------------------------------


def deletion(**overrides) -> InstitutionDeletionRequest:
    return InstitutionDeletionRequest(**{"confirmacionNombre": "Hospital X", "password": PASSWORD, **overrides})


def test_cierre_bloquea_pacientes_y_conserva_hasta_el_vencimiento(db, mails, team):
    created = patients.createPatient(db, team.operator, team.id, patientData())
    profile = reload(db, MeasurementProfile, created.idPerfilMedicion)
    device = Device(idDispositivo=uuid.uuid4(), codigoDispositivo=uuid.uuid4().hex, modeloSensor="MAX30102")
    db.add(device)
    db.flush()
    db.add(Measurement(
        idMedicion=uuid.uuid4(), idPerfilMedicion=profile.idPerfilMedicion, idDispositivo=device.idDispositivo,
        modoMedicion="OXIMETRIA", estadoMedicion="COMPLETADA", edadAlMomento=46, sexoModelo="MASCULINO",
        condicionComida="POSTPRANDIAL", fechaHoraInicio=nowForDb() - timedelta(days=3),
        fechaHoraUltimaComida=nowForDb() - timedelta(days=3, hours=2), spo2=97, frecuenciaCardiaca=72,
        modeloSensorAlMomento="MAX30102",
    ))
    db.commit()

    institutions.deleteInstitution(db, team.owner, team.id, deletion())
    institution = reload(db, Institution, team.id)
    assert institution.estado == "CERRADA"
    retentionEnd = reload(db, MeasurementProfile, created.idPerfilMedicion).fechaExpiracionDatosPersonales
    assert retentionEnd == institutions.addMonths(institution.fechaActualizacion, 12)
    # Sin acceso operativo para nadie de la institución.
    for user in (team.owner, team.moderator, team.operator):
        expectError("INSTITUCION_NO_ENCONTRADA", patients.listPatients, db, user, team.id)
        expectError("INSTITUCION_NO_ENCONTRADA", patients.getPatient, db, user, team.id, created.idPerfilMedicion)
    expectError("INSTITUCION_NO_ENCONTRADA", patients.createPatient, db, team.operator, team.id, patientData(dni="30111222"))

    # Antes del vencimiento, la depuración no toca nada.
    assert purgeExpiredPatientData(db, now=retentionEnd - timedelta(minutes=1)) == 0
    assert reload(db, MeasurementProfile, created.idPerfilMedicion).dni == "20111222"
    # Vencido el período: ANONIMIZACIÓN irreversible (031). La persona queda sin datos ni seudónimo conocido, y sus mediciones, separadas de
    # ella en la cohorte anónima de la institución (tests/test_retention_anonymization.py prueba el detalle).
    assert purgeExpiredPatientData(db, now=retentionEnd + timedelta(minutes=1)) == 1
    purged = reload(db, MeasurementProfile, created.idPerfilMedicion)
    assert (purged.nombre, purged.apellido, purged.dni, purged.fechaNacimiento) == (None, None, None, None)
    assert purged.fechaDepuracionDatosPersonales is not None and purged.identificadorPseudonimo != created.identificadorPseudonimo
    assert db.scalar(select(Measurement).where(Measurement.idPerfilMedicion == purged.idPerfilMedicion)) is None
    assert db.scalar(select(Measurement)).edadAlMomento == 46
    assert db.scalar(select(Audit).where(Audit.accion == "ANONIMIZAR_PACIENTES")) is not None
    # Idempotente.
    assert purgeExpiredPatientData(db, now=retentionEnd + timedelta(days=1)) == 0
    # Las cuentas de los miembros siguen activas.
    for user in (team.owner, team.moderator, team.operator):
        assert reload(db, type(user), user.idUsuario).estado == "ACTIVO"


def test_add_months_como_sql_server():
    assert institutions.addMonths(nowForDb().replace(year=2024, month=2, day=29), 12).date() == date(2025, 2, 28)
    assert institutions.addMonths(nowForDb().replace(year=2026, month=10, day=8), 12).date() == date(2027, 10, 8)


# --- Reautenticación de cuentas solo Google -------------------------------------------------


def googleOwnerTeam(db):
    owner = institutional(db, "google@example.com", "googleowner", local=False, google=True)
    institution = newInstitution(db, owner)
    return owner, institution


def test_cuenta_google_sin_mfa_no_puede_confirmar_la_eliminacion(db, mails):
    owner, institution = googleOwnerTeam(db)
    error = expectError("REAUTENTICACION_REQUERIDA", institutions.deleteInstitution, db, owner,
                        institution.idInstitucion, deletion(password=None))
    assert "verificación en dos pasos" in error.message
    assert reload(db, Institution, institution.idInstitucion).estado == "ACTIVA"


def test_cuenta_google_con_mfa_confirma_sin_contraseña(db, mails):
    owner, institution = googleOwnerTeam(db)
    secret = enableMfa(db, owner)
    expectError("CODIGO_MFA_REQUERIDO", institutions.deleteInstitution, db, owner, institution.idInstitucion,
                deletion(password=None))
    institutions.deleteInstitution(db, owner, institution.idInstitucion, deletion(password=None, codigo=totpCode(secret)))
    assert reload(db, Institution, institution.idInstitucion).estado == "CERRADA"


# --- Mediciones del perfil ------------------------------------------------------------------


def addMeasurementTo(db, idPerfilMedicion, daysAgo, spo2):
    device = Device(idDispositivo=uuid.uuid4(), codigoDispositivo=uuid.uuid4().hex, modeloSensor="MAX30102")
    db.add(device)
    db.flush()
    measurement = Measurement(
        idMedicion=uuid.uuid4(), idPerfilMedicion=idPerfilMedicion, idDispositivo=device.idDispositivo,
        modoMedicion="OXIMETRIA", estadoMedicion="COMPLETADA", edadAlMomento=46, sexoModelo="MASCULINO",
        condicionComida="POSTPRANDIAL", fechaHoraInicio=nowForDb() - timedelta(days=daysAgo),
        fechaHoraUltimaComida=nowForDb() - timedelta(days=daysAgo, hours=2), spo2=spo2, frecuenciaCardiaca=72,
        modeloSensorAlMomento="MAX30102",
    )
    db.add(measurement)
    db.commit()
    return measurement


def test_mediciones_del_perfil_se_conservan_al_reasignar_y_dar_de_baja(db, mails, team):
    created = patients.createPatient(db, team.operator, team.id, patientData())
    addMeasurementTo(db, created.idPerfilMedicion, 3, 95)
    addMeasurementTo(db, created.idPerfilMedicion, 1, 98)
    page = measurementService.listPatientHistory(db, team.operator, team.id, created.idPerfilMedicion)
    assert page.total == 2 and [float(m.spo2) for m in page.items] == [98.0, 95.0]  # más reciente primero

    second = addOperator(db, team)
    managerReassign(db, team, team.moderator, created.idPerfilMedicion, second)
    patients.dischargePatient(db, team.moderator, team.id, created.idPerfilMedicion)
    # Tras la baja el paciente queda anonimizado: sus mediciones se conservan SIN persona (cohorte anónima) y nadie las consulta por paciente.
    secondUser = db.get(User, second.idUsuarioInvitado)
    for actor in (secondUser, team.owner, team.moderator, team.operator):
        expectError("PACIENTE_NO_ENCONTRADO", measurementService.listPatientHistory, db, actor, team.id, created.idPerfilMedicion)
    assert db.scalar(select(func.count()).select_from(Measurement)) == 2


def test_mediciones_de_otra_institucion_no_se_consultan(db, mails, team):
    created = patients.createPatient(db, team.operator, team.id, patientData())
    addMeasurementTo(db, created.idPerfilMedicion, 1, 97)
    other, otherOperator, _ = otherInstitution(db)
    expectError("PACIENTE_NO_ENCONTRADO", measurementService.listPatientHistory, db, otherOperator, other.idInstitucion,
                created.idPerfilMedicion)
    expectError("INSTITUCION_NO_ENCONTRADA", measurementService.listPatientHistory, db, otherOperator, team.id,
                created.idPerfilMedicion)
