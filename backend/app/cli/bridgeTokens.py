# BridgeTokens - Administración de las credenciales individuales de los puentes serie (H-16)
#
# Cada puente tiene su propio token, atado a un código de dispositivo y con vencimiento. El token en claro se muestra UNA sola vez al crearlo o
# rotarlo: copiarlo al bridge.env de ese equipo (BRIDGE_TOKEN) y no guardarlo en ningún otro lado. En la base solo queda su hash.
#
#     python -m app.cli.bridgeTokens listar                       # solo lectura: huella, nombre, dispositivo, estado, vencimiento, último uso
#     python -m app.cli.bridgeTokens crear   --nombre "Puente laboratorio" --dispositivo GLUCOLUME-01 [--dias 180] --confirmo-base <DB_NAME>
#     python -m app.cli.bridgeTokens rotar   --huella 1a2b3c4d [--superposicion-horas 24] [--dias 180] --confirmo-base <DB_NAME>
#     python -m app.cli.bridgeTokens revocar --huella 1a2b3c4d --confirmo-base <DB_NAME>
#
# Las operaciones que escriben exigen nombrar la base configurada (como mfaKeys): no corren por error contra otra. Usan la cuenta de base de los
# procesos de conservación (DB_JOBS_USER) si está configurada; la cuenta de la API solo lee y registra el último uso (GlucoLume_permisos.sql).

import argparse
import sys

from app.core.config import getSettings
from app.db.session import getJobsSessionFactory
from app.services import bridgeCredentials


def _print(rows: list[dict]) -> None:
    if not rows:
        print("No hay credenciales individuales de puente.")
        return
    print(f"{'HUELLA':<10}{'ESTADO':<10}{'DISPOSITIVO':<24}{'VENCE':<21}{'ÚLTIMO USO':<21}NOMBRE")
    for row in rows:
        last = row["ultimoUso"].isoformat(" ", "seconds") if row["ultimoUso"] else "nunca"
        print(f"{row['huella']:<10}{row['estado']:<10}{row['dispositivo']:<24}{row['vence'].isoformat(' ', 'seconds'):<21}{last:<21}{row['nombre']}")


def _showToken(label: str, credential, token: str) -> None:
    print(f"{label}: huella {bridgeCredentials.fingerprint(credential.tokenHash)}, dispositivo {credential.codigoDispositivo}, "
          f"vence {credential.fechaExpiracion.isoformat(' ', 'seconds')}.")
    print("TOKEN (se muestra una sola vez; copialo al bridge.env de ese equipo como BRIDGE_TOKEN):")
    print(token)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Credenciales individuales de los puentes serie.")
    sub = parser.add_subparsers(dest="orden", required=True)
    sub.add_parser("listar", help="Lista las credenciales (solo lectura).")
    create = sub.add_parser("crear", help="Crea una credencial para un puente y un dispositivo.")
    create.add_argument("--nombre", required=True)
    create.add_argument("--dispositivo", required=True, help="Código del dispositivo en el inventario al que queda atada.")
    create.add_argument("--dias", type=int, default=bridgeCredentials.DEFAULT_VALID_DAYS)
    rotate = sub.add_parser("rotar", help="Emite una credencial nueva y acorta la anterior.")
    rotate.add_argument("--huella", required=True)
    rotate.add_argument("--superposicion-horas", type=int, default=bridgeCredentials.DEFAULT_OVERLAP_HOURS)
    rotate.add_argument("--dias", type=int, default=bridgeCredentials.DEFAULT_VALID_DAYS)
    revoke = sub.add_parser("revocar", help="Revoca una credencial de inmediato.")
    revoke.add_argument("--huella", required=True)
    for item in (create, rotate, revoke):
        item.add_argument("--confirmo-base", default=None, help="Nombre exacto de la base configurada (DB_NAME).")
    args = parser.parse_args(argv)

    if args.orden != "listar" and args.confirmo_base != getSettings().DB_NAME:
        print("No se modificó nada: --confirmo-base debe ser el nombre exacto de la base configurada.", file=sys.stderr)
        return 2
    with getJobsSessionFactory()() as db:
        if not bridgeCredentials.available(db):
            print("La base instalada no tiene la tabla PuenteCredencial: aplicá primero el esquema (docs/SEGURIDAD.md, H-16).", file=sys.stderr)
            return 3
        try:
            if args.orden == "listar":
                _print(bridgeCredentials.listAll(db))
            elif args.orden == "crear":
                credential, token = bridgeCredentials.create(db, args.nombre, args.dispositivo, args.dias)
                _showToken("Credencial creada", credential, token)
            elif args.orden == "rotar":
                credential, token = bridgeCredentials.rotate(db, args.huella, args.superposicion_horas, args.dias)
                _showToken("Credencial rotada (la anterior vale unas horas más)", credential, token)
            else:
                credential = bridgeCredentials.revoke(db, args.huella)
                print(f"Credencial {bridgeCredentials.fingerprint(credential.tokenHash)} revocada.")
        except ValueError as error:
            print(f"Error: {error}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
