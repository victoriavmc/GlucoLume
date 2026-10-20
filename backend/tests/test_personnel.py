# Módulo Personal: listado unificado (una fila por persona), indicadores, filtros combinables, perfil con fechas diferenciadas e
# historial administrativo reconstruido de la auditoría y de las fechas del vínculo. Permisos y aislamiento por institución.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_personnel.py -v

import json
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.exceptions import AuthError
from app.models.audit import Audit
from app.models.institutionUser import InstitutionUser
from app.services import institution as institutions
from app.services import personnel
from tests.test_account_deletion import db, engine, mails, makeUser, reload  # noqa: F401 - fixtures
from tests.test_audit import admin, api  # noqa: F401 - fixtures
from tests.test_audit_names import anonymize, named
from tests.test_institution_patients import addOperator
from tests.test_institutions import expectError, freshLookupLimiter, institutional, relationOf, team  # noqa: F401


def people(page):
    return {p.nombreCompleto: p for p in page.items}


def listing(db, team, actor=None, **filters):
    return personnel.listPersonnel(db, actor or team.owner, team.id, **filters)


def test_todos_muestra_una_fila_por_persona_con_propietario_moderador_y_operador(db, mails, team):
    page = listing(db, team)
    assert page.total == 3 and len(page.items) == 3
    assert [p.rolInstitucion for p in page.items] == ["PROPIETARIO", "MODERADOR", "OPERADOR"]
    assert all(p.estadoRelacion == "ACTIVO" and p.periodos == 1 and p.fechaIncorporacion for p in page.items)
    assert all(p.correoElectronico for p in page.items)  # lo ve quien consulta el equipo


def test_los_indicadores_salen_de_los_datos_reales_y_no_cuentan_invitaciones_como_personal(db, mails, team):
    extra = institutional(db, "pendiente@example.com", "pendiente")
    institutions.invite(db, team.moderator, team.id, "OPERADOR", extra.correoElectronico)
    summary = listing(db, team).resumen
    assert (summary.totalActivos, summary.moderadoresActivos, summary.operadoresActivos, summary.propietariosActivos) == (3, 1, 1, 1)
    assert (summary.invitacionesPendientes, summary.bajas) == (1, 0)
    # La invitación pendiente aparece en la lista, pero no suma como activa.
    assert listing(db, team).total == 4 and listing(db, team, estado="PENDIENTE").total == 1
    institutions.revokeMember(db, team.moderator, team.id, "OPERADOR", relationOf(db, team, team.operator).idInstitucionUsuario)
    summary = listing(db, team).resumen
    assert (summary.totalActivos, summary.operadoresActivos, summary.bajas) == (2, 0, 1)
    # Los indicadores no dependen de los filtros.
    assert listing(db, team, rol="MODERADOR").resumen == summary


def test_filtros_por_rol_y_por_estado_incluida_la_baja(db, mails, team):
    assert [p.rolInstitucion for p in listing(db, team, rol="MODERADOR").items] == ["MODERADOR"]
    assert [p.rolInstitucion for p in listing(db, team, rol="OPERADOR").items] == ["OPERADOR"]
    assert [p.rolInstitucion for p in listing(db, team, rol="PROPIETARIO").items] == ["PROPIETARIO"]
    operator = relationOf(db, team, team.operator).idInstitucionUsuario
    institutions.revokeMember(db, team.moderator, team.id, "OPERADOR", operator)
    baja = listing(db, team, estado="BAJA")
    assert [p.idInstitucionUsuario for p in baja.items] == [operator] and baja.items[0].fechaBaja is not None
    assert listing(db, team, estado="ACTIVO").total == 2
    assert listing(db, team, rol="OPERADOR", estado="BAJA").total == 1 and listing(db, team, rol="MODERADOR", estado="BAJA").total == 0
    expectError("DATOS_INVALIDOS", personnel.listPersonnel, db, team.owner, team.id, rol="ADMIN")
    expectError("DATOS_INVALIDOS", personnel.listPersonnel, db, team.owner, team.id, estado="ELIMINADO")


def test_la_busqueda_combina_nombre_apellido_correo_legajo_y_matricula_sin_distinguir_tildes(db, mails, team):
    named(db, team.operator, "Joaquín", "Pérez")
    relation = db.get(InstitutionUser, relationOf(db, team, team.operator).idInstitucionUsuario)
    relation.legajoInstitucional, relation.matriculaProfesional = "L-4521", "MP-90210"
    db.commit()
    for term in ("joaquin", "PEREZ", "perez", "L-4521", "mp-90210", team.operator.correoElectronico.split("@")[0]):
        found = listing(db, team, busqueda=term)
        assert team.operator.correoElectronico in {p.correoElectronico for p in found.items}, term
    assert listing(db, team, busqueda="sin coincidencias xyz").total == 0
    # Combinada con rol y estado.
    assert listing(db, team, busqueda="L-4521", rol="OPERADOR", estado="ACTIVO").total == 1
    assert listing(db, team, busqueda="L-4521", rol="MODERADOR").total == 0


def test_una_persona_que_cambia_de_rol_no_se_duplica_y_conserva_sus_roles_anteriores(db, mails, team):
    operator = relationOf(db, team, team.operator)
    old = operator.idInstitucionUsuario
    institutions.revokeMember(db, team.moderator, team.id, "OPERADOR", old)
    invitation = institutions.invite(db, team.owner, team.id, "MODERADOR", team.operator.correoElectronico)
    institutions.respondInvitation(db, team.operator, invitation.idInstitucionUsuario, accept=True)
    page = listing(db, team)
    assert page.total == 3  # sigue siendo una sola fila para esa persona
    person = next(p for p in page.items if p.correoElectronico == team.operator.correoElectronico)
    assert person.rolInstitucion == "MODERADOR" and person.rolesAnteriores == ["OPERADOR"] and person.periodos == 2
    assert person.estadoRelacion == "ACTIVO" and person.idInstitucionUsuario != old
    # Aparece al filtrar por cualquiera de los roles que tuvo, y por su estado actual.
    assert person.correoElectronico in {p.correoElectronico for p in listing(db, team, rol="OPERADOR").items}
    assert person.correoElectronico in {p.correoElectronico for p in listing(db, team, rol="MODERADOR").items}
    assert listing(db, team, estado="BAJA").total == 0  # reincorporada: su período anterior no cuenta como baja actual
    profile = personnel.getProfile(db, team.owner, team.id, old)  # abrir el período anterior muestra a la persona vigente
    assert profile.rolInstitucion == "MODERADOR" and [p.rolInstitucion for p in profile.periodosAnteriores] == ["OPERADOR"]
    assert profile.periodosAnteriores[0].estadoRelacion == "BAJA" and profile.periodosAnteriores[0].fechaBaja is not None


def test_el_perfil_distingue_invitacion_cuenta_incorporacion_modificacion_y_baja(db, mails, team):
    relation = db.get(InstitutionUser, relationOf(db, team, team.operator).idInstitucionUsuario)
    relation.fechaIncorporacion = relation.fechaInvitacion + timedelta(days=3)  # aceptó varios días después de ser invitada
    db.commit()
    first = personnel.getProfile(db, team.owner, team.id, relation.idInstitucionUsuario)
    assert first.fechaIncorporacion - first.fechaInvitacion == timedelta(days=3)
    assert first.fechaCuentaCreada is not None and first.fechaCuentaCreada != first.fechaIncorporacion
    assert first.fechaUltimaModificacion is None and first.fechaBaja is None
    assert first.nombreInstitucion == "Hospital X" and first.invitadoPor
    institutions.updateMemberAdmin(db, team.moderator, team.id, "OPERADOR", relation.idInstitucionUsuario,
                                   {"legajoInstitucional": "L-1", "matriculaProfesional": "MP-1"})
    modified = personnel.getProfile(db, team.owner, team.id, relation.idInstitucionUsuario)
    assert modified.fechaUltimaModificacion is not None and modified.legajoInstitucional == "L-1" and modified.matriculaProfesional == "MP-1"
    institutions.revokeMember(db, team.moderator, team.id, "OPERADOR", relation.idInstitucionUsuario)
    ended = personnel.getProfile(db, team.owner, team.id, relation.idInstitucionUsuario)
    assert ended.estadoRelacion == "BAJA" and ended.fechaBaja is not None and ended.fechaIncorporacion is not None
    assert not ended.acciones.puedeEditar and not ended.acciones.puedeDesvincular  # no se administra a quien ya no integra la institución


def test_el_historial_es_cronologico_con_responsable_y_sin_eventos_inventados_ni_duplicados(db, mails, team):
    relation = relationOf(db, team, team.operator)
    named(db, team.moderator, "Mario", "Moderno")
    institutions.updateMemberAdmin(db, team.moderator, team.id, "OPERADOR", relation.idInstitucionUsuario, {"legajoInstitucional": "L-9"})
    institutions.revokeMember(db, team.moderator, team.id, "OPERADOR", relation.idInstitucionUsuario)
    profile = personnel.getProfile(db, team.owner, team.id, relation.idInstitucionUsuario)
    kinds = [e.tipo for e in profile.historial]
    assert kinds == ["DESVINCULACION", "DATOS_LABORALES", "INCORPORACION", "INVITACION"]  # más reciente primero
    dates = [e.fechaHora for e in profile.historial]
    assert dates == sorted(dates, reverse=True)
    assert all(e.origen == "AUDITORIA" and e.resultado == "EXITO" and e.realizadoPor for e in profile.historial)
    by = {e.tipo: e for e in profile.historial}
    assert "legajo" in by["DATOS_LABORALES"].descripcion
    assert "incorporó como Operador/a" in by["INCORPORACION"].descripcion
    assert by["DESVINCULACION"].titulo == "Desvinculación"
    assert len(kinds) == len(set(kinds))  # cada hecho una sola vez


def test_si_falta_el_evento_de_auditoria_el_hecho_sale_de_las_fechas_del_vinculo_marcado_como_registro(db, mails, team):
    relation = relationOf(db, team, team.operator)
    for audit in db.scalars(select(Audit).where(Audit.idRegistro == relation.idInstitucionUsuario)):
        db.delete(audit)
    db.commit()
    profile = personnel.getProfile(db, team.owner, team.id, relation.idInstitucionUsuario)
    assert {e.tipo for e in profile.historial} == {"INVITACION", "INCORPORACION"}
    assert all(e.origen == "REGISTRO" for e in profile.historial)
    assert next(e for e in profile.historial if e.tipo == "INVITACION").fechaHora == relation.fechaInvitacion
    owner = personnel.getProfile(db, team.owner, team.id, relationOf(db, team, team.owner).idInstitucionUsuario)
    assert owner.historial[-1].titulo == "Alta como propietario/a" and owner.acciones == personnel.PersonnelActions()


def test_las_acciones_del_perfil_siguen_los_permisos_de_cada_rol(db, mails, team):
    operator = relationOf(db, team, team.operator).idInstitucionUsuario
    moderator = relationOf(db, team, team.moderator).idInstitucionUsuario
    asOwner = personnel.getProfile(db, team.owner, team.id, moderator).acciones
    assert asOwner.puedeEditar and asOwner.puedeDesvincular and not asOwner.puedeVerDashboard
    byModerator = personnel.getProfile(db, team.moderator, team.id, operator).acciones
    assert byModerator.puedeEditar and byModerator.puedeDesvincular and byModerator.puedeVerDashboard
    # Un moderador no administra a otros moderadores: los consulta sin acciones.
    assert not personnel.getProfile(db, team.moderator, team.id, moderator).acciones.puedeEditar
    # Invitación pendiente: se puede reenviar según el permiso de invitar ese rol.
    pending = institutional(db, "nueva@example.com", "nueva")
    invited = institutions.invite(db, team.moderator, team.id, "OPERADOR", pending.correoElectronico)
    assert personnel.getProfile(db, team.moderator, team.id, invited.idInstitucionUsuario).acciones.puedeReenviar
    assert not personnel.getProfile(db, team.owner, team.id, invited.idInstitucionUsuario).acciones.puedeReenviar  # el propietario no incorpora operadores


def test_el_operador_y_quien_no_pertenece_no_consultan_el_personal(db, mails, team):
    with pytest.raises(AuthError) as denied:
        listing(db, team, actor=team.operator)
    assert denied.value.code == "PERMISO_INSUFICIENTE"
    stranger = institutional(db, "ajeno@example.com", "ajeno")
    with pytest.raises(AuthError) as hidden:
        listing(db, team, actor=stranger)
    assert hidden.value.code == "INSTITUCION_NO_ENCONTRADA"
    other = relationOf(db, team, team.operator).idInstitucionUsuario
    with pytest.raises(AuthError):
        personnel.getProfile(db, team.operator, team.id, other)
    expectError("MIEMBRO_NO_ENCONTRADO", personnel.getProfile, db, team.owner, team.id, uuid.uuid4())


def test_un_vinculo_de_otra_institucion_no_se_abre_desde_esta(db, mails, team):
    foreign = institutional(db, "dueno-norte@example.com", "duenonorte")
    from tests.test_institutions import newInstitution
    north = newInstitution(db, foreign, "87654321", "Clínica Norte")
    foreignRelation = db.scalar(select(InstitutionUser).where(InstitutionUser.idInstitucion == north.idInstitucion))
    expectError("MIEMBRO_NO_ENCONTRADO", personnel.getProfile, db, team.owner, team.id, foreignRelation.idInstitucionUsuario)
    assert foreign.correoElectronico not in {p.correoElectronico for p in listing(db, team).items}


def test_una_cuenta_eliminada_conserva_la_identidad_historica_y_pierde_el_correo(db, mails, team):
    ghost = institutional(db, "fantasma@example.com", "fantasma")
    invitation = institutions.invite(db, team.moderator, team.id, "OPERADOR", ghost.correoElectronico)
    institutions.respondInvitation(db, ghost, invitation.idInstitucionUsuario, accept=True)
    anonymize(db, ghost)
    person = next(p for p in listing(db, team).items if p.idInstitucionUsuario == invitation.idInstitucionUsuario)
    assert person.correoElectronico is None  # el correo de una cuenta eliminada no se recupera
    profile = personnel.getProfile(db, team.owner, team.id, invitation.idInstitucionUsuario)
    assert profile.correoElectronico is None and profile.fechaCuentaCreada is None
    assert "fantasma" not in json.dumps(profile.model_dump(mode="json"), default=str).lower().replace("fantasma@", "")


def test_http_listado_perfil_y_permisos(db, mails, team, api):
    base = f"/api/v1/institutions/{team.id}/personnel"
    ok = api(team.moderator).get(f"{base}?rol=OPERADOR&estado=ACTIVO&busqueda=&pagina=1&tamanioPagina=5")
    assert ok.status_code == 200 and ok.json()["total"] == 1 and ok.json()["resumen"]["totalActivos"] == 3
    item = ok.json()["items"][0]
    profile = api(team.owner).get(f"{base}/{item['idInstitucionUsuario']}")
    assert profile.status_code == 200 and profile.json()["rolInstitucion"] == "OPERADOR" and profile.json()["historial"]
    assert api(team.operator).get(base).status_code == 403
    assert api(team.owner).get(f"{base}?rol=ROBOT").status_code == 422
    assert api(team.owner).get(f"{base}/{uuid.uuid4()}").status_code == 404
    stranger = institutional(db, "ajeno2@example.com", "ajeno2")
    assert api(stranger).get(base).status_code == 404
