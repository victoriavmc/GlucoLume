# Pruebas del inventario de dispositivos: alta, estados, asignación institucional, aislamiento por institución, retiro
# sin perder historial, identificación durante la adquisición e integración con las mediciones y la auditoría.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_devices.py -v

import threading
import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.core.exceptions import AuthError
from app.main import app
from app.models.device import Device
from app.models.institutionUser import InstitutionUser
from app.models.measurement import Measurement
from app.models.user import User
from app.schemas.device import (
    DeviceAssignRequest,
    DeviceEditRequest,
    DeviceRegisterRequest,
    DeviceResolveRequest,
    DeviceStateRequest,
)
from app.schemas.measurement import MeasurementFinish, MeasurementStart
from app.services import auditQuery
from app.services import device as devices
from app.services import institution as institutions
from app.services import institutionPatients as patients
from app.services import measurement as measurements
from tests.legacy_offboarding import legacyRevoke
from tests.test_account_deletion import audits, db, engine, mails, makeUser, reload  # noqa: F401 - fixtures
from tests.test_audit import admin, api  # noqa: F401 - fixtures
from tests.test_institution_patients import addOperator, patientData
from tests.test_institutions import (  # noqa: F401 - fixtures
    expectError,
    freshLookupLimiter,
    institutional,
    newInstitution,
    relationOf,
    team,
)
from tests.test_matrices import north  # noqa: F401 - fixtures
from tests.test_measurements import samples, signalSamples


def register(code="GL-0001", sensor="MAX30102", **extra):
    return DeviceRegisterRequest(codigoDispositivo=code, modeloSensor=sensor, nombre="Oxímetro", modelo="UNO + HC-06",
                                 versionFirmware="1.0.0", **extra)


@pytest.fixture
def platformModerator(db, mails):
    return makeUser(db, tipoCuenta="MODERADOR_PLATAFORMA", email="mod@example.com", usuario="mod")


def globalScope(db, actor):
    return devices.platformScope(db, actor)


def instScope(db, actor, institution):
    return devices.institutionScope(db, actor, institution)


def count(db, model=Device):
    db.expire_all()
    return db.scalar(select(func.count()).select_from(model))


def holdBy(db, idDispositivo, idRelacion):
    """Fija un responsable directamente en la base: la institución ya no puede elegirlo (lo asigna el alta al propietario),
    pero los datos previos o cargados por la plataforma pueden tenerlo y la lógica de uso debe respetarlo."""
    device = db.get(Device, idDispositivo)
    device.idInstitucionUsuarioResponsable = idRelacion
    db.commit()


def operatorUser(db, team_):
    return team_.operator


# --- Alta ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("sensor", ["MAX30100", "MAX30102"])
def test_registra_dispositivos_con_cada_sensor_admitido(db, mails, admin, sensor):
    detail = devices.registerDevice(db, globalScope(db, admin), register(f"GL-{sensor}", sensor))
    assert (detail.modeloSensor, detail.estado, detail.idInstitucionAsignada, detail.responsable) == (sensor, "OPERATIVO", None, None)
    stored = reload(db, Device, detail.idDispositivo)
    assert stored.codigoDispositivo == f"GL-{sensor}" and stored.versionFirmware == "1.0.0" and stored.fechaRegistro is not None
    assert stored.idDispositivo is not None and detail.disponibleParaMedir and detail.permisos.puedeAsignarInstitucion


def test_el_alta_valida_codigo_sensor_y_estado():
    for bad in ({"codigoDispositivo": "ab"}, {"codigoDispositivo": "COM3 puerto"}, {"codigoDispositivo": ""},
                {"modeloSensor": "MAX30105"}, {"modeloSensor": "DS18B20"}, {"estado": "BAJA"}, {"estado": "DESCOMISIONADO"},
                {"estado": "ROTO"}):
        with pytest.raises(ValidationError):
            DeviceRegisterRequest(**{"codigoDispositivo": "GL-0001", "modeloSensor": "MAX30102", **bad})
    assert register("  GL-0002  ").codigoDispositivo == "GL-0002"
    assert DeviceRegisterRequest(codigoDispositivo="GL-0003", modeloSensor="max30100").modeloSensor == "MAX30100"
    assert DeviceRegisterRequest(codigoDispositivo="GL-0003", modeloSensor="MAX30102", estado="en_mantenimiento").estado == "EN_MANTENIMIENTO"


def test_un_responsable_requiere_institucion_en_el_inventario_global(db, mails, admin):
    expectError("RESPONSABLE_DISPOSITIVO_INVALIDO", devices.registerDevice, db, globalScope(db, admin),
                register("GL-0009", idInstitucionUsuarioResponsable=uuid.uuid4()))
    assert count(db) == 0


def test_rechaza_codigos_duplicados_sin_importar_mayusculas_ni_institucion(db, mails, team, admin):
    devices.registerDevice(db, globalScope(db, admin), register("GL-0001"))
    expectError("DISPOSITIVO_DUPLICADO", devices.registerDevice, db, globalScope(db, admin), register("GL-0001"))
    expectError("DISPOSITIVO_DUPLICADO", devices.registerDevice, db, globalScope(db, admin), register("gl-0001"))
    # Tampoco una institución puede registrar el mismo código (ni enterarse de quién lo tiene).
    expectError("DISPOSITIVO_DUPLICADO", devices.registerDevice, db, instScope(db, team.owner, team.id), register("GL-0001"))
    assert count(db) == 1


def test_codigo_duplicado_por_condicion_de_carrera_no_crea_dos_registros(engine, db, mails, admin):
    makeSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    barrier = threading.Barrier(2)
    results = []

    def run():
        session = makeSession()
        try:
            actor = session.get(User, admin.idUsuario)
            barrier.wait()
            devices.registerDevice(session, devices.platformScope(session, actor), register("GL-CARRERA"))
            results.append("OK")
        except AuthError as error:
            results.append(error.code)
        finally:
            session.close()

    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(results) == ["DISPOSITIVO_DUPLICADO", "OK"] and count(db) == 1


def test_el_propietario_y_el_moderador_registran_dentro_de_su_institucion(db, mails, team, north):
    own = devices.registerDevice(db, instScope(db, team.owner, team.id), register("GL-OWN"))
    assert own.idInstitucionAsignada == team.id and own.fechaAsignacionInstitucional is not None
    byModerator = devices.registerDevice(db, instScope(db, team.moderator, team.id), register("GL-MOD", "MAX30100"))
    assert byModerator.idInstitucionAsignada == team.id
    # Ambos quedan a cargo del PROPIETARIO (también el que registró el moderador): el backend lo decide.
    ownerRelation = relationOf(db, team, team.owner).idInstitucionUsuario
    assert own.responsable.idInstitucionUsuario == ownerRelation == byModerator.responsable.idInstitucionUsuario
    # No pueden registrar a nombre de otra institución aunque lo envíen en el cuerpo.
    expectError("PERMISO_INSUFICIENTE", devices.registerDevice, db, instScope(db, team.owner, team.id),
                register("GL-OTRA", idInstitucionAsignada=north.id))
    assert db.scalar(select(Device).where(Device.codigoDispositivo == "GL-OTRA")) is None


def test_el_alta_institucional_asigna_al_propietario_y_no_admite_elegir_a_otra_persona(db, mails, team, north):
    ownerRelation = relationOf(db, team, team.owner).idInstitucionUsuario
    operatorRelation = relationOf(db, team, team.operator).idInstitucionUsuario
    foreign = relationOf(db, north, north.operator).idInstitucionUsuario
    scope = instScope(db, team.owner, team.id)
    # Indicar al propietario vigente es redundante pero válido; cualquier otra persona (de la institución o ajena) se rechaza.
    ok = devices.registerDevice(db, scope, register("GL-OK", idInstitucionUsuarioResponsable=ownerRelation))
    assert ok.responsable.idInstitucionUsuario == ownerRelation
    for chosen in (operatorRelation, relationOf(db, team, team.moderator).idInstitucionUsuario, foreign, uuid.uuid4()):
        expectError("PERMISO_INSUFICIENTE", devices.registerDevice, db, scope,
                    register("GL-MAL", idInstitucionUsuarioResponsable=chosen))
        expectError("PERMISO_INSUFICIENTE", devices.registerDevice, db, instScope(db, team.moderator, team.id),
                    register("GL-MAL", idInstitucionUsuarioResponsable=chosen))
    assert count(db) == 1
    assert reload(db, Device, ok.idDispositivo).idInstitucionUsuarioResponsable == ownerRelation


def test_si_no_hay_un_propietario_vigente_no_se_asigna_a_otra_persona(db, mails, team):
    moderator = instScope(db, team.moderator, team.id)
    db.get(InstitutionUser, relationOf(db, team, team.owner).idInstitucionUsuario).estadoRelacion = "SUSPENDIDO"
    db.commit()
    expectError("PROPIETARIO_NO_DETERMINADO", devices.registerDevice, db, moderator, register("GL-SIN"))
    assert count(db) == 0


# --- Roles ---------------------------------------------------------------------------------------------------


def test_el_operador_no_administra_el_inventario_y_los_intentos_quedan_auditados(db, mails, team):
    owner = instScope(db, team.owner, team.id)
    device = devices.registerDevice(db, owner, register("GL-0001"))
    scope = instScope(db, team.operator, team.id)
    mine = relationOf(db, team, team.operator).idInstitucionUsuario
    attempts = (
        (devices.registerDevice, (register("GL-OP"),)),
        (devices.editDevice, (device.idDispositivo, DeviceEditRequest(nombre="x"))),
        (devices.changeState, (device.idDispositivo, "EN_MANTENIMIENTO", None)),
        (devices.changeResponsible, (device.idDispositivo, mine)),
        (devices.unassign, (device.idDispositivo,)),
        (devices.decommission, (device.idDispositivo,)),
        (devices.listResponsibles, ()),
    )
    for fn, args in attempts:
        expectError("PERMISO_INSUFICIENTE", fn, db, scope, *args)
    stored = reload(db, Device, device.idDispositivo)
    assert (stored.estado, stored.nombre, stored.idInstitucionAsignada) == ("OPERATIVO", "Oxímetro", team.id)
    failures = [a for a in db.scalars(select(__import__("app.models.audit", fromlist=["Audit"]).Audit)) if a.resultado == "FALLO" and a.modulo == "DISPOSITIVOS"]
    assert len(failures) == len(attempts) and all(a.idUsuario == team.operator.idUsuario and a.idInstitucion == team.id for a in failures)
    # El propietario puede consultar esos intentos en la auditoría de su institución.
    page = auditQuery.listInstitution(db, team.owner, team.id, modulo="DISPOSITIVOS", resultado="FALLO", tamanioPagina=100)
    assert page.total == len(attempts)


def test_el_operador_consulta_solo_dispositivos_operativos_propios_o_sin_responsable_con_datos_minimos(db, mails, team):
    owner = instScope(db, team.owner, team.id)
    mine = relationOf(db, team, team.operator).idInstitucionUsuario
    other = addOperator(db, team)
    free = devices.registerDevice(db, owner, register("GL-LIBRE"))
    ownDevice = devices.registerDevice(db, owner, register("GL-MIO"))
    holdBy(db, ownDevice.idDispositivo, mine)
    othersDevice = devices.registerDevice(db, owner, register("GL-AJENO"))
    holdBy(db, othersDevice.idDispositivo, other.idInstitucionUsuario)
    maintenance = devices.registerDevice(db, owner, register("GL-MANT", estado="EN_MANTENIMIENTO"))
    page = devices.listDevices(db, instScope(db, team.operator, team.id))
    assert {i.codigoDispositivo for i in page.items} == {"GL-LIBRE", "GL-MIO"}
    mineItem = next(i for i in page.items if i.codigoDispositivo == "GL-MIO")
    freeItem = next(i for i in page.items if i.codigoDispositivo == "GL-LIBRE")
    assert mineItem.esMio and mineItem.responsable is not None and freeItem.responsable is None
    assert all(i.fechaAsignacionInstitucional is None for i in page.items)  # sin datos administrativos
    scope = instScope(db, team.operator, team.id)
    for hidden in (othersDevice, maintenance):
        expectError("DISPOSITIVO_NO_ENCONTRADO", devices.getDevice, db, scope, hidden.idDispositivo)
    detail = devices.getDevice(db, scope, free.idDispositivo)
    assert not any(detail.permisos.model_dump().values()) and detail.medicionesRegistradas is None
    assert ownDevice.idDispositivo and devices.summary(db, scope).total == 2


def test_el_moderador_institucional_registra_edita_el_nombre_y_cambia_estados(db, mails, team):
    moderator = instScope(db, team.moderator, team.id)
    device = devices.registerDevice(db, moderator, register("GL-0001"))
    assert devices.changeState(db, moderator, device.idDispositivo, "FUERA_DE_SERVICIO", "falla").estado == "FUERA_DE_SERVICIO"
    mine = relationOf(db, team, team.operator).idInstitucionUsuario
    permissions = devices.getDevice(db, moderator, device.idDispositivo).permisos
    assert permissions.puedeCambiarEstado and permissions.puedeEditar
    assert not any([permissions.puedeCambiarResponsable, permissions.puedeDesvincular, permissions.puedeDescomisionar])
    # Edita el nombre y el modelo; el sensor y el firmware los informa la conexión (no los reescribe una institución).
    assert devices.editDevice(db, moderator, device.idDispositivo, DeviceEditRequest(nombre="Consultorio 1")).nombre == "Consultorio 1"
    expectError("PERMISO_INSUFICIENTE", devices.editDevice, db, moderator, device.idDispositivo, DeviceEditRequest(modeloSensor="MAX30100"))
    expectError("PERMISO_INSUFICIENTE", devices.editDevice, db, moderator, device.idDispositivo, DeviceEditRequest(versionFirmware="9.9.9"))
    # Sin responsable, ni desvinculación, ni retiro.
    expectError("PERMISO_INSUFICIENTE", devices.changeResponsible, db, moderator, device.idDispositivo, mine)
    expectError("PERMISO_INSUFICIENTE", devices.listResponsibles, db, moderator)
    expectError("PERMISO_INSUFICIENTE", devices.unassign, db, moderator, device.idDispositivo)
    expectError("PERMISO_INSUFICIENTE", devices.decommission, db, moderator, device.idDispositivo)
    stored = reload(db, Device, device.idDispositivo)
    assert (stored.nombre, stored.modeloSensor, stored.versionFirmware) == ("Consultorio 1", "MAX30102", "1.0.0")
    assert stored.idInstitucionUsuarioResponsable == relationOf(db, team, team.owner).idInstitucionUsuario  # la titularidad no cambia


def test_el_propietario_cambia_estado_y_descomisiona_edita_el_nombre_pero_no_reasigna(db, mails, team):
    owner = instScope(db, team.owner, team.id)
    device = devices.registerDevice(db, owner, register("GL-0001"))
    assert devices.changeState(db, owner, device.idDispositivo, "EN_MANTENIMIENTO", None).estado == "EN_MANTENIMIENTO"
    permissions = devices.getDevice(db, owner, device.idDispositivo).permisos
    assert permissions.puedeCambiarEstado and permissions.puedeDescomisionar
    assert permissions.puedeEditar and not any([permissions.puedeCambiarResponsable, permissions.puedeDesvincular])
    mine = relationOf(db, team, team.operator).idInstitucionUsuario
    assert devices.editDevice(db, owner, device.idDispositivo, DeviceEditRequest(nombre="Consultorio 2", modelo="UNO + HC-05")).modelo == "UNO + HC-05"
    expectError("PERMISO_INSUFICIENTE", devices.changeResponsible, db, owner, device.idDispositivo, mine)
    expectError("PERMISO_INSUFICIENTE", devices.unassign, db, owner, device.idDispositivo)
    expectError("PERMISO_INSUFICIENTE", devices.listResponsibles, db, owner)
    # BAJA no es un estado que se imponga con el cambio de estado: es el retiro, con su propia operación.
    with pytest.raises(ValidationError):
        DeviceStateRequest(estado="BAJA")


def test_la_moderacion_de_plataforma_no_se_equipara_con_el_administrador(db, mails, team, admin, platformModerator):
    scope = globalScope(db, platformModerator)
    device = devices.registerDevice(db, scope, register("GL-0001"))
    assert devices.editDevice(db, scope, device.idDispositivo, DeviceEditRequest(nombre="Edit")).nombre == "Edit"
    assert devices.changeState(db, scope, device.idDispositivo, "EN_MANTENIMIENTO", None).estado == "EN_MANTENIMIENTO"
    assert devices.listDevices(db, scope).total == 1
    expectError("PERMISO_INSUFICIENTE", devices.assignInstitution, db, scope, device.idDispositivo, DeviceAssignRequest(idInstitucion=team.id))
    expectError("PERMISO_INSUFICIENTE", devices.decommission, db, scope, device.idDispositivo)
    expectError("PERMISO_INSUFICIENTE", devices.registerDevice, db, scope, register("GL-ASIG", idInstitucionAsignada=team.id))
    assert reload(db, Device, device.idDispositivo).idInstitucionAsignada is None
    detail = devices.getDevice(db, scope, device.idDispositivo)
    assert not detail.permisos.puedeAsignarInstitucion and not detail.permisos.puedeDescomisionar
    assert devices.getDevice(db, globalScope(db, admin), device.idDispositivo).permisos.puedeAsignarInstitucion


def test_quien_no_es_de_plataforma_no_entra_al_inventario_global(db, mails, team):
    consumer = makeUser(db, email="persona@example.com", usuario="persona")
    for actor in (team.owner, team.moderator, team.operator, consumer):
        expectError("PERMISO_INSUFICIENTE", devices.platformScope, db, actor)
    expectError("PERMISO_INSUFICIENTE", devices.institutionScope, db, consumer, team.id)


# --- Aislamiento institucional ----------------------------------------------------------------------------


def test_una_institucion_no_ve_ni_administra_dispositivos_de_otra(db, mails, team, north):
    mine = devices.registerDevice(db, instScope(db, team.owner, team.id), register("GL-HX"))
    theirs = devices.registerDevice(db, instScope(db, north.owner, north.id), register("GL-NORTE"))
    assert [i.codigoDispositivo for i in devices.listDevices(db, instScope(db, team.owner, team.id)).items] == ["GL-HX"]
    northScope = instScope(db, north.owner, north.id)
    for fn, args in ((devices.getDevice, ()), (devices.changeState, ("EN_MANTENIMIENTO", None)),
                     (devices.decommission, ()), (devices.listMeasurements, ())):
        expectError("DISPOSITIVO_NO_ENCONTRADO", fn, db, northScope, mine.idDispositivo, *args)
    expectError("DISPOSITIVO_NO_ENCONTRADO", devices.editDevice, db, northScope, mine.idDispositivo, DeviceEditRequest(nombre="x"))
    for fn, args in ((devices.changeResponsible, (None,)), (devices.unassign, ())):
        expectError("PERMISO_INSUFICIENTE", fn, db, northScope, mine.idDispositivo, *args)
    expectError("INSTITUCION_NO_ENCONTRADA", devices.institutionScope, db, team.owner, north.id)
    assert reload(db, Device, mine.idDispositivo).estado == "OPERATIVO" and theirs.idDispositivo


def test_http_codigos_y_aislamiento_por_ruta(db, mails, team, north, admin, api):
    mine = devices.registerDevice(db, instScope(db, team.owner, team.id), register("GL-HX"))
    body = {"codigoDispositivo": "GL-HTTP", "modeloSensor": "MAX30102", "nombre": "HTTP"}
    created = api(team.owner).post(f"/api/v1/institutions/{team.id}/devices", json=body)
    assert created.status_code == 201 and created.json()["idInstitucionAsignada"] == str(team.id)
    assert api(team.owner).post(f"/api/v1/institutions/{team.id}/devices", json=body).status_code == 409
    assert api(team.operator).post(f"/api/v1/institutions/{team.id}/devices", json={**body, "codigoDispositivo": "GL-X1"}).status_code == 403
    assert api(team.operator).post(f"/api/v1/institutions/{team.id}/devices/{mine.idDispositivo}/state", json={"estado": "EN_MANTENIMIENTO"}).status_code == 403
    assert api(north.owner).get(f"/api/v1/institutions/{team.id}/devices").status_code == 404
    assert api(north.owner).get(f"/api/v1/institutions/{north.id}/devices/{mine.idDispositivo}").status_code == 404
    assert api(team.owner).get("/api/v1/devices").status_code == 403
    assert api(admin).get("/api/v1/devices").json()["total"] == 2
    assert api(team.owner).post(f"/api/v1/institutions/{team.id}/devices", json={**body, "codigoDispositivo": "GL-X2", "modeloSensor": "MAX30105"}).status_code == 422
    # No hay forma de eliminar dispositivos por la API.
    for route in app.routes:
        if "/devices" in getattr(route, "path", ""):
            assert "DELETE" not in route.methods, route.path


def test_http_la_institucion_no_elige_responsable_ni_desvincula_y_solo_edita_el_nombre(db, mails, team, api):
    base = f"/api/v1/institutions/{team.id}/devices"
    ownerRelation = str(relationOf(db, team, team.owner).idInstitucionUsuario)
    operatorRelation = str(relationOf(db, team, team.operator).idInstitucionUsuario)
    body = {"codigoDispositivo": "GL-HTTP", "modeloSensor": "MAX30102"}
    # Solicitud directa eligiendo a otra persona: se rechaza y no se crea nada.
    assert api(team.owner).post(base, json={**body, "idInstitucionUsuarioResponsable": operatorRelation}).status_code == 403
    assert count(db) == 0
    created = api(team.moderator).post(base, json=body)
    assert created.status_code == 201 and created.json()["responsable"]["idInstitucionUsuario"] == ownerRelation
    device = created.json()["idDispositivo"]
    # Propietario y moderador editan el nombre; el operador no; ninguno cambia el sensor ni el firmware (los informa la conexión).
    assert api(team.operator).patch(f"{base}/{device}", json={"nombre": "Otro"}).status_code == 403
    for actor in (team.owner, team.moderator):
        assert api(actor).patch(f"{base}/{device}", json={"modeloSensor": "MAX30100"}).status_code == 403
        assert api(actor).patch(f"{base}/{device}", json={"versionFirmware": "9.9"}).status_code == 403
    assert api(team.owner).patch(f"{base}/{device}", json={"nombre": "Consultorio 3"}).json()["nombre"] == "Consultorio 3"
    forbidden = (("post", f"{base}/{device}/unassign", None),
                 ("post", f"{base}/{device}/responsible", {"idInstitucionUsuarioResponsable": operatorRelation}),
                 ("get", f"{base}/responsibles", None))
    for actor in (team.owner, team.moderator, team.operator):
        for method, url, payload in forbidden:
            response = getattr(api(actor), method)(url, **({"json": payload} if payload is not None else {}))
            assert response.status_code == 403, (actor.usuario, method, url)
    stored = reload(db, Device, uuid.UUID(device))
    assert stored.nombre == "Consultorio 3" and stored.modeloSensor == "MAX30102" and str(stored.idInstitucionUsuarioResponsable) == ownerRelation
    # Estado: propietario y moderador sí; el operador no; BAJA no se impone por esta vía.
    assert api(team.owner).post(f"{base}/{device}/state", json={"estado": "EN_MANTENIMIENTO"}).status_code == 200
    assert api(team.moderator).post(f"{base}/{device}/state", json={"estado": "OPERATIVO"}).status_code == 200
    assert api(team.operator).post(f"{base}/{device}/state", json={"estado": "FUERA_DE_SERVICIO"}).status_code == 403
    assert api(team.owner).post(f"{base}/{device}/state", json={"estado": "BAJA"}).status_code == 422
    assert reload(db, Device, uuid.UUID(device)).estado == "OPERATIVO"


# --- Edición y persistencia -----------------------------------------------------------------------------------


def test_modificar_persiste_y_precarga_los_valores(db, mails, admin):
    scope = globalScope(db, admin)
    device = devices.registerDevice(db, scope, register("GL-0001"))
    edited = devices.editDevice(db, scope, device.idDispositivo, DeviceEditRequest(
        nombre="Prototipo 2", modelo="UNO + HC-06 v2", modeloSensor="MAX30100", versionFirmware="1.1.0"))
    assert (edited.nombre, edited.modelo, edited.modeloSensor, edited.versionFirmware) == ("Prototipo 2", "UNO + HC-06 v2", "MAX30100", "1.1.0")
    stored = reload(db, Device, device.idDispositivo)
    assert (stored.nombre, stored.modeloSensor, stored.versionFirmware, stored.codigoDispositivo) == ("Prototipo 2", "MAX30100", "1.1.0", "GL-0001")
    with pytest.raises(ValidationError):
        DeviceEditRequest(codigoDispositivo="OTRO")  # el código identifica al dispositivo y no cambia
    with pytest.raises(ValidationError):
        DeviceEditRequest(modeloSensor="MAX30105")
    assert devices.getDevice(db, scope, device.idDispositivo).nombre == "Prototipo 2"


# --- Estados y mediciones ---------------------------------------------------------------------------------------


def institutionalSetup(db, team):
    patient = patients.createPatient(db, team.operator, team.id, patientData(sexoModelo="femenino"))
    device = devices.registerDevice(db, instScope(db, team.owner, team.id), register("GL-0001"))
    return patient, device


def start(db, team, patient, device):
    return measurements.startMeasurement(db, team.operator, MeasurementStart(
        idPerfilMedicion=patient.idPerfilMedicion, idDispositivo=device.idDispositivo))


def test_un_dispositivo_no_operativo_no_inicia_ni_continua_adquisiciones(db, mails, team):
    patient, device = institutionalSetup(db, team)
    owner = instScope(db, team.owner, team.id)
    for state in ("EN_MANTENIMIENTO", "FUERA_DE_SERVICIO"):
        detail = devices.changeState(db, owner, device.idDispositivo, state, "prueba")
        assert detail.estado == state and not detail.disponibleParaMedir
        expectError("DISPOSITIVO_NO_DISPONIBLE", start, db, team, patient, device)
        assert [d.idDispositivo for d in measurements.listDevices(db, team.operator, patient.idPerfilMedicion)] == []
    assert count(db, Measurement) == 0
    devices.changeState(db, owner, device.idDispositivo, "OPERATIVO", None)
    started = start(db, team, patient, device)
    assert started.dispositivo.idDispositivo == device.idDispositivo  # la medición conserva idDispositivo
    assert reload(db, Measurement, started.idMedicion).idDispositivo == device.idDispositivo
    # Pasa a mantenimiento a mitad de la medición: no se reciben más datos (se puede cancelar).
    devices.changeState(db, owner, device.idDispositivo, "EN_MANTENIMIENTO", None)
    expectError("DISPOSITIVO_NO_DISPONIBLE", measurements.addSamples, db, team.operator, started.idMedicion, samples())
    assert measurements.cancelMeasurement(db, team.operator, started.idMedicion).estadoMedicion == "CANCELADA"


def test_el_dispositivo_del_propietario_se_usa_y_el_de_otro_operador_no(db, mails, team):
    patient, device = institutionalSetup(db, team)
    other = addOperator(db, team)
    # Custodia del propietario (el alta por defecto): el operador puede medir con el dispositivo.
    assert reload(db, Device, device.idDispositivo).idInstitucionUsuarioResponsable == relationOf(db, team, team.owner).idInstitucionUsuario
    started = start(db, team, patient, device)
    assert started.estadoMedicion == "PENDIENTE" and measurements.cancelMeasurement(db, team.operator, started.idMedicion)
    # A cargo de otro operador (dato previo): no se usa; a cargo del propio, sí.
    holdBy(db, device.idDispositivo, other.idInstitucionUsuario)
    expectError("DISPOSITIVO_NO_DISPONIBLE", start, db, team, patient, device)
    holdBy(db, device.idDispositivo, relationOf(db, team, team.operator).idInstitucionUsuario)
    assert start(db, team, patient, device).estadoMedicion == "PENDIENTE"


def test_el_firmware_de_una_medicion_no_cambia_si_se_actualiza_el_dispositivo(db, mails, team, admin):
    patient, device = institutionalSetup(db, team)
    started = start(db, team, patient, device)
    assert started.versionFirmwareAlMomento == "1.0.0" and started.modeloSensorAlMomento == "MAX30102"
    measurements.addSamples(db, team.operator, started.idMedicion, samples())
    measurements.finishMeasurement(db, team.operator, started.idMedicion, MeasurementFinish())
    devices.editDevice(db, globalScope(db, admin), device.idDispositivo,
                       DeviceEditRequest(versionFirmware="1.1.0", modeloSensor="MAX30100"))
    again = measurements.getMeasurement(db, team.operator, started.idMedicion)
    assert (again.versionFirmwareAlMomento, again.modeloSensorAlMomento) == ("1.0.0", "MAX30102")  # historial intacto
    new = start(db, team, patient, device)
    assert (new.versionFirmwareAlMomento, new.modeloSensorAlMomento) == ("1.1.0", "MAX30100")


# --- Asignación ---------------------------------------------------------------------------------------------


def test_asignar_a_una_institucion_con_responsable_valido_y_rechazar_el_de_otra(db, mails, team, north, admin):
    scope = globalScope(db, admin)
    device = devices.registerDevice(db, scope, register("GL-0001"))
    mine = relationOf(db, team, team.operator).idInstitucionUsuario
    foreign = relationOf(db, north, north.operator).idInstitucionUsuario
    expectError("RESPONSABLE_DISPOSITIVO_INVALIDO", devices.assignInstitution, db, scope, device.idDispositivo,
                DeviceAssignRequest(idInstitucion=team.id, idInstitucionUsuarioResponsable=foreign))
    assert reload(db, Device, device.idDispositivo).idInstitucionAsignada is None
    assigned = devices.assignInstitution(db, scope, device.idDispositivo,
                                         DeviceAssignRequest(idInstitucion=team.id, idInstitucionUsuarioResponsable=mine))
    assert assigned.idInstitucionAsignada == team.id and assigned.nombreInstitucion == "Hospital X"
    assert assigned.responsable.idInstitucionUsuario == mine and assigned.fechaAsignacionInstitucional >= assigned.fechaRegistro
    # Cambiar el responsable ya no es de la institución (ni propietario ni moderador); la plataforma sí lo hace.
    other = addOperator(db, team)
    owner = instScope(db, team.owner, team.id)
    expectError("PERMISO_INSUFICIENTE", devices.changeResponsible, db, owner, device.idDispositivo, other.idInstitucionUsuario)
    assert reload(db, Device, device.idDispositivo).idInstitucionUsuarioResponsable == mine
    assert devices.changeResponsible(db, scope, device.idDispositivo, other.idInstitucionUsuario).responsable.idInstitucionUsuario == other.idInstitucionUsuario
    expectError("RESPONSABLE_DISPOSITIVO_INVALIDO", devices.changeResponsible, db, scope, device.idDispositivo, foreign)
    expectError("RESPONSABLE_DISPOSITIVO_INVALIDO", devices.changeResponsible, db, scope, device.idDispositivo, uuid.uuid4())
    assert devices.changeResponsible(db, scope, device.idDispositivo, None).responsable is None
    expectError("PERMISO_INSUFICIENTE", devices.assignInstitution, db, owner, device.idDispositivo, DeviceAssignRequest(idInstitucion=team.id))


def test_no_se_asigna_a_una_institucion_inexistente_cerrada_ni_a_un_integrante_dado_de_baja(db, mails, team, admin):
    scope = globalScope(db, admin)
    device = devices.registerDevice(db, scope, register("GL-0001"))
    expectError("INSTITUCION_NO_ENCONTRADA", devices.assignInstitution, db, scope, device.idDispositivo,
                DeviceAssignRequest(idInstitucion=uuid.uuid4()))
    leaving = relationOf(db, team, team.operator).idInstitucionUsuario
    institutions.revokeMember(db, team.moderator, team.id, "OPERADOR", leaving)
    expectError("RESPONSABLE_DISPOSITIVO_INVALIDO", devices.assignInstitution, db, scope, device.idDispositivo,
                DeviceAssignRequest(idInstitucion=team.id, idInstitucionUsuarioResponsable=leaving))


def test_reasignar_a_otra_institucion_conserva_el_historial_y_no_expone_lo_medido_antes(db, mails, team, north, admin):
    patient, device = institutionalSetup(db, team)
    started = start(db, team, patient, device)
    measurements.addSamples(db, team.operator, started.idMedicion, samples())
    measurements.finishMeasurement(db, team.operator, started.idMedicion, MeasurementFinish())
    adminScope = globalScope(db, admin)
    devices.assignInstitution(db, adminScope, device.idDispositivo, DeviceAssignRequest(idInstitucion=north.id))
    moved = reload(db, Device, device.idDispositivo)
    assert moved.idInstitucionAsignada == north.id and moved.idInstitucionUsuarioResponsable is None
    # La medición anterior sigue apuntando al dispositivo y a su contexto original.
    assert reload(db, Measurement, started.idMedicion).idDispositivo == device.idDispositivo
    assert measurements.getMeasurement(db, team.operator, started.idMedicion).dispositivo.codigoDispositivo == "GL-0001"
    # La institución nueva no ve las mediciones previas; la anterior ya no ve el dispositivo.
    assert devices.listMeasurements(db, instScope(db, north.owner, north.id), device.idDispositivo).total == 0
    expectError("DISPOSITIVO_NO_ENCONTRADO", devices.getDevice, db, instScope(db, team.owner, team.id), device.idDispositivo)
    expectError("MEDICION_NO_ENCONTRADA", measurements.getMeasurement, db, north.operator, started.idMedicion)
    global_ = devices.listMeasurements(db, adminScope, device.idDispositivo)
    assert global_.total == 1 and global_.items[0].nombreInstitucion == "Hospital X"
    assert set(global_.items[0].model_dump()) == {"idMedicion", "fechaHoraInicio", "modoMedicion", "estadoMedicion",
                                                  "versionFirmwareAlMomento", "modeloSensorAlMomento", "nombreInstitucion"}
    # Auditoría: la institución anterior ve la desvinculación; la nueva, la asignación.
    teamActions = {i.accion for i in auditQuery.listInstitution(db, team.owner, team.id, modulo="DISPOSITIVOS", tamanioPagina=100).items}
    northActions = {i.accion for i in auditQuery.listInstitution(db, north.owner, north.id, modulo="DISPOSITIVOS", tamanioPagina=100).items}
    assert "DESVINCULAR_DISPOSITIVO" in teamActions and "ASIGNAR_DISPOSITIVO" in northActions


def test_reasignado_el_dispositivo_la_nueva_institucion_no_ve_quien_lo_registro_ni_lo_medido_antes(db, mails, team, north, admin):
    patient, device = institutionalSetup(db, team)
    started = start(db, team, patient, device)
    measurements.addSamples(db, team.operator, started.idMedicion, samples())
    measurements.finishMeasurement(db, team.operator, started.idMedicion, MeasurementFinish())
    before = devices.getDevice(db, instScope(db, team.owner, team.id), device.idDispositivo)
    assert before.medicionesRegistradas == 1 and before.registro is not None  # la institución de origen sí ve lo suyo
    devices.assignInstitution(db, globalScope(db, admin), device.idDispositivo, DeviceAssignRequest(idInstitucion=north.id))
    after = devices.getDevice(db, instScope(db, north.owner, north.id), device.idDispositivo)
    assert after.registro is None, "quién registró el dispositivo en la institución anterior no se informa a la nueva"
    assert after.medicionesRegistradas == 0, "coincide con listMeasurements: lo medido en la anterior no se cuenta"
    assert devices.listMeasurements(db, instScope(db, north.owner, north.id), device.idDispositivo).total == 0
    # La plataforma conserva la visión completa.
    assert devices.getDevice(db, globalScope(db, admin), device.idDispositivo).medicionesRegistradas == 1


def test_las_mediciones_del_dispositivo_de_una_institucion_solo_incluyen_sus_pacientes(db, mails, team, north, admin):
    patient, device = institutionalSetup(db, team)
    started = start(db, team, patient, device)
    page = devices.listMeasurements(db, instScope(db, team.moderator, team.id), device.idDispositivo)
    assert page.total == 1 and page.items[0].idMedicion == started.idMedicion and page.items[0].nombreInstitucion is None
    expectError("PERMISO_INSUFICIENTE", devices.listMeasurements, db, instScope(db, team.operator, team.id), device.idDispositivo)
    assert devices.getDevice(db, instScope(db, team.owner, team.id), device.idDispositivo).medicionesRegistradas == 1


# --- Desvincular y descomisionar ----------------------------------------------------------------------------


def test_desvincular_es_de_la_plataforma_y_conserva_el_dispositivo_y_las_mediciones(db, mails, team, admin):
    patient, device = institutionalSetup(db, team)
    started = start(db, team, patient, device)
    expectError("PERMISO_INSUFICIENTE", devices.unassign, db, instScope(db, team.owner, team.id), device.idDispositivo)
    expectError("DISPOSITIVO_EN_USO", devices.unassign, db, globalScope(db, admin), device.idDispositivo)
    measurements.cancelMeasurement(db, team.operator, started.idMedicion)
    devices.unassign(db, globalScope(db, admin), device.idDispositivo)
    stored = reload(db, Device, device.idDispositivo)
    assert (stored.idInstitucionAsignada, stored.idInstitucionUsuarioResponsable, stored.fechaAsignacionInstitucional) == (None, None, None)
    assert stored.estado == "OPERATIVO" and count(db) == 1 and count(db, Measurement) == 1
    assert reload(db, Measurement, started.idMedicion).idDispositivo == device.idDispositivo
    expectError("DISPOSITIVO_NO_ENCONTRADO", devices.getDevice, db, instScope(db, team.owner, team.id), device.idDispositivo)
    expectError("DISPOSITIVO_SIN_INSTITUCION", devices.unassign, db, globalScope(db, admin), device.idDispositivo)


def retire(db, team):
    """Un dispositivo institucional con una medición terminada, descomisionado por el propietario."""
    patient, device = institutionalSetup(db, team)
    started = start(db, team, patient, device)
    measurements.addSamples(db, team.operator, started.idMedicion, signalSamples(70, 97))
    measurements.finishMeasurement(db, team.operator, started.idMedicion, MeasurementFinish())
    result = devices.decommission(db, instScope(db, team.owner, team.id), device.idDispositivo)
    return patient, device, started, result


def test_descomisionar_conserva_la_institucion_el_responsable_y_las_mediciones(db, mails, team):
    patient, device = institutionalSetup(db, team)
    owner = instScope(db, team.owner, team.id)
    started = start(db, team, patient, device)
    expectError("DISPOSITIVO_EN_USO", devices.decommission, db, owner, device.idDispositivo)  # con una medición en curso, no
    assert reload(db, Device, device.idDispositivo).estado == "OPERATIVO"
    measurements.addSamples(db, team.operator, started.idMedicion, signalSamples(70, 97))
    measurements.finishMeasurement(db, team.operator, started.idMedicion, MeasurementFinish())
    ownerRelation = relationOf(db, team, team.owner).idInstitucionUsuario
    result = devices.decommission(db, owner, device.idDispositivo)
    assert result.estado == "BAJA" and result.idInstitucionAsignada == team.id
    assert result.responsable.idInstitucionUsuario == ownerRelation and not result.disponibleParaMedir
    stored = reload(db, Device, device.idDispositivo)
    assert (stored.estado, stored.idInstitucionAsignada, stored.idInstitucionUsuarioResponsable) == ("BAJA", team.id, ownerRelation)
    assert stored.fechaAsignacionInstitucional is not None and stored.codigoDispositivo == "GL-0001"
    assert count(db) == 1 and count(db, Measurement) == 1  # nada se borró
    assert measurements.getMeasurement(db, team.operator, started.idMedicion).spo2 is not None
    # Una sola operación, sin desvinculaciones intermedias: un único evento, en la auditoría de SU institución.
    page = auditQuery.listInstitution(db, team.owner, team.id, modulo="DISPOSITIVOS", tamanioPagina=100)
    actions = [i.accion for i in page.items]
    assert actions.count("DESCOMISIONAR_DISPOSITIVO") == 1 and "DESVINCULAR_DISPOSITIVO" not in actions
    retired = next(i for i in page.items if i.accion == "DESCOMISIONAR_DISPOSITIVO")
    assert retired.idInstitucion == team.id and retired.critica


def test_el_descomisionado_sigue_en_el_inventario_de_su_institucion_y_cuenta_como_descomisionado(db, mails, team, north):
    patient, device, started, _ = retire(db, team)
    other = devices.registerDevice(db, instScope(db, team.owner, team.id), register("GL-0002", "MAX30100"))
    for actor in (team.owner, team.moderator):
        scope = instScope(db, actor, team.id)
        page = devices.listDevices(db, scope)
        by_code = {i.codigoDispositivo: i for i in page.items}
        assert set(by_code) == {"GL-0001", "GL-0002"} and by_code["GL-0001"].estado == "BAJA"
        assert by_code["GL-0001"].responsable is not None
        assert [i.codigoDispositivo for i in devices.listDevices(db, scope, estado="BAJA").items] == ["GL-0001"]
        counts = devices.summary(db, scope)
        assert (counts.total, counts.operativos, counts.enMantenimiento, counts.fueraDeServicio, counts.descomisionados) == (2, 1, 0, 0, 1)
    # Sin acciones: el detalle solo permite consultar, también las mediciones anteriores (según permisos).
    detail = devices.getDevice(db, instScope(db, team.owner, team.id), device.idDispositivo)
    assert detail.estado == "BAJA" and detail.medicionesRegistradas == 1
    assert not any(value for key, value in detail.permisos.model_dump().items() if key != "puedeVerMediciones")
    history = devices.listMeasurements(db, instScope(db, team.owner, team.id), device.idDispositivo)
    assert history.total == 1 and history.items[0].idMedicion == started.idMedicion
    # Otra institución no lo ve ni lo cuenta.
    northScope = instScope(db, north.owner, north.id)
    assert devices.listDevices(db, northScope).total == 0
    counts = devices.summary(db, northScope)
    assert (counts.total, counts.descomisionados) == (0, 0)
    expectError("DISPOSITIVO_NO_ENCONTRADO", devices.getDevice, db, northScope, device.idDispositivo)
    # El operador solo ve dispositivos operativos: el descomisionado no existe para él.
    operatorScope = instScope(db, team.operator, team.id)
    assert [i.codigoDispositivo for i in devices.listDevices(db, operatorScope).items] == ["GL-0002"]
    expectError("DISPOSITIVO_NO_ENCONTRADO", devices.getDevice, db, operatorScope, device.idDispositivo)
    assert other.idDispositivo


def test_el_descomisionado_no_admite_cambios_ni_reactivacion(db, mails, team, admin):
    _, device, _, _ = retire(db, team)
    id_ = device.idDispositivo
    owner, moderator, platform = instScope(db, team.owner, team.id), instScope(db, team.moderator, team.id), globalScope(db, admin)
    mine = relationOf(db, team, team.operator).idInstitucionUsuario
    for state in ("OPERATIVO", "EN_MANTENIMIENTO", "FUERA_DE_SERVICIO"):
        expectError("DISPOSITIVO_DESCOMISIONADO", devices.changeState, db, owner, id_, state, None)
        expectError("DISPOSITIVO_DESCOMISIONADO", devices.changeState, db, moderator, id_, state, None)
        expectError("DISPOSITIVO_DESCOMISIONADO", devices.changeState, db, platform, id_, state, None)
    expectError("DISPOSITIVO_DESCOMISIONADO", devices.decommission, db, owner, id_)
    expectError("DISPOSITIVO_DESCOMISIONADO", devices.changeResponsible, db, platform, id_, mine)
    expectError("DISPOSITIVO_DESCOMISIONADO", devices.changeResponsible, db, platform, id_, None)
    expectError("DISPOSITIVO_DESCOMISIONADO", devices.assignInstitution, db, platform, id_, DeviceAssignRequest(idInstitucion=team.id))
    expectError("DISPOSITIVO_DESCOMISIONADO", devices.unassign, db, platform, id_)
    expectError("DISPOSITIVO_DESCOMISIONADO", devices.editDevice, db, platform, id_, DeviceEditRequest(nombre="x"))
    with pytest.raises(ValidationError):
        DeviceStateRequest(estado="BAJA")  # tampoco se impone por la API de estados
    stored = reload(db, Device, id_)
    assert (stored.estado, stored.idInstitucionAsignada) == ("BAJA", team.id)
    assert stored.idInstitucionUsuarioResponsable == relationOf(db, team, team.owner).idInstitucionUsuario


def test_el_descomisionado_no_se_usa_para_medir_ni_se_reutiliza_su_identificador(db, mails, team, north):
    patient, device, _, _ = retire(db, team)
    expectError("DISPOSITIVO_NO_DISPONIBLE", start, db, team, patient, device)
    assert [d.idDispositivo for d in measurements.listDevices(db, team.operator, patient.idPerfilMedicion)] == []
    # La identificación durante la adquisición lo reconoce pero lo informa como no disponible, sin tocarlo.
    identified = resolve(db, team.moderator, "GL-0001", idInstitucion=team.id, versionFirmware="9.9.9")
    assert not identified.creado and not identified.disponibleParaMedir and "descomisionado" in identified.motivoNoDisponible
    assert not identified.firmwareActualizado
    stored = reload(db, Device, device.idDispositivo)
    assert (stored.estado, stored.versionFirmware) == ("BAJA", "1.0.0")
    # El identificador no se reutiliza: ni la misma institución ni otra, aunque cambie mayúsculas.
    for scope in (instScope(db, team.owner, team.id), instScope(db, north.owner, north.id)):
        expectError("DISPOSITIVO_DUPLICADO", devices.registerDevice, db, scope, register("gl-0001"))
    expectError("DISPOSITIVO_NO_DISPONIBLE", resolve, db, north.moderator, "GL-0001", idInstitucion=north.id)
    assert count(db) == 1


def test_el_responsable_de_un_descomisionado_se_conserva_aunque_su_vinculo_termine(db, mails, team):
    patient, device = institutionalSetup(db, team)
    leaving = relationOf(db, team, team.operator).idInstitucionUsuario
    holdBy(db, device.idDispositivo, leaving)
    devices.decommission(db, instScope(db, team.owner, team.id), device.idDispositivo)
    legacyRevoke(db, team.moderator, team.id, leaving)
    stored = reload(db, Device, device.idDispositivo)
    assert (stored.estado, stored.idInstitucionAsignada, stored.idInstitucionUsuarioResponsable) == ("BAJA", team.id, leaving)
    assert patient


def test_http_el_descomisionado_aparece_en_el_listado_y_rechaza_cambios(db, mails, team, north, api):
    _, device, _, _ = retire(db, team)
    base = f"/api/v1/institutions/{team.id}/devices"
    listed = api(team.owner).get(base).json()
    assert [i["estado"] for i in listed["items"]] == ["BAJA"] and listed["items"][0]["idInstitucionAsignada"] == str(team.id)
    assert api(team.owner).get(f"{base}/summary").json()["descomisionados"] == 1
    assert api(team.owner).post(f"{base}/{device.idDispositivo}/state", json={"estado": "OPERATIVO"}).status_code == 409
    assert api(team.owner).post(f"{base}/{device.idDispositivo}/decommission").status_code == 409
    assert api(north.owner).get(f"/api/v1/institutions/{north.id}/devices").json()["total"] == 0
    assert api(north.owner).get(f"/api/v1/institutions/{north.id}/devices/summary").json()["descomisionados"] == 0
    assert api(north.owner).post(f"/api/v1/institutions/{north.id}/devices/{device.idDispositivo}/state", json={"estado": "OPERATIVO"}).status_code == 404


def test_un_dispositivo_sin_asignar_tambien_se_descomisiona_y_no_vuelve(db, mails, admin):
    scope = globalScope(db, admin)
    device = devices.registerDevice(db, scope, register("GL-0001"))
    retired = devices.decommission(db, scope, device.idDispositivo)
    assert retired.estado == "BAJA" and not retired.disponibleParaMedir
    assert not any([retired.permisos.puedeEditar, retired.permisos.puedeCambiarEstado, retired.permisos.puedeDescomisionar])
    expectError("DISPOSITIVO_DESCOMISIONADO", devices.decommission, db, scope, device.idDispositivo)
    expectError("DISPOSITIVO_DESCOMISIONADO", devices.editDevice, db, scope, device.idDispositivo, DeviceEditRequest(nombre="x"))
    expectError("DISPOSITIVO_DESCOMISIONADO", devices.assignInstitution, db, scope, device.idDispositivo,
                DeviceAssignRequest(idInstitucion=uuid.uuid4()))
    assert devices.listDevices(db, scope, estado="DESCOMISIONADO").total == 1  # alias del estado BAJA
    assert devices.summary(db, scope).descomisionados == 1


# --- Identificación durante la adquisición ----------------------------------------------------------------------


def resolve(db, actor, code="GL-0001", **extra):
    return devices.resolveDevice(db, actor, DeviceResolveRequest(codigoDispositivo=code, modeloSensor=extra.pop("modeloSensor", "MAX30102"), **extra))


def test_identifica_y_reutiliza_el_dispositivo_sin_duplicarlo_al_reconectar(db, mails, team):
    first = resolve(db, team.owner, "GL-AUTO", versionFirmware="1.0.0", idInstitucion=team.id)
    assert first.creado and first.dispositivo.idInstitucionAsignada == team.id and first.disponibleParaMedir
    assert first.conexionVerificada is False  # el inventario no afirma conexión
    for _ in range(3):  # reconexiones
        again = resolve(db, team.owner, "gl-auto", versionFirmware="1.0.0", idInstitucion=team.id)
        assert not again.creado and again.dispositivo.idDispositivo == first.dispositivo.idDispositivo
    assert count(db) == 1
    # El operador también lo identifica, pero no puede crear uno nuevo.
    reused = resolve(db, team.operator, "GL-AUTO", idInstitucion=team.id)
    assert not reused.creado and reused.disponibleParaMedir
    expectError("DISPOSITIVO_NO_REGISTRADO", resolve, db, team.operator, "GL-DESCONOCIDO", idInstitucion=team.id)
    assert count(db) == 1
    assert [a.resultado for a in audits(db, "REGISTRAR_DISPOSITIVO") if a.idUsuario == team.operator.idUsuario] == ["FALLO"]


def test_el_alta_automatica_solo_con_contexto_autorizado(db, mails, team, admin):
    consumer = makeUser(db, email="persona@example.com", usuario="persona")
    expectError("DISPOSITIVO_NO_REGISTRADO", resolve, db, consumer, "GL-0001")  # una cuenta individual no registra
    assert count(db) == 0
    created = resolve(db, admin, "GL-GLOBAL")  # la plataforma registra en el inventario global
    assert created.creado and created.dispositivo.idInstitucionAsignada is None
    # Un dispositivo sin asignar lo puede usar una cuenta individual o una institución.
    assert resolve(db, consumer, "GL-GLOBAL").disponibleParaMedir
    assert resolve(db, team.moderator, "GL-GLOBAL", idInstitucion=team.id).disponibleParaMedir
    assert count(db) == 1


def test_el_alta_automatica_en_una_institucion_tambien_queda_a_cargo_del_propietario(db, mails, team):
    created = resolve(db, team.moderator, "GL-AUTO", idInstitucion=team.id)
    assert created.creado and created.dispositivo.idInstitucionAsignada == team.id
    assert reload(db, Device, created.dispositivo.idDispositivo).idInstitucionUsuarioResponsable == relationOf(
        db, team, team.owner).idInstitucionUsuario
    assert created.disponibleParaMedir  # la custodia del propietario no excluye a los demás


def test_el_dispositivo_de_otra_institucion_no_se_identifica_ni_se_revela(db, mails, team, north):
    resolve(db, north.owner, "GL-NORTE", idInstitucion=north.id)
    expectError("DISPOSITIVO_NO_DISPONIBLE", resolve, db, team.owner, "GL-NORTE", idInstitucion=team.id)
    expectError("DISPOSITIVO_NO_DISPONIBLE", resolve, db, makeUser(db, email="p@example.com", usuario="p"), "GL-NORTE")
    expectError("INSTITUCION_NO_ENCONTRADA", resolve, db, team.owner, "GL-0001", idInstitucion=north.id)
    assert count(db) == 1


def test_la_identificacion_actualiza_el_firmware_y_rechaza_un_sensor_distinto(db, mails, team):
    first = resolve(db, team.owner, "GL-0001", versionFirmware="1.0.0", idInstitucion=team.id)
    assert reload(db, Device, first.dispositivo.idDispositivo).versionFirmware == "1.0.0"
    updated = resolve(db, team.owner, "GL-0001", versionFirmware="1.1.0", idInstitucion=team.id)
    assert updated.firmwareActualizado and updated.dispositivo.versionFirmware == "1.1.0"
    assert not resolve(db, team.owner, "GL-0001", versionFirmware="1.1.0", idInstitucion=team.id).firmwareActualizado
    expectError("DISPOSITIVO_INCONSISTENTE", resolve, db, team.owner, "GL-0001", modeloSensor="MAX30100", idInstitucion=team.id)
    assert reload(db, Device, first.dispositivo.idDispositivo).modeloSensor == "MAX30102"


def test_identificar_un_dispositivo_no_operativo_informa_el_motivo_sin_habilitarlo(db, mails, team):
    first = resolve(db, team.owner, "GL-0001", idInstitucion=team.id)
    devices.changeState(db, instScope(db, team.owner, team.id), first.dispositivo.idDispositivo, "EN_MANTENIMIENTO", None)
    result = resolve(db, team.owner, "GL-0001", idInstitucion=team.id)
    assert not result.disponibleParaMedir and "operativo" in result.motivoNoDisponible
    assert result.dispositivo.estado == "EN_MANTENIMIENTO"


def test_la_identificacion_simultanea_no_duplica_el_registro(engine, db, mails, team):
    makeSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    barrier = threading.Barrier(3)
    failures = []

    def run():
        session = makeSession()
        try:
            actor = session.get(User, team.owner.idUsuario)
            barrier.wait()
            devices.resolveDevice(session, actor, DeviceResolveRequest(codigoDispositivo="GL-CONCURRENTE", modeloSensor="MAX30102", idInstitucion=team.id))
        except Exception as error:  # pragma: no cover - diagnóstico
            failures.append(error)
        finally:
            session.close()

    threads = [threading.Thread(target=run) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert failures == [] and count(db) == 1


# --- Indicadores, filtros y auditoría --------------------------------------------------------------------------


def test_indicadores_filtros_y_paginacion_reales(db, mails, team, north, admin):
    scope = globalScope(db, admin)
    codes = [("GL-1", "MAX30100", "OPERATIVO"), ("GL-2", "MAX30102", "EN_MANTENIMIENTO"), ("GL-3", "MAX30102", "FUERA_DE_SERVICIO"),
             ("GL-4", "MAX30102", "OPERATIVO"), ("GL-5", "MAX30100", "OPERATIVO")]
    for code, sensor, state in codes:
        devices.registerDevice(db, scope, register(code, sensor, estado=state))
    last = devices.registerDevice(db, scope, register("GL-6"))
    devices.assignInstitution(db, scope, last.idDispositivo, DeviceAssignRequest(idInstitucion=team.id))
    devices.decommission(db, scope, devices.registerDevice(db, scope, register("GL-7")).idDispositivo)
    summary = devices.summary(db, scope)
    assert (summary.total, summary.operativos, summary.enMantenimiento, summary.fueraDeServicio, summary.descomisionados) == (7, 4, 1, 1, 1)
    assert (summary.asignados, summary.sinAsignar, summary.conectividadDisponible) == (1, 6, False)
    assert devices.listDevices(db, scope, estado="OPERATIVO").total == 4
    assert devices.listDevices(db, scope, asignado=True).total == 1 and devices.listDevices(db, scope, asignado=False).total == 6
    assert devices.listDevices(db, scope, idInstitucion=team.id).items[0].codigoDispositivo == "GL-6"
    assert [i.codigoDispositivo for i in devices.listDevices(db, scope, busqueda="gl-3").items] == ["GL-3"]
    assert devices.listDevices(db, scope, busqueda="%").total == 0  # el comodín del usuario no es un patrón
    page = devices.listDevices(db, scope, tamanioPagina=3, pagina=3)
    assert len(page.items) == 1 and page.total == 7
    expectError("DATOS_INVALIDOS", devices.listDevices, db, scope, estado="ROTO")
    inst = instScope(db, team.owner, team.id)
    assert devices.summary(db, inst).total == 1 and devices.summary(db, instScope(db, north.owner, north.id)).total == 0


def test_las_operaciones_administrativas_quedan_auditadas_por_institucion(db, mails, team, north, admin):
    owner = instScope(db, team.owner, team.id)
    device = devices.registerDevice(db, owner, register("GL-0001"))
    devices.editDevice(db, globalScope(db, admin), device.idDispositivo, DeviceEditRequest(versionFirmware="1.1.0"))
    devices.changeState(db, owner, device.idDispositivo, "EN_MANTENIMIENTO", "revisión")
    devices.changeResponsible(db, globalScope(db, admin), device.idDispositivo, relationOf(db, team, team.operator).idInstitucionUsuario)
    devices.changeState(db, owner, device.idDispositivo, "OPERATIVO", None)
    devices.decommission(db, owner, device.idDispositivo)
    page = auditQuery.listInstitution(db, team.owner, team.id, modulo="DISPOSITIVOS", tamanioPagina=100)
    actions = [i.accion for i in page.items]
    for expected in ("REGISTRAR_DISPOSITIVO", "MODIFICAR_DISPOSITIVO", "CAMBIAR_ESTADO_DISPOSITIVO", "CAMBIAR_RESPONSABLE_DISPOSITIVO",
                     "DESCOMISIONAR_DISPOSITIVO"):
        assert expected in actions, expected
    assert "DESVINCULAR_DISPOSITIVO" not in actions  # descomisionar ya no desvincula
    assert actions.count("CAMBIAR_ESTADO_DISPOSITIVO") == 2
    assert {i.idInstitucion for i in page.items} == {team.id}
    assert next(i for i in page.items if i.accion == "DESCOMISIONAR_DISPOSITIVO").critica
    # Moderador y operador generan eventos pero no consultan la auditoría; Clínica Norte no ve nada de esto.
    devices.changeState(db, instScope(db, team.moderator, team.id), devices.registerDevice(
        db, instScope(db, team.moderator, team.id), register("GL-0002")).idDispositivo, "FUERA_DE_SERVICIO", None)
    moderatorEvents = [a for a in audits(db, "CAMBIAR_ESTADO_DISPOSITIVO") if a.idUsuario == team.moderator.idUsuario]
    assert moderatorEvents and moderatorEvents[0].idInstitucion == team.id
    expectError("PERMISO_INSUFICIENTE", auditQuery.listInstitution, db, team.moderator, team.id)
    assert auditQuery.listInstitution(db, north.owner, north.id, modulo="DISPOSITIVOS").total == 0
    # El administrador ve todo desde la auditoría general.
    assert auditQuery.listGlobal(db, admin, modulo="DISPOSITIVOS", tamanioPagina=100).total >= len(actions)
    stored = [a.datosNuevos or "" for a in audits(db, "MODIFICAR_DISPOSITIVO")]
    assert all("password" not in blob for blob in stored)


def test_el_administrador_elige_institucion_y_responsable_entre_opciones_reales(db, mails, team, north, admin, platformModerator, api):
    scope = globalScope(db, admin)
    options = devices.institutionOptions(db, scope)
    assert {o.nombre for o in options} == {"Hospital X", "Clínica Norte"}
    assert [o.nombre for o in devices.institutionOptions(db, scope, "norte")] == ["Clínica Norte"]
    members = devices.responsiblesOf(db, scope, team.id)
    assert {m.idInstitucionUsuario for m in members} == {relationOf(db, team, u).idInstitucionUsuario
                                                         for u in (team.owner, team.moderator, team.operator)}
    expectError("INSTITUCION_NO_ENCONTRADA", devices.responsiblesOf, db, scope, uuid.uuid4())
    for other in (globalScope(db, platformModerator), instScope(db, team.owner, team.id)):
        expectError("PERMISO_INSUFICIENTE", devices.institutionOptions, db, other)
        expectError("PERMISO_INSUFICIENTE", devices.responsiblesOf, db, other, team.id)
    assert api(admin).get("/api/v1/devices/institutions").status_code == 200
    assert api(team.owner).get("/api/v1/devices/institutions").status_code == 403
