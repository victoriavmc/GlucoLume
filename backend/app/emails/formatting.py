# EmailFormatting - Formato y enmascarado de datos mostrados en los correos

from datetime import date, datetime

from app.utils.timeZone import toDbTime

ROLE_LABELS = {
    "PROPIETARIO": "Propietario/a",
    "MODERADOR": "Moderador/a",
    "OPERADOR": "Operador/a",
    "MIEMBRO": "Integrante",
}

MFA_METHOD_LABELS = {
    "TOTP": "Aplicación autenticadora",
    "EMAIL": "Código por correo electrónico",
}


def formatDateTime(value) -> str:
    """dd/mm/aaaa hh:mm en hora de Argentina (la hora que persiste el backend)."""
    if isinstance(value, datetime):
        return f"{toDbTime(value):%d/%m/%Y %H:%M} (hora de Argentina)"
    if isinstance(value, date):
        return f"{value:%d/%m/%Y}"
    return str(value)


def formatDate(value) -> str:
    if isinstance(value, datetime):
        return f"{toDbTime(value):%d/%m/%Y}"
    if isinstance(value, date):
        return f"{value:%d/%m/%Y}"
    return str(value)


def maskEmail(email: str | None) -> str:
    """vi*****@gmail.com: conserva las 2 primeras letras de la parte local y el dominio."""
    if not email or "@" not in email:
        return ""
    local, _, domain = email.rpartition("@")
    visible = local[:2] if len(local) > 2 else local[:1]
    return f"{visible}{'*' * max(len(local) - len(visible), 3)}@{domain}"


def roleLabel(role: str | None) -> str:
    return ROLE_LABELS.get(role or "", role or "")


def mfaMethodLabel(method: str | None) -> str:
    return MFA_METHOD_LABELS.get(method or "", method or "")
