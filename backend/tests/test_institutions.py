# Pruebas del módulo Institución: tipo de cuenta y registro, creación con CUIT único, jerarquía de roles,
# invitaciones con aceptación, matriz de permisos y eliminación lógica.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_institutions.py -v
#
# Usan el esquema SQLite temporal y el SMTP simulado de test_account_deletion.py.

import re
import uuid
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import AuthError
from app.integrations.google.oauth import GoogleIdentity
from app.models.institution import Institution
from app.models.device import Device
from app.models.institutionUser import InstitutionUser
from app.models.measurement import Measurement
from app.models.measurementProfile import MeasurementProfile
from app.models.user import User
from app.schemas.auth import RegisterRequest
from app.schemas.institution import (
    CUIT_WEIGHTS,
    InstitutionCreateRequest,
    InstitutionDeletionRequest,
    InstitutionUpdateRequest,
    isValidCuit,
)
from app.schemas.measurementProfile import InstitutionalProfileCreate
from app.services import auth as authService
from app.integrations.email import sender
from app.services import institution as institutions
from app.services import notifications
from app.services.accountDeletion import findBlocker
from app.services.contact import RateLimiter
from app.services.measurementProfile import buildInstitutionalProfile
from app.utils.timeZone import nowForDb
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
from tests.test_google_exchange import googleEnv, runCallback  # noqa: F401 - fixtures


def cuit(prefix: str = "30", number: str = "71234567") -> str:
    body = prefix + number
    remainder = 11 - sum(int(d) * w for d, w in zip(body, CUIT_WEIGHTS)) % 11
    return body + str({11: 0, 10: 9}.get(remainder, remainder))


def registration(**overrides) -> RegisterRequest:
    data = {"nombre": "María", "apellido": "López", "usuario": "marialopez", "correoElectronico": "maria@example.com",
            "password": PASSWORD, "tipoCuenta": "USUARIO_INSTITUCIONAL"}
    return RegisterRequest(aceptaPoliticaPrivacidad=True, **{**data, **overrides})


def count(db, model) -> int:
    return db.scalar(select(func.count()).select_from(model))


def newInstitution(db, owner, number="71234567", nombre="Hospital X") -> Institution:
    data = InstitutionCreateRequest(nombre=nombre, tipoInstitucion="HOSPITAL", identificadorLegal=cuit("30", number))
    return institutions.createInstitution(db, owner, data)


def institutional(db, email, usuario, **kwargs) -> User:
    return makeUser(db, tipoCuenta="USUARIO_INSTITUCIONAL", email=email, usuario=usuario, **kwargs)


# --- Registro ------------------------------------------------------------------------------


@pytest.mark.parametrize(("tipo", "esperado"), [("CONSUMIDOR_FINAL", "CONSUMIDOR_FINAL"),
                                                ("usuario_institucional", "USUARIO_INSTITUCIONAL")])
def test_registro_local_persiste_el_tipo_sin_crear_instituciones(db, mails, tipo, esperado):
    user = authService.registerLocal(db, registration(tipoCuenta=tipo))
    assert reload(db, User, user.idUsuario).tipoCuenta == esperado
    assert count(db, Institution) == 0 and count(db, InstitutionUser) == 0


def test_registro_no_acepta_datos_de_institucion_ni_tipos_no_publicos():
    with pytest.raises(ValidationError):
        registration(institucion={"nombre": "Hospital X", "tipoInstitucion": "HOSPITAL", "identificadorLegal": cuit()})
    for tipo in ("ADMINISTRADOR_PLATAFORMA", "INSTITUCIONAL", "OTRO"):
        with pytest.raises(ValidationError):
            registration(tipoCuenta=tipo)


def test_cuenta_institucional_sin_institucion_inicia_sesion(db, mails):
    authService.registerLocal(db, registration())
    token = re.search(r"verificar-correo\?token=([A-Za-z0-9_\-]+)", mails[0]["html"]).group(1)
    authService.verifyEmail(db, token)
    assert authService.loginLocal(db, "marialopez", PASSWORD).estado == "AUTENTICADO"
    user = db.scalar(select(User))
    assert institutions.listMine(db, user) == []


@pytest.mark.parametrize(("intencion", "esperado"), [("usuario", "CONSUMIDOR_FINAL"),
                                                     ("institucion", "USUARIO_INSTITUCIONAL")])
def test_registro_con_google_respeta_el_tipo_elegido(db, mails, googleEnv, monkeypatch, intencion, esperado):
    identity = GoogleIdentity(subject=f"g-{intencion}", email=f"{intencion}@example.com", emailVerified=True,
                              givenName="Ana", familyName="Pérez")

    async def fetchIdentity(request):
        return identity

    session = {"glucolume_registro": intencion, "glucolume_politica": True}
    assert runCallback(db, monkeypatch, fetchIdentity, session).startswith("code=")
    user = db.scalar(select(User).where(User.correoElectronico == identity.email))
    assert user.tipoCuenta == esperado
    assert count(db, Institution) == 0 and count(db, InstitutionUser) == 0


def test_login_con_google_conserva_el_tipo_de_la_cuenta(db, mails, googleEnv, monkeypatch):
    personal = makeUser(db, local=False, google=True, email="victoria@example.com")
    identity = GoogleIdentity(subject=f"sub-{personal.idUsuario}", email="victoria@example.com", emailVerified=True,
                              givenName=None, familyName=None)

    async def fetchIdentity(request):
        return identity

    # Aunque la intención guardada sea "institucion", una cuenta existente solo inicia sesión.
    runCallback(db, monkeypatch, fetchIdentity, {"glucolume_registro": "institucion", "glucolume_politica": True})
    assert reload(db, User, personal.idUsuario).tipoCuenta == "CONSUMIDOR_FINAL"
    assert count(db, User) == 1


# --- Escenario base ------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def freshLookupLimiter(monkeypatch):
    monkeypatch.setattr(institutions, "_lookupLimiter", RateLimiter(institutions.LOOKUP_LIMIT_MAX,
                                                                    institutions.LOOKUP_LIMIT_WINDOW_SECONDS))


def expectError(code, fn, *args, **kwargs) -> AuthError:
    with pytest.raises(AuthError) as error:
        fn(*args, **kwargs)
    assert error.value.code == code, error.value.message
    return error.value


@pytest.fixture
def team(db, mails):
    """Institución con propietaria, moderador activo y operadora activa (incorporados por invitación aceptada)."""
    owner = institutional(db, "duenia@example.com", "duenia")
    moderator = institutional(db, "moderador@example.com", "moderador")
    operator = institutional(db, "operadora@example.com", "operadora")
    institution = newInstitution(db, owner)
    invitation = institutions.invite(db, owner, institution.idInstitucion, "MODERADOR", moderator.correoElectronico)
    institutions.respondInvitation(db, moderator, invitation.idInstitucionUsuario, accept=True)
    invitation = institutions.invite(db, moderator, institution.idInstitucion, "OPERADOR", operator.correoElectronico,
                                     datos={"matriculaProfesional": "MP-123"})
    institutions.respondInvitation(db, operator, invitation.idInstitucionUsuario, accept=True)
    mails.clear()
    return SimpleNamespace(owner=owner, moderator=moderator, operator=operator, institution=institution,
                           id=institution.idInstitucion)


def relationOf(db, team, user) -> InstitutionUser:
    db.expire_all()
    return db.scalar(select(InstitutionUser).where(InstitutionUser.idInstitucion == team.id,
                                                   InstitutionUser.idUsuarioInvitado == user.idUsuario,
                                                   InstitutionUser.estadoRelacion != "BAJA"))


# --- Crear institución ---------------------------------------------------------------------


def test_cuenta_institucional_crea_institucion_y_queda_propietaria(db, mails):
    owner = institutional(db, "duenia@example.com", "duenia")
    institution = newInstitution(db, owner)
    [mine] = institutions.listMine(db, owner)
    assert mine.idInstitucion == institution.idInstitucion and mine.rolInstitucion == "PROPIETARIO"
    assert set(mine.permisos) >= {"MODIFICAR_INSTITUCION", "GESTIONAR_MODERADORES", "ELIMINAR_INSTITUCION"}
    assert "INCORPORAR_OPERADORES" not in mine.permisos
    assert [a.accion for a in audits(db, "CREAR_INSTITUCION")] == ["CREAR_INSTITUCION"]


def test_mismo_nombre_con_cuit_distinto_puede_coexistir(db, mails):
    owner = institutional(db, "duenia@example.com", "duenia")
    newInstitution(db, owner, "71234567", "Centro Médico San José")
    newInstitution(db, owner, "87654321", "Centro Médico San José")
    assert count(db, Institution) == 2


def test_cuit_duplicado_rechazado_sin_modificar_la_existente(db, mails):
    owner = institutional(db, "duenia@example.com", "duenia")
    other = institutional(db, "otra@example.com", "otra")
    existing = newInstitution(db, owner, nombre="Hospital X")
    # Mismo CUIT con formato distinto: se normaliza antes de verificar.
    data = InstitutionCreateRequest(nombre="Otro nombre", tipoInstitucion="CLINICA",
                                    identificadorLegal=f"30-{cuit()[2:10]}-{cuit()[10]}")
    error = expectError("INSTITUCION_REGISTRADA", institutions.createInstitution, db, other, data)
    assert error.message == "Ya existe una institución activa registrada con este CUIT."
    assert count(db, Institution) == 1 and reload(db, Institution, existing.idInstitucion).nombre == "Hospital X"
    assert institutions.listMine(db, other) == []


def test_cuit_duplicado_concurrente_lo_rechaza_la_restriccion(db, mails, monkeypatch):
    owner = institutional(db, "duenia@example.com", "duenia")
    newInstitution(db, owner)
    # Simula la carrera: la verificación previa no ve la otra institución y decide la restricción de la base.
    original = db.scalar
    monkeypatch.setattr(db, "scalar", lambda *a, **k: None)
    data = InstitutionCreateRequest(nombre="Hospital Y", tipoInstitucion="HOSPITAL", identificadorLegal=cuit())
    expectError("INSTITUCION_REGISTRADA", institutions.createInstitution, db, owner, data)
    monkeypatch.setattr(db, "scalar", original)
    assert count(db, Institution) == 1


@pytest.mark.parametrize("value", ["30712345675", "3071234567", "30-7123456-71", "abcdefghijk", ""])
def test_cuit_invalido_rechazado(value):
    with pytest.raises(ValidationError):
        InstitutionCreateRequest(nombre="Hospital X", tipoInstitucion="HOSPITAL", identificadorLegal=value)
    assert isValidCuit(cuit()) and not isValidCuit("30712345675")


def test_consumidor_final_no_puede_crear_instituciones(db, mails):
    personal = makeUser(db)
    expectError("PERMISO_INSUFICIENTE", newInstitution, db, personal)
    assert count(db, Institution) == 0


# --- Moderadores y operadores por invitación ------------------------------------------------


def test_propietario_invita_moderador_y_queda_activo_solo_al_aceptar(db, mails):
    owner = institutional(db, "duenia@example.com", "duenia")
    moderator = institutional(db, "moderador@example.com", "moderador")
    institution = newInstitution(db, owner)

    candidate = institutions.lookupCandidate(db, owner, institution.idInstitucion, "MODERADOR",
                                             "moderador@example.com")
    # Solo datos mínimos para confirmar.
    assert candidate.model_dump() == {"nombre": "Victoria", "apellido": "Cortés", "rolPropuesto": "MODERADOR",
                                      "cuentaPendiente": False}

    invitation = institutions.invite(db, owner, institution.idInstitucion, "MODERADOR", "moderador@example.com")
    assert invitation.estadoRelacion == "PENDIENTE" and invitation.fechaVencimientoInvitacion is not None
    mail = mails[-1]
    assert mail["to"] == "moderador@example.com" and "/app/instituciones" in mail["html"]
    # Todavía no tiene acceso: la invitación no es un vínculo activo.
    assert institutions.listMine(db, moderator) == []
    expectError("INSTITUCION_NO_ENCONTRADA", institutions.getDetail, db, moderator, institution.idInstitucion)

    [received] = institutions.listInvitations(db, moderator)
    assert received.nombreInstitucion == "Hospital X" and received.rolInstitucion == "MODERADOR"
    accepted = institutions.respondInvitation(db, moderator, received.idInstitucionUsuario, accept=True)
    assert accepted.rolInstitucion == "MODERADOR"
    assert "INCORPORAR_OPERADORES" in accepted.permisos and "GESTIONAR_MODERADORES" not in accepted.permisos
    # INVITACION_ACEPTADA a quien invitó y AGREGADO_INSTITUCION de confirmación a la persona incorporada.
    assert {mail["to"] for mail in mails[-2:]} == {"duenia@example.com", "moderador@example.com"}
    detail = institutions.getDetail(db, owner, institution.idInstitucion)
    assert (detail.cantidadModeradores, detail.cantidadOperadores) == (1, 0)


def test_moderador_incorpora_operadores(db, mails, team):
    detail = institutions.getDetail(db, team.owner, team.id)
    assert (detail.cantidadModeradores, detail.cantidadOperadores) == (1, 1)
    relation = relationOf(db, team, team.operator)
    assert relation.rolInstitucion == "OPERADOR" and relation.estadoRelacion == "ACTIVO"
    assert relation.idUsuarioInvitador == team.moderator.idUsuario and relation.matriculaProfesional == "MP-123"


def test_rechazar_una_invitacion(db, mails, team):
    nueva = institutional(db, "nueva@example.com", "nueva")
    invitation = institutions.invite(db, team.moderator, team.id, "OPERADOR", "nueva@example.com")
    assert institutions.respondInvitation(db, nueva, invitation.idInstitucionUsuario, accept=False) is None
    assert relationOf(db, team, nueva) is None
    # Ya respondida: no se puede volver a usar.
    expectError("INVITACION_NO_ENCONTRADA", institutions.respondInvitation, db, nueva,
                invitation.idInstitucionUsuario, True)


def test_solo_la_cuenta_invitada_responde(db, mails, team):
    nueva = institutional(db, "nueva@example.com", "nueva")
    invitation = institutions.invite(db, team.moderator, team.id, "OPERADOR", "nueva@example.com")
    expectError("INVITACION_NO_ENCONTRADA", institutions.respondInvitation, db, team.operator,
                invitation.idInstitucionUsuario, True)


def test_invitacion_vencida_no_se_acepta_y_permite_invitar_de_nuevo(db, mails, team):
    nueva = institutional(db, "nueva@example.com", "nueva")
    invitation = institutions.invite(db, team.moderator, team.id, "OPERADOR", "nueva@example.com")
    relation = db.get(InstitutionUser, invitation.idInstitucionUsuario)
    relation.fechaInvitacion = nowForDb() - timedelta(days=institutions.INVITATION_VALIDITY_DAYS, seconds=1)
    db.commit()
    # Se informa como vencida, sin poder responderla.
    assert [i.estado for i in institutions.listInvitations(db, nueva)] == ["VENCIDA"]
    expectError("INVITACION_VENCIDA", institutions.respondInvitation, db, nueva, invitation.idInstitucionUsuario, True)
    again = institutions.invite(db, team.moderator, team.id, "OPERADOR", "nueva@example.com")
    assert again.estadoRelacion == "PENDIENTE"


@pytest.mark.parametrize(("actor", "rol"), [("operator", "OPERADOR"), ("operator", "MODERADOR"),
                                            ("moderator", "MODERADOR"), ("owner", "OPERADOR")])
def test_matriz_de_invitaciones(db, mails, team, actor, rol):
    """El operador no incorpora; el moderador no crea moderadores; el propietario no incorpora operadores."""
    institutional(db, "nueva@example.com", "nueva")
    expectError("PERMISO_INSUFICIENTE", institutions.invite, db, getattr(team, actor), team.id, rol,
                "nueva@example.com")
    expectError("PERMISO_INSUFICIENTE", institutions.lookupCandidate, db, getattr(team, actor), team.id, rol,
                "nueva@example.com")
    assert count(db, InstitutionUser) == 3


def test_propietario_no_es_un_rol_invitable(db, mails, team):
    institutional(db, "nueva@example.com", "nueva")
    expectError("PERMISO_INSUFICIENTE", institutions.invite, db, team.owner, team.id, "PROPIETARIO",
                "nueva@example.com")


def test_cuenta_individual_no_se_incorpora_ni_cambia_de_tipo(db, mails, team):
    personal = makeUser(db, email="personal@example.com", usuario="personal")
    error = expectError("CUENTA_PERSONAL_NO_INCORPORABLE", institutions.invite, db, team.moderator, team.id,
                        "OPERADOR", "personal@example.com")
    assert error.message == ("El correo ingresado no corresponde a una cuenta institucional. "
                             "Para ser incorporado, el usuario debe contar con una cuenta institucional válida, no personal.")
    assert reload(db, User, personal.idUsuario).tipoCuenta == "CONSUMIDOR_FINAL"
    assert relationOf(db, team, personal) is None


def test_correo_inexistente_o_sin_verificar(db, mails, team):
    # Sin cuenta: la búsqueda lo informa y el formulario pide nombre y apellido para crearla.
    error = expectError("USUARIO_NO_ENCONTRADO", institutions.lookupCandidate, db, team.moderator, team.id,
                        "OPERADOR", "nadie@example.com")
    assert error.message.startswith("No existe una cuenta con este correo.")
    # Cuenta registrada por la propia persona que todavía no confirmó su correo: no se invita.
    pendiente = institutional(db, "pendiente@example.com", "pendiente")
    pendiente.estado = "PENDIENTE"
    db.commit()
    expectError("CUENTA_SIN_VERIFICAR", institutions.lookupCandidate, db, team.moderator, team.id, "OPERADOR",
                "pendiente@example.com")
    expectError("CUENTA_SIN_VERIFICAR", institutions.invite, db, team.moderator, team.id, "OPERADOR",
                "pendiente@example.com", nombre="Otro", apellido="Nombre")


def test_no_se_duplican_vinculos_ni_invitaciones(db, mails, team):
    error = expectError("VINCULO_EXISTENTE", institutions.invite, db, team.moderator, team.id, "OPERADOR",
                        team.operator.correoElectronico)
    assert error.message == "Esta persona ya es operador/a de la institución."
    institutional(db, "nueva@example.com", "nueva")
    institutions.invite(db, team.moderator, team.id, "OPERADOR", "nueva@example.com")
    expectError("INVITACION_PENDIENTE", institutions.invite, db, team.moderator, team.id, "OPERADOR",
                "nueva@example.com")
    assert count(db, InstitutionUser) == 4


def test_indice_unico_impide_duplicados_vigentes_pero_no_historial(db, mails, team):
    relation = relationOf(db, team, team.operator)
    db.add(InstitutionUser(idInstitucion=team.id, idUsuarioInvitado=team.operator.idUsuario, rolInstitucion="OPERADOR",
                           estadoRelacion="PENDIENTE", origenVinculo="INVITACION",
                           idUsuarioInvitador=team.moderator.idUsuario))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    institutions.revokeMember(db, team.owner, team.id, "OPERADOR", relation.idInstitucionUsuario)
    again = institutions.invite(db, team.moderator, team.id, "OPERADOR", team.operator.correoElectronico)
    assert again.estadoRelacion == "PENDIENTE"


def test_una_cuenta_en_varias_instituciones_con_roles_distintos(db, mails, team):
    otra = newInstitution(db, team.operator, "87654321", "Laboratorio Norte")
    roles = {item.nombre: item.rolInstitucion for item in institutions.listMine(db, team.operator)}
    assert roles == {"Hospital X": "OPERADOR", "Laboratorio Norte": "PROPIETARIO"}
    assert otra.idInstitucion != team.id


def test_busqueda_limitada_por_cuenta(db, mails, team, monkeypatch):
    monkeypatch.setattr(institutions, "_lookupLimiter", RateLimiter(2, 600))
    for _ in range(2):
        expectError("USUARIO_NO_ENCONTRADO", institutions.lookupCandidate, db, team.moderator, team.id, "OPERADOR",
                    "nadie@example.com")
    expectError("DEMASIADAS_SOLICITUDES", institutions.lookupCandidate, db, team.moderator, team.id, "OPERADOR",
                "nadie@example.com")


# --- Permisos de consulta, modificación y revocación ----------------------------------------


def test_ajenos_no_ven_la_institucion_y_consumidores_reciben_403(db, mails, team):
    ajena = institutional(db, "ajena@example.com", "ajena")
    expectError("INSTITUCION_NO_ENCONTRADA", institutions.getDetail, db, ajena, team.id)
    expectError("PERMISO_INSUFICIENTE", institutions.getDetail, db, makeUser(db), team.id)


def test_operador_consulta_la_institucion_pero_no_el_equipo(db, mails, team):
    detail = institutions.getDetail(db, team.operator, team.id)
    # Consulta la institución y gestiona pacientes, pero no administra personal.
    # y consulta qué matriz de estimación se aplica (sin administrarla).
    assert detail.permisos == ["CONSULTAR_INSTITUCION", "CONSULTAR_PACIENTES", "GESTIONAR_PACIENTES", "CONSULTAR_MATRIZ",
                               "CONSULTAR_DISPOSITIVOS"]
    assert detail.rolInstitucion == "OPERADOR"
    expectError("PERMISO_INSUFICIENTE", institutions.listMembers, db, team.operator, team.id)
    members = institutions.listMembers(db, team.moderator, team.id)
    assert [m.rolInstitucion for m in members] == ["PROPIETARIO", "MODERADOR", "OPERADOR"]
    # Quien gestiona el equipo ve los correos (para contactar e invitar); el operador no accede al listado.
    assert {m.correoElectronico for m in members} == {"duenia@example.com", "moderador@example.com",
                                                      "operadora@example.com"}


def test_solo_el_propietario_modifica_los_datos(db, mails, team):
    expectError("PERMISO_INSUFICIENTE", institutions.updateInstitution, db, team.moderator, team.id,
                InstitutionUpdateRequest(nombre="Otro"))
    detail = institutions.updateInstitution(db, team.owner, team.id,
                                            InstitutionUpdateRequest(nombre="Hospital Central", descripcion="Sede"))
    assert (detail.nombre, detail.descripcion) == ("Hospital Central", "Sede")
    assert audits(db, "MODIFICAR_INSTITUCION")[0].idUsuario == team.owner.idUsuario
    with pytest.raises(ValidationError):  # el CUIT no se modifica
        InstitutionUpdateRequest(identificadorLegal=cuit("30", "87654321"))


def test_moderador_desvincula_operadores_pero_no_moderadores(db, mails, team):
    moderatorRelation = relationOf(db, team, team.moderator)
    expectError("PERMISO_INSUFICIENTE", institutions.revokeMember, db, team.moderator, team.id, "MODERADOR",
                moderatorRelation.idInstitucionUsuario)
    operatorRelation = relationOf(db, team, team.operator)
    institutions.revokeMember(db, team.moderator, team.id, "OPERADOR", operatorRelation.idInstitucionUsuario)
    ended = reload(db, InstitutionUser, operatorRelation.idInstitucionUsuario)
    assert ended.estadoRelacion == "BAJA" and ended.fechaBaja is not None
    assert mails[-1]["to"] == "operadora@example.com"  # ELIMINADO_INSTITUCION


def test_el_rol_del_cliente_no_cuenta_para_revocar(db, mails, team):
    """Un id de otro rol en la ruta de operadores no revoca a un moderador."""
    moderatorRelation = relationOf(db, team, team.moderator)
    expectError("MIEMBRO_NO_ENCONTRADO", institutions.revokeMember, db, team.owner, team.id, "OPERADOR",
                moderatorRelation.idInstitucionUsuario)
    assert relationOf(db, team, team.moderator).estadoRelacion == "ACTIVO"


def test_revocar_un_moderador_rige_en_sesiones_iniciadas_y_cancela_sus_invitaciones(db, mails, team):
    institutional(db, "nueva@example.com", "nueva")
    pending = institutions.invite(db, team.moderator, team.id, "OPERADOR", "nueva@example.com")
    assert institutions.getDetail(db, team.moderator, team.id).rolInstitucion == "MODERADOR"

    institutions.revokeMember(db, team.owner, team.id, "MODERADOR", relationOf(db, team, team.moderator).idInstitucionUsuario)
    # El rol no viaja en el token: la siguiente operación del moderador ya no tiene acceso.
    expectError("INSTITUCION_NO_ENCONTRADA", institutions.getDetail, db, team.moderator, team.id)
    expectError("INSTITUCION_NO_ENCONTRADA", institutions.invite, db, team.moderator, team.id, "OPERADOR",
                "otra@example.com")
    assert reload(db, InstitutionUser, pending.idInstitucionUsuario).estadoRelacion == "BAJA"
    # El operador que ya había incorporado sigue activo.
    assert relationOf(db, team, team.operator).estadoRelacion == "ACTIVO"


def test_invitacion_de_un_moderador_revocado_no_se_puede_aceptar(db, mails, team):
    nueva = institutional(db, "nueva@example.com", "nueva")
    pending = institutions.invite(db, team.moderator, team.id, "OPERADOR", "nueva@example.com")
    relation = db.get(InstitutionUser, pending.idInstitucionUsuario)
    # Aunque la invitación hubiera quedado pendiente, al aceptar se verifica que quien invitó conserve el permiso.
    moderatorRelation = relationOf(db, team, team.moderator)
    moderatorRelation.estadoRelacion, moderatorRelation.fechaBaja = "BAJA", nowForDb()
    db.commit()
    expectError("INVITACION_VENCIDA", institutions.respondInvitation, db, nueva, relation.idInstitucionUsuario, True)


# --- Eliminación lógica ---------------------------------------------------------------------


def deletion(**overrides) -> InstitutionDeletionRequest:
    return InstitutionDeletionRequest(**{"confirmacionNombre": "Hospital X", "password": PASSWORD, **overrides})


def addPatient(db, team) -> tuple[MeasurementProfile, Measurement, Device]:
    operatorRelation = relationOf(db, team, team.operator)
    profile = MeasurementProfile(
        idPerfilMedicion=uuid.uuid4(), tipoPerfil="INSTITUCIONAL", idInstitucionUsuarioResponsable=operatorRelation.idInstitucionUsuario,
        identificadorPseudonimo="PAC-ABC123", nombre="Juan", apellido="Paciente", dni="20111222",
        fechaNacimiento=date(1980, 1, 2), sexoModelo="MASCULINO",
    )
    device = Device(idDispositivo=uuid.uuid4(), codigoDispositivo=uuid.uuid4().hex, modeloSensor="MAX30102",
                    idInstitucionAsignada=team.id, idInstitucionUsuarioResponsable=operatorRelation.idInstitucionUsuario)
    db.add_all([profile, device])
    db.flush()
    measurement = Measurement(
        idMedicion=uuid.uuid4(), idPerfilMedicion=profile.idPerfilMedicion, idDispositivo=device.idDispositivo,
        modoMedicion="OXIMETRIA", estadoMedicion="COMPLETADA", edadAlMomento=46, sexoModelo="MASCULINO",
        condicionComida="POSTPRANDIAL", fechaHoraInicio=nowForDb() - timedelta(days=3),
        fechaHoraUltimaComida=nowForDb() - timedelta(days=3, hours=2), spo2=97, frecuenciaCardiaca=72,
        modeloSensorAlMomento="MAX30102",
    )
    db.add(measurement)
    db.commit()
    return profile, measurement, device


@pytest.mark.parametrize("actor", ["moderator", "operator"])
def test_solo_el_propietario_elimina(db, mails, team, actor):
    expectError("PERMISO_INSUFICIENTE", institutions.deleteInstitution, db, getattr(team, actor), team.id, deletion())
    assert reload(db, Institution, team.id).estado == "ACTIVA"


def test_eliminacion_exige_confirmacion_y_reautenticacion(db, mails, team):
    expectError("CONFIRMACION_INVALIDA", institutions.deleteInstitution, db, team.owner, team.id,
                deletion(confirmacionNombre="Hospital"))
    expectError("PASSWORD_REQUERIDA", institutions.deleteInstitution, db, team.owner, team.id, deletion(password=None))
    expectError("PASSWORD_INCORRECTA", institutions.deleteInstitution, db, team.owner, team.id,
                deletion(password="OtraClave#2026"))
    assert reload(db, Institution, team.id).estado == "ACTIVA"


def test_eliminacion_con_mfa_exige_el_codigo(db, mails, team):
    secret = enableMfa(db, team.owner)
    expectError("CODIGO_MFA_REQUERIDO", institutions.deleteInstitution, db, team.owner, team.id, deletion())
    institutions.deleteInstitution(db, team.owner, team.id, deletion(codigo=totpCode(secret)))
    assert reload(db, Institution, team.id).estado == "CERRADA"


def test_eliminacion_logica_completa(db, mails, team):
    profile, measurement, device = addPatient(db, team)
    institutional(db, "nueva@example.com", "nueva")
    pending = institutions.invite(db, team.moderator, team.id, "OPERADOR", "nueva@example.com")
    mails.clear()

    institutions.deleteInstitution(db, team.owner, team.id, deletion())

    # Lógica, no física: la fila existe, CERRADA, con fecha; el responsable queda en la auditoría.
    institution = reload(db, Institution, team.id)
    assert institution is not None and institution.estado == "CERRADA"
    [audit] = audits(db, "ELIMINAR_INSTITUCION")
    assert audit.idUsuario == team.owner.idUsuario and audit.resultado == "EXITO"
    # Todos los vínculos e invitaciones terminan; las cuentas personales siguen activas.
    relations = db.scalars(select(InstitutionUser).where(InstitutionUser.idInstitucion == team.id)).all()
    assert {r.estadoRelacion for r in relations} == {"BAJA"} and all(r.fechaBaja for r in relations)
    assert reload(db, InstitutionUser, pending.idInstitucionUsuario).estadoRelacion == "BAJA"
    for user in (team.owner, team.moderator, team.operator):
        assert reload(db, User, user.idUsuario).estado == "ACTIVO"
    # Cierre con período de conservación de 12 meses en el propio perfil: datos conservados, sin acceso operativo.
    profile = reload(db, MeasurementProfile, profile.idPerfilMedicion)
    assert (profile.nombre, profile.dni) == ("Juan", "20111222") and profile.fechaDepuracionDatosPersonales is None
    assert profile.fechaExpiracionDatosPersonales == institutions.addMonths(institution.fechaActualizacion, 12)
    kept = reload(db, Measurement, measurement.idMedicion)
    assert kept is not None and kept.edadAlMomento == 46
    assert reload(db, Device, device.idDispositivo).idInstitucionUsuarioResponsable is None
    # Aviso a quienes tenían acceso.
    assert {m["to"] for m in mails} == {"duenia@example.com", "moderador@example.com", "operadora@example.com"}


def test_institucion_eliminada_no_permite_operaciones(db, mails, team):
    nueva = institutional(db, "nueva@example.com", "nueva")
    pending = institutions.invite(db, team.moderator, team.id, "OPERADOR", "nueva@example.com")
    operatorRelation = relationOf(db, team, team.operator)
    institutions.deleteInstitution(db, team.owner, team.id, deletion())

    for user in (team.owner, team.moderator, team.operator):
        assert institutions.listMine(db, user) == []
        expectError("INSTITUCION_NO_ENCONTRADA", institutions.getDetail, db, user, team.id)
    expectError("INSTITUCION_NO_ENCONTRADA", institutions.invite, db, team.moderator, team.id, "OPERADOR",
                "nueva@example.com")
    expectError("INSTITUCION_NO_ENCONTRADA", institutions.deleteInstitution, db, team.owner, team.id, deletion())
    expectError("INVITACION_NO_ENCONTRADA", institutions.respondInvitation, db, nueva, pending.idInstitucionUsuario, True)
    assert institutions.listInvitations(db, nueva) == []
    # No se registran pacientes (ni sus mediciones) en una institución eliminada.
    expectError("RESPONSABLE_INVALIDO", buildInstitutionalProfile, reload(db, InstitutionUser, operatorRelation.idInstitucionUsuario),
                InstitutionalProfileCreate(nombre="Ana", apellido="Paz", dni="30111222", fechaNacimiento=date(1990, 1, 1), sexoModelo="FEMENINO"))


def test_cuit_de_una_institucion_eliminada_queda_reservado(db, mails, team):
    institutions.deleteInstitution(db, team.owner, team.id, deletion())
    # No se crea otra institución con ese CUIT: corresponde reabrir la existente (solo su último propietario).
    error = expectError("INSTITUCION_CERRADA", newInstitution, db, team.moderator)
    assert "Solo quien fue su último propietario" in error.message
    assert count(db, Institution) == 1
    # La propietaria puede eliminar su cuenta: ya no es propietaria de una institución activa.
    assert findBlocker(db, reload(db, User, team.owner.idUsuario)) is None


# --- Confirmación de registro por correo -----------------------------------------------------------


def test_crear_institucion_notifica_al_propietario_despues_del_commit(db, mails, engine, monkeypatch):
    seen = []
    original = sender.sendHtmlEmail

    def checkCommitted(*args, **kwargs):
        with engine.connect() as connection:
            seen.append(connection.execute(text("SELECT COUNT(*) FROM dbo.Institucion")).scalar())
        return original(*args, **kwargs)

    monkeypatch.setattr(sender, "sendHtmlEmail", checkCommitted)
    owner = institutional(db, "duenia@example.com", "duenia")
    institution = newInstitution(db, owner)
    assert seen == [1]
    [mail] = mails
    assert mail["to"] == "duenia@example.com"
    assert mail["subject"] == "GlucoLume — Institución registrada correctamente"
    for fragment in ("Hospital X", "Hospital", institution.identificadorLegal, "Propietario/a",
                     f"/app/instituciones/{institution.idInstitucion}"):
        assert fragment in mail["html"], fragment
    [notice] = audits(db, notifications.ACCION_INSTITUCION)
    assert notice.resultado == "EXITO" and notice.idRegistro == institution.idInstitucion


def test_fallo_smtp_no_revierte_la_institucion_y_el_reintento_no_duplica(db, mails, monkeypatch):
    original = sender.sendHtmlEmail
    monkeypatch.setattr(sender, "sendHtmlEmail", lambda *a, **k: (_ for _ in ()).throw(OSError("SMTP caído")))
    owner = institutional(db, "duenia@example.com", "duenia")
    institution = newInstitution(db, owner)
    assert reload(db, Institution, institution.idInstitucion).estado == "ACTIVA"
    assert [a.resultado for a in audits(db, notifications.ACCION_INSTITUCION)] == ["FALLO"]
    expectError("NOTIFICACION_NO_ENVIADA", institutions.resendCreationNotice, db, owner, institution.idInstitucion)
    monkeypatch.setattr(sender, "sendHtmlEmail", original)
    institutions.resendCreationNotice(db, owner, institution.idInstitucion)
    expectError("NOTIFICACION_YA_ENVIADA", institutions.resendCreationNotice, db, owner, institution.idInstitucion)
    assert len(mails) == 1


def test_solo_el_propietario_reenvia_la_confirmacion(db, mails, team):
    for actor in (team.moderator, team.operator):
        expectError("PERMISO_INSUFICIENTE", institutions.resendCreationNotice, db, actor, team.id)
