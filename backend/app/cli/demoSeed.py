# DemoSeed - Carga, verificación y limpieza de los datos de DEMOSTRACIÓN académica
#
# Por defecto NO escribe nada (dry-run). Para escribir hay que pasar --aplicar. Ejemplos (desde backend/):
#
#     python -m app.cli.demoSeed                      # dry-run: qué se crearía, colisiones y cantidades
#     python -m app.cli.demoSeed --aplicar            # carga (idempotente: una segunda ejecución no duplica nada)
#     python -m app.cli.demoSeed --verificar          # comprueba cuentas y contraseñas del archivo privado (sin sesión)
#     python -m app.cli.demoSeed --limpiar            # dry-run de la limpieza (solo datos demo)
#     python -m app.cli.demoSeed --limpiar --aplicar  # elimina los datos demo (requiere DB_DEMO_USER)
#     python -m app.cli.demoSeed --aplicar --regenerar-contrasenas   # nuevas contraseñas demo (cuentas existentes incluidas)
#
# Nunca imprime contraseñas: van solo al archivo privado (ver app/demo/inventory.py).

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from app.demo import inventory, limpieza, seeder
from app.demo import catalog as C

def _parseAnchor(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.strptime(value, "%Y-%m-%d")


def _printPlan(plan: seeder.Plan, out) -> None:
    out("Resumen (CREAR = se agregará · YA_EXISTE = se conserva · REGENERAR_CONTRASENA = nueva contraseña):")
    for entidad, acciones in plan.conteo().items():
        detalle = ", ".join(f"{accion}: {n}" for accion, n in sorted(acciones.items()))
        out(f"  {entidad:<22} {detalle}")


def runSeed(args, out) -> int:
    seeder.assertAllowed(autorizarProduccion=args.autorizar_produccion, confirmarBase=args.confirmar_base)
    credenciales = Path(args.credenciales).expanduser() if args.credenciales else seeder.defaultCredentialsPath()
    seeder.assertOutsideRepo(credenciales)
    anchor = _parseAnchor(args.fecha_ancla) or seeder.defaultAnchor()
    from app.db.session import getSessionFactory
    session = getSessionFactory()()
    try:
        preview = seeder.buildPlan(session, anchor=anchor, regenerarContrasenas=args.regenerar_contrasenas)
        if preview.bloqueado:
            out("CARGA BLOQUEADA: hay datos que no son demo con los mismos identificadores. No se escribió nada:")
            for motivo in preview.bloqueos:
                out(f"  - {motivo}")
            return 1
        out(f"Fecha de ancla de los datos: {anchor:%Y-%m-%d}")
        _printPlan(preview, out)
        for advertencia in preview.advertencias:
            out(f"ADVERTENCIA: {advertencia}")
        if not args.aplicar:
            out("\nDry-run: no se escribió nada. Para cargar, ejecutá de nuevo con --aplicar.")
            return 0

        generate = list(dict.fromkeys(preview.cuentasACrear + preview.cuentasARegenerar))
        passwords = {key: seeder.generatePassword(C.ACCOUNTS_BY_KEY[key]) for key in generate}
        plan = seeder.buildPlan(session, anchor=anchor, passwords=passwords, regenerarContrasenas=args.regenerar_contrasenas)
        if plan.bloqueado:  # cambió la base entre las dos lecturas: no se escribe nada
            out("CARGA BLOQUEADA tras releer la base. No se escribió nada.")
            return 1
        created = seeder.apply(session, plan)
        out("\nCarga aplicada (una sola transacción):")
        for entidad, n in created.items():
            out(f"  {entidad:<22} creados: {n}")
    except seeder.SeedError as error:
        session.rollback()
        out(f"ERROR: {error}")
        return 1
    finally:
        session.close()

    known = inventory.readPasswords(credenciales)
    known.update(passwords)  # cuentas creadas o regeneradas en esta ejecución
    warnings = inventory.writePrivateFile(credenciales, known, anchor)
    out(f"\nArchivo privado de credenciales: {credenciales}")
    for warning in warnings:
        out(f"ADVERTENCIA: {warning}")
    missing = [a.key for a in C.ACCOUNTS if a.key not in known]
    if missing:
        out(f"Sin contraseña conocida para {len(missing)} cuenta(s) existentes: ejecutá con --regenerar-contrasenas para emitirlas.")
    if args.inventario_publico:
        target = Path(args.inventario_publico)
        inventory.writePublicMarkdown(target, anchor)
        out(f"Inventario público (sin contraseñas): {target}")
    return 0


def runVerify(args, out) -> int:
    credenciales = Path(args.credenciales).expanduser() if args.credenciales else seeder.defaultCredentialsPath()
    passwords = inventory.readPasswords(credenciales)
    from app.db.session import getSessionFactory
    session = getSessionFactory()()
    try:
        results = seeder.verifyAccounts(session, passwords)
    finally:
        session.close()
    fallos = 0
    for result in results:
        out(f"  {'OK   ' if result.ok else 'FALLA'} {result.cuenta:<22} {result.correo:<36} {result.detalle}")
        fallos += 0 if result.ok else 1
    out(f"\nCuentas verificadas: {len(results) - fallos} de {len(results)}. (No se abrió ninguna sesión ni se escribió auditoría.)")
    return 0 if fallos == 0 else 1


def runCleanup(args, out) -> int:
    seeder.assertAllowed(autorizarProduccion=args.autorizar_produccion, confirmarBase=args.confirmar_base)
    from app.db.session import getSessionFactory
    session = getSessionFactory()()
    try:
        cleanup = limpieza.plan(session)
    finally:
        session.close()
    if cleanup.bloqueada:
        out("LIMPIEZA BLOQUEADA: no se borró nada.")
        for motivo in cleanup.bloqueos:
            out(f"  - {motivo}")
        out("La auditoría es de solo inserción para la API (GL-03): esos registros no los elimina este procedimiento.")
        return 1
    out("Registros demo que se eliminarían (hijos antes que padres):")
    for tabla, n in cleanup.resumen().items():
        out(f"  {tabla:<22} {n}")
    if not cleanup.resumen():
        out("  (no hay datos demo cargados)")
        return 0
    if not args.aplicar:
        out("\nDry-run: no se borró nada. Para eliminar, ejecutá de nuevo con --limpiar --aplicar.")
        return 0
    from app.db.session import getDemoSessionFactory
    try:
        borrados = limpieza.execute(cleanup, getDemoSessionFactory())
    except (limpieza.LimpiezaBloqueada, RuntimeError) as error:
        out(f"ERROR: {error}")
        return 1
    out("Eliminado (una sola transacción):")
    for tabla, n in borrados.items():
        out(f"  {tabla:<22} {n}")
    return 0


def run(argv: list[str] | None = None, out=print) -> int:
    parser = argparse.ArgumentParser(description="Datos de demostración académica de GlucoLume (sintéticos).")
    parser.add_argument("--aplicar", action="store_true", help="Escribe en la base (sin esta bandera no se escribe nada).")
    parser.add_argument("--verificar", action="store_true", help="Verifica cuentas y contraseñas del archivo privado (sin sesión).")
    parser.add_argument("--limpiar", action="store_true", help="Elimina SOLO los datos demo (con --aplicar).")
    parser.add_argument("--regenerar-contrasenas", action="store_true", help="Emite nuevas contraseñas demo (con --aplicar).")
    parser.add_argument("--fecha-ancla", help="Fecha de referencia YYYY-MM-DD (por defecto, hoy).")
    parser.add_argument("--credenciales", help="Ruta del archivo privado de credenciales (fuera del repositorio).")
    parser.add_argument("--inventario-publico", help="Ruta del inventario Markdown sin contraseñas.")
    parser.add_argument("--autorizar-produccion", action="store_true", help="Solo para API_ENV=production (ver --confirmar-base).")
    parser.add_argument("--confirmar-base", help="Nombre exacto de la base, requerido con --autorizar-produccion.")
    args = parser.parse_args(argv)
    try:
        if args.verificar:
            return runVerify(args, out)
        if args.limpiar:
            return runCleanup(args, out)
        return runSeed(args, out)
    except seeder.SeedError as error:
        out(f"ERROR: {error}")
        return 1


if __name__ == "__main__":
    sys.exit(run())
