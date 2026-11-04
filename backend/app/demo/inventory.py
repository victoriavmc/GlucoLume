# Demo - Inventario de accesos: archivo PRIVADO (con contraseñas, fuera del repositorio) e inventario PÚBLICO (sin contraseñas)
#
# Archivo privado: texto plano con un bloque por cuenta. Permisos restrictivos (solo el usuario de Windows o POSIX 0600). Nunca
# se incluye en el repositorio, en imágenes Docker ni en logs. Su ruta por defecto es %USERPROFILE%\GlucoLumeDemo\ y puede
# cambiarse con GLUCOLUME_DEMO_CREDENCIALES o --credenciales.
#
# Inventario público: tabla Markdown sin contraseñas, apta para el anexo académico (docs/DATOS_DEMO.md).

from __future__ import annotations

import getpass
import os
import subprocess
from datetime import datetime
from pathlib import Path

from app.demo import catalog as C

PLACEHOLDER_NO_DISPONIBLE = "(no disponible: regenerar con --regenerar-contrasenas)"
CATEGORIAS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Usuarios individuales", ("individual-a",)),
    ("Integrantes del grupo familiar", ("grupo-admin", "grupo-integrante-1", "grupo-integrante-2", "grupo-integrante-3",
                                         "grupo-integrante-4", "grupo-integrante-5")),
    ("Propietarios", ("propietario-a", "propietario-b")),
    ("Moderadores", ("moderador-a-1", "moderador-a-2", "moderador-b-1", "moderador-b-2")),
    ("Operadores", tuple(f"operador-{i}-{n}" for i in ("a", "b") for n in (1, 2, 3, 4))),
)
PRIVACIDAD = ("Datos básicos", "Última medición", "Historial", "Avisos")


def _privacidad(key: str) -> str:
    for member, flags, _ in C.GROUP_MEMBERS:
        if member == key:
            return " · ".join(f"{label}: {'sí' if on else 'no'}" for label, on in zip(PRIVACIDAD, flags))
    if key == "grupo-admin":
        return "Sus datos no se comparten con el grupo (todas en no)"
    return "No aplica"


def _institucion(key: str) -> str:
    account = C.ACCOUNTS_BY_KEY[key]
    if account.key == "individual-a":
        return "Sin grupo familiar"
    if account.individual:
        return "Grupo familiar DEMO (administrador)" if key == "grupo-admin" else "Grupo familiar DEMO (integrante)"
    links = [s for s in C.STAFF if s.account == key]
    names = ", ".join(C.INSTITUTIONS_BY_KEY[s.institution].nombre for s in links)
    return names


def inventoryRows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for category, keys in CATEGORIAS:
        for key in keys:
            account = C.ACCOUNTS_BY_KEY[key]
            rows.append({
                "categoria": category,
                "clave": key,
                "nombre": f"{account.nombre} {account.apellido}",
                "correo": account.correo,
                "tipoCuenta": "Individual (CONSUMIDOR_FINAL)" if account.individual else "Institucional (USUARIO_INSTITUCIONAL)",
                "rol": account.rol,
                "institucion": _institucion(key),
                "privacidad": _privacidad(key),
                "escenario": account.escenario,
            })
    return rows


def writePrivateFile(path: Path, passwords: dict[str, str], anchor: datetime) -> list[str]:
    """Escribe el archivo privado. Devuelve advertencias (p. ej., permisos no aplicados). Nunca imprime contraseñas."""
    lines = [
        "GlucoLume - credenciales de DEMOSTRACIÓN (privado)",
        "NO compartir. NO subir al repositorio. Cuentas sintéticas: no corresponden a personas reales.",
        f"Fecha de ancla de los datos: {anchor:%Y-%m-%d}   Generado: {datetime.now():%Y-%m-%d %H:%M}",
        "Para regenerar contraseñas: python -m app.cli.demoSeed --aplicar --regenerar-contrasenas",
        "",
    ]
    for row in inventoryRows():
        password = passwords.get(row["clave"], PLACEHOLDER_NO_DISPONIBLE)
        lines += [
            f"[{row['clave']}]",
            f"Categoría: {row['categoria']}",
            f"Nombre: {row['nombre']}",
            f"Correo: {row['correo']}",
            f"Contraseña: {password}",
            f"Tipo de cuenta: {row['tipoCuenta']}",
            f"Rol: {row['rol']}",
            f"Institución o grupo: {row['institucion']}",
            f"Privacidad: {row['privacidad']}",
            f"Escenario: {row['escenario']}",
            "",
        ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return restrictPermissions(path)


def readPasswords(path: str | Path) -> dict[str, str]:
    """Lee las contraseñas del archivo privado (clave de cuenta → contraseña). Sin archivo, devuelve vacío."""
    file = Path(path)
    if not file.exists():
        return {}
    passwords: dict[str, str] = {}
    current: str | None = None
    for line in file.read_text(encoding="utf-8").splitlines():
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1]
        elif line.startswith("Contraseña: ") and current is not None:
            value = line[len("Contraseña: "):].strip()
            if value and not value.startswith("(no disponible"):
                passwords[current] = value
    return passwords


def restrictPermissions(path: Path) -> list[str]:
    """Solo el usuario actual puede leer el archivo. Windows: icacls sin herencia; POSIX: chmod 600."""
    warnings: list[str] = []
    try:
        if os.name == "nt":
            user = os.environ.get("USERNAME") or getpass.getuser()
            result = subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r", f"{user}:F"],
                                    capture_output=True, text=True, check=False)
            if result.returncode != 0:
                warnings.append("No se pudieron restringir los permisos del archivo con icacls: revisalos a mano.")
        else:
            os.chmod(path, 0o600)
    except OSError:
        warnings.append("No se pudieron restringir los permisos del archivo: revisalos a mano.")
    return warnings


def writePublicMarkdown(path: Path, anchor: datetime) -> None:
    """Inventario público sin contraseñas (para el anexo académico)."""
    out = [
        "# Cuentas de demostración: inventario sin contraseñas",
        "",
        f"Generado por `app/demo/inventory.py` para la fecha de ancla {anchor:%Y-%m-%d}. Todas las cuentas son sintéticas: los correos "
        "usan el dominio reservado `example.com`, los documentos llevan el prefijo `DEMO` y los dispositivos son `DEMO-DISP-*`. "
        "Las contraseñas están solo en el archivo privado de credenciales (fuera del repositorio).",
        "",
    ]
    for category, keys in CATEGORIAS:
        out += [f"## {category}", "", "| Clave | Nombre | Correo de acceso | Tipo de cuenta | Rol | Institución o grupo | "
                "Privacidad (grupo) | Escenario que demuestra |",
                "|---|---|---|---|---|---|---|---|"]
        for row in (r for r in inventoryRows() if r["categoria"] == category):
            out.append(f"| `{row['clave']}` | {row['nombre']} | `{row['correo']}` | {row['tipoCuenta']} | {row['rol']} | "
                       f"{row['institucion']} | {row['privacidad']} | {row['escenario']} |")
        out.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out), encoding="utf-8")
