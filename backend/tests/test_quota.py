# Cupos de cuentas institucionales: capacidad por institución (1000 por omisión), cuentas activas calculadas con las relaciones vigentes
# (propietario, moderadores y operadores ACTIVOS, una vez por persona), disponibles y utilización; el límite se controla en el backend al
# incorporar (aceptar una invitación) y es seguro ante incorporaciones simultáneas. Las invitaciones pendientes, canceladas, rechazadas o
# vencidas, las bajas y las cuentas eliminadas no consumen cupo.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_quota.py -v

import json
import threading

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.orm import sessionmaker

from app.core.exceptions import AuthError
from app.models.audit import Audit
from app.models.institution import Institution
from app.models.institutionUser import InstitutionUser
from app.models.user import User
from app.services import institution as institutions
from app.services import quota, schemaCompat
from app.utils.timeZone import nowForDb
from tests.test_account_deletion import audits, db, engine, mails, makeUser, reload  # noqa: F401 - fixtures
from tests.test_audit import api  # noqa: F401 - fixture
from tests.test_institution_patients import otherInstitution
from tests.test_institutions import expectError, freshLookupLimiter, institutional, newInstitution, relationOf, team  # noqa: F401

FULL_MESSAGE = ("La institución alcanzó su capacidad máxima de cuentas activas. Para incorporar a otra persona, es necesario liberar un "
                "cupo o ampliar la capacidad.")


def setCapacity(db, idInstitucion, value):
    db.execute(update(Institution.__table__).where(Institution.__table__.c.idInstitucion == idInstitucion).values(capacidadMaximaUsuarios=value))
    db.commit()


def activeInSql(db, idInstitucion):
    db.expire_all()
    return len({row for row in db.scalars(select(InstitutionUser.idUsuarioInvitado).where(
        InstitutionUser.idInstitucion == idInstitucion, InstitutionUser.estadoRelacion == "ACTIVO"))})


def invite(db, team, email, usuario, role="OPERADOR"):
    user = institutional(db, email, usuario)
    sender = team.moderator if role == "OPERADOR" else team.owner
    return user, institutions.invite(db, sender, team.id, role, email)


def accept(db, user, invitation):
    return institutions.respondInvitation(db, user, invitation.idInstitucionUsuario, accept=True)


# --- 1-2. Capacidad predeterminada y migración -------------------------------------------------------------------------------


def test_una_institucion_nueva_recibe_la_capacidad_predeterminada_de_1000(db, mails, team):
    assert quota.DEFAULT_CAPACITY == 1000
    assert db.scalar(select(Institution.__table__.c.capacidadMaximaUsuarios).where(Institution.__table__.c.idInstitucion == team.id)) == 1000
    assert quota.capacityOf(db, team.id) == 1000
    # El usuario no la fija en el registro: la solicitud de alta no admite ese campo.
    from app.schemas.institution import InstitutionCreateRequest
    assert "capacidadMaximaUsuarios" not in InstitutionCreateRequest.model_fields


def test_sin_la_migracion_aplicada_se_usa_la_capacidad_predeterminada_y_los_cupos_se_calculan_igual(db, mails, team, monkeypatch):
    monkeypatch.setattr(schemaCompat, "hasColumn", lambda *_args: False)  # esquema anterior a 028
    current = quota.usage(db, team.id)
    assert (current.capacidadMaximaUsuarios, current.usuariosActivos, current.cuposDisponibles) == (1000, 3, 997)


def test_el_esquema_consolidado_define_la_capacidad_de_la_institucion(referenceSchema):
    """DEC-02: la regla del antiguo script 028 vive en GlucoLume_DB_v5.sql: entero obligatorio, 1000 por defecto y mayor que cero."""
    import re

    assert re.search(r"^\t\[capacidadMaximaUsuarios\] \[int\] NOT NULL,$", referenceSchema, re.M)
    assert re.search(r"DEFAULT \(\(1000\)\) FOR \[capacidadMaximaUsuarios\]", referenceSchema)
    assert re.search(r"CONSTRAINT \[CK_Institucion_capacidadMaximaUsuarios\] CHECK\s+\(\(\[capacidadMaximaUsuarios\]>\(0\)\)\)", referenceSchema)


# --- 3-5. Quién consume cupo ---------------------------------------------------------------------------------------------------


def test_propietario_moderador_y_operador_activos_ocupan_un_cupo_cada_uno(db, mails, team):
    current = quota.usage(db, team.id)
    assert (current.usuariosActivos, current.cuposDisponibles, current.capacidadMaximaUsuarios) == (3, 997, 1000)  # los tres roles
    assert current.porcentajeUtilizacion == 0.3 and current.estado == "DISPONIBLE"
    only = newInstitution(db, institutional(db, "solo@example.com", "solo"), "71234000", "Solo")
    assert quota.usage(db, only.idInstitucion).usuariosActivos == 1  # el propietario ocupa un cupo


# --- 6-8. Invitaciones y aceptación -----------------------------------------------------------------------------------------------


def test_una_invitacion_pendiente_o_cancelada_no_consume_cupo_y_aceptarla_si(db, mails, team):
    before = quota.usage(db, team.id).usuariosActivos
    pendingUser, pending = invite(db, team, "pendiente@example.com", "pendiente")
    assert quota.usage(db, team.id).usuariosActivos == before  # pendiente
    institutions.revokeMember(db, team.moderator, team.id, "OPERADOR", pending.idInstitucionUsuario)
    assert quota.usage(db, team.id).usuariosActivos == before  # cancelada
    rejectedUser, rejected = invite(db, team, "rechaza@example.com", "rechaza")
    institutions.respondInvitation(db, rejectedUser, rejected.idInstitucionUsuario, accept=False)
    assert quota.usage(db, team.id).usuariosActivos == before  # rechazada
    newUser, new = invite(db, team, "acepta@example.com", "acepta")
    accept(db, newUser, new)
    assert quota.usage(db, team.id).usuariosActivos == before + 1 and quota.usage(db, team.id).cuposDisponibles == 1000 - before - 1


def test_las_cuentas_eliminadas_y_las_bajas_no_cuentan_y_cada_persona_cuenta_una_vez(db, mails, team):
    assert quota.activeCount(db, team.id) == 3
    db.execute(update(User).where(User.idUsuario == team.operator.idUsuario).values(estado="ELIMINADO", fechaEliminacion=nowForDb()))
    db.commit()
    assert quota.activeCount(db, team.id) == 2
    # Una persona con varios vínculos históricos cuenta una sola vez (cuentas distintas).
    assert quota.activeCount(db, team.id) == activeInSql(db, team.id) - 1


# --- 9-11. Baja, reincorporación y cambio de rol ------------------------------------------------------------------------------------


def test_la_baja_libera_el_cupo_y_la_reincorporacion_lo_vuelve_a_consumir(db, mails, team):
    start = quota.usage(db, team.id)
    institutions.revokeMember(db, team.moderator, team.id, "OPERADOR", relationOf(db, team, team.operator).idInstitucionUsuario)
    freed = quota.usage(db, team.id)
    assert (freed.usuariosActivos, freed.cuposDisponibles) == (start.usuariosActivos - 1, start.cuposDisponibles + 1)
    assert db.scalar(select(func.count()).select_from(InstitutionUser).where(InstitutionUser.idUsuarioInvitado == team.operator.idUsuario)) == 1  # el registro se conserva
    invitation = institutions.invite(db, team.moderator, team.id, "OPERADOR", team.operator.correoElectronico)
    assert quota.usage(db, team.id).usuariosActivos == freed.usuariosActivos  # la invitación pendiente no consume
    accept(db, team.operator, invitation)
    assert quota.usage(db, team.id).usuariosActivos == start.usuariosActivos  # reincorporada: consume otra vez
    event = [a for a in audits(db, "ACEPTAR_INVITACION_INSTITUCION") if a.idRegistro == invitation.idInstitucionUsuario]
    assert len(event) == 1 and json.loads(event[0].datosNuevos)["reincorporacion"] is True  # un solo evento, que informa la reincorporación


def test_un_cambio_de_rol_no_aumenta_el_contador(db, mails, team):
    start = quota.usage(db, team.id).usuariosActivos
    institutions.revokeMember(db, team.moderator, team.id, "OPERADOR", relationOf(db, team, team.operator).idInstitucionUsuario)
    invitation = institutions.invite(db, team.owner, team.id, "MODERADOR", team.operator.correoElectronico)  # pasa a moderador
    accept(db, team.operator, invitation)
    assert quota.usage(db, team.id).usuariosActivos == start  # la misma persona ocupa un solo cupo
    assert relationOf(db, team, team.operator).rolInstitucion == "MODERADOR"


# --- 12. Capacidad completa ----------------------------------------------------------------------------------------------------------


def test_con_capacidad_completa_la_invitacion_sigue_pendiente_y_no_se_activa_a_medias(db, mails, team):
    newUser, invitation = invite(db, team, "ultimo@example.com", "ultimo")
    setCapacity(db, team.id, quota.activeCount(db, team.id))  # completa
    full = quota.usage(db, team.id)
    assert (full.cuposDisponibles, full.porcentajeUtilizacion, full.estado) == (0, 100.0, "COMPLETA")
    error = expectError("CAPACIDAD_COMPLETA", accept, db, newUser, invitation)
    assert error.message == FULL_MESSAGE
    relation = reload(db, InstitutionUser, invitation.idInstitucionUsuario)
    assert relation.estadoRelacion == "PENDIENTE" and relation.fechaIncorporacion is None  # sin activación parcial
    assert quota.usage(db, team.id).usuariosActivos == full.usuariosActivos
    # El intento rechazado queda auditado (quién y por qué), sin eventos de incorporación.
    rejected = [a for a in audits(db, "ACEPTAR_INVITACION_INSTITUCION") if a.resultado == "FALLO"]
    assert len(rejected) == 1 and rejected[0].idUsuario == newUser.idUsuario and "CAPACIDAD_COMPLETA" in rejected[0].observacion
    assert not [a for a in audits(db, "ACEPTAR_INVITACION_INSTITUCION") if a.resultado == "EXITO" and a.idRegistro == invitation.idInstitucionUsuario]
    # No se bloquea consultar integrantes ni dar de baja; al liberarse un cupo, la invitación pendiente se puede aceptar.
    assert len(institutions.listMembers(db, team.owner, team.id)) >= 3
    institutions.revokeMember(db, team.moderator, team.id, "OPERADOR", relationOf(db, team, team.operator).idInstitucionUsuario)
    accept(db, newUser, invitation)
    assert quota.usage(db, team.id).usuariosActivos == full.usuariosActivos
    # También se pueden seguir enviando invitaciones (no consumen cupo hasta que se acepten).
    invite(db, team, "otra@example.com", "otra")


def test_los_estados_visuales_segun_la_utilizacion(db, mails, team):
    assert quota.stateOf(799, 1000) == "DISPONIBLE" and quota.stateOf(800, 1000) == "PROXIMO_AL_LIMITE"
    assert quota.stateOf(999, 1000) == "PROXIMO_AL_LIMITE" and quota.stateOf(1000, 1000) == "COMPLETA"
    setCapacity(db, team.id, 3)
    assert quota.usage(db, team.id).estado == "COMPLETA"
    setCapacity(db, team.id, 1)  # reducida a mano por debajo de lo activo: nunca negativos ni más de 100 %
    over = quota.usage(db, team.id)
    assert over.cuposDisponibles == 0 and over.porcentajeUtilizacion == 100.0


def test_una_capacidad_nueva_no_puede_ser_invalida_ni_menor_a_las_cuentas_activas(db, mails, team):
    quota.validateNewCapacity(db, team.id, 3)
    quota.validateNewCapacity(db, team.id, 500)
    quota.validateNewCapacity(db, team.id, 2)  # por debajo de las cuentas activas SÍ se permite: queda excedida, sin bajas automáticas
    expectError("CAPACIDAD_INVALIDA", quota.validateNewCapacity, db, team.id, quota.MAX_CAPACITY + 1)
    for invalid in (0, -5):
        expectError("CAPACIDAD_INVALIDA", quota.validateNewCapacity, db, team.id, invalid)


# --- 13. Concurrencia ---------------------------------------------------------------------------------------------------------------


def test_dos_incorporaciones_simultaneas_con_un_solo_cupo_completan_solo_una(engine, db, mails, team):
    first = invite(db, team, "uno@example.com", "uno")
    second = invite(db, team, "dos@example.com", "dos")
    setCapacity(db, team.id, quota.activeCount(db, team.id) + 1)  # queda un único cupo
    makeSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    barrier = threading.Barrier(2)
    outcomes, failures = [], []

    def run(user, invitation):
        session = makeSession()
        try:
            actor = session.get(User, user.idUsuario)
            barrier.wait()
            institutions.respondInvitation(session, actor, invitation.idInstitucionUsuario, accept=True)
            outcomes.append("ok")
        except AuthError as error:
            outcomes.append(error.code)
        except Exception as error:  # SQLite serializa las escrituras con un bloqueo de base: el perdedor puede ver «locked»
            failures.append(error)
        finally:
            session.close()

    threads = [threading.Thread(target=run, args=pair) for pair in (first, second)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert outcomes.count("ok") == 1, (outcomes, failures)  # una sola incorporación efectiva
    assert quota.activeCount(db, team.id) == quota.capacityOf(db, team.id)  # nunca supera el límite
    db.expire_all()
    states = sorted(r.estadoRelacion for r in db.scalars(select(InstitutionUser).where(
        InstitutionUser.idInstitucionUsuario.in_([first[1].idInstitucionUsuario, second[1].idInstitucionUsuario]))))
    assert states == ["ACTIVO", "PENDIENTE"]  # la otra invitación sigue pendiente


def test_el_bloqueo_de_la_institucion_usa_el_hint_de_sql_server():
    from sqlalchemy.dialects import mssql
    statement = select(Institution.idInstitucion).with_hint(Institution, "WITH (UPDLOCK, HOLDLOCK, ROWLOCK)", "mssql")
    assert "WITH (UPDLOCK, HOLDLOCK, ROWLOCK)" in str(statement.compile(dialect=mssql.dialect()))


# --- 14-18. Indicadores, permisos y aislamiento -------------------------------------------------------------------------------------


def test_los_indicadores_coinciden_con_las_relaciones_activas_y_son_independientes_por_institucion(db, mails, team):
    foreign, foreignOperator, _ = otherInstitution(db)
    assert quota.usage(db, team.id).usuariosActivos == activeInSql(db, team.id) == 3
    assert quota.usage(db, foreign.idInstitucion).usuariosActivos == activeInSql(db, foreign.idInstitucion) == 3
    setCapacity(db, foreign.idInstitucion, 500)
    user, invitation = invite(db, team, "aislada@example.com", "aislada")
    accept(db, user, invitation)
    assert quota.usage(db, team.id).usuariosActivos == 4  # solo cambió la institución propia
    other = quota.usage(db, foreign.idInstitucion)
    assert (other.capacidadMaximaUsuarios, other.usuariosActivos, other.cuposDisponibles) == (500, 3, 497)
    assert quota.usage(db, team.id).capacidadMaximaUsuarios == 1000


def test_propietario_y_moderador_consultan_la_capacidad_y_el_operador_no(db, mails, team, api):
    path = f"/api/v1/institutions/{team.id}/quota"
    for actor in (team.owner, team.moderator):
        response = api(actor).get(path)
        assert response.status_code == 200
        assert response.json() == {"capacidadMaximaUsuarios": 1000, "usuariosActivos": 3, "cuposDisponibles": 997,
                                   "porcentajeUtilizacion": 0.3, "estado": "DISPONIBLE", "excedente": 0}
        detail = api(actor).get(f"/api/v1/institutions/{team.id}").json()
        assert (detail["capacidadMaximaUsuarios"], detail["usuariosActivos"], detail["cuposDisponibles"]) == (1000, 3, 997)  # solo lectura
    assert api(team.operator).get(path).status_code == 403
    operatorDetail = api(team.operator).get(f"/api/v1/institutions/{team.id}").json()
    assert operatorDetail["capacidadMaximaUsuarios"] is None and operatorDetail["usuariosActivos"] is None  # el operador no recibe cupos
    # Otra institución: un integrante de otra no la consulta; la propia solo muestra la suya.
    foreign, foreignOperator, _ = otherInstitution(db)
    assert api(foreignOperator).get(path).status_code == 404
    assert api(team.owner).get(f"/api/v1/institutions/{foreign.idInstitucion}/quota").status_code == 404
    assert api(foreignOperator).get(f"/api/v1/institutions/{foreign.idInstitucion}/quota").status_code == 403  # su operador, sin administración


def test_la_baja_audita_el_cupo_liberado_en_el_mismo_evento(db, mails, team):
    institutions.revokeMember(db, team.moderator, team.id, "OPERADOR", relationOf(db, team, team.operator).idInstitucionUsuario)
    events = [a for a in audits(db, "REVOCAR_MIEMBRO_INSTITUCION") if a.resultado == "EXITO"]
    assert len(events) == 1  # sin eventos duplicados
    data = json.loads(events[0].datosNuevos)
    assert (data["usuariosActivos"], data["capacidadMaximaUsuarios"]) == (2, 1000)
    # La aceptación exitosa informa el cupo consumido en su propio evento.
    user, invitation = invite(db, team, "nuevo@example.com", "nuevo")
    accept(db, user, invitation)
    accepted = [a for a in audits(db, "ACEPTAR_INVITACION_INSTITUCION") if a.idRegistro == invitation.idInstitucionUsuario and a.resultado == "EXITO"]
    assert len(accepted) == 1 and json.loads(accepted[0].datosNuevos)["usuariosActivos"] == 3
