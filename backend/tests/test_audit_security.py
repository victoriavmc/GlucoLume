# Pruebas de la auditoría administrativa y el monitoreo de seguridad (docs/AUDITORIA_ADMINISTRATIVA.md).
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_audit_security.py -v
#
# Usan el esquema SQLite temporal de test_account_deletion.py y datos de prueba: no tocan SQL Server ni ningún sistema externo. Los ataques
# simulados son solicitudes a la API en memoria (TestClient) con datos inventados.

import json
import re
import uuid
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.dialects import mssql
from sqlalchemy.orm import sessionmaker

from app.core import requestContext
from app.core.config import getSettings
from app.core.exceptions import AuthError
from app.db.session import getDb
from app.main import app
from app.models.audit import Audit
from app.models.auditContext import AuditContext
from app.models.localCredential import LocalCredential
from app.services import auditClassification as classification
from app.services import platformDashboard
from app.services import auditQuery, auditRetention, exportAudit, securityDetection, securityMonitor
from app.services import auth as authService
from app.services import institution as institutions
from app.services.audit import hashIdentifier, registerEvent
from app.utils.timeZone import nowForDb
from tests.test_account_deletion import EMAIL, PASSWORD, db, engine, mails, makeUser  # noqa: F401 - fixtures
from tests.test_audit import admin, api  # noqa: F401 - fixtures
from tests.test_institutions import expectError, institutional, newInstitution, team  # noqa: F401 - fixtures
from tests.test_matrices import north  # noqa: F401 - fixtures
from tests.test_mfa_flow import activate

WRONG = "OtraClave#2026"
CHROME = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
# Funciones reales del monitor: el conftest las reemplaza por una que no escribe; estas pruebas necesitan la verdadera.
REAL_PERSIST_BURST, REAL_PERSIST_RATE_LIMIT = securityMonitor.persistBurst, securityMonitor.persistRateLimit
REAL_ALERT = securityMonitor.alertAdministrator


# --- Utilidades ----------------------------------------------------------------------------------------------------------------


def client(ip="203.0.113.7", **headers) -> TestClient:
    return TestClient(app, raise_server_exceptions=False, client=(ip, 50000), headers=headers)


def events(db, accion=None, **where):
    db.expire_all()
    query = select(Audit).order_by(Audit.fechaHora, Audit.idAuditoria)
    if accion:
        query = query.where(Audit.accion == accion)
    for name, value in where.items():
        query = query.where(getattr(Audit, name) == value)
    return list(db.scalars(query))


def contextOf(db, audit) -> AuditContext | None:
    db.expire_all()
    return db.get(AuditContext, audit.idAuditoria)


def everything(db) -> str:
    """Todo el texto de las tablas de auditoría: para comprobar que un secreto no quedó en NINGUNA columna."""
    parts = []
    for table in ("Auditoria", "AuditoriaContexto"):
        for row in db.execute(text(f"SELECT * FROM dbo.{table}")):
            parts.extend(str(value) for value in row)
    return "\n".join(parts)


def plant(db, accion, *, resultado="FALLO", user=None, ip=None, motivo=None, minutes=0, tipo="LOGIN", modulo="CUENTA", institution=None,
          fingerprint=None, correlation=None, agent=None, at=None) -> Audit:
    """Un evento con fecha y contexto elegidos (para probar ventanas y retención sin esperar)."""
    audit = Audit(idUsuario=user.idUsuario if user is not None else None, tipoEvento=tipo, modulo=modulo, idInstitucion=institution, accion=accion,
                  resultado=resultado, fechaHora=(at or nowForDb()) - timedelta(minutes=minutes))
    if ip or motivo or fingerprint or correlation or agent:
        audit.contexto = AuditContext(ipOrigen=ip, motivo=motivo, identificadorHash=fingerprint, idCorrelacion=correlation, agenteUsuario=agent)
    db.add(audit)
    db.commit()
    return audit


def login(http, identifier=EMAIL, password=WRONG):
    return http.post("/api/v1/auth/login", json={"identificador": identifier, "password": password})


def items(response):
    assert response.status_code == 200, response.text
    return response.json()["items"]


@pytest.fixture
def web(db, api):
    """Cliente HTTP (la base de la prueba) sin identidad: los endpoints públicos no la usan."""
    return client


# --- Contexto de la solicitud: IP, cliente y correlación ------------------------------------------------------------------------


def test_un_login_fallido_guarda_ip_cliente_correlacion_y_motivo(db, mails, web):
    user = makeUser(db)
    response = login(web("203.0.113.7", **{"User-Agent": CHROME, "X-Request-ID": "req-abc12345"}))
    assert response.status_code == 401
    assert response.headers["X-Request-ID"] == "req-abc12345"
    [failure] = events(db, "LOGIN_LOCAL", idUsuario=user.idUsuario)
    context = contextOf(db, failure)
    assert failure.resultado == "FALLO" and failure.tipoEvento == "LOGIN"
    assert (context.ipOrigen, context.idCorrelacion, context.motivo) == ("203.0.113.7", "req-abc12345", "PASSWORD_INCORRECTA")
    assert context.agenteUsuario == "Chrome · Windows · Computadora"


def test_un_identificador_de_correlacion_inseguro_se_reemplaza(db, mails, web):
    makeUser(db)
    for hostile in ("x" * 200, "corto", "con espacios y <script>", "a;b;c;d;e;f;g;h"):
        response = login(web(**{"X-Request-ID": hostile}))
        sent = response.headers["X-Request-ID"]
        assert sent != hostile and re.fullmatch(r"[A-Za-z0-9._-]{8,64}", sent)
    [first, *_] = events(db, "LOGIN_LOCAL")
    assert re.fullmatch(r"[0-9a-f]{32}", contextOf(db, first).idCorrelacion)


def test_un_cliente_que_no_es_un_navegador_conserva_su_identificacion_acotada(db, mails, web):
    makeUser(db)
    login(web(**{"User-Agent": "sqlmap/1.7.2#stable (https://sqlmap.org)\x00\x01" + "z" * 300}))
    agent = contextOf(db, events(db, "LOGIN_LOCAL")[0]).agenteUsuario
    assert agent.startswith("sqlmap/1.7.2") and len(agent) <= 100 and all(c.isprintable() for c in agent)


def test_fuera_de_una_solicitud_no_se_inventa_contexto(db, mails):
    registerEvent(db, "CRUD", "CREAR_GRUPO", True)
    db.commit()
    assert contextOf(db, events(db, "CREAR_GRUPO")[0]) is None


def test_el_contexto_se_vincula_a_los_eventos_de_cualquier_modulo_durante_la_solicitud(db, mails):
    token = requestContext.bind(requestContext.RequestContext("corr-123456789", "198.51.100.4", "Firefox · Linux · Computadora"))
    try:
        registerEvent(db, "CRUD", "CREAR_GRUPO", True)
        db.commit()
    finally:
        requestContext.unbind(token)
    context = contextOf(db, events(db, "CREAR_GRUPO")[0])
    assert (context.idCorrelacion, context.ipOrigen) == ("corr-123456789", "198.51.100.4")


# --- Accesos fallidos ------------------------------------------------------------------------------------------------------------


def test_cuenta_inexistente_se_audita_sin_guardar_lo_escrito(db, mails, web):
    typed = "fantasma.secreto@example.com"
    login(web(), typed)
    [event] = events(db, "LOGIN_LOCAL")
    context = contextOf(db, event)
    assert event.idUsuario is None and event.resultado == "FALLO"
    assert (context.motivo, context.identificadorHash) == ("CUENTA_INEXISTENTE", hashIdentifier(typed))
    assert typed not in everything(db) and "fantasma" not in everything(db)


def test_cuenta_inexistente_y_contrasenia_incorrecta_responden_igual(db, mails, web):
    makeUser(db)
    existing, missing = login(web(), EMAIL), login(web(), "nadie@example.com")
    assert (existing.status_code, existing.json()) == (missing.status_code, missing.json())
    assert set(existing.headers) - {"x-request-id"} == set(missing.headers) - {"x-request-id"}


def test_el_mismo_identificador_inexistente_se_reconoce_sin_guardarlo(db, mails, web):
    for _ in range(3):
        login(web(), "  Repetido@Example.com ")
    login(web(), "otro@example.com")
    hashes = [contextOf(db, e).identificadorHash for e in events(db, "LOGIN_LOCAL")]
    assert hashes[0] == hashes[1] == hashes[2] != hashes[3]


def test_la_contrasenia_escrita_nunca_queda_en_la_auditoria(db, mails, web):
    makeUser(db)
    login(web(), EMAIL, "ContraseniaEscrita#9876")
    login(web(), "ContraseniaEscrita#9876@example.com", "ContraseniaEscrita#9876")
    assert "ContraseniaEscrita" not in everything(db)


def test_cuenta_inactiva_y_sin_verificar_se_registran_con_su_motivo(db, mails, web):
    makeUser(db).estado = "BLOQUEADO"
    db.commit()
    response = login(web(), EMAIL, PASSWORD)
    assert response.status_code == 403
    pending = makeUser(db, email="pendiente@example.com", usuario="pendiente")
    pending.estado = "PENDIENTE"
    db.commit()
    login(web(), "pendiente@example.com", PASSWORD)
    motives = [contextOf(db, e).motivo for e in events(db, "LOGIN_LOCAL")]
    assert motives == ["CUENTA_INACTIVA", "CORREO_NO_VERIFICADO"]


def test_el_bloqueo_temporal_es_un_evento_confirmado_propio(db, mails, web):
    user = makeUser(db)
    for _ in range(3):
        login(web(), EMAIL)
    login(web(), EMAIL, PASSWORD)  # cuenta bloqueada: ni siquiera la contraseña correcta entra
    motives = sorted((e.accion, contextOf(db, e).motivo) for e in events(db) if e.tipoEvento == "LOGIN")  # el 3.º fallo y el bloqueo comparten instante
    assert motives == sorted([("LOGIN_LOCAL", "PASSWORD_INCORRECTA")] * 3 + [("BLOQUEO_TEMPORAL_CUENTA", "INTENTOS_EXCEDIDOS"), ("LOGIN_LOCAL", "CUENTA_BLOQUEADA")])
    [lock] = events(db, "BLOQUEO_TEMPORAL_CUENTA")
    assert lock.idUsuario == user.idUsuario and lock.modulo == "SEGURIDAD"
    assert classification.classify(lock.accion, lock.resultado) == classification.CONFIRMADO


def test_segundo_factor_fallido_y_bloqueado(db, mails):
    user = makeUser(db)
    activate(db, user)
    response = authService.loginLocal(db, EMAIL, PASSWORD)
    assert response.estado == "MFA_REQUERIDO"
    codes = []
    for _ in range(6):
        with pytest.raises(AuthError) as error:
            authService.verifyMfaChallenge(db, response.challengeToken, "000000", None)
        codes.append(error.value.code)
    assert codes[-1] == "MFA_BLOQUEADO"
    motives = [contextOf(db, e).motivo for e in events(db, "MFA_CODIGO_INVALIDO")]
    assert motives == ["CODIGO_MFA_INVALIDO"] * 5 + ["MFA_BLOQUEADO"]  # cinco códigos incorrectos, y un intento más con el factor bloqueado
    [lock] = events(db, "BLOQUEO_TEMPORAL_CUENTA")
    assert lock.modulo == "SEGURIDAD" and contextOf(db, lock).motivo == "MFA_BLOQUEADO"
    assert "000000" not in everything(db)


def test_acceso_fallido_de_personal_de_una_sola_institucion_queda_en_su_auditoria(db, mails, team, web):
    login(web(), team.operator.correoElectronico)
    [event] = events(db, "LOGIN_LOCAL", idUsuario=team.operator.idUsuario)
    assert event.idInstitucion == team.id


def test_cuenta_en_varias_instituciones_no_ensucia_la_auditoria_de_ninguna(db, mails, team, north, web):
    invitation = institutions.invite(db, north.moderator, north.id, "OPERADOR", team.operator.correoElectronico,
                                     datos={"matriculaProfesional": "MP-9"})
    institutions.respondInvitation(db, team.operator, invitation.idInstitucionUsuario, accept=True)
    login(web(), team.operator.correoElectronico)
    [event] = events(db, "LOGIN_LOCAL", idUsuario=team.operator.idUsuario)
    assert event.idInstitucion is None  # el intento sobre la cuenta no ocurrió en ninguna institución en particular


# --- Consulta: ámbitos, aislamiento y datos sensibles ------------------------------------------------------------------------------


def test_la_administracion_ve_ip_y_correlacion_la_institucion_no(db, mails, team, admin, api, web):
    login(web("203.0.113.50", **{"X-Request-ID": "corr-operadora-1"}), team.operator.correoElectronico)
    mine = items(api(admin).get(f"/api/v1/audit?idInstitucion={team.id}&categoria=ACCESOS_FALLIDOS"))
    assert [(i["ipOrigen"], i["idCorrelacion"], i["motivo"]) for i in mine] == [("203.0.113.50", "corr-operadora-1", "PASSWORD_INCORRECTA")]
    seen = items(api(team.owner).get(f"/api/v1/institutions/{team.id}/audit?categoria=ACCESOS_FALLIDOS"))
    assert len(seen) == 1 and seen[0]["motivo"] == "PASSWORD_INCORRECTA" and seen[0]["motivoEtiqueta"] == "Contraseña incorrecta"
    assert seen[0]["usuario"]  # el personal sí se identifica por su nombre
    assert all(seen[0][key] is None for key in ("ipOrigen", "agenteUsuario", "idCorrelacion", "referenciaIdentificador"))
    text_seen = json.dumps(seen)
    assert "203.0.113.50" not in text_seen and "corr-operadora-1" not in text_seen
    detail = api(team.owner).get(f"/api/v1/institutions/{team.id}/audit/events/{seen[0]['idAuditoria']}").json()
    assert detail["ipOrigen"] is None and "203.0.113.50" not in json.dumps(detail)
    adminDetail = api(admin).get(f"/api/v1/audit/events/{mine[0]['idAuditoria']}").json()
    assert adminDetail["ipOrigen"] == "203.0.113.50"


def test_los_filtros_de_red_no_existen_para_una_institucion(db, mails, team, north, api, web):
    login(web("203.0.113.50"), team.operator.correoElectronico)
    own = api(team.owner)
    for param in ("ip=203.0.113.50", "idCorrelacion=cualquiera", "identificador=a@b.com", "refIdentificador=abc", f"idCuenta={team.operator.idUsuario}"):
        # el parámetro se ignora (el ámbito sale de la ruta): no sirve para buscar por IP ni por cuenta
        filtered = items(own.get(f"/api/v1/institutions/{team.id}/audit?{param}&tamanioPagina=100"))
        assert len(filtered) == len(items(own.get(f"/api/v1/institutions/{team.id}/audit?tamanioPagina=100")))


def test_no_se_mezclan_eventos_de_distintas_instituciones(db, mails, team, north, api, web):
    login(web("203.0.113.50"), team.operator.correoElectronico)
    login(web("203.0.113.60"), north.operator.correoElectronico)
    ours = items(api(team.owner).get(f"/api/v1/institutions/{team.id}/audit?tamanioPagina=100"))
    theirs = items(api(north.owner).get(f"/api/v1/institutions/{north.id}/audit?tamanioPagina=100"))
    assert {i["idInstitucion"] for i in ours} == {str(team.id)} and {i["idInstitucion"] for i in theirs} == {str(north.id)}
    ours_ids, theirs_ids = {i["idAuditoria"] for i in ours}, {i["idAuditoria"] for i in theirs}
    assert not ours_ids & theirs_ids
    foreign = [i["idAuditoria"] for i in theirs if i["accion"] == "LOGIN_LOCAL"][0]
    assert api(team.owner).get(f"/api/v1/institutions/{team.id}/audit/events/{foreign}").status_code == 404
    assert api(north.owner).get(f"/api/v1/institutions/{team.id}/audit").status_code in (403, 404)


def test_se_distingue_al_personal_de_la_administracion_en_la_auditoria_de_la_institucion(db, mails, team, admin, api):
    registerEvent(db, "CRUD", "MODIFICAR_INSTITUCION", True, admin.idUsuario, "Institucion", team.id)
    registerEvent(db, "CRUD", "MODIFICAR_INSTITUCION", True, team.owner.idUsuario, "Institucion", team.id)
    db.commit()
    owner = api(team.owner)
    both = [i for i in items(owner.get(f"/api/v1/institutions/{team.id}/audit?accion=MODIFICAR_INSTITUCION"))]
    assert sorted(i["origenActor"] for i in both) == ["PLATAFORMA", "USUARIO"]
    platform = items(owner.get(f"/api/v1/institutions/{team.id}/audit?origenActor=PLATAFORMA"))
    assert platform and {i["origenActor"] for i in platform} == {"PLATAFORMA"} and platform[0]["usuario"] == "Administración de GlucoLume"
    staff = items(owner.get(f"/api/v1/institutions/{team.id}/audit?origenActor=USUARIO&accion=MODIFICAR_INSTITUCION"))
    assert [i["origenActor"] for i in staff] == ["USUARIO"]
    anonymous = items(api(admin).get("/api/v1/audit?origenActor=SISTEMA&tamanioPagina=100"))
    assert all(i["origenActor"] == "SISTEMA" for i in anonymous)


def test_los_registros_internos_de_la_administracion_no_llegan_a_la_institucion(db, mails, team, admin, api):
    registerEvent(db, "PERMISO", "REVOCAR_MODERADOR_PLATAFORMA", True, admin.idUsuario, "Usuario", admin.idUsuario, idInstitucion=team.id, modulo="PLATAFORMA")
    db.commit()
    seen = items(api(team.owner).get(f"/api/v1/institutions/{team.id}/audit?tamanioPagina=100"))
    assert "REVOCAR_MODERADOR_PLATAFORMA" not in {i["accion"] for i in seen}
    mine = items(api(admin).get(f"/api/v1/audit?idInstitucion={team.id}&modulo=PLATAFORMA"))
    assert [i["accion"] for i in mine] == ["REVOCAR_MODERADOR_PLATAFORMA"]
    hidden = mine[0]["idAuditoria"]
    assert api(team.owner).get(f"/api/v1/institutions/{team.id}/audit/events/{hidden}").status_code == 404


def test_solo_la_administracion_usa_las_vistas_de_seguridad_y_el_intento_queda_registrado(db, mails, team, api):
    stranger = makeUser(db, email="persona@example.com", usuario="persona")
    routes = ["/api/v1/audit/security/signals", "/api/v1/audit/accounts?q=perez", f"/api/v1/audit/accounts/{stranger.idUsuario}",
              "/api/v1/audit/institutions", "/api/v1/audit"]
    for actor in (stranger, team.operator, team.moderator, team.owner):
        http = api(actor)
        for route in routes:
            assert http.get(route).status_code == 403, (actor.usuario, route)
    denied = events(db, "CONSULTAR_AUDITORIA")
    assert len(denied) >= 4 * len(routes) and all(e.resultado == "FALLO" and e.modulo == "AUDITORIA" for e in denied)
    assert {e.idUsuario for e in denied} == {stranger.idUsuario, team.operator.idUsuario, team.moderator.idUsuario, team.owner.idUsuario}


def test_ficha_de_cuenta_enmascara_el_correo_deja_constancia_y_no_trae_datos_clinicos(db, mails, team, admin, api):
    http = api(admin)
    found = http.get("/api/v1/audit/accounts?q=operadora").json()
    assert [f["usuario"] for f in found] == ["operadora"] and found[0]["correo"].startswith("op") and "@example.com" in found[0]["correo"]
    assert "operadora@example.com" not in json.dumps(found)
    header = http.get(f"/api/v1/audit/accounts/{team.operator.idUsuario}").json()
    assert header["instituciones"][0]["rol"] == "OPERADOR" and header["mfaHabilitado"] is False
    assert not {"passwordHash", "dni", "mediciones", "glucosa", "fechaNacimiento", "sexo"} & set(header)
    [consulted] = events(db, "CONSULTAR_AUDITORIA_CUENTA")
    assert (consulted.idUsuario, consulted.idRegistro, consulted.resultado) == (admin.idUsuario, team.operator.idUsuario, "EXITO")
    assert http.get("/api/v1/audit/accounts?q=ab").status_code == 422
    assert http.get(f"/api/v1/audit/accounts/{uuid.uuid4()}").status_code == 404


def test_eventos_de_una_cuenta_como_autora_y_como_afectada(db, mails, team, admin, api, web):
    login(web(), team.operator.correoElectronico)
    registerEvent(db, "PERMISO", "REVOCAR_MIEMBRO_INSTITUCION", True, team.owner.idUsuario, "Usuario", team.operator.idUsuario)
    db.commit()
    mine = items(api(admin).get(f"/api/v1/audit?idCuenta={team.operator.idUsuario}&tamanioPagina=100"))
    actions = {i["accion"] for i in mine}
    assert {"LOGIN_LOCAL", "REVOCAR_MIEMBRO_INSTITUCION"} <= actions  # la cuenta como autora (login) y como afectada (baja)
    others = items(api(admin).get(f"/api/v1/audit?idCuenta={team.moderator.idUsuario}&tamanioPagina=100"))
    assert not {i["idAuditoria"] for i in others} & {i["idAuditoria"] for i in mine if i["accion"] == "LOGIN_LOCAL"}


def test_busqueda_por_identificador_encuentra_la_cuenta_y_los_intentos_sobre_un_identificador_inexistente(db, mails, admin, api, web):
    user = makeUser(db)
    login(web(), EMAIL)
    login(web(), "fantasma@example.com")
    login(web(), "fantasma@example.com")
    http = api(admin)
    assert len(items(http.get(f"/api/v1/audit?identificador={EMAIL}"))) == 1
    ghosts = items(http.get("/api/v1/audit?identificador=Fantasma@example.com"))
    assert len(ghosts) == 2 and all(g["usuario"] == "Cuenta no registrada" and g["motivo"] == "CUENTA_INEXISTENTE" for g in ghosts)
    ref = ghosts[0]["referenciaIdentificador"]
    assert ref == hashIdentifier("fantasma@example.com")[:8] and "fantasma" not in json.dumps(ghosts)
    full = hashIdentifier("fantasma@example.com")
    assert len(items(http.get(f"/api/v1/audit?refIdentificador={full}"))) == 2
    assert user.idUsuario  # la cuenta existente no se confunde con el identificador inexistente


def test_filtros_por_fecha_tipo_resultado_motivo_correlacion_e_ip(db, mails, admin, api, web):
    makeUser(db)
    login(web("203.0.113.7", **{"X-Request-ID": "corr-primero-1"}), EMAIL)
    login(web("203.0.113.99", **{"X-Request-ID": "corr-segundo-2"}), "otro@example.com")
    http = api(admin)

    def total(query):
        response = http.get(f"/api/v1/audit?{query}")
        assert response.status_code == 200, response.text
        return response.json()["total"]

    assert total("idCorrelacion=corr-primero-1") == 1 and total("idCorrelacion=no-existe-9999") == 0
    assert total("ip=203.0.113.7") == 1 and total("ip=203.0.113.*") == 2 and total("ip=198.51.100.1") == 0
    assert total("motivo=CUENTA_INEXISTENTE") == 1 and total("motivo=PASSWORD_INCORRECTA") == 1
    assert total("categoria=ACCESOS_FALLIDOS") == 2 and total("resultado=EXITO&categoria=ACCESOS_FALLIDOS") == 0
    assert total("clasificacion=OPERATIVO") == 2 and total("clasificacion=CONFIRMADO") == 0
    today = date.today().isoformat()
    assert total(f"desde={today}&hasta={today}&categoria=ACCESOS_FALLIDOS") == 2
    assert total(f"desde={(date.today() + timedelta(days=1)).isoformat()}") == 0


def test_los_limites_del_dia_en_hora_de_argentina_son_inclusivos_y_exclusivos(db, mails, admin, api):
    day = date.today() - timedelta(days=3)
    from datetime import datetime as dt, time as tm

    plant(db, "LOGIN_LOCAL", at=dt.combine(day, tm(23, 59, 59)), minutes=0)
    plant(db, "LOGIN_LOCAL", at=dt.combine(day + timedelta(days=1), tm(0, 0, 0)), minutes=0)
    http = api(admin)
    only = http.get(f"/api/v1/audit?desde={day}&hasta={day}&accion=LOGIN_LOCAL").json()
    assert only["total"] == 1
    assert only["items"][0]["fechaHora"].endswith("-03:00") and only["items"][0]["fechaHora"].startswith(f"{day}T23:59:59")


def test_la_paginacion_es_del_servidor_y_esta_acotada(db, mails, admin, api):
    for minute in range(30):
        plant(db, "LOGIN_LOCAL", minutes=minute)
    http = api(admin)
    first = http.get("/api/v1/audit?accion=LOGIN_LOCAL&tamanioPagina=10&pagina=1").json()
    third = http.get("/api/v1/audit?accion=LOGIN_LOCAL&tamanioPagina=10&pagina=3").json()
    assert first["total"] == third["total"] == 30 and len(first["items"]) == len(third["items"]) == 10
    assert not {i["idAuditoria"] for i in first["items"]} & {i["idAuditoria"] for i in third["items"]}
    assert http.get("/api/v1/audit?tamanioPagina=101").status_code == 422
    assert http.get("/api/v1/audit?pagina=0").status_code == 422
    assert len(http.get("/api/v1/audit?tamanioPagina=100").json()["items"]) <= 100


@pytest.mark.parametrize("payload", ["' OR 1=1 --", "'; DROP TABLE Auditoria; --", "%' UNION SELECT passwordHash FROM CredencialLocal --", "\\' OR ''='"])
def test_los_filtros_se_parametrizan_y_un_intento_de_inyeccion_no_encuentra_nada(db, mails, admin, api, payload):
    makeUser(db)
    plant(db, "LOGIN_LOCAL", ip="203.0.113.7", motivo="PASSWORD_INCORRECTA", correlation="corr-real-0001")
    http = api(admin)
    for name in ("usuario", "accion", "identificador", "idCorrelacion", "motivo", "refIdentificador"):
        response = http.get("/api/v1/audit", params={name: payload})
        assert response.status_code in (200, 422), (name, response.text)
        if response.status_code == 200:
            assert response.json()["total"] == 0, (name, payload)
    assert http.get("/api/v1/audit", params={"ip": payload}).status_code in (400, 422)  # una IP solo admite dígitos, hexadecimales, punto, dos puntos y *
    assert db.scalar(select(func.count()).select_from(Audit)) >= 1  # la tabla sigue ahí
    assert "passwordHash" not in http.get("/api/v1/audit").text


def test_el_sql_generado_usa_parametros_y_no_concatena_la_entrada():
    payload = "x' OR 1=1; --"
    query = auditQuery._filtered(select(Audit), usuario=payload, accion=payload, identificador=payload, idCorrelacion=payload, motivo=payload,
                                 refIdentificador=payload, ip="203.0.113.1")
    compiled = query.compile(dialect=mssql.dialect())
    assert "OR 1=1" not in str(compiled) and "DROP" not in str(compiled)
    assert sum(value == payload or payload in str(value) for value in compiled.params.values()) >= 4  # la entrada viaja como parámetro enlazado


def test_la_respuesta_nunca_trae_secretos_ni_cuerpos(db, mails, admin, api, web):
    user = makeUser(db)
    login(web(), EMAIL, "Secreta#Clave2026")
    activate(db, user)
    body = api(admin).get("/api/v1/audit?tamanioPagina=100").text.lower()
    hash_ = db.scalar(select(LocalCredential.passwordHash)).lower()
    for forbidden in ("secreta#clave2026", hash_, "secretocifrado", "authorization", "cookie", "bearer ", "refreshtoken"):
        assert forbidden not in body


def test_la_api_de_auditoria_es_de_solo_lectura_tambien_las_rutas_nuevas(admin, api):
    for route in app.routes:
        path = getattr(route, "path", "")
        if path.startswith("/api/v1/audit") or (path.startswith("/api/v1/institutions/") and "/audit" in path):
            assert set(route.methods) <= {"GET", "HEAD", "OPTIONS"}, path
    client_ = api(admin)
    for path in ("/api/v1/audit", "/api/v1/audit/accounts", "/api/v1/audit/security/signals", "/api/v1/audit/events/" + str(uuid.uuid4())):
        for method in ("post", "put", "patch", "delete"):
            assert getattr(client_, method)(path).status_code in (404, 405)


# --- Clasificación ---------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("accion", "resultado", "tipo", "clasificacion", "severidad"), [
    ("LOGIN_LOCAL", "FALLO", "LOGIN", "OPERATIVO", "ADVERTENCIA"),  # un error de autenticación aislado NO es un ataque
    ("LOGIN_PWD", "EXITO", "LOGIN", "INFORMATIVO", "EXITO"),
    ("LOGIN_PWD_MFA_PENDIENTE", "EXITO", "LOGIN", "INFORMATIVO", "INFO"),
    ("BLOQUEO_TEMPORAL_CUENTA", "FALLO", "LOGIN", "CONFIRMADO", "CRITICO"),
    ("REFRESH_REUTILIZADO", "FALLO", "LOGIN", "CONFIRMADO", "CRITICO"),
    ("LIMITE_SOLICITUDES_EXCEDIDO", "FALLO", "ACCESO", "CONFIRMADO", "CRITICO"),
    ("RAFAGA_RECHAZOS_HTTP", "FALLO", "ACCESO", "SOSPECHOSO", "ADVERTENCIA"),
    ("ACCESO_PLATAFORMA_DENEGADO", "FALLO", "ACCESO", "SOSPECHOSO", "ADVERTENCIA"),
    ("CONSULTAR_PACIENTE", "EXITO", "ACCESO", "INFORMATIVO", "INFO"),
    ("ELIMINAR_INSTITUCION", "EXITO", "CRUD", "INFORMATIVO", "EXITO"),
    ("ELIMINAR_INSTITUCION", "FALLO", "CRUD", "OPERATIVO", "CRITICO"),
    ("ENVIAR_RESULTADO_MEDICION", "FALLO", "CRUD", "OPERATIVO", "CRITICO"),
    ("REVOCAR_MIEMBRO_INSTITUCION", "FALLO", "PERMISO", "OPERATIVO", "CRITICO"),
    ("MODIFICAR_PACIENTE", "FALLO", "PERMISO", "OPERATIVO", "ADVERTENCIA"),
])
def test_clasificacion_y_color(accion, resultado, tipo, clasificacion, severidad):
    kind = classification.classify(accion, resultado)
    assert (kind, classification.severity(accion, resultado, tipo, kind)) == (clasificacion, severidad)


def test_el_filtro_sql_de_clasificacion_coincide_con_la_etiqueta_de_cada_fila(db, mails):
    samples = [("LOGIN_LOCAL", "FALLO"), ("LOGIN_PWD", "EXITO"), ("BLOQUEO_TEMPORAL_CUENTA", "FALLO"), ("RAFAGA_RECHAZOS_HTTP", "FALLO"),
               ("CREAR_GRUPO", "EXITO"), ("ELIMINAR_GRUPO", "FALLO"), ("LIMITE_SOLICITUDES_EXCEDIDO", "FALLO"), ("REFRESH_REUTILIZADO", "FALLO")]
    for accion, resultado in samples:
        plant(db, accion, resultado=resultado)
    for kind in classification.CLASIFICACIONES:
        found = set(db.scalars(select(Audit.accion).where(classification.classificationFilter(kind))))
        expected = {a for a, r in samples if classification.classify(a, r) == kind}
        assert found == expected, kind


def test_las_categorias_cubren_las_acciones_reales():
    expected = {
        "LOGIN_PWD": "AUTENTICACION", "LOGIN_GOOGLE_MFA": "AUTENTICACION", "LOGIN_LOCAL": "AUTENTICACION", "MFA_CODIGO_INVALIDO": "AUTENTICACION",
        "REGISTRO_LOCAL": "CUENTAS", "ELIMINACION_CUENTA": "CUENTAS", "ELIMINACION_AUTOMATICA_CUENTA": "CUENTAS", "CANCELAR_PERIODO_GRACIA": "CUENTAS",
        "CREAR_INSTITUCION": "INSTITUCIONES", "ELIMINAR_INSTITUCION": "INSTITUCIONES", "REABRIR_INSTITUCION": "INSTITUCIONES",
        "MODIFICAR_MIEMBRO_INSTITUCION": "PERMISOS", "EXPORTACION_COMPLETADA": "EXPORTACIONES", "BLOQUEO_TEMPORAL_CUENTA": "SEGURIDAD",
    }
    for accion, categoria in expected.items():
        assert classification.inCategory(accion, categoria), (accion, categoria)
    assert not classification.inCategory("CREAR_GRUPO", "SEGURIDAD")


# --- Exportaciones ---------------------------------------------------------------------------------------------------------------


def test_exportacion_completada_deja_solicitud_y_resultado_sin_el_contenido(db, mails, team, api):
    secret = "PACIENTE-SECRETO-12345"
    with exportAudit.auditedExport(db, team.owner, "MEDICIONES_PACIENTE", ambito="INSTITUCION", idInstitucion=team.id, formato="CSV") as export:
        rows = [secret] * 7
        export.registros = len(rows)
    asked, done = events(db, "EXPORTACION_SOLICITADA")[0], events(db, "EXPORTACION_COMPLETADA")[0]
    one, two = json.loads(asked.datosNuevos), json.loads(done.datosNuevos)
    assert one["idExportacion"] == two["idExportacion"] and two["cantidadRegistros"] == 7
    assert (two["tipoDatos"], two["ambito"], two["formato"]) == ("MEDICIONES_PACIENTE", "INSTITUCION", "CSV")
    assert {asked.idUsuario, done.idUsuario} == {team.owner.idUsuario} and done.idInstitucion == team.id and done.resultado == "EXITO"
    assert secret not in everything(db)
    seen = items(api(team.owner).get(f"/api/v1/institutions/{team.id}/audit?categoria=EXPORTACIONES"))
    assert sorted(i["accion"] for i in seen) == ["EXPORTACION_COMPLETADA", "EXPORTACION_SOLICITADA"]


def test_exportacion_fallida_se_registra_sin_el_mensaje_del_error(db, mails, team):
    with pytest.raises(RuntimeError):
        with exportAudit.auditedExport(db, team.owner, "AUDITORIA", ambito="PLATAFORMA", formato="PDF"):
            raise RuntimeError("SELECT * FROM Paciente WHERE dni='30111222'")
    with pytest.raises(AuthError):
        with exportAudit.auditedExport(db, team.owner, "AUDITORIA", ambito="CUENTA"):
            raise AuthError("PERMISO_INSUFICIENTE", "no")
    assert events(db, "EXPORTACION_COMPLETADA") == []
    failed = events(db, "EXPORTACION_FALLIDA")
    assert [contextOf(db, f).motivo for f in failed] == ["ERROR_INTERNO", "PERMISO_INSUFICIENTE"] and all(f.resultado == "FALLO" for f in failed)
    assert "30111222" not in everything(db) and "SELECT" not in everything(db)
    assert len(events(db, "EXPORTACION_SOLICITADA")) == 2


def test_exportacion_rechazada_antes_de_empezar(db, mails, team):
    exportAudit.rejectExport(db, team.moderator, "PERSONAL", ambito="INSTITUCION", idInstitucion=team.id)
    [rejected] = events(db, "EXPORTACION_FALLIDA")
    assert rejected.idUsuario == team.moderator.idUsuario and rejected.idInstitucion == team.id and contextOf(db, rejected).motivo == "PERMISO_INSUFICIENTE"
    assert events(db, "EXPORTACION_SOLICITADA") == []
    with pytest.raises(ValueError):
        exportAudit.rejectExport(db, team.moderator, "PERSONAL", ambito="OTRO")


def test_el_panel_de_la_plataforma_cuenta_una_exportacion_completada_y_no_duplica_el_bloqueo(db, mails, team, admin):
    makeUser(db)
    for _ in range(3):
        with pytest.raises(AuthError):
            authService.loginLocal(db, EMAIL, WRONG)
    with exportAudit.auditedExport(db, team.owner, "AUDITORIA", ambito="PLATAFORMA"):
        pass
    data = platformDashboard.dashboard(db, admin).seguridad
    assert data.exportaciones == 1  # solicitada + completada = una exportación
    assert data.loginsFallidos == 3  # el bloqueo es del mismo intento, no un cuarto inicio de sesión fallido


def test_hoy_no_hay_exportaciones_inventadas(db, mails, team, admin, api):
    assert items(api(admin).get("/api/v1/audit?categoria=EXPORTACIONES")) == []


# --- Detección ---------------------------------------------------------------------------------------------------------------------


def signals(db, **kwargs):
    today = nowForDb().date()
    return securityDetection.analyze(db, today - timedelta(days=1), today, securityDetection.thresholds(**kwargs))


def test_un_fallo_aislado_o_pocos_fallos_no_son_una_senal(db, mails):
    user = makeUser(db)
    for minute in range(4):
        plant(db, "LOGIN_LOCAL", user=user, ip="203.0.113.7", motivo="PASSWORD_INCORRECTA", minutes=minute)
    result = signals(db)
    assert result.senales == [] and result.indicadores.intentosFallidos == 4


def test_fallos_repetidos_contra_una_cuenta_dentro_de_la_ventana(db, mails):
    user = makeUser(db)
    for minute in range(5):
        plant(db, "LOGIN_LOCAL", user=user, ip="203.0.113.7", motivo="PASSWORD_INCORRECTA", minutes=minute)
    [signal] = signals(db).senales
    assert (signal.tipo, signal.clasificacion, signal.cantidad, signal.umbral) == ("FALLOS_REPETIDOS_CUENTA", "SOSPECHOSO", 5, 5)
    assert signal.filtros["idCuenta"] == str(user.idUsuario)


def test_los_fallos_espaciados_fuera_de_la_ventana_no_se_acumulan(db, mails):
    user = makeUser(db)
    for hours in range(6):
        plant(db, "LOGIN_LOCAL", user=user, ip="203.0.113.7", motivo="PASSWORD_INCORRECTA", minutes=hours * 60)
    assert signals(db).senales == []
    assert signals(db, ventanaMinutos=24 * 60).senales[0].cantidad == 6  # el umbral y la ventana son configurables


def test_los_umbrales_son_configurables_por_entorno(db, mails, monkeypatch):
    user = makeUser(db)
    for minute in range(3):
        plant(db, "LOGIN_LOCAL", user=user, ip="203.0.113.7", motivo="PASSWORD_INCORRECTA", minutes=minute)
    monkeypatch.setenv("AUDIT_ALERT_FAILURES_PER_ACCOUNT", "3")
    getSettings.cache_clear()
    assert [s.tipo for s in signals(db).senales] == ["FALLOS_REPETIDOS_CUENTA"]
    getSettings.cache_clear()


def test_un_origen_que_prueba_muchas_cuentas(db, mails):
    for number in range(5):
        plant(db, "LOGIN_LOCAL", ip="203.0.113.9", motivo="CUENTA_INEXISTENTE", fingerprint=hashIdentifier(f"cuenta{number}@example.com"), minutes=number)
    [signal] = signals(db).senales
    assert (signal.tipo, signal.cantidad, signal.ipOrigen) == ("MULTIPLES_CUENTAS_ORIGEN", 5, "203.0.113.9")
    assert signal.filtros["ip"] == "203.0.113.9"
    # la misma cuenta cinco veces desde un origen NO es «muchas cuentas»
    other = makeUser(db)
    for minute in range(4):
        plant(db, "LOGIN_LOCAL", user=other, ip="198.51.100.4", motivo="PASSWORD_INCORRECTA", minutes=minute)
    assert [s.ipOrigen for s in signals(db).senales if s.tipo == "MULTIPLES_CUENTAS_ORIGEN"] == ["203.0.113.9"]


def test_origen_inusual_solo_con_historia_suficiente(db, mails):
    user = makeUser(db)
    for day in range(1, 6):
        plant(db, "LOGIN_PWD", resultado="EXITO", user=user, ip="203.0.113.7", minutes=(day + 3) * 24 * 60)
    plant(db, "LOGIN_LOCAL", user=user, ip="198.51.100.77", motivo="PASSWORD_INCORRECTA")
    [signal] = signals(db).senales
    assert signal.tipo == "ORIGEN_INUSUAL" and signal.clasificacion == "SOSPECHOSO" and "indicio débil" in signal.descripcion
    newcomer = makeUser(db, email="nueva@example.com", usuario="nueva")
    for day in range(1, 3):  # solo dos accesos previos: no alcanza para afirmar que un origen es inusual
        plant(db, "LOGIN_PWD", resultado="EXITO", user=newcomer, ip="203.0.113.7", minutes=(day + 3) * 24 * 60)
    plant(db, "LOGIN_LOCAL", user=newcomer, ip="198.51.100.88", motivo="PASSWORD_INCORRECTA")
    assert [s.cuenta for s in signals(db).senales] == [signal.cuenta] and len(signals(db).senales) == 1
    # un fallo desde un origen que la cuenta ya usó tampoco es inusual
    plant(db, "LOGIN_LOCAL", user=user, ip="203.0.113.7", motivo="PASSWORD_INCORRECTA")
    assert len(signals(db).senales) == 1


def test_los_rechazos_por_estado_de_la_cuenta_no_cuentan_como_adivinar(db, mails):
    user = makeUser(db)
    for minute in range(8):
        plant(db, "LOGIN_LOCAL", user=user, ip="203.0.113.7", motivo="CUENTA_INACTIVA", minutes=minute)
    assert signals(db).senales == []


def test_los_controles_activados_son_hechos_confirmados_y_no_acusan(db, mails):
    user = makeUser(db)
    plant(db, "BLOQUEO_TEMPORAL_CUENTA", user=user, modulo="SEGURIDAD", ip="203.0.113.7", motivo="INTENTOS_EXCEDIDOS")
    plant(db, "LIMITE_SOLICITUDES_EXCEDIDO", tipo="ACCESO", modulo="SEGURIDAD", ip="203.0.113.8", motivo="LIMITE_POR_ORIGEN")
    plant(db, "RAFAGA_RECHAZOS_HTTP", tipo="ACCESO", modulo="SEGURIDAD", ip="203.0.113.8", motivo="RECHAZOS_REITERADOS")
    result = signals(db)
    kinds = {s.tipo: s.clasificacion for s in result.senales}
    assert kinds == {"BLOQUEOS_CUENTA": "CONFIRMADO", "LIMITE_SOLICITUDES": "CONFIRMADO", "RAFAGA_RECHAZOS": "SOSPECHOSO"}
    assert result.senales[-1].clasificacion == "SOSPECHOSO"  # lo confirmado va primero
    assert all("ataque" not in s.descripcion.lower() or "no indica" in s.descripcion for s in result.senales)
    assert (result.indicadores.bloqueos, result.indicadores.limitesExcedidos, result.indicadores.rafagasRechazos) == (1, 1, 1)


def test_analizar_no_escribe_nada_ni_inventa_registros(db, mails):
    user = makeUser(db)
    for minute in range(6):
        plant(db, "LOGIN_LOCAL", user=user, ip="203.0.113.7", motivo="PASSWORD_INCORRECTA", minutes=minute)
    before = db.scalar(select(func.count()).select_from(Audit))
    assert signals(db).senales
    assert db.scalar(select(func.count()).select_from(Audit)) == before


def test_el_endpoint_de_senales_acota_el_periodo_y_los_umbrales(db, mails, admin, api):
    http = api(admin)
    assert http.get("/api/v1/audit/security/signals").status_code == 200
    assert http.get("/api/v1/audit/security/signals?fallosPorCuenta=1").status_code == 422
    assert http.get("/api/v1/audit/security/signals?ventanaMinutos=5000").status_code == 422
    far = (date.today() - timedelta(days=90)).isoformat()
    assert http.get(f"/api/v1/audit/security/signals?desde={far}").json()["detail"].startswith("El análisis de seguridad admite")
    body = http.get("/api/v1/audit/security/signals?fallosPorCuenta=3&ventanaMinutos=30").json()
    assert body["umbrales"]["fallosPorCuenta"] == 3 and body["umbrales"]["ventanaMinutos"] == 30 and body["contextoDisponible"] is True


def test_el_resumen_cuenta_accesos_fallidos_sospechosos_y_controles(db, mails, admin, api):
    user = makeUser(db)
    plant(db, "LOGIN_LOCAL", user=user)
    plant(db, "LOGIN_LOCAL", user=user)
    plant(db, "BLOQUEO_TEMPORAL_CUENTA", user=user, modulo="SEGURIDAD")
    plant(db, "RAFAGA_RECHAZOS_HTTP", tipo="ACCESO", modulo="SEGURIDAD")
    plant(db, "LOGIN_PWD", resultado="EXITO", user=user)
    summary = api(admin).get("/api/v1/audit/summary").json()
    assert (summary["total"], summary["accesosFallidos"], summary["sospechosos"], summary["confirmados"]) == (5, 3, 1, 1)
    assert summary["exitosos"] == 1 and summary["fallidos"] == 4


# --- Monitor de rechazos ---------------------------------------------------------------------------------------------------------


@pytest.fixture
def onlyDb(engine):
    """Solo reemplaza la base de la aplicación por la de la prueba (sin identidad): las rutas públicas y las rechazadas por falta de credenciales."""
    makeSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def getTestDb():
        session = makeSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[getDb] = getTestDb
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def liveMonitor(engine, onlyDb, monkeypatch):
    """El monitor con su persistencia real, apuntada a la base de la prueba."""
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(securityMonitor, "sessionFactory", lambda: sessions())
    monkeypatch.setattr(securityMonitor, "persistBurst", REAL_PERSIST_BURST)
    monkeypatch.setattr(securityMonitor, "persistRateLimit", REAL_PERSIST_RATE_LIMIT)


def test_una_rafaga_de_rechazos_deja_un_solo_evento_con_el_origen(db, mails, liveMonitor, monkeypatch):
    monkeypatch.setenv("AUDIT_ALERT_AUTH_REJECTIONS", "6")
    getSettings.cache_clear()
    http = client("203.0.113.66", **{"User-Agent": "python-requests/2.31"})
    for _ in range(15):
        assert http.get("/api/v1/audit/events/" + str(uuid.uuid4())).status_code == 401  # sin credenciales
    [burst] = events(db, "RAFAGA_RECHAZOS_HTTP")
    context = contextOf(db, burst)
    assert (burst.modulo, burst.resultado, context.ipOrigen, context.motivo) == ("SEGURIDAD", "FALLO", "203.0.113.66", "RECHAZOS_REITERADOS")
    assert context.agenteUsuario == "python-requests/2.31"
    assert json.loads(burst.datosNuevos)["cantidad"] == 6 and json.loads(burst.datosNuevos)["respuestas"] == [{"respuesta": "TOKEN_INVALIDO", "cantidad": 6}]
    assert classification.classify(burst.accion, burst.resultado) == classification.SOSPECHOSO
    getSettings.cache_clear()


def test_no_cuentan_ni_el_token_vencido_ni_el_login_fallido_ni_otro_origen(db, mails, liveMonitor, monkeypatch):
    monkeypatch.setenv("AUDIT_ALERT_AUTH_REJECTIONS", "4")
    getSettings.cache_clear()
    makeUser(db)
    http = client("203.0.113.67")
    for _ in range(10):
        login(http)  # 401 de credenciales: ya se audita de a uno (y a partir del tercero la cuenta se bloquea)
    assert securityMonitor.classifyRejection(401, ("TOKEN_INVALIDO", "TOKEN_VENCIDO")) is None
    assert securityMonitor.classifyRejection(401, ("TOKEN_INVALIDO", "SESION_INVALIDA")) is None
    assert securityMonitor.classifyRejection(401, ("CREDENCIALES_INVALIDAS", None)) is None
    assert securityMonitor.classifyRejection(403, ("CUENTA_NO_ACTIVA", None)) is None
    assert securityMonitor.classifyRejection(401, ("TOKEN_INVALIDO", "TOKEN_MALFORMADO")) == ("AUTORIZACION", "TOKEN_INVALIDO")
    assert securityMonitor.classifyRejection(403, ("PERMISO_INSUFICIENTE", None)) == ("AUTORIZACION", "PERMISO_INSUFICIENTE")
    assert securityMonitor.classifyRejection(422, ("VALIDACION_ENTRADA", None)) == ("VALIDACION", "VALIDACION_ENTRADA")
    assert securityMonitor.classifyRejection(400, ("CORREO_REGISTRADO", None)) is None
    assert events(db, "RAFAGA_RECHAZOS_HTTP") == []
    getSettings.cache_clear()


def test_el_monitor_cuenta_por_origen_y_reinicia_por_ventana():
    monitor = securityMonitor.SecurityMonitor()
    first = [monitor.observe("AUTORIZACION", "198.51.100.1", "TOKEN_INVALIDO", now=float(t)) for t in range(25)]
    assert sum(b is not None for b in first) == 1 and first[19].count == 20  # umbral por defecto 20
    assert monitor.observe("AUTORIZACION", "198.51.100.2", "TOKEN_INVALIDO", now=30.0) is None
    window = getSettings().AUDIT_ALERT_WINDOW_MINUTES * 60
    later = [monitor.observe("AUTORIZACION", "198.51.100.1", "TOKEN_INVALIDO", now=float(window * 3 + t)) for t in range(20)]
    assert later[-1] is not None  # pasada la ventana, un nuevo episodio vuelve a señalarse


def test_las_entradas_rechazadas_por_validacion_se_cuentan_aparte(db, mails, liveMonitor, monkeypatch):
    monkeypatch.setenv("AUDIT_ALERT_VALIDATION_REJECTIONS", "5")
    getSettings.cache_clear()
    http = client("203.0.113.68")
    for _ in range(8):
        assert http.post("/api/v1/auth/login", json={"identificador": 5}).status_code == 422
    [burst] = events(db, "RAFAGA_VALIDACION_HTTP")
    assert contextOf(db, burst).ipOrigen == "203.0.113.68" and "entradas rechazadas" in burst.observacion
    getSettings.cache_clear()


def test_el_limite_de_solicitudes_por_ip_deja_un_evento_por_ventana(db, mails, liveMonitor):
    http = client("203.0.113.69")
    statuses = [http.post("/api/v1/auth/password/forgot", json={"correoElectronico": "alguien@example.com"}).status_code for _ in range(9)]
    assert 429 in statuses
    [limit] = events(db, "LIMITE_SOLICITUDES_EXCEDIDO")
    context = contextOf(db, limit)
    assert (context.ipOrigen, context.motivo, json.loads(limit.datosNuevos)) == ("203.0.113.69", "LIMITE_POR_ORIGEN", {"limite": "passwordForgot"})
    assert classification.classify(limit.accion, limit.resultado) == classification.CONFIRMADO


def test_un_fallo_del_monitor_no_afecta_la_respuesta(db, mails, onlyDb, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("base caída")

    monkeypatch.setattr(securityMonitor, "persistBurst", broken)
    monkeypatch.setenv("AUDIT_ALERT_AUTH_REJECTIONS", "2")
    getSettings.cache_clear()
    http = client("203.0.113.70")
    assert [http.get("/api/v1/audit/events/" + str(uuid.uuid4())).status_code for _ in range(5)] == [401] * 5
    getSettings.cache_clear()


# --- Conservación ------------------------------------------------------------------------------------------------------------------


def test_la_ip_y_el_cliente_se_anulan_vencido_el_plazo_pero_el_evento_sigue(db, mails):
    old = plant(db, "LOGIN_LOCAL", ip="203.0.113.7", agent="Chrome · Windows · Computadora", motivo="PASSWORD_INCORRECTA", correlation="corr-vieja-001",
                minutes=91 * 24 * 60)
    recent = plant(db, "LOGIN_LOCAL", ip="203.0.113.8", agent="Chrome · Windows · Computadora", motivo="PASSWORD_INCORRECTA", minutes=10 * 24 * 60)
    result = auditRetention.run(db)
    assert result["contextosMinimizados"] == 1
    oldContext, recentContext = contextOf(db, old), contextOf(db, recent)
    assert (oldContext.ipOrigen, oldContext.agenteUsuario) == (None, None)
    assert (oldContext.motivo, oldContext.idCorrelacion) == ("PASSWORD_INCORRECTA", "corr-vieja-001")  # lo que no es dato personal se conserva
    assert (recentContext.ipOrigen, recentContext.agenteUsuario) == ("203.0.113.8", "Chrome · Windows · Computadora")
    assert db.get(Audit, old.idAuditoria) is not None
    assert auditRetention.run(db)["contextosMinimizados"] == 0  # idempotente


def test_los_intentos_sin_cuenta_se_depuran_a_los_doce_meses_y_nada_mas(db, mails):
    user = makeUser(db)
    gone = plant(db, "LOGIN_LOCAL", ip="203.0.113.7", motivo="CUENTA_INEXISTENTE", fingerprint="f" * 32, minutes=13 * 30 * 24 * 60)
    keptWithUser = plant(db, "LOGIN_LOCAL", user=user, ip="203.0.113.7", motivo="PASSWORD_INCORRECTA", minutes=13 * 30 * 24 * 60)
    keptRecent = plant(db, "LOGIN_LOCAL", ip="203.0.113.7", motivo="CUENTA_INEXISTENTE", fingerprint="e" * 32, minutes=30 * 24 * 60)
    keptOther = plant(db, "CREAR_GRUPO", resultado="EXITO", tipo="CRUD", modulo="GRUPOS", minutes=13 * 30 * 24 * 60)
    goneId = gone.idAuditoria
    result = auditRetention.run(db)
    db.expire_all()
    assert result["intentosSinCuentaEliminados"] == 1 and result["eventosEliminados"] == 0
    assert db.get(Audit, goneId) is None and db.get(AuditContext, goneId) is None  # el contexto se va con su evento
    assert all(db.get(Audit, a.idAuditoria) is not None for a in (keptWithUser, keptRecent, keptOther))
    [trace] = events(db, "DEPURAR_AUDITORIA")
    assert json.loads(trace.datosNuevos)["intentosSinCuentaEliminados"] == 1 and trace.idUsuario is None


def test_la_depuracion_total_solo_corre_si_se_configura(db, mails, monkeypatch):
    plant(db, "CREAR_GRUPO", resultado="EXITO", tipo="CRUD", modulo="GRUPOS", minutes=40 * 30 * 24 * 60)
    assert auditRetention.run(db)["eventosEliminados"] == 0  # por defecto se conserva todo
    monkeypatch.setenv("AUDIT_RETENTION_MONTHS", "36")
    getSettings.cache_clear()
    assert auditRetention.run(db)["eventosEliminados"] == 0  # un plazo sin la aprobación legal (RETENTION_APPROVAL_REFERENCE) no se aplica (H-04)
    monkeypatch.setenv("RETENTION_APPROVAL_REFERENCE", "Dictamen sintetico 0001")
    getSettings.cache_clear()
    assert auditRetention.run(db)["eventosEliminados"] == 1
    monkeypatch.setenv("AUDIT_RETENTION_MONTHS", "0")
    monkeypatch.setenv("AUDIT_CONTEXT_RETENTION_DAYS", "0")
    getSettings.cache_clear()
    plant(db, "LOGIN_LOCAL", ip="203.0.113.7", motivo="PASSWORD_INCORRECTA", minutes=400 * 24 * 60)
    assert auditRetention.run(db)["contextosMinimizados"] == 0  # 0 desactiva
    getSettings.cache_clear()


def test_no_hay_ninguna_ruta_para_depurar_ni_editar_auditoria():
    mutating = [(sorted(route.methods), route.path) for route in app.routes
                if "audit" in getattr(route, "path", "").lower() and set(route.methods) - {"GET", "HEAD", "OPTIONS"}]
    assert mutating == []


def test_sin_la_tabla_de_contexto_la_auditoria_sigue_funcionando(db, mails, monkeypatch):
    from app.services import schemaCompat

    monkeypatch.setattr(schemaCompat, "auditContextReady", lambda session: False)
    token = requestContext.bind(requestContext.RequestContext("corr-sintabla-1", "203.0.113.7", None))
    try:
        registerEvent(db, "LOGIN", "LOGIN_LOCAL", False, motivo="PASSWORD_INCORRECTA")
        db.commit()
    finally:
        requestContext.unbind(token)
    assert db.scalar(select(func.count()).select_from(AuditContext)) == 0 and len(events(db, "LOGIN_LOCAL")) == 1
    with pytest.raises(AuthError) as error:  # y un filtro que lo necesita lo dice en lugar de ignorarse
        auditQuery.listGlobal(db, makeUser(db, tipoCuenta="ADMINISTRADOR_PLATAFORMA", email="a@example.com", usuario="adm"), ip="203.0.113.7")
    assert error.value.code == "ESQUEMA_DESACTUALIZADO"


def test_toda_exportacion_futura_pasa_por_audited_export():
    # Prueba de arquitectura (pendiente G): hoy no hay exportaciones. Un módulo de app/ que arme un archivo descargable (CSV, PDF, planilla o
    # Content-Disposition) tiene que usar exportAudit.auditedExport, que registra quién exportó qué y desde dónde.
    from pathlib import Path

    markers = ("Content-Disposition", "FileResponse", "text/csv", "application/pdf", "csv.writer", "openpyxl", "spreadsheetml")
    app = Path(__file__).resolve().parents[1] / "app"
    offenders = [str(path.relative_to(app)) for path in app.rglob("*.py") if path.name != "exportAudit.py"
                 and any(marker in path.read_text(encoding="utf-8") for marker in markers)
                 and "auditedExport" not in path.read_text(encoding="utf-8")]
    assert offenders == []


def test_una_rafaga_avisa_al_administrador_una_vez_por_hora_sin_la_ip(db, mails, liveMonitor, monkeypatch):
    # GL-15: alerta activa por correo, acotada (un aviso por patrón y hora) y sin datos del origen.
    monkeypatch.setattr(securityMonitor, "alertAdministrator", REAL_ALERT)
    monkeypatch.setenv("AUDIT_ALERT_AUTH_REJECTIONS", "6")
    getSettings.cache_clear()
    admin = makeUser(db, tipoCuenta="ADMINISTRADOR_PLATAFORMA", email="admin.alerta@example.com", usuario="adminalerta")
    http = client("203.0.113.77")
    for _ in range(30):
        http.get("/api/v1/audit/events/" + str(uuid.uuid4()))
    alerts = [m for m in mails if m["subject"] == "Actividad sospechosa en GlucoLume"]
    assert [m["to"] for m in alerts] == [admin.correoElectronico]  # varias ráfagas, un solo aviso
    assert "203.0.113.77" not in alerts[0]["html"] and "/plataforma/auditoria" in alerts[0]["html"]
    burst = securityMonitor.Burst(securityMonitor.KIND_AUTH, "x", 6, 6, 15)
    assert securityMonitor.alertAdministrator(burst, now=10**9) is True  # pasada la hora vuelve a avisar
    monkeypatch.setenv("SECURITY_ALERT_EMAIL_MINUTES", "0")
    getSettings.cache_clear()
    assert securityMonitor.alertAdministrator(burst, now=2 * 10**9) is False  # desactivable

