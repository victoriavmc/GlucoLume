# MfaKeys - Diagnóstico de las claves de cifrado de MFA (GL-06), sin mostrar nunca una clave
#
# Si el .env define MFA_ENCRYPTION_KEY más de una vez, vale la última y los secretos TOTP cifrados con otra dejarían de descifrarse. Antes de
# quitar una línea hay que saber cuál descifra los factores guardados:
#
#     python -m app.cli.mfaKeys                 # solo lectura: cuántos factores descifra cada clave candidata
#     python -m app.cli.mfaKeys --reencriptar --confirmo-base <nombre de la base>
#                                               # vuelve a cifrar con la clave vigente lo cifrado con una anterior (escribe en la base)
#
# Claves candidatas: cada aparición de MFA_ENCRYPTION_KEY en el .env (por número de línea) y las de MFA_PREVIOUS_ENCRYPTION_KEYS. Se informan
# con una huella corta (SHA-256 truncado), nunca con su valor. Procedimiento recomendado: dejar en MFA_ENCRYPTION_KEY la clave que descifra los
# factores, pasar la otra (si descifra alguno) a MFA_PREVIOUS_ENCRYPTION_KEYS, reiniciar el backend y, con autorización, --reencriptar.

import argparse
import hashlib
import sys
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import ENV_FILE, envFileEntries, getSettings
from app.models.mfaFactor import MfaFactor


def fingerprint(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:8]


def candidates(envPath: Path) -> list[tuple[str, str]]:
    """(origen, clave) de cada clave candidata, sin repetir claves iguales. El origen nunca incluye la clave."""
    found: list[tuple[str, str]] = []
    for number, name, value in envFileEntries(envPath):
        if name == "MFA_ENCRYPTION_KEY" and value:
            found.append((f".env línea {number}", value))
    settings = getSettings()
    if settings.MFA_ENCRYPTION_KEY:
        found.append(("clave vigente (la que usa la aplicación)", settings.MFA_ENCRYPTION_KEY.get_secret_value()))
    for index, key in enumerate(settings.mfaKeys()[1:], start=1):
        found.append((f"MFA_PREVIOUS_ENCRYPTION_KEYS #{index}", key))
    unique: dict[str, tuple[str, str]] = {}
    for origin, key in found:
        if key in unique:
            unique[key] = (f"{unique[key][0]} = {origin}", key)
        else:
            unique[key] = (origin, key)
    return list(unique.values())


def report(db: Session, keys: list[tuple[str, str]]) -> list[dict]:
    """Cuántos secretos TOTP descifra cada clave. No modifica nada."""
    secrets = [row for row in db.scalars(select(MfaFactor.secretoCifrado)).all() if row]
    result = []
    for origin, key in keys:
        try:
            fernet = Fernet(key.encode("ascii"))
        except (ValueError, UnicodeEncodeError):
            result.append({"origen": origin, "huella": fingerprint(key), "valida": False, "descifra": 0, "total": len(secrets)})
            continue
        count = 0
        for secret in secrets:
            try:
                fernet.decrypt(secret.encode("ascii"))
                count += 1
            except InvalidToken:
                pass
        result.append({"origen": origin, "huella": fingerprint(key), "valida": True, "descifra": count, "total": len(secrets)})
    return result


def reencrypt(db: Session) -> tuple[int, int]:
    """Vuelve a cifrar con la clave vigente (MultiFernet.rotate). Devuelve (re-cifrados, no descifrables). Un secreto que ninguna clave
    descifra no se toca."""
    keys = getSettings().mfaKeys()
    if not keys:
        raise RuntimeError("MFA_ENCRYPTION_KEY no está configurada.")
    multi = MultiFernet([Fernet(key.encode("ascii")) for key in keys])
    done = failed = 0
    for factor in db.scalars(select(MfaFactor)).all():
        try:
            factor.secretoCifrado = multi.rotate(factor.secretoCifrado.encode("ascii")).decode("ascii")
            done += 1
        except InvalidToken:
            failed += 1
    db.commit()
    return done, failed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Diagnóstico de las claves de cifrado de MFA (no muestra claves).")
    parser.add_argument("--env-file", default=str(ENV_FILE))
    parser.add_argument("--reencriptar", action="store_true", help="Vuelve a cifrar con la clave vigente (escribe en la base).")
    parser.add_argument("--confirmo-base", default=None, help="Nombre de la base sobre la que se autoriza --reencriptar.")
    args = parser.parse_args(argv)
    from app.db.session import getSessionFactory

    db = getSessionFactory()()
    try:
        for row in report(db, candidates(Path(args.env_file))):
            state = "clave inválida" if not row["valida"] else f"descifra {row['descifra']} de {row['total']} factores"
            print(f"{row['origen']} (huella {row['huella']}): {state}")
        if args.reencriptar:
            if args.confirmo_base != getSettings().DB_NAME:
                print("No se re-cifró nada: --confirmo-base debe ser el nombre exacto de la base configurada.", file=sys.stderr)
                return 2
            done, failed = reencrypt(db)
            print(f"Re-cifrados con la clave vigente: {done}. Sin clave que los descifre: {failed}.")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
