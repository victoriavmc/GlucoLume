# Prueba de CARRERAS del ciclo de vida de cuentas, con conexiones independientes y datos 100 % sintéticos.
#
# Verifica que la eliminación automática y las operaciones que "salvan" a una cuenta vencida no puedan producir un estado inconsistente:
#   R1  aceptar una invitación  vs  eliminación automática           (misma cuenta, mismo instante)
#   R2  crear una institución   vs  eliminación automática
#   R3  dos pasadas de eliminación simultáneas sobre la misma cuenta (una sola eliminación, un solo correo)
#   R4  nueva invitación a una cuenta invitada sin salida  vs  su depuración   (la invitación nueva y válida no puede quedar cancelada)
#   R5  reenvío de una invitación vencida  vs  depuración de la cuenta invitada
# En cada ronda debe ganar exactamente una de las dos partes, y nunca puede quedar una cuenta ELIMINADA con un vínculo ACTIVO, ni una cuenta
# ACTIVA con la incorporación perdida. No usa cuentas reales: crea las suyas (prefijo zz-conc-<marca>) y NO toca ninguna otra.
#
# IMPORTANTE: escribe datos reales (confirmados) en la base a la que apunte. Esa base conserva luego usuarios sintéticos, instituciones
# sintéticas y filas de Auditoria (que son de solo lectura por diseño y no se borran). Por eso el comando no corre contra una base hasta que se
# confirma su nombre explícitamente (ver main). Para la base real de GlucoLume requiere una autorización expresa.
#
#   Desde backend/, con la configuración habitual (DB_*):
#     LIFECYCLE_CONCURRENCY_CONFIRM=<nombre exacto de la base> python -m tests.lifecycle_concurrency [--rondas 10]
#   Sin dependencias de pytest: sirve en un contenedor con tests/ montado, o en SQLite desde tests/test_lifecycle_concurrency.py.

import os
import random
import sys
import threading
import time
import uuid
from datetime import date, timedelta

from sqlalchemy import func, select, update

from app.core import security
from app.core.exceptions import AuthError
from app.models.accountToken import AccountToken
from app.models.audit import Audit
from app.models.institutionUser import InstitutionUser
from app.models.localCredential import LocalCredential
from app.models.user import User
from app.schemas.institution import InstitutionCreateRequest
from app.services import accountLifecycle, pendingAccounts
from app.services import consent as consentService
from app.services import email as emailService
from app.services import institution as institutions
from app.models.consent import TipoConsentimiento
from app.utils.timeZone import nowForDb

PASSWORD = "Glucolume#Prueba2026"  # nosec B105 - contraseña de prueba
WEIGHTS = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)


def _cuit(number: str) -> str:
    body = "30" + number
    rest = 11 - sum(int(d) * w for d, w in zip(body, WEIGHTS)) % 11
    return body + str({11: 0, 10: 9}.get(rest, rest))


class Run:
    def __init__(self, makeSession, tolerateLocks: bool = False):
        self.makeSession = makeSession
        self.tolerateLocks = tolerateLocks  # SQLite serializa con un bloqueo de base: el perdedor puede ver «locked»
        self.tag = uuid.uuid4().hex[:8]
        self.failures: list[str] = []
        self.checks = 0
        self.mails: list[tuple[str, str]] = []
        self.counter = 0

    # --- datos sintéticos -----------------------------------------------------------------------------------------------------------
    def user(self, s, label, expired=True) -> User:
        self.counter += 1
        user = User(idUsuario=uuid.uuid4(), nombre="Sintetico", apellido=label, correoElectronico=f"zz-conc-{self.tag}-{self.counter}@example.com",
                    usuario=f"zzconc{self.tag}{self.counter}", tipoCuenta="USUARIO_INSTITUCIONAL", estado="ACTIVO",
                    fechaNacimiento=date(1990, 1, 1), sexo="FEMENINO")
        if expired:  # plazo de 30 días ya cumplido (vencido hace una hora)
            user.fechaInicioGracia = nowForDb() - timedelta(days=31)
            user.fechaVencimientoGracia = nowForDb() - timedelta(hours=1)
        s.add(user)
        s.flush()
        s.add(LocalCredential(idUsuario=user.idUsuario, passwordHash=security.hashPassword(PASSWORD)))
        consentService.record(s, user, TipoConsentimiento.POLITICA_PRIVACIDAD, True)
        consentService.record(s, user, TipoConsentimiento.DATOS_EXPERIMENTALES, True)
        s.commit()
        return user

    def institution(self, s, owner):
        digits = "".join(str(random.randint(0, 9)) for _ in range(8))
        return institutions.createInstitution(s, owner, InstitutionCreateRequest(
            nombre=f"ZZ Concurrencia {self.tag}", tipoInstitucion="HOSPITAL", identificadorLegal=_cuit(digits)))

    # --- ejecución de una carrera -----------------------------------------------------------------------------------------------------
    def race(self, *tasks):
        """Cada tarea corre en su hilo y con SU PROPIA sesión/conexión; todas arrancan a la vez (barrera) con una espera aleatoria mínima."""
        barrier = threading.Barrier(len(tasks))
        outcomes: list = [None] * len(tasks)

        def worker(index, task):
            session = self.makeSession()
            try:
                barrier.wait(timeout=30)
                time.sleep(random.random() * 0.02)
                outcomes[index] = ("ok", task(session))
            except AuthError as error:
                outcomes[index] = ("auth", error.code)
            except Exception as error:  # noqa: BLE001 - se informa: un deadlock u otro error técnico es un fallo de la prueba
                session.rollback()
                text = str(error).lower()
                outcomes[index] = ("lock", repr(error)) if (self.tolerateLocks and "locked" in text) else ("error", repr(error))
            finally:
                session.close()

        threads = [threading.Thread(target=worker, args=(i, t)) for i, t in enumerate(tasks)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=120)
            if thread.is_alive():
                self.fail("hilo bloqueado (posible deadlock)")
        return outcomes

    def fail(self, message):
        self.failures.append(message)
        print("  FALLA", message)

    def check(self, condition, message):
        self.checks += 1
        if not condition:
            self.fail(message)

    # --- estado final leído con una conexión nueva ---------------------------------------------------------------------------------------
    def snapshot(self, idUsuario):
        with self.makeSession() as s:
            user = s.get(User, idUsuario)
            bonds = [r.estadoRelacion for r in s.scalars(select(InstitutionUser).where(InstitutionUser.idUsuarioInvitado == idUsuario))]
            deleted = s.scalar(select(func.count()).select_from(Audit).where(
                Audit.accion == "ELIMINACION_AUTOMATICA_CUENTA", Audit.resultado == "EXITO", Audit.idRegistro == idUsuario)) or 0
            return user.estado, user.fechaVencimientoGracia, bonds, deleted

    def mailsTo(self, address):
        return [m for m in self.mails if m[0] == address]

    # --- escenarios -----------------------------------------------------------------------------------------------------------------------
    def r1_accept_vs_delete(self, rounds):
        print(f"R1 aceptar invitación vs eliminación automática ({rounds} rondas)")
        wins = {"incorporada": 0, "eliminada": 0}
        for n in range(rounds):
            with self.makeSession() as s:
                owner = self.user(s, f"duenio{n}", expired=False)
                self.institution(s, owner)
                institution = s.scalar(select(InstitutionUser.idInstitucion).where(InstitutionUser.idUsuarioInvitado == owner.idUsuario))
                guest = self.user(s, f"invitado{n}")
                invitation = institutions.invite(s, owner, institution, "MODERADOR", guest.correoElectronico)
                ids = (guest.idUsuario, invitation.idInstitucionUsuario)

            def accept(session, ids=ids):
                return institutions.respondInvitation(session, session.get(User, ids[0]), ids[1], accept=True)

            def delete(session, ids=ids):
                return accountLifecycle.deleteExpired(session, ids[0], nowForDb())

            results = self.race(accept, delete)
            state, expires, bonds, deletions = self.snapshot(ids[0])
            label = f"R1 ronda {n}: {results} -> {state}, vínculos={bonds}, eliminaciones={deletions}"
            if any(kind == "error" for kind, _ in results):
                self.fail(label + " (error técnico)")
            elif state == "ACTIVO":
                self.check("ACTIVO" in bonds and expires is None and deletions == 0 and results[0][0] == "ok", label + " (incorporada: debe quedar vinculada, sin plazo y sin eliminación)")
                wins["incorporada"] += 1
            else:
                self.check(state == "ELIMINADO" and "ACTIVO" not in bonds and deletions == 1 and results[0][0] != "ok",
                           label + " (eliminada: sin vínculo activo, una sola eliminación y la aceptación debe fallar)")
                wins["eliminada"] += 1
        print(f"   resultados: {wins}")

    def r2_create_vs_delete(self, rounds):
        print(f"R2 crear una institución vs eliminación automática ({rounds} rondas)")
        wins = {"propietaria": 0, "eliminada": 0}
        for n in range(rounds):
            with self.makeSession() as s:
                person = self.user(s, f"creadora{n}")
                idUsuario = person.idUsuario
            digits = "".join(str(random.randint(0, 9)) for _ in range(8))

            def create(session, idUsuario=idUsuario, digits=digits):
                return institutions.createInstitution(session, session.get(User, idUsuario), InstitutionCreateRequest(
                    nombre=f"ZZ Concurrencia {self.tag}", tipoInstitucion="HOSPITAL", identificadorLegal=_cuit(digits)))

            def delete(session, idUsuario=idUsuario):
                return accountLifecycle.deleteExpired(session, idUsuario, nowForDb())

            results = self.race(create, delete)
            state, expires, bonds, deletions = self.snapshot(idUsuario)
            label = f"R2 ronda {n}: {[r[0] + ':' + str(r[1])[:40] for r in results]} -> {state}, vínculos={bonds}, eliminaciones={deletions}"
            if any(kind == "error" for kind, _ in results):
                self.fail(label + " (error técnico)")
            elif state == "ACTIVO":
                self.check(bonds == ["ACTIVO"] and expires is None and deletions == 0 and results[0][0] == "ok", label + " (propietaria: vínculo activo y sin plazo)")
                wins["propietaria"] += 1
            else:
                self.check(state == "ELIMINADO" and "ACTIVO" not in bonds and deletions == 1 and results[0][0] != "ok", label + " (eliminada y sin institución creada)")
                wins["eliminada"] += 1
        print(f"   resultados: {wins}")

    def r3_double_sweep(self, rounds):
        print(f"R3 dos pasadas de eliminación simultáneas ({rounds} rondas)")
        for n in range(rounds):
            with self.makeSession() as s:
                person = self.user(s, f"doble{n}")
                idUsuario, address = person.idUsuario, person.correoElectronico

            def delete(session, idUsuario=idUsuario):
                return accountLifecycle.deleteExpired(session, idUsuario, nowForDb())

            results = self.race(delete, delete, delete)
            state, _, _, deletions = self.snapshot(idUsuario)
            deleted = [r for r in results if r[0] == "ok" and r[1][0] == accountLifecycle.ELIMINADA]
            label = f"R3 ronda {n}: {[(k, v if k != 'ok' else v) for k, v in results]}"
            if any(kind == "error" for kind, _ in results):
                self.fail(label + " (error técnico)")
                continue
            self.check(state == "ELIMINADO" and deletions == 1 and len(deleted) == 1, label + f" -> estado={state}, eliminaciones={deletions}: debe ser una sola")
            self.check(len(self.mailsTo(address)) == 1, f"R3 ronda {n}: debe enviarse un solo correo de eliminación (hubo {len(self.mailsTo(address))})")


def _deadInvitedAccount(self, s, owner, institution, email, expiredRelation: bool):
    """Cuenta invitada sin salida: la invitación está cancelada (o vencida) y su enlace de activación venció."""
    invitation = institutions.invite(s, owner, institution, "MODERADOR", email, nombre="sin", apellido="salida")
    if expiredRelation:
        s.execute(update(InstitutionUser).where(InstitutionUser.idInstitucionUsuario == invitation.idInstitucionUsuario)
                  .values(fechaInvitacion=nowForDb() - timedelta(days=8)))
    else:
        institutions.revokeMember(s, owner, institution, "MODERADOR", invitation.idInstitucionUsuario)
    guest = s.scalar(select(User).where(User.correoElectronico == email))
    s.execute(update(AccountToken).where(AccountToken.idUsuario == guest.idUsuario).values(
        fechaCreacion=nowForDb() - timedelta(days=9), fechaExpiracion=nowForDb() - timedelta(days=1)))
    s.commit()
    return guest.idUsuario, invitation.idInstitucionUsuario


def _liveInvitationFor(self, email):
    """Estado de la invitación vigente de ese correo, leído con una conexión nueva: (cuentas con el correo, estado, invitaciones vivas, enlaces válidos)."""
    with self.makeSession() as s:
        users = list(s.scalars(select(User).where(User.correoElectronico == email)))
        if len(users) != 1:
            return len(users), None, 0, 0
        user = users[0]
        live = s.scalar(select(func.count()).select_from(InstitutionUser).where(
            InstitutionUser.idUsuarioInvitado == user.idUsuario, InstitutionUser.estadoRelacion == "PENDIENTE",
            InstitutionUser.fechaInvitacion > nowForDb() - timedelta(days=7)))
        links = s.scalar(select(func.count()).select_from(AccountToken).where(
            AccountToken.idUsuario == user.idUsuario, AccountToken.fechaUso.is_(None), AccountToken.fechaExpiracion > nowForDb()))
        return 1, user.estado, live, links


def _r4(self, rounds):
    print(f"R4 nueva invitación vs depuración de la cuenta invitada sin salida ({rounds} rondas)")
    wins = {"invitacion_gano": 0, "depuracion_gano": 0}
    for n in range(rounds):
        email = f"zz-conc-{self.tag}-inv{n}@example.com"
        with self.makeSession() as s:
            owner = self.user(s, f"duenio4-{n}", expired=False)
            self.institution(s, owner)
            institution = s.scalar(select(InstitutionUser.idInstitucion).where(InstitutionUser.idUsuarioInvitado == owner.idUsuario))
            oldId, _ = _deadInvitedAccount(self, s, owner, institution, email, expiredRelation=False)
            ownerId = owner.idUsuario

        def invite(session, ownerId=ownerId, institution=institution, email=email):
            return institutions.invite(session, session.get(User, ownerId), institution, "MODERADOR", email, nombre="sin", apellido="salida")

        def purge(session, oldId=oldId):
            return pendingAccounts.purgeOne(session, oldId, nowForDb())

        results = self.race(invite, purge)
        accounts, state, live, links = _liveInvitationFor(self, email)
        label = f"R4 ronda {n}: {[(k, str(v)[:(400 if k == 'error' else 30)]) for k, v in results]} -> cuentas={accounts}, estado={state}, invitaciones vivas={live}, enlaces válidos={links}"
        if any(kind == "error" for kind, _ in results):
            self.fail(label + " (error técnico)")
            continue
        # En cualquier orden debe quedar UNA cuenta con ese correo, pendiente, con la invitación nueva viva y su enlace utilizable.
        self.check(results[0][0] == "ok" and accounts == 1 and state == "PENDIENTE" and live == 1 and links == 1,
                   label + " (la invitación nueva debe quedar viva y utilizable)")
        with self.makeSession() as s:
            old = s.get(User, oldId).estado
        wins["depuracion_gano" if old == "ELIMINADO" else "invitacion_gano"] += 1
    print(f"   resultados: {wins}")


def _r5(self, rounds):
    print(f"R5 reenvío de una invitación vencida vs depuración de la cuenta invitada ({rounds} rondas)")
    wins = {"reenvio_gano": 0, "depuracion_gano": 0}
    for n in range(rounds):
        email = f"zz-conc-{self.tag}-rev{n}@example.com"
        with self.makeSession() as s:
            owner = self.user(s, f"duenio5-{n}", expired=False)
            self.institution(s, owner)
            institution = s.scalar(select(InstitutionUser.idInstitucion).where(InstitutionUser.idUsuarioInvitado == owner.idUsuario))
            oldId, relationId = _deadInvitedAccount(self, s, owner, institution, email, expiredRelation=True)
            ownerId = owner.idUsuario

        def resend(session, ownerId=ownerId, institution=institution, relationId=relationId):
            return institutions.resendInvitation(session, session.get(User, ownerId), institution, "MODERADOR", relationId)

        def purge(session, oldId=oldId):
            return pendingAccounts.purgeOne(session, oldId, nowForDb())

        results = self.race(resend, purge)
        with self.makeSession() as s:
            old = s.get(User, oldId).estado
        _, state, live, links = _liveInvitationFor(self, email)
        label = f"R5 ronda {n}: {[(k, str(v)[:(400 if k == 'error' else 30)]) for k, v in results]} -> cuenta={old}, vivas={live}, enlaces={links}"
        if any(kind == "error" for kind, _ in results):
            self.fail(label + " (error técnico)")
        elif results[0][0] == "ok":  # el reenvío respondió bien: la invitación debe seguir viva y la cuenta intacta
            self.check(old == "PENDIENTE" and live == 1 and links == 1, label + " (reenvío exitoso: invitación viva y cuenta pendiente)")
            wins["reenvio_gano"] += 1
        else:  # perdió: la cuenta fue depurada y el reenvío informó que no encontró la invitación
            self.check(old == "ELIMINADO" and results[0][1] == "INVITACION_NO_ENCONTRADA", label + " (depurada: el reenvío debe fallar limpiamente)")
            wins["depuracion_gano"] += 1
    print(f"   resultados: {wins}")


Run.r4_invite_vs_purge = _r4
Run.r5_resend_vs_purge = _r5


def lockCheck(makeSession) -> list[str]:
    """Comprobación DETERMINISTA del bloqueo de fila: una sesión toma la fila de Usuario con UPDLOCK sin confirmar y otra, independiente, no
    puede tomarla (expira por tiempo de espera, error 1222) hasta que la primera termina. Solo tiene sentido en SQL Server."""
    from sqlalchemy import text
    from app.services import accountGrace
    harness = Run(makeSession)
    problems = []
    with makeSession() as setup:
        person = harness.user(setup, "bloqueo")
        idUsuario = person.idUsuario
    first, second = makeSession(), makeSession()
    try:
        accountGrace.lockUser(first, idUsuario)  # transacción abierta con UPDLOCK
        second.execute(text("SET LOCK_TIMEOUT 1500"))
        started = time.time()
        try:
            accountGrace.lockUser(second, idUsuario)
            problems.append("la segunda sesión obtuvo la fila bloqueada: el bloqueo UPDLOCK no se aplicó")
        except Exception as error:  # noqa: BLE001
            if "1222" not in str(error):
                problems.append(f"error inesperado en la segunda sesión: {error!r}")
            elif time.time() - started < 1.0:
                problems.append("el tiempo de espera fue demasiado corto")
        second.rollback()
        first.rollback()  # libera el bloqueo
        accountGrace.lockUser(second, idUsuario)
        second.rollback()
    finally:
        first.close()
        second.close()
    return problems


def run(makeSession, rounds=10, tolerateLocks=False) -> Run:
    """Corre los tres escenarios con datos sintéticos y devuelve el resumen."""
    from app.integrations.email import sender
    harness = Run(makeSession, tolerateLocks)

    class Inline:
        def submit(self, fn, *args, **kwargs):
            return fn(*args, **kwargs)

    def fakeSend(recipient, subject, html, plainText, inlineImages=(), replyTo=None):
        if subject == "Tu cuenta de GlucoLume fue eliminada":
            harness.mails.append((recipient, subject))

    original = (sender.sendHtmlEmail, emailService._executor)
    sender.sendHtmlEmail, emailService._executor = fakeSend, Inline()
    try:
        harness.r1_accept_vs_delete(rounds)
        harness.r2_create_vs_delete(rounds)
        harness.r3_double_sweep(rounds)
        harness.r4_invite_vs_purge(rounds)
        harness.r5_resend_vs_purge(rounds)
    finally:
        sender.sendHtmlEmail, emailService._executor = original
    return harness


def main(argv) -> int:
    from app.core.config import getSettings
    from app.db.session import getSessionFactory
    name = getSettings().DB_NAME
    if name.lower() == "glucolume" and os.environ.get("LIFECYCLE_CONCURRENCY_PERMITIR_BASE_REAL") != "SI":
        print("La base «GlucoLume» es la real: esta prueba no se ejecuta ahí. Usá una base de pruebas aislada (DB_NAME=...).")
        return 2
    if os.environ.get("LIFECYCLE_CONCURRENCY_CONFIRM") != name:
        print(f"Esta prueba ESCRIBE datos sintéticos en la base «{name}». Para ejecutarla definí LIFECYCLE_CONCURRENCY_CONFIRM={name}.")
        return 2
    if "--bloqueos" in argv:
        problems = lockCheck(getSessionFactory())
        print("Bloqueo de fila (UPDLOCK) entre sesiones independientes:", "CORRECTO" if not problems else problems)
        return 1 if problems else 0
    rounds = int(argv[argv.index("--rondas") + 1]) if "--rondas" in argv else 10
    harness = run(getSessionFactory(), rounds)
    print(f"\n{harness.checks - len(harness.failures)}/{harness.checks} comprobaciones correctas; marca de datos sintéticos: zz-conc-{harness.tag}")
    return 1 if harness.failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
