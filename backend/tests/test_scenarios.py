# Escenario integral: todos los módulos con todos los tipos de cuenta (individual, grupo familiar, institución
# con propietario/moderador/operadores y plataforma con administrador/moderador). Al final imprime y valida:
#   - cómo queda la auditoría (por actor, módulo y resultado),
#   - qué correos se enviaron (destinatario y asunto) y qué tipos de correo del catálogo no se enviaron nunca,
#   - cómo queda cada usuario (rol, estado, MFA, sesiones, membresías).
#
# Ejecutar desde backend/ (con -s para ver el informe):
#     python -m pytest tests/test_scenarios.py -s -q

import re
from collections import Counter, defaultdict

import pytest
from sqlalchemy import func, select

from app.emails.eventTypes import EmailEventType
from app.models.audit import Audit
from app.models.groupUser import GroupUser
from app.models.institutionUser import InstitutionUser
from app.models.user import User
from app.models.userSession import UserSession
from app.schemas.measurement import MeasurementStart
from app.schemas.platform import ModeratorInvite
from app.services import auditQuery
from app.services import dashboard as dashboards
from app.services import institution as institutions
from app.services import institutionPatients as patients
from app.services import measurement as measurements
from app.services import platform
from app.services import platformDashboard
from app.services import profileTransfers as transfers
from tests.test_account_deletion import audits, db, engine, mails, makeUser, reload  # noqa: F401
from tests.test_groups import create as createGroup
from tests.test_groups import join, person, share
from tests.test_institution_patients import addOperator, patientData
from tests.test_institutions import expectError, freshLookupLimiter, relationOf, team  # noqa: F401
from tests.test_matrices import activeMatrix
from tests.test_measurements import completeOximetry, device
from tests.test_platform import ADMIN, MOD, platformUser, reauth, strictPolicy  # noqa: F401
from tests.test_dashboards import measure


@pytest.fixture
def sentEvents(monkeypatch):
    """Registra (tipo de evento, destinatario) de cada correo que el sistema intenta enviar, sin cambiar su comportamiento."""
    from app.services import email as emailService

    seen = []
    original = emailService.sendEmailEvent

    def spy(eventType, destinatario, *args, **kwargs):
        seen.append((eventType, destinatario))
        return original(eventType, destinatario, *args, **kwargs)

    monkeypatch.setattr(emailService, "sendEmailEvent", spy)
    return seen


def mask(email: str | None) -> str:
    return re.sub(r"^(.).*@", r"\1***@", email or "-")


def report(db, mails, sentEvents, users) -> str:
    lines = ["", "=" * 100, "AUDITORÍA (actor -> módulo / acción / resultado)", "=" * 100]
    rows = db.execute(select(Audit).order_by(Audit.fechaHora)).scalars().all()
    byActor = defaultdict(Counter)
    for row in rows:
        actor = row.usuario.usuario if row.usuario is not None else "(sistema/anónimo)"
        byActor[actor][(row.modulo or "-", row.accion, row.resultado)] += 1
    for actor, counter in sorted(byActor.items()):
        lines.append(f"- {actor}")
        for (modulo, accion, resultado), n in sorted(counter.items()):
            lines.append(f"    {modulo:<16} {accion:<45} {resultado:<8} x{n}")
    lines += ["", f"Total de eventos: {len(rows)} | sin módulo: {sum(1 for r in rows if not r.modulo)} | "
                  f"con institución: {sum(1 for r in rows if r.idInstitucion)}"]
    lines += ["", "=" * 100, "CORREOS ENVIADOS (SMTP simulado)", "=" * 100]
    for mail in mails:
        lines.append(f"- a {mask(mail['to'])}: {mail['subject']}")
    lines.append(f"Total: {len(mails)}")
    sentTypes = {event for event, _ in sentEvents}
    never = sorted(e.name for e in EmailEventType if e not in sentTypes)
    lines += ["", "Tipos de evento del catálogo que NUNCA se enviaron en todo el escenario:", "  " + ", ".join(never)]
    lines += ["", "=" * 100, "ESTADO DE CADA USUARIO", "=" * 100]
    for label, user in users.items():
        fresh = reload(db, User, user.idUsuario)
        sessions = db.scalar(select(func.count()).select_from(UserSession).where(UserSession.idUsuario == user.idUsuario))
        institutional = [f"{r.rolInstitucion}:{r.estadoRelacion}" for r in db.scalars(
            select(InstitutionUser).where(InstitutionUser.idUsuarioInvitado == user.idUsuario))]
        family = [f"{r.rolGrupo}:{r.estadoRelacion}" for r in db.scalars(select(GroupUser).where(GroupUser.idUsuario == user.idUsuario))]
        lines.append(f"- {label:<22} {fresh.tipoCuenta:<26} {fresh.estado:<10} sesiones={sessions} "
                     f"inst={institutional or '-'} grupo={family or '-'}")
    text = "\n".join(lines)
    print(text)
    return text


def test_escenario_integral_todos_los_modulos_y_tipos_de_cuenta(db, mails, sentEvents, team):
    users = {}
    # --- Plataforma: administrador y moderador con MFA ---------------------------------------------------------
    admin, adminSecret = platformUser(db, ADMIN, "admin@example.com", "adminsys")
    mod, modSecret = platformUser(db, MOD, "modsistema@example.com", "modsys")
    users.update({"plataforma admin": admin, "plataforma moderador": mod})
    invited, sent, _ = platform.inviteModerator(db, admin, ModeratorInvite(
        nombre="Luis", apellido="Gómez", correoElectronico="luis@example.com", reautenticacion=reauth(db, admin, adminSecret)))
    assert sent
    matrix = activeMatrix(db, mod)  # matriz global creada y activada por el moderador del sistema
    assert matrix.estado == "ACTIVA"
    data = platformDashboard.dashboard(db, admin, 30)
    assert data.usuarios.total >= 5

    # --- Individuales y grupo familiar ------------------------------------------------------------------------
    ana, beto = person(db, "ana"), person(db, "beto")
    users.update({"individual Ana (adm. grupo)": ana, "individual Beto (miembro)": beto})
    group = createGroup(db, ana)
    join(db, ana, group.idGrupo, beto)
    dev = device(db)
    for user in (ana, beto):
        completeOximetry(db, user, measurements.getOwnProfile(db, user).idPerfilMedicion, dev, spo2="97", hr=70)
    share(db, beto, group.idGrupo, comparteUltimaMedicion=True, comparteHistorial=True)
    assert dashboards.personalDashboard(db, ana, 30).resumen.completadas == 1
    assert dashboards.groupDashboard(db, ana, group.idGrupo, 30).integrantesActivos == 2
    outsider = person(db, "intruso")
    users["individual ajeno al grupo"] = outsider
    expectError("GRUPO_NO_ENCONTRADO", dashboards.groupDashboard, db, outsider, group.idGrupo, 30)

    # --- Institución: propietario, moderador, dos operadores, pacientes, mediciones, transferencia -------------
    second = addOperator(db, team)
    secondUser = db.get(User, second.idUsuarioInvitado)
    users.update({"inst. propietario": team.owner, "inst. moderador": team.moderator,
                  "inst. operador 1": team.operator, "inst. operador 2": secondUser})
    instDevice = device(db, institucion=team.id)
    patient = patients.createPatient(db, team.operator, team.id, patientData(nombre="rosa", apellido="díaz"))
    measure(db, team.operator, patient.idPerfilMedicion, instDevice, "96", 70)
    request = transfers.requestTransfer(db, team.operator, team.id, patient.idPerfilMedicion, second.idInstitucionUsuario, None)
    transfers.acceptTransfer(db, secondUser, team.id, request.idTransferenciaPerfil)
    measure(db, secondUser, patient.idPerfilMedicion, instDevice, "98", 75)
    assert dashboards.institutionDashboard(db, team.owner, team.id, 30).medicionesTotal == 2
    expectError("PERMISO_INSUFICIENTE", dashboards.institutionDashboard, db, team.operator, team.id)
    # Auditoría institucional: el propietario ve; el operador no.
    ownerPage = auditQuery.listInstitution(db, team.owner, team.id, tamanioPagina=100)
    assert ownerPage.items and all(i.accion for i in ownerPage.items)
    with pytest.raises(Exception):
        auditQuery.listInstitution(db, team.operator, team.id, tamanioPagina=100)
    # Una persona ajena a la institución no puede leer su auditoría.
    with pytest.raises(Exception):
        auditQuery.listInstitution(db, outsider, team.id, tamanioPagina=100)

    # --- Transferencia del control de la plataforma -----------------------------------------------------------
    platform.startTransfer(db, admin, mod.idUsuario, reauth(db, admin, adminSecret))
    platform.respondTransfer(db, mod, True, reauth(db, mod, modSecret))
    assert reload(db, User, mod.idUsuario).tipoCuenta == ADMIN and reload(db, User, admin.idUsuario).tipoCuenta == MOD

    # --- Informe ----------------------------------------------------------------------------------------------
    text = report(db, mails, sentEvents, users)
    # La auditoría no debe contener contraseñas ni tokens ni correos completos.
    blob = " ".join(str(a.datosNuevos) + str(a.datosPrevios) + str(a.detalle) + str(a.observacion) for a in db.scalars(select(Audit)))
    for forbidden in ("Zorro#", "passwordHash", "refreshToken", "luis@example.com", "ana@example.com"):
        assert forbidden not in blob, forbidden
    assert "DIAGNOSTICO" not in text
    import os
    out = os.environ.get("SCENARIO_REPORT")
    if out:
        with open(out, "w", encoding="utf-8") as handle:
            handle.write(text)
