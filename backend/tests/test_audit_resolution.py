# Resolución de identificadores de la auditoría: el detalle de un evento nombra la entidad afectada, a quien realizó la operación
# y a la institución, con datos reales del modelo relacional, sin confundir responsable con entidad, priorizando lo registrado en el
# evento sobre lo vigente hoy y respetando a las cuentas eliminadas. Los UUID siguen siendo la referencia técnica.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_audit_resolution.py -v

import json
import uuid

from sqlalchemy import select

from app.models.audit import Audit
from app.models.user import User
from app.services import auditQuery
from app.services import device as devices
from app.services import institution as institutions
from tests.test_account_deletion import db, engine, mails, makeUser, reload  # noqa: F401 - fixtures
from tests.test_audit import admin  # noqa: F401 - fixture
from tests.test_audit_names import anonymize, named
from tests.test_devices import instScope, register
from tests.test_institutions import freshLookupLimiter, institutional, relationOf, team  # noqa: F401
from tests.test_matrices import newMatrix


def detailOf(db, team, action, index=0, entity=None):
    """Detalle de un evento de la institución; con `entity` elige el que afectó a esa entidad (el equipo genera varios)."""
    page = auditQuery.listInstitution(db, team.owner, team.id, accion=action, tamanioPagina=100)
    assert page.items, action
    if entity is not None:
        page.items = [i for i in page.items if i.idEntidad == entity]
        assert page.items, (action, entity)
    return auditQuery.detailInstitution(db, team.owner, team.id, page.items[index].idAuditoria)


def refs(detail):
    return {r.etiqueta: r for r in detail.referencias}


def attrs(entity):
    return {a.etiqueta: a for a in entity.atributos}


def test_la_invitacion_nombra_al_integrante_su_rol_su_estado_y_su_institucion_sin_confundirlo_con_quien_invita(db, mails, team):
    named(db, team.owner, "Ana", "Dueña")  # se renombra DESPUÉS de los eventos: el detalle conserva lo que figuraba entonces
    moderatorRelation = relationOf(db, team, team.moderator).idInstitucionUsuario
    ownerRelation = relationOf(db, team, team.owner).idInstitucionUsuario
    detail = detailOf(db, team, "INVITAR_MIEMBRO_INSTITUCION", entity=moderatorRelation)
    entity = detail.entidad
    assert entity.tipo == "Integrante de la institución" and entity.id == str(moderatorRelation)
    assert entity.origen == "EVENTO" and entity.rol == "MODERADOR"
    assert detail.usuario  # los usuarios de prueba comparten nombre: el responsable y la entidad se distinguen por sus identificadores
    assert "Ana" not in detail.usuario  # nombre vigente hoy, no el del momento del evento
    assert attrs(entity)["Rol asignado"].texto == "Moderador/a" and attrs(entity)["Rol asignado"].origen == "EVENTO"
    assert attrs(entity)["Estado de la relación"].texto == "Pendiente"
    assert attrs(entity)["Pertenece a"].texto == "Hospital X"
    by = refs(detail)
    assert by["Entidad afectada"].id == str(moderatorRelation) and by["Entidad afectada"].nombre == entity.texto
    assert by["Institución (identificador interno)"].id == str(team.id) and by["Institución (identificador interno)"].nombre == "Hospital X"
    assert by["Responsable de la operación (vínculo)"].nombre == detail.usuario
    assert by["Responsable de la operación (vínculo)"].id == str(ownerRelation) and by["Responsable de la operación (vínculo)"].id != by["Entidad afectada"].id
    assert by["Identificador del evento"].id == str(detail.idAuditoria)


def test_lo_registrado_en_el_evento_manda_sobre_el_nombre_actual_y_lo_actual_se_marca(db, mails, team):
    named(db, team.moderator, "Mario", "Moderno")
    event = detailOf(db, team, "INVITAR_MIEMBRO_INSTITUCION", entity=relationOf(db, team, team.moderator).idInstitucionUsuario)
    stored = db.scalar(select(Audit).where(Audit.idAuditoria == event.idAuditoria))
    assert "personas" in json.loads(stored.detalle)  # el evento guardó el nombre de ese momento
    # Se renombra a la persona DESPUÉS del evento: el evento conserva el nombre que tenía cuando ocurrió.
    named(db, team.moderator, "Mariano", "Cambiado")
    after = auditQuery.detailInstitution(db, team.owner, team.id, event.idAuditoria)
    assert after.entidad.texto == event.entidad.texto and after.entidad.origen == "EVENTO"
    # Un evento antiguo sin referencia guardada solo puede mostrar el dato vigente, y lo dice.
    stored.detalle = None
    db.commit()
    legacy = auditQuery.detailInstitution(db, team.owner, team.id, event.idAuditoria)
    assert legacy.entidad.origen == "ACTUAL" and legacy.entidad.texto.startswith("Mariano Cambiado")
    assert refs(legacy)["Entidad afectada"].origen == "ACTUAL"


def test_una_cuenta_eliminada_se_indica_como_tal_y_no_se_recupera_su_nombre(db, mails, team):
    ghost = institutional(db, "fantasma@example.com", "fantasma")
    invitation = institutions.invite(db, team.moderator, team.id, "OPERADOR", ghost.correoElectronico)
    institutions.respondInvitation(db, ghost, invitation.idInstitucionUsuario, accept=True)
    relation = relationOf(db, team, ghost)
    relation.nombreProfesionalHistorico = relation.apellidoProfesionalHistorico = None
    db.commit()
    # El evento antiguo no guardó la referencia del integrante.
    for audit in db.scalars(select(Audit).where(Audit.idRegistro == relation.idInstitucionUsuario)):
        audit.detalle = None
    db.commit()
    anonymize(db, ghost)
    page = auditQuery.listInstitution(db, team.owner, team.id, accion="ACEPTAR_INVITACION", tamanioPagina=100)
    detail = auditQuery.detailInstitution(db, team.owner, team.id, page.items[0].idAuditoria)
    assert detail.entidad.texto == "Usuario eliminado" and not detail.entidad.disponible
    assert detail.entidad.id == str(relation.idInstitucionUsuario)  # el UUID se conserva
    assert "fantasma" not in json.dumps(detail.model_dump(), default=str)


def test_dispositivos_matrices_e_instituciones_se_nombran_con_sus_datos_reales(db, mails, team):
    device = devices.registerDevice(db, instScope(db, team.owner, team.id), register("GL-0042"))
    from app.services import audit as auditService
    auditService.registerEvent(db, "CRUD", "REGISTRAR_DISPOSITIVO", True, team.owner.idUsuario, "Dispositivo", device.idDispositivo,
                               idInstitucion=team.id)
    db.commit()
    detail = detailOf(db, team, "REGISTRAR_DISPOSITIVO")
    assert detail.entidad.tipo == "Dispositivo" and detail.entidad.texto == "Dispositivo GL-0042"
    assert refs(detail)["Entidad afectada"].id == str(device.idDispositivo)
    matrix = newMatrix(db, team.owner, ambito="INSTITUCION", idInstitucion=team.id, nombre="Matriz de prueba")
    detail = detailOf(db, team, "CREAR_MATRIZ")
    assert detail.entidad.tipo == "Matriz" and detail.entidad.texto.startswith("Matriz Matriz de prueba, versión")
    assert refs(detail)["Entidad afectada"].id == str(matrix.idMatriz)
    rule = db.scalar(select(Audit).where(Audit.tablaAfectada == "ReglaMatriz"))
    if rule is not None:  # la regla se nombra por su código y la matriz a la que pertenece
        detail = auditQuery.detailInstitution(db, team.owner, team.id, rule.idAuditoria)
        assert detail.entidad.tipo == "Regla de matriz" and "Matriz de prueba" in detail.entidad.texto
    created = detailOf(db, team, "CREAR_INSTITUCION")
    assert created.entidad.texto == "Institución Hospital X" and created.nombreInstitucion == "Hospital X"


def test_la_cuenta_afectada_se_nombra_segun_el_ambito_y_una_eliminada_no_se_recupera(db, mails, team, admin):
    account = db.get(User, team.moderator.idUsuario)
    db.add(Audit(idUsuario=team.owner.idUsuario, tipoEvento="CRUD", accion="CREAR_CUENTA_INVITADA", tablaAfectada="Usuario",
                 idRegistro=account.idUsuario, resultado="EXITO", idInstitucion=team.id, modulo="INSTITUCIONES"))
    db.commit()
    named(db, team.moderator, "Mario", "Moderno")
    scoped = detailOf(db, team, "CREAR_CUENTA_INVITADA")
    assert scoped.entidad.tipo == "Cuenta" and scoped.entidad.texto == "Cuenta de Mario Moderno"
    assert auditQuery.detailGlobal(db, admin, scoped.idAuditoria).entidad.texto == "Cuenta de Mario Moderno"
    anonymize(db, team.moderator)  # la cuenta eliminada no se recupera en la auditoría general
    glob = auditQuery.detailGlobal(db, admin, scoped.idAuditoria)
    assert glob.entidad.texto == "Cuenta eliminada"
    assert "Moderno" not in json.dumps(glob.model_dump(), default=str)


def test_la_auditoria_de_una_institucion_no_resuelve_integrantes_de_otra(db, mails, team):
    stranger = uuid.uuid4()
    db.add(Audit(idUsuario=team.owner.idUsuario, tipoEvento="CRUD", accion="MODIFICAR_MIEMBRO_INSTITUCION", tablaAfectada="InstitucionUsuario",
                 idRegistro=stranger, resultado="EXITO", idInstitucion=team.id, modulo="INSTITUCIONES",
                 datosNuevos=json.dumps({"rolInstitucion": "OPERADOR"})))
    db.commit()
    detail = auditQuery.detailInstitution(db, team.owner, team.id, db.scalar(select(Audit.idAuditoria).where(Audit.idRegistro == stranger)))
    assert detail.entidad.texto == auditQuery.UNAVAILABLE and not detail.entidad.disponible
    assert detail.entidad.id == str(stranger)
