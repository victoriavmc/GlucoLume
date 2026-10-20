# Pruebas de incorporación de personal institucional (moderadores y operadores): creación de la cuenta pendiente,
# activación con credenciales propias o con Google, aceptación, reenvío, permisos e independencia de PerfilMedicion.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_institution_staff.py -v

import re
from datetime import timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app.core.exceptions import AuthError
from app.integrations.google.oauth import GoogleIdentity
from app.models.accountToken import AccountToken
from app.models.externalIdentity import ExternalIdentity
from app.models.institutionUser import InstitutionUser
from app.models.localCredential import LocalCredential
from app.models.measurementProfile import MeasurementProfile
from app.models.user import User
from app.schemas.auth import RegisterRequest
from app.schemas.institution import MemberAdminUpdateRequest, MemberInviteRequest
from app.services import accountActivation
from app.services import auth as authService
from app.services import institution as institutions
from app.utils.timeZone import nowForDb
from tests.test_account_deletion import (  # noqa: F401 - fixtures
    PASSWORD,
    audits,
    db,
    engine,
    mails,
    makeUser,
    reload,
)
from tests.test_institutions import (  # noqa: F401 - fixtures
    expectError,
    freshLookupLimiter,
    institutional,
    relationOf,
    team,
)

NEW_PASSWORD = "Moderacion#Segura2026"  # nosec B105 - contraseña de prueba


def count(db, model) -> int:
    db.expire_all()
    return db.scalar(select(func.count()).select_from(model))


def tokenFrom(mail) -> str:
    match = re.search(r"/activar-cuenta\?token=([A-Za-z0-9_\-]+)", mail["html"])
    assert match, "El correo debe traer el enlace de activación."
    return match.group(1)


def addNewModerator(db, team, mails, email="nueva@example.com"):
    member = institutions.invite(db, team.owner, team.id, "MODERADOR", email, nombre="lucía", apellido="sosa")
    return member, tokenFrom(mails[-1])


# --- Escenario 1: moderador sin cuenta ------------------------------------------------------


def test_moderador_nuevo_crea_cuenta_pendiente_y_vinculo_pendiente(db, mails, team):
    users, profiles = count(db, User), count(db, MeasurementProfile)
    member, token = addNewModerator(db, team, mails)

    user = db.scalar(select(User).where(User.correoElectronico == "nueva@example.com"))
    assert (user.tipoCuenta, user.estado, user.nombre, user.apellido, user.usuario) == (
        "USUARIO_INSTITUCIONAL", "PENDIENTE", "Lucía", "Sosa", None)
    assert db.scalar(select(LocalCredential).where(LocalCredential.idUsuario == user.idUsuario)) is None
    relation = reload(db, InstitutionUser, member.idInstitucionUsuario)
    assert (relation.rolInstitucion, relation.estadoRelacion, relation.idUsuarioInvitador) == (
        "MODERADOR", "PENDIENTE", team.owner.idUsuario)
    assert member.cuentaPendiente is True and member.correoElectronico == "nueva@example.com"
    # Correo de activación (solo el hash del token queda en la base) y nada en PerfilMedicion.
    assert mails[-1]["to"] == "nueva@example.com" and "Activá tu cuenta" in mails[-1]["subject"]
    stored = db.scalar(select(AccountToken).where(AccountToken.idUsuario == user.idUsuario))
    assert stored.tipo == "ACTIVACION_CUENTA" and token not in stored.tokenHash
    assert (count(db, User), count(db, MeasurementProfile)) == (users + 1, profiles)
    assert [a.accion for a in audits(db) if a.accion in ("CREAR_CUENTA_INVITADA", "INVITAR_MIEMBRO_INSTITUCION")
            and a.resultado == "EXITO"][-2:] == ["CREAR_CUENTA_INVITADA", "INVITAR_MIEMBRO_INSTITUCION"]


def test_sin_activar_no_hay_acceso(db, mails, team):
    addNewModerator(db, team, mails)
    user = db.scalar(select(User).where(User.correoElectronico == "nueva@example.com"))
    expectError("CREDENCIALES_INVALIDAS", authService.loginLocal, db, "nueva@example.com", NEW_PASSWORD)
    expectError("INSTITUCION_NO_ENCONTRADA", institutions.getDetail, db, user, team.id)


def test_activar_aceptar_y_gestionar_operadores(db, mails, team):
    member, token = addNewModerator(db, team, mails)
    info = accountActivation.checkActivation(db, token)
    assert (info.nombre, info.invitaciones[0].nombreInstitucion, info.invitaciones[0].rolInstitucion) == (
        "Lucía", "Hospital X", "MODERADOR")

    session = accountActivation.completeActivation(db, token, "luciasosa", NEW_PASSWORD, aceptaPolitica=True)
    assert session.estado == "AUTENTICADO" and session.tokens.accessToken
    user = db.scalar(select(User).where(User.correoElectronico == "nueva@example.com"))
    assert (user.estado, user.usuario) == ("ACTIVO", "luciasosa")
    # El enlace es de un solo uso y el vínculo sigue PENDIENTE hasta aceptar.
    expectError("TOKEN_INVALIDO", accountActivation.completeActivation, db, token, "otra", NEW_PASSWORD, aceptaPolitica=True)
    assert reload(db, InstitutionUser, member.idInstitucionUsuario).estadoRelacion == "PENDIENTE"

    [invitation] = institutions.listInvitations(db, user)
    institutions.respondInvitation(db, user, invitation.idInstitucionUsuario, accept=True)
    assert reload(db, InstitutionUser, member.idInstitucionUsuario).estadoRelacion == "ACTIVO"
    # Inicia sesión con sus propias credenciales y gestiona operadores.
    assert authService.loginLocal(db, "luciasosa", NEW_PASSWORD).estado == "AUTENTICADO"
    assert "INCORPORAR_OPERADORES" in institutions.getDetail(db, user, team.id).permisos
    institutional(db, "op2@example.com", "op2")
    assert institutions.invite(db, user, team.id, "OPERADOR", "op2@example.com").estadoRelacion == "PENDIENTE"


def test_activacion_valida_usuario_y_contrasena(db, mails, team):
    _, token = addNewModerator(db, team, mails)
    expectError("USUARIO_REGISTRADO", accountActivation.completeActivation, db, token, "moderador", NEW_PASSWORD, aceptaPolitica=True)
    expectError("PASSWORD_DEBIL", accountActivation.completeActivation, db, token, "luciasosa", "Lucia#Sosa2026x", aceptaPolitica=True)
    assert db.scalar(select(User).where(User.correoElectronico == "nueva@example.com")).estado == "PENDIENTE"


def test_enlace_vencido(db, mails, team):
    _, token = addNewModerator(db, team, mails)
    stored = db.scalar(select(AccountToken).where(AccountToken.tipo == "ACTIVACION_CUENTA"))
    stored.fechaCreacion = nowForDb() - timedelta(days=8)  # CK_TokenCuenta_expiracion: vence después de crearse
    stored.fechaExpiracion = nowForDb() - timedelta(minutes=1)
    db.commit()
    expectError("TOKEN_VENCIDO", accountActivation.checkActivation, db, token)


def test_activacion_con_google_del_mismo_correo(db, mails, team):
    addNewModerator(db, team, mails)
    identity = GoogleIdentity(subject="g-nueva", email="nueva@example.com", emailVerified=True,
                              givenName="Lucía", familyName="Sosa")
    # La activación con Google llega sin intención de registro (no hay tipo que elegir) y con la política confirmada.
    user = authService.identifyGoogleUser(db, identity, None, True)
    assert (user.estado, user.tipoCuenta) == ("ACTIVO", "USUARIO_INSTITUCIONAL")
    assert db.scalar(select(ExternalIdentity).where(ExternalIdentity.idUsuario == user.idUsuario)) is not None
    assert db.scalar(select(AccountToken).where(AccountToken.tipo == "ACTIVACION_CUENTA")).fechaUso is not None
    assert len(institutions.listInvitations(db, user)) == 1  # la aceptación sigue siendo explícita


def test_registro_propio_con_un_correo_invitado_indica_activar(db, mails, team):
    addNewModerator(db, team, mails)
    error = expectError("CORREO_REGISTRADO", authService.registerLocal, db, RegisterRequest(aceptaPoliticaPrivacidad=True, 
        nombre="Lucía", apellido="Sosa", usuario="luciasosa", correoElectronico="nueva@example.com",
        password=NEW_PASSWORD, tipoCuenta="USUARIO_INSTITUCIONAL"))
    assert "Activá tu cuenta" in error.message
    expectError("ACTIVACION_PENDIENTE", authService.resendVerification, db, "nueva@example.com")


def test_faltan_nombre_y_apellido_para_una_cuenta_nueva(db, mails, team):
    users = count(db, User)
    expectError("DATOS_REQUERIDOS", institutions.invite, db, team.owner, team.id, "MODERADOR", "nueva@example.com")
    assert count(db, User) == users


def test_falla_la_transaccion_no_quedan_registros_inconsistentes(db, mails, team, monkeypatch):
    users, relations = count(db, User), count(db, InstitutionUser)
    original = institutions.registerEvent

    def failing(db_, tipo, accion, exito, *args, **kwargs):
        if accion == "INVITAR_MIEMBRO_INSTITUCION" and exito:
            raise RuntimeError("falla simulada")
        return original(db_, tipo, accion, exito, *args, **kwargs)

    monkeypatch.setattr(institutions, "registerEvent", failing)
    with pytest.raises(RuntimeError):
        institutions.invite(db, team.owner, team.id, "MODERADOR", "nueva@example.com", nombre="Lucía", apellido="Sosa")
    db.rollback()
    assert (count(db, User), count(db, InstitutionUser)) == (users, relations)


def test_reenviar_no_duplica_y_renueva_el_enlace(db, mails, team):
    member, firstToken = addNewModerator(db, team, mails)
    users, relations = count(db, User), count(db, InstitutionUser)
    resent = institutions.resendInvitation(db, team.owner, team.id, "MODERADOR", member.idInstitucionUsuario)
    secondToken = tokenFrom(mails[-1])
    assert secondToken != firstToken and resent.estadoRelacion == "PENDIENTE"
    assert (count(db, User), count(db, InstitutionUser)) == (users, relations)
    expectError("TOKEN_INVALIDO", accountActivation.checkActivation, db, firstToken)
    assert accountActivation.checkActivation(db, secondToken).nombre == "Lucía"
    expectError("PERMISO_INSUFICIENTE", institutions.resendInvitation, db, team.moderator, team.id, "MODERADOR",
                member.idInstitucionUsuario)


# --- Escenario 2: cuenta institucional existente ----------------------------------------------


def test_cuenta_institucional_existente_se_reutiliza(db, mails, team):
    existing = institutional(db, "existente@example.com", "existente")
    users = count(db, User)
    candidate = institutions.lookupCandidate(db, team.owner, team.id, "MODERADOR", "existente@example.com")
    assert candidate.cuentaPendiente is False
    member = institutions.invite(db, team.owner, team.id, "MODERADOR", "existente@example.com",
                                 nombre="Otro", apellido="Nombre")  # no se sobrescriben sus datos
    assert count(db, User) == users and reload(db, User, existing.idUsuario).nombre == "Victoria"
    assert "invitó" in mails[-1]["subject"] and "/activar-cuenta" not in mails[-1]["html"]
    institutions.respondInvitation(db, existing, member.idInstitucionUsuario, accept=True)
    [moderator] = [m for m in institutions.listMembers(db, team.owner, team.id, "MODERADOR")
                   if m.correoElectronico == "existente@example.com"]
    assert moderator.estadoRelacion == "ACTIVO"


def test_cuenta_invitada_pendiente_se_reutiliza_en_otra_institucion(db, mails, team):
    addNewModerator(db, team, mails)
    other = institutional(db, "otra-duenia@example.com", "otraduenia")
    from tests.test_institutions import newInstitution
    second = newInstitution(db, other, "87654321", "Laboratorio Norte")
    users = count(db, User)
    candidate = institutions.lookupCandidate(db, other, second.idInstitucion, "MODERADOR", "nueva@example.com")
    assert candidate.cuentaPendiente is True
    institutions.invite(db, other, second.idInstitucion, "MODERADOR", "nueva@example.com")
    assert count(db, User) == users
    info = accountActivation.checkActivation(db, tokenFrom(mails[-1]))
    assert {i.nombreInstitucion for i in info.invitaciones} == {"Hospital X", "Laboratorio Norte"}


# --- Escenario 3: autorización ----------------------------------------------------------------


@pytest.mark.parametrize("actor", ["operator", "moderator"])
def test_solo_el_propietario_agrega_moderadores(db, mails, team, actor):
    users = count(db, User)
    expectError("PERMISO_INSUFICIENTE", institutions.invite, db, getattr(team, actor), team.id, "MODERADOR",
                "nueva@example.com", nombre="Lucía", apellido="Sosa")
    assert count(db, User) == users


# --- Casos C y D ------------------------------------------------------------------------------


def test_cuenta_individual_no_se_incorpora(db, mails, team):
    personal = makeUser(db, email="personal@example.com", usuario="personal")
    expectError("CUENTA_PERSONAL_NO_INCORPORABLE", institutions.invite, db, team.owner, team.id, "MODERADOR",
                "personal@example.com", nombre="Otra", apellido="Persona")
    assert reload(db, User, personal.idUsuario).tipoCuenta == "CONSUMIDOR_FINAL"
    assert db.scalar(select(func.count()).select_from(User).where(User.correoElectronico == "personal@example.com")) == 1


def test_ya_vinculada_no_se_duplica_ni_cambia_de_rol(db, mails, team):
    error = expectError("VINCULO_EXISTENTE", institutions.invite, db, team.owner, team.id, "MODERADOR",
                        team.moderator.correoElectronico)
    assert error.message == "Esta persona ya es moderador/a de la institución."
    error = expectError("VINCULO_EXISTENTE", institutions.invite, db, team.owner, team.id, "MODERADOR",
                        team.operator.correoElectronico)
    assert "como operador/a" in error.message and "no se cambia automáticamente" in error.message
    assert relationOf(db, team, team.operator).rolInstitucion == "OPERADOR"
    addNewModerator(db, team, mails)
    expectError("INVITACION_PENDIENTE", institutions.invite, db, team.owner, team.id, "MODERADOR", "nueva@example.com")


# --- Listado y estados ------------------------------------------------------------------------


def test_listado_distingue_pendiente_activo_y_baja(db, mails, team):
    member, _ = addNewModerator(db, team, mails)
    moderatorLink = relationOf(db, team, team.moderator).idInstitucionUsuario
    institutions.revokeMember(db, team.owner, team.id, "MODERADOR", moderatorLink)
    current = {m.correoElectronico: m for m in institutions.listMembers(db, team.owner, team.id, "MODERADOR")}
    assert set(current) == {"nueva@example.com"} and current["nueva@example.com"].cuentaPendiente
    history = {m.correoElectronico: m.estadoRelacion for m in
               institutions.listMembers(db, team.owner, team.id, "MODERADOR", incluirBajas=True)}
    assert history == {"nueva@example.com": "PENDIENTE", "moderador@example.com": "BAJA"}


# --- Datos administrativos del vínculo (InstitucionUsuario) -------------------------------------


ADMIN = {"matriculaProfesional": "MN 4521", "legajoInstitucional": "L-0098",
         "nombreProfesionalHistorico": "lucía belén", "apellidoProfesionalHistorico": "sosa"}


def inviteRequest(**kwargs):
    return MemberInviteRequest(correoElectronico="nueva@example.com", **kwargs)


def test_moderador_nuevo_registra_usuario_y_todos_los_datos_del_vinculo(db, mails, team):
    data = inviteRequest(nombre="lucía", apellido="sosa", **ADMIN)
    member = institutions.invite(db, team.owner, team.id, "MODERADOR", data.correoElectronico,
                                 nombre=data.nombre, apellido=data.apellido, datos=data.adminFields())
    user = db.scalar(select(User).where(User.correoElectronico == "nueva@example.com"))
    assert (user.nombre, user.apellido, user.tipoCuenta) == ("Lucía", "Sosa", "USUARIO_INSTITUCIONAL")
    relation = reload(db, InstitutionUser, member.idInstitucionUsuario)
    assert (relation.matriculaProfesional, relation.legajoInstitucional, relation.nombreProfesionalHistorico,
            relation.apellidoProfesionalHistorico) == ("MN 4521", "L-0098", "Lucía Belén", "Sosa")
    assert (member.legajoInstitucional, member.nombreProfesionalHistorico) == ("L-0098", "Lucía Belén")


def test_nombre_historico_por_defecto_es_el_de_la_persona(db, mails, team):
    member = institutions.invite(db, team.owner, team.id, "MODERADOR", "nueva@example.com",
                                 nombre="lucía", apellido="sosa")
    relation = reload(db, InstitutionUser, member.idInstitucionUsuario)
    assert (relation.nombreProfesionalHistorico, relation.apellidoProfesionalHistorico) == ("Lucía", "Sosa")
    assert relation.matriculaProfesional is None and relation.legajoInstitucional is None  # opcionales


def test_cuenta_existente_conserva_sus_nombres_globales(db, mails, team):
    existing = institutional(db, "nueva@example.com", "nueva")
    before = (existing.nombre, existing.apellido)
    member = institutions.invite(db, team.owner, team.id, "MODERADOR", "nueva@example.com", nombre="Otro",
                                 apellido="Nombre", datos={"nombreProfesionalHistorico": "Dra. Ana",
                                                           "apellidoProfesionalHistorico": "Pérez"})
    assert (reload(db, User, existing.idUsuario).nombre, reload(db, User, existing.idUsuario).apellido) == before
    relation = reload(db, InstitutionUser, member.idInstitucionUsuario)
    assert (relation.nombreProfesionalHistorico, relation.apellidoProfesionalHistorico) == ("Dra. Ana", "Pérez")


def test_cuenta_existente_sin_nombre_historico_toma_el_de_su_cuenta(db, mails, team):
    existing = institutional(db, "nueva@example.com", "nueva")
    member = institutions.invite(db, team.owner, team.id, "MODERADOR", "nueva@example.com")
    relation = reload(db, InstitutionUser, member.idInstitucionUsuario)
    assert (relation.nombreProfesionalHistorico, relation.apellidoProfesionalHistorico) == (
        existing.nombre, existing.apellido)


def test_operador_registra_los_mismos_cuatro_campos(db, mails, team):
    member = institutions.invite(db, team.moderator, team.id, "OPERADOR", "nueva@example.com", nombre="Pía",
                                 apellido="Gómez", datos={"matriculaProfesional": "MP 77", "legajoInstitucional": "9"})
    relation = reload(db, InstitutionUser, member.idInstitucionUsuario)
    assert (relation.matriculaProfesional, relation.legajoInstitucional, relation.nombreProfesionalHistorico,
            relation.apellidoProfesionalHistorico) == ("MP 77", "9", "Pía", "Gómez")


def test_matricula_y_legajo_vacios_se_guardan_como_nulos_sin_reglas_inventadas():
    data = inviteRequest(matriculaProfesional="  ", legajoInstitucional="", nombreProfesionalHistorico=" ")
    assert (data.matriculaProfesional, data.legajoInstitucional, data.nombreProfesionalHistorico) == (None, None, None)
    assert inviteRequest(legajoInstitucional="abc/12-x").legajoInstitucional == "abc/12-x"  # sin formato fijo


def test_propietario_edita_los_datos_del_moderador_y_queda_auditado(db, mails, team):
    link = relationOf(db, team, team.moderator).idInstitucionUsuario
    names = (team.moderator.nombre, team.moderator.apellido)
    changes = MemberAdminUpdateRequest(legajoInstitucional="L-1", matriculaProfesional="MN 1").model_dump(
        exclude_unset=True)
    member = institutions.updateMemberAdmin(db, team.owner, team.id, "MODERADOR", link, changes)
    assert (member.legajoInstitucional, member.matriculaProfesional, member.rolInstitucion) == (
        "L-1", "MN 1", "MODERADOR")
    assert (reload(db, User, team.moderator.idUsuario).nombre, reload(db, User, team.moderator.idUsuario).apellido) == names
    [audit] = audits(db, "MODIFICAR_MIEMBRO_INSTITUCION")
    assert audit.resultado == "EXITO" and "L-1" not in audit.datosNuevos and "legajoInstitucional" in audit.datosNuevos


def test_la_edicion_no_cambia_el_rol():
    with pytest.raises(ValueError):
        MemberAdminUpdateRequest(rolInstitucion="PROPIETARIO")


@pytest.mark.parametrize("actor", ["moderator", "operator"])
def test_solo_el_propietario_edita_moderadores(db, mails, team, actor):
    link = relationOf(db, team, team.moderator).idInstitucionUsuario
    expectError("PERMISO_INSUFICIENTE", institutions.updateMemberAdmin, db, getattr(team, actor), team.id,
                "MODERADOR", link, {"legajoInstitucional": "X"})
    assert reload(db, InstitutionUser, link).legajoInstitucional is None


@pytest.mark.parametrize("actor", ["owner", "moderator"])
def test_propietario_o_moderador_editan_operadores(db, mails, team, actor):
    link = relationOf(db, team, team.operator).idInstitucionUsuario
    member = institutions.updateMemberAdmin(db, getattr(team, actor), team.id, "OPERADOR", link,
                                            {"legajoInstitucional": "OP-5", "nombreProfesionalHistorico": "Ana"})
    assert (member.legajoInstitucional, member.nombreProfesionalHistorico) == ("OP-5", "Ana")
    assert member.matriculaProfesional == "MP-123"  # lo no enviado no cambia


def test_un_operador_no_edita_a_otro_y_no_se_edita_por_otra_ruta(db, mails, team):
    link = relationOf(db, team, team.operator).idInstitucionUsuario
    expectError("PERMISO_INSUFICIENTE", institutions.updateMemberAdmin, db, team.operator, team.id, "OPERADOR",
                link, {"legajoInstitucional": "X"})
    # Un vínculo de operador no se modifica como moderador (el rol de la ruta debe coincidir).
    expectError("MIEMBRO_NO_ENCONTRADO", institutions.updateMemberAdmin, db, team.owner, team.id, "MODERADOR",
                link, {"legajoInstitucional": "X"})


# --- Función profesional (operador, enfermero/a, médico/a): descriptiva, no cambia permisos ---------------------


def test_funcion_profesional_opcional_se_registra_y_no_cambia_los_permisos(db, mails, team):
    data = inviteRequest(funcionProfesional="medico", nombre="Lucía", apellido="Sosa")
    assert data.funcionProfesional == "MEDICO"
    member = institutions.invite(db, team.moderator, team.id, "OPERADOR", "nueva@example.com", nombre="Lucía",
                                 apellido="Sosa", datos=data.adminFields())
    relation = reload(db, InstitutionUser, member.idInstitucionUsuario)
    assert relation.funcionProfesional == "MEDICO" and relation.rolInstitucion == "OPERADOR"
    assert member.funcionProfesional == "MEDICO"
    # Sin funcion: queda vacía (opcional).
    plain = institutions.invite(db, team.moderator, team.id, "OPERADOR", "otra@example.com", nombre="Pía", apellido="Gómez")
    assert reload(db, InstitutionUser, plain.idInstitucionUsuario).funcionProfesional is None


def test_funcion_profesional_solo_acepta_las_opciones_definidas():
    assert inviteRequest(funcionProfesional="").funcionProfesional is None
    assert inviteRequest(funcionProfesional="enfermero").funcionProfesional == "ENFERMERO"
    for invalid in ("DIRECTOR", "PROPIETARIO", "MODERADOR"):  # ni roles de permisos ni valores inventados
        with pytest.raises(ValidationError):
            inviteRequest(funcionProfesional=invalid)


def test_la_funcion_profesional_se_edita_y_se_borra_sin_cambiar_el_rol(db, mails, team):
    link = relationOf(db, team, team.operator).idInstitucionUsuario
    member = institutions.updateMemberAdmin(db, team.moderator, team.id, "OPERADOR", link,
                                            MemberAdminUpdateRequest(funcionProfesional="ENFERMERO").model_dump(exclude_unset=True))
    assert (member.funcionProfesional, member.rolInstitucion) == ("ENFERMERO", "OPERADOR")
    cleared = institutions.updateMemberAdmin(db, team.moderator, team.id, "OPERADOR", link,
                                             MemberAdminUpdateRequest(funcionProfesional=None).model_dump(exclude_unset=True))
    assert cleared.funcionProfesional is None
