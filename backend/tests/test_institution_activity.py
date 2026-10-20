# «Actividad reciente» de una institución: resumen curado de la auditoría (única fuente), ordenado globalmente por fecha, sin duplicados,
# filtrado por permisos y sin datos personales de pacientes.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_institution_activity.py -v

import pytest
from sqlalchemy import select

from app.core.exceptions import AuthError
from app.models.audit import Audit
from app.services import device as devices
from app.services import institutionActivity as activity
from app.services import institutionPatients as patients
from tests.test_account_deletion import db, engine, mails, makeUser, reload  # noqa: F401 - fixtures
from tests.test_audit import admin, api  # noqa: F401 - fixtures
from tests.test_devices import instScope, register
from tests.test_institution_patients import patientData
from tests.test_institutions import freshLookupLimiter, institutional, relationOf, team  # noqa: F401
from tests.test_matrices import newMatrix


def titles(page):
    return [item.titulo for item in page.items]


def seed(db, team):
    """Un poco de actividad de cada módulo, en orden: paciente, dispositivo, estado del dispositivo y matriz."""
    patients.createPatient(db, team.operator, team.id, patientData(nombre="rosa", apellido="díaz"))
    device = devices.registerDevice(db, instScope(db, team.owner, team.id), register("GL-0001"))
    devices.changeState(db, instScope(db, team.owner, team.id), device.idDispositivo, "EN_MANTENIMIENTO", None)
    newMatrix(db, team.owner, ambito="INSTITUCION", idInstitucion=team.id, nombre="Matriz de prueba")
    return device


def test_las_ultimas_actividades_de_todos_los_modulos_van_ordenadas_por_fecha_y_no_por_modulo(db, mails, team):
    seed(db, team)
    page = activity.listActivity(db, team.owner, team.id, limit=20)
    dates = [item.fechaHora for item in page.items]
    assert dates == sorted(dates, reverse=True)
    categories = [item.categoria for item in page.items]
    assert {"MATRICES", "DISPOSITIVOS", "PACIENTES", "MODERADORES", "OPERADORES", "INSTITUCION"} <= set(categories)
    assert page.items[0].categoria == "MATRICES"  # lo último que pasó, aunque no sea de auditoría de personal
    assert "Dispositivo en mantenimiento" in titles(page) and "Dispositivo registrado" in titles(page)
    assert len(activity.listActivity(db, team.owner, team.id, limit=3).items) == 3


def test_incluye_las_invitaciones_y_la_incorporacion_por_rol_y_omite_los_eventos_secundarios(db, mails, team):
    page = activity.listActivity(db, team.owner, team.id, limit=20)
    assert {"Moderador invitado", "Moderador incorporado", "Operador invitado", "Operador incorporado", "Institución creada"} <= set(titles(page))
    joined = " ".join(titles(page))
    assert "Aviso" not in joined and "cuenta" not in joined.lower()  # NOTIFICAR_CREACION y CREAR_CUENTA_INVITADA no aparecen
    created = next(i for i in page.items if i.titulo == "Institución creada")
    assert created.entidad is None and created.ruta == "administracion/datos"


def test_una_misma_operacion_registrada_dos_veces_se_muestra_una_sola_vez(db, mails, team):
    before = len(activity.listActivity(db, team.owner, team.id, limit=20).items)
    original = db.scalar(select(Audit).where(Audit.idInstitucion == team.id, Audit.accion == "INVITAR_MIEMBRO_INSTITUCION"))
    db.add(Audit(idUsuario=original.idUsuario, tipoEvento=original.tipoEvento, accion=original.accion, tablaAfectada=original.tablaAfectada,
                 idRegistro=original.idRegistro, resultado="EXITO", idInstitucion=team.id, modulo=original.modulo,
                 datosNuevos=original.datosNuevos, fechaHora=original.fechaHora))
    db.commit()
    assert len(activity.listActivity(db, team.owner, team.id, limit=20).items) == before


def test_cada_actividad_trae_responsable_entidad_ruta_y_criticidad_sin_datos_de_pacientes(db, mails, team):
    device = seed(db, team)
    devices.decommission(db, instScope(db, team.owner, team.id), device.idDispositivo)
    page = activity.listActivity(db, team.owner, team.id, limit=20)
    retired = next(i for i in page.items if i.titulo == "Dispositivo descomisionado")
    assert retired.entidad == "Dispositivo GL-0001" and retired.critica and retired.usuario
    assert retired.ruta == f"dispositivos/{device.idDispositivo}" and retired.idAuditoria is not None
    patient = next(i for i in page.items if i.titulo == "Paciente registrado")
    assert patient.entidad.startswith("Paciente PAC-") and "rosa" not in str(patient.model_dump()).lower()
    assert patient.ruta.startswith("pacientes/")


def test_el_moderador_ve_lo_suyo_sin_gestion_de_moderadores_ni_rechazos_ni_enlaces_a_la_auditoria(db, mails, team):
    seed(db, team)
    with pytest.raises(AuthError):
        devices.registerDevice(db, instScope(db, team.operator, team.id), register("GL-OP"))  # genera un rechazo que el moderador no ve
    page = activity.listActivity(db, team.moderator, team.id, limit=20)
    joined = " ".join(titles(page))
    assert "Dispositivo registrado" in joined and "Operador incorporado" in joined
    assert "Moderador" not in joined  # la gestión de moderadores es del propietario
    assert all(not i.rechazado and i.idAuditoria is None and i.categoria != "SEGURIDAD" for i in page.items)


def test_el_operador_ve_solo_lo_que_hizo_el_mismo(db, mails, team):
    seed(db, team)
    page = activity.listActivity(db, team.operator, team.id, limit=20)
    assert page.items and all(i.categoria in ("PACIENTES", "OPERADORES") for i in page.items)
    own = {i.usuario for i in page.items}
    assert len(own) == 1  # todas las hizo la misma persona: él
    assert "Dispositivo registrado" not in titles(page)  # lo hizo el propietario


def test_las_operaciones_rechazadas_las_ve_solo_quien_audita(db, mails, team):
    seed(db, team)
    with pytest.raises(AuthError):
        devices.registerDevice(db, instScope(db, team.operator, team.id), register("GL-OP"))  # el operador no registra: queda un rechazo
    owner = activity.listActivity(db, team.owner, team.id, limit=3)
    rejected = next(i for i in owner.items if i.rechazado)
    assert rejected.titulo.startswith("Operación rechazada") and rejected.categoria == "SEGURIDAD" and rejected.critica
    assert rejected.idAuditoria is not None and rejected.ruta == f"auditoria/{rejected.idAuditoria}"
    assert not any(i.rechazado for i in activity.listActivity(db, team.moderator, team.id, limit=20).items)
    # El operador ve su propio intento rechazado como un resultado, pero no el detalle de auditoría: no se le ofrece.
    assert not any(i.rechazado for i in activity.listActivity(db, team.operator, team.id, limit=20).items)


def test_la_actividad_de_otra_institucion_no_se_ve_y_quien_no_pertenece_recibe_404(db, mails, team):
    stranger = institutional(db, "otro-dueno@example.com", "otrodueno")
    with pytest.raises(AuthError) as error:
        activity.listActivity(db, stranger, team.id)
    assert error.value.code == "INSTITUCION_NO_ENCONTRADA"


def test_http_el_limite_se_valida_y_el_endpoint_responde_a_los_integrantes(db, mails, team, api):
    seed(db, team)
    ok = api(team.moderator).get(f"/api/v1/institutions/{team.id}/activity?limite=2")
    assert ok.status_code == 200 and len(ok.json()["items"]) == 2
    assert {"titulo", "categoria", "entidad", "usuario", "fechaHora", "resultado", "critica", "ruta"} <= set(ok.json()["items"][0])
    assert api(team.moderator).get(f"/api/v1/institutions/{team.id}/activity?limite=99").status_code == 422
    stranger = institutional(db, "ajeno@example.com", "ajeno")
    assert api(stranger).get(f"/api/v1/institutions/{team.id}/activity").status_code == 404
    default = api(team.owner).get(f"/api/v1/institutions/{team.id}/activity").json()["items"]
    assert len(default) == 5 and default[0]["fechaHora"] >= default[-1]["fechaHora"]
