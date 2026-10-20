# RecoverAdmin - Recuperación controlada de la administración de la plataforma GlucoLume
#
# Se ejecuta en el servidor (quien lo corre ya controla el entorno, igual que initAdmin). No hay ruta HTTP ni contraseña maestra: la persona
# que recupera su acceso o la que lo recibe usa enlaces de un solo uso y MFA. Todo queda en Auditoria (RECUPERAR_ADMINISTRACION_PLATAFORMA /
# REINVITAR_ADMINISTRADOR_PLATAFORMA), siempre con el motivo, sin enlaces, contraseñas ni códigos.
#
#   Reemplazar al administrador (pérdida de acceso, desactivación, necesidad de reemplazo) por un moderador del sistema activo y con MFA:
#       python -m app.cli.recoverAdmin reemplazar --destino moderador@ejemplo.com --motivo "…"      [--conservar-anterior]
#   Recuperar el acceso de la MISMA persona (olvidó la contraseña y no puede usar el restablecimiento, o perdió el segundo factor):
#       python -m app.cli.recoverAdmin reinvitar --motivo "…" [--resetear-mfa] [--mostrar-enlace]
#
# Nunca deja dos administradores vigentes (UX_Usuario_administradorUnico + cambios condicionados en una sola transacción) ni ninguno.
# Pide confirmación escribiendo el correo afectado. --confirmar la omite solo para automatización controlada y además exige que quien la
# ejecuta declare la autorización con GLUCOLUME_RECUPERACION_AUTORIZADA=SI (así un script copiado o una ejecución accidental no recupera nada).
# Cada ejecución —también las rechazadas— deja en Auditoria el motivo, el usuario del sistema y el equipo desde donde se corrió.

import argparse
import os
import sys

from sqlalchemy import select

from app.core.exceptions import AuthError
from app.db.session import getSessionFactory
from app.models.user import User
from app.services import platform as platformService
from app.utils.normalizers import normalizeEmail, normalizeSentence


AUTHORIZATION_ENV = "GLUCOLUME_RECUPERACION_AUTORIZADA"


def _confirm(args, out, expected: str, question: str) -> bool:
    if args.confirmar:
        if os.environ.get(AUTHORIZATION_ENV) != "SI":
            out(f"--confirmar exige declarar la autorización con {AUTHORIZATION_ENV}=SI: no se hizo nada.")
            return False
        return True
    answer = input(f"{question} Escribí el correo ({expected}) para confirmar: ")
    if normalizeEmail(answer) != expected:
        out("Confirmación incorrecta: no se hizo nada.")
        return False
    return True


def run(argv: list[str] | None = None, sessionFactory=None, out=print) -> int:
    parser = argparse.ArgumentParser(description="Recuperación controlada de la administración de GlucoLume.")
    commands = parser.add_subparsers(dest="comando", required=True)
    replace = commands.add_parser("reemplazar", help="Otro moderador del sistema pasa a ser el administrador.")
    replace.add_argument("--destino", required=True, help="Correo del moderador del sistema (activo y con MFA).")
    replace.add_argument("--conservar-anterior", action="store_true", help="El administrador anterior queda como moderador (por omisión, sin acceso).")
    reinvite = commands.add_parser("reinvitar", help="El administrador actual recupera su acceso con un enlace de un solo uso.")
    reinvite.add_argument("--resetear-mfa", action="store_true", help="Elimina su segundo factor: deberá configurarlo de nuevo.")
    reinvite.add_argument("--mostrar-enlace", action="store_true", help="Imprime el enlace (sin SMTP), por única vez.")
    for sub in (replace, reinvite):
        sub.add_argument("--motivo", required=True, help="Por qué se recupera (queda en la auditoría).")
        sub.add_argument("--confirmar", action="store_true", help="Confirma sin preguntar (automatización controlada).")
    args = parser.parse_args(argv)
    motivo = normalizeSentence(args.motivo)
    if not motivo:
        out("El motivo es obligatorio.")
        return 2
    db = (sessionFactory or getSessionFactory())()
    try:
        if args.comando == "reemplazar":
            destino = normalizeEmail(args.destino)
            if not _confirm(args, out, destino, f"Se hará ADMINISTRADOR DEL SISTEMA a <{destino}> y se retirará al actual."):
                return 1
            previous, new = platformService.replaceAdministrator(db, destino, motivo, args.conservar_anterior)
            out(f"Listo: {new.idUsuario} es ahora el administrador del sistema. Anterior {previous.idUsuario}: "
                f"{'moderador' if previous.estado == 'ACTIVO' else 'sin acceso'}. Sus sesiones se cerraron.")
            return 0
        current = db.scalar(select(User).where(User.tipoCuenta == platformService.ADMIN, User.estado != "ELIMINADO"))
        if current is None:
            out("No hay un administrador del sistema para recuperar: usá app.cli.initAdmin.")
            return 1
        if not _confirm(args, out, normalizeEmail(current.correoElectronico), "Se le cerrarán las sesiones al administrador y recibirá un enlace nuevo."):
            return 1
        user, link, expires, sent = platformService.reinviteAdministrator(db, motivo, args.resetear_mfa)
        out(f"Enlace creado para el administrador {user.idUsuario}. Vence: {expires:%d/%m/%Y %H:%M}.")
        out("Se envió el correo con el enlace." if sent else "No se pudo enviar el correo.")
        if args.mostrar_enlace:
            out(f"Enlace de activación (único, no se vuelve a mostrar): {link}")
        elif not sent:
            out("Volvé a ejecutar el comando con --mostrar-enlace si necesitás el enlace.")
        return 0
    except AuthError as error:
        out(f"No se recuperó: {error.message}")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(run())
