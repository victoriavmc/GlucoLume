# InitAdmin - Inicialización segura del PRIMER administrador del sistema de GlucoLume
#
# Se ejecuta en el servidor, con las credenciales de base de datos del .env (quien lo corre ya tiene control del entorno):
#
#     python -m app.cli.initAdmin --nombre Ana --apellido Pérez --correo ana@ejemplo.com
#
# - No hay ruta HTTP ni formulario público para crear administradores.
# - Se niega si ya existe un administrador del sistema activo (volver a ejecutarlo no crea otro).
# - No define contraseñas: crea la cuenta PENDIENTE y envía a ese correo un enlace de un solo uso; la persona elige su
#   usuario y su contraseña y debe activar MFA antes de operar. Queda en Auditoria (INICIALIZAR_ADMINISTRADOR).
# - Si el correo no pudo enviarse (SMTP sin configurar), --mostrar-enlace imprime el enlace por única vez en esta terminal.
# - Con una invitación de administrador ya pendiente para el mismo correo, la renueva (el enlace anterior deja de servir).

import argparse
import sys

from app.core.exceptions import AuthError
from app.db.session import getSessionFactory
from app.services import platform as platformService
from app.utils.normalizers import normalizeEmail, normalizeSentence


def run(argv: list[str] | None = None, sessionFactory=None, out=print) -> int:
    parser = argparse.ArgumentParser(description="Crea la invitación del primer administrador del sistema de GlucoLume.")
    parser.add_argument("--nombre", required=True)
    parser.add_argument("--apellido", required=True)
    parser.add_argument("--correo", required=True)
    parser.add_argument("--mostrar-enlace", action="store_true", help="Imprime el enlace de activación (sin SMTP).")
    parser.add_argument("--confirmar", action="store_true", help="Confirma sin preguntar (automatización controlada).")
    args = parser.parse_args(argv)
    nombre, apellido, correo = normalizeSentence(args.nombre), normalizeSentence(args.apellido), normalizeEmail(args.correo)
    if not (nombre and apellido and correo and "@" in correo):
        out("Nombre, apellido y un correo válido son obligatorios.")
        return 2
    if not args.confirmar:
        answer = input(f"Se invitará como ADMINISTRADOR DEL SISTEMA a {nombre} {apellido} <{correo}>. Escribí el correo para confirmar: ")
        if normalizeEmail(answer) != correo:
            out("Confirmación incorrecta: no se hizo nada.")
            return 1
    db = (sessionFactory or getSessionFactory())()
    try:
        user, link, expires, sent = platformService.initializeFirstAdmin(db, nombre, apellido, correo)
    except AuthError as error:
        out(f"No se inicializó: {error.message}")
        return 1
    finally:
        db.close()
    out(f"Invitación creada para el administrador {user.idUsuario}. Vence: {expires:%d/%m/%Y %H:%M}.")
    out("Se envió el correo con el enlace." if sent else "No se pudo enviar el correo.")
    if args.mostrar_enlace:
        out(f"Enlace de activación (único, no se vuelve a mostrar): {link}")
    elif not sent:
        out("Volvé a ejecutar el comando con --mostrar-enlace si necesitás el enlace.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
