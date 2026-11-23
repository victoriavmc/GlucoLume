# Demo - Carga y verificación de los datos de demostración (dry-run y aplicación)
#
# Flujo:
#   1. buildPlan() LEE la base (nunca escribe). Decide, registro por registro, si se CREA o YA EXISTE y detecta colisiones
#      (correo, CUIT, código de dispositivo, documento de paciente) con datos que no son demo. Con colisiones, no se aplica nada.
#   2. apply() escribe el plan en UNA transacción por etapas (usuarios → instituciones/grupo/dispositivos/credenciales → vínculos
#      → perfiles → mediciones). Cualquier error deshace todo. Las cuentas se crean con el mecanismo real de la aplicación: hash de
#      contraseña de security.py, credencial local, consentimientos del servicio de consentimientos y estado ACTIVO (el correo queda
#      verificado por este proceso autorizado). No se configura MFA.
#   3. Ninguna función de este módulo envía correo: no usa services/email ni services/notifications.
#
# Lo que verifican las pruebas (tests/test_demo_seed.py): idempotencia, aislamiento, cantidades, autenticación real, permisos por
# configuración de privacidad, aislamiento de pacientes entre operadores e instituciones, y que el administrador de plataforma
# existente no se modifica.
#
# Este módulo unifica catálogo (cuentas, dispositivos y mediciones sintéticas), inventario de credenciales
# y limpieza de datos demo. Las funciones públicas se usan como seeder.<nombre>.

from __future__ import annotations

import getpass
import os
import random
import secrets
import string
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import delete, inspect, select
from sqlalchemy.orm import Session, sessionmaker

from app.core import security
from app.core.config import getSettings
from app.db.base import Base
from app.models.accountDeviceLink import AccountDeviceLink
from app.models.audit import Audit
from app.models.consent import TipoConsentimiento
from app.models.device import Device
from app.models.group import Group
from app.models.groupUser import GroupUser
from app.models.localCredential import LocalCredential
from app.models.measurement import Measurement
from app.models.measurementProfile import MeasurementProfile
from app.models.mfaFactor import MfaFactor
from app.models.user import User
from app.services import consent as consentService
from app.services import matrix as matrixService
from app.services import schemaCompat
from app.services.audit import registerEvent
from app.services.measurementProfile import calculateAge
from app.utils.timeZone import nowForDb


# --- Catálogo: cuentas, grupo, dispositivos y mediciones sintéticas ---------------------------------------------

DEMO_NAMESPACE = uuid.UUID("6f1c2a7e-3b8d-4e51-9a0c-64d0e0b1d3a7")  # fijo: cambiarlo cambia todos los IDs demo
EMAIL_DOMAIN = "example.com"
NOTA_MEDICION = "DEMO - medición sintética de demostración académica. No es un dato médico ni un resultado validado."
NOTA_GRUPO = "Grupo familiar sintético de demostración académica."
HISTORY_START = date(2022, 1, 1)  # primera medición del historial demo
DATA_END_DATE = date(2026, 11, 23)  # último día del historial: la última medición de cada cuenta es ese día a las 17:00
DATA_END_HOUR = 17
HISTORY_DAYS = (DATA_END_DATE - HISTORY_START).days
HISTORY_START_DATETIME = datetime.combine(HISTORY_START, time(0, 0))

CONSUMIDOR_FINAL = "CONSUMIDOR_FINAL"
PERFIL_CONSUMIDOR = "CONSUMIDOR_FINAL"
ROL_PROPIETARIO = "PROPIETARIO"
MODO_GLUCOSA, MODO_OXIMETRIA = "GLUCOSA_EXPERIMENTAL", "OXIMETRIA"
ESTADO_COMPLETADA, ESTADO_CANCELADA, ESTADO_INVALIDA = "COMPLETADA", "CANCELADA", "INVALIDA"
ORIGEN_DEMO = "DEMO"
SENSOR_DEMO = "MAX30100"
VERSION_FIRMWARE_DEMO = "demo-1.0"
ALGORITMO_DEMO = "firmware-glucolume-max30100-v1"


def demoId(kind: str, key: str) -> uuid.UUID:
    """Identificador determinista de un registro demo (misma clave, mismo ID en cada ejecución)."""
    return uuid.uuid5(DEMO_NAMESPACE, f"{kind}:{key}")


# --- Cuentas individuales --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Account:
    key: str
    nombre: str
    apellido: str
    tipoCuenta: str
    sexo: str | None
    rol: str
    escenario: str
    fechaNacimiento: date | None = None

    @property
    def correo(self) -> str:
        return f"demo.{self.key}@{EMAIL_DOMAIN}"

    @property
    def id(self) -> uuid.UUID:
        return demoId("usuario", self.key)

    @property
    def individual(self) -> bool:
        return self.tipoCuenta == CONSUMIDOR_FINAL


ACCOUNTS: tuple[Account, ...] = (
    Account("individual-a", "Valeria", "Soto", CONSUMIDOR_FINAL, "FEMENINO", "Individual sin grupo",
            "A: perfil propio con mediciones, estadísticas, historial y última medición. Sin grupo familiar.", date(1990, 3, 14)),
    Account("grupo-admin", "Tomás", "Herrera", CONSUMIDOR_FINAL, "MASCULINO", "Individual - administrador de grupo familiar",
            "B: administra el grupo. Sus propios datos no están compartidos: el grupo no los ve.", date(1982, 7, 2)),
    Account("grupo-integrante-1", "Sofía", "Castro", CONSUMIDOR_FINAL, "FEMENINO", "Integrante del grupo familiar 1",
            "B - Integrante 1: solo datos básicos (edad y sexo).", date(2001, 11, 20)),
    Account("grupo-integrante-2", "Nicolás", "Vega", CONSUMIDOR_FINAL, "MASCULINO", "Integrante del grupo familiar 2",
            "B - Integrante 2: solo la última medición.", date(1975, 1, 9)),
    Account("grupo-integrante-3", "Julieta", "Pardo", CONSUMIDOR_FINAL, "FEMENINO", "Integrante del grupo familiar 3",
            "B - Integrante 3: solo el historial (incluye gráficos y estadísticas).", date(1968, 5, 30)),
    Account("grupo-integrante-4", "Mateo", "Ríos", CONSUMIDOR_FINAL, "MASCULINO", "Integrante del grupo familiar 4",
            "B - Integrante 4: solo avisos (fecha y hora de cada medición, nunca valores).", date(1996, 2, 25)),
    Account("grupo-integrante-5", "Carla", "Núñez", CONSUMIDOR_FINAL, "FEMENINO", "Integrante del grupo familiar 5",
            "B - Integrante 5: comparte datos básicos, última medición, historial y avisos.", date(1959, 12, 4)),
    Account("grupo-integrante-6", "Lucas", "Ferrari", CONSUMIDOR_FINAL, "MASCULINO", "Integrante del grupo familiar 6",
            "B - Integrante 6: comparte datos básicos, última medición, historial y avisos.", date(1989, 8, 17)),
    Account("grupo-integrante-7", "Julia", "Bravo", CONSUMIDOR_FINAL, "FEMENINO", "Integrante del grupo familiar 7",
            "B - Integrante 7: comparte datos básicos, última medición, historial y avisos.", date(1973, 4, 22)),
)
ACCOUNTS_BY_KEY = {account.key: account for account in ACCOUNTS}
# Nombre de usuario (login) de cada cuenta demo: individuo1 a individuo9, en el orden de ACCOUNTS.
USUARIOS_DEMO = {account.key: f"individuo{n}" for n, account in enumerate(ACCOUNTS, start=1)}

# Integrantes del grupo: permisos de compartición (compartePerfil, comparteUltimaMedicion, comparteHistorial, notificaMedicion)
# y frecuencia de medición propia (porcentaje de días del historial con medición: 1, 2 o 3 mediciones por día).
GROUP_MEMBERS: tuple[tuple[str, tuple[bool, bool, bool, bool], int], ...] = (
    ("grupo-integrante-1", (True, False, False, False), 35),
    ("grupo-integrante-2", (False, True, False, False), 50),
    ("grupo-integrante-3", (False, False, True, False), 40),
    ("grupo-integrante-4", (False, False, False, True), 30),
    ("grupo-integrante-5", (True, True, True, True), 55),
    ("grupo-integrante-6", (True, True, True, True), 45),
    ("grupo-integrante-7", (True, True, True, True), 25),
)
GROUP_ADMIN_ACTIVITY = 45
INDIVIDUAL_A_ACTIVITY = 60
GROUP_KEY = "familia-demo"
GROUP_NAME = "Grupo familiar DEMO"


# --- Dispositivos (uno propio por cuenta individual) -----------------------------------------------------------------


@dataclass(frozen=True)
class DemoDevice:
    key: str
    codigo: str

    @property
    def id(self) -> uuid.UUID:
        return demoId("dispositivo", self.key)


DEVICES: tuple[DemoDevice, ...] = (
    DemoDevice("ind-01", "DEMO-DISP-IND-01"),
    DemoDevice("ind-02", "DEMO-DISP-IND-02"),
    DemoDevice("ind-03", "DEMO-DISP-IND-03"),
    DemoDevice("ind-04", "DEMO-DISP-IND-04"),
    DemoDevice("ind-05", "DEMO-DISP-IND-05"),
    DemoDevice("ind-06", "DEMO-DISP-IND-06"),
    DemoDevice("ind-07", "DEMO-DISP-IND-07"),
    DemoDevice("ind-08", "DEMO-DISP-IND-08"),
    DemoDevice("ind-09", "DEMO-DISP-IND-09"),
)

# Dispositivo con el que mide cada cuenta individual (cada una tiene el suyo).
INDIVIDUAL_DEVICE_KEYS: dict[str, str] = {
    "individual-a": "ind-01",
    "grupo-admin": "ind-02",
    "grupo-integrante-1": "ind-03",
    "grupo-integrante-2": "ind-04",
    "grupo-integrante-3": "ind-05",
    "grupo-integrante-4": "ind-06",
    "grupo-integrante-5": "ind-07",
    "grupo-integrante-6": "ind-08",
    "grupo-integrante-7": "ind-09",
}


def deviceKeyForIndividual(accountKey: str) -> str:
    return INDIVIDUAL_DEVICE_KEYS[accountKey]


# --- Mediciones sintéticas -------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class MeasurementSpec:
    profileKey: str
    index: int
    dayOffset: int  # días hacia atrás desde la fecha de ancla (0 = DATA_END_DATE, hasta HISTORY_DAYS)
    hour: int
    minute: int
    modo: str
    estado: str
    condicion: str  # NO_INFORMADA | AYUNO | POSTPRANDIAL
    minutosDesdeComida: int | None
    frecuenciaCardiaca: int | None
    spo2: Decimal | None
    glucosa: Decimal | None
    calidadSenal: Decimal | None
    indiceOptico: Decimal | None
    lecturas: int | None

    @property
    def id(self) -> uuid.UUID:
        return demoId("medicion", f"{self.profileKey}:{self.index}")

    def start(self, anchor: datetime) -> datetime:
        return anchor - timedelta(days=self.dayOffset) + timedelta(hours=self.hour, minutes=self.minute)


def _glucosaDemo(rng: random.Random, condicion: str) -> Decimal:
    """Glucosa sintética (mg/dL) con valores en todas las zonas del semáforo: mayoría en rango, algunas fuera de rango."""
    roll = rng.random()
    if roll < 0.10:  # por debajo del rango de la condición
        low, high = 55, 70
    elif roll < 0.22:  # por encima del rango de la condición
        low, high = {"AYUNO": (108, 140), "POSTPRANDIAL": (176, 235), "NO_INFORMADA": (142, 190)}[condicion]
    else:
        low, high = {"AYUNO": (78, 104), "POSTPRANDIAL": (118, 172), "NO_INFORMADA": (92, 138)}[condicion]
    return Decimal(rng.randint(low * 10, high * 10)) / Decimal(10)


def _spec(profileKey: str, index: int, dayOffset: int, hour: int, minute: int, estado: str, rng: random.Random,
          baseBpm: int) -> MeasurementSpec:
    completed = estado == ESTADO_COMPLETADA
    modo = MODO_GLUCOSA if rng.random() < 0.6 else MODO_OXIMETRIA
    condicion = rng.choice(("AYUNO", "POSTPRANDIAL", "NO_INFORMADA"))
    minutosComida = None
    if condicion == "AYUNO":
        minutosComida = rng.randint(480, 720)
    elif condicion == "POSTPRANDIAL":
        minutosComida = rng.randint(45, 180)
    glucosa = _glucosaDemo(rng, condicion) if completed and modo == MODO_GLUCOSA else None
    return MeasurementSpec(
        profileKey=profileKey, index=index, dayOffset=dayOffset, hour=hour, minute=minute, modo=modo, estado=estado,
        condicion=condicion, minutosDesdeComida=minutosComida,
        frecuenciaCardiaca=max(52, min(110, baseBpm + rng.randint(-8, 14))) if completed else None,
        spo2=Decimal(rng.randint(950, 995)) / Decimal(10) if completed else None,
        glucosa=glucosa,
        calidadSenal=Decimal(str(round(rng.uniform(0.72, 0.98), 3))) if completed else None,
        indiceOptico=Decimal(str(round(rng.uniform(1.8, 2.9), 5))) if completed else None,
        lecturas=rng.randint(8, 25) if completed else None,
    )


def _estado(rng: random.Random) -> str:
    roll = rng.random()
    if roll < 0.02:
        return ESTADO_INVALIDA
    if roll < 0.06:
        return ESTADO_CANCELADA
    return ESTADO_COMPLETADA


def individualMeasurementsFor(profileKey: str, *, activity: int, baseBpm: int) -> tuple[MeasurementSpec, ...]:
    """Historial de una cuenta individual desde HISTORY_START hasta DATA_END_DATE. Cada día tiene medición con probabilidad
    `activity` (%), y ese día 1, 2 o 3 mediciones en horas distintas. El último día termina con una medición a las 17:00."""
    rng = random.Random(f"demo-mediciones:{profileKey}")
    out: list[MeasurementSpec] = []
    for dayOffset in range(HISTORY_DAYS, -1, -1):
        if dayOffset == 0:
            hours = sorted(rng.sample(range(7, DATA_END_HOUR), k=rng.randint(0, 2))) + [DATA_END_HOUR]
        elif rng.random() * 100 < activity:
            hours = sorted(rng.sample(range(7, 23), k=rng.choices((1, 2, 3), weights=(5, 3, 2))[0]))
        else:
            continue
        for position, hour in enumerate(hours):
            last = dayOffset == 0 and position == len(hours) - 1
            minute = 0 if last else rng.randint(0, 59)
            estado = ESTADO_COMPLETADA if last else _estado(rng)
            out.append(_spec(profileKey, len(out), dayOffset, hour, minute, estado, rng, baseBpm))
    return tuple(out)


def individualMeasurements() -> tuple[tuple[str, tuple[MeasurementSpec, ...]], ...]:
    """(clave de cuenta, mediciones) de cada cuenta individual."""
    plan = [("individual-a", INDIVIDUAL_A_ACTIVITY), ("grupo-admin", GROUP_ADMIN_ACTIVITY)]
    plan += [(key, activity) for key, _, activity in GROUP_MEMBERS]
    return tuple((key, individualMeasurementsFor(key, activity=activity, baseBpm=64 + (index * 3) % 14))
                 for index, (key, activity) in enumerate(plan))


def expectedCounts() -> dict[str, int]:
    """Cantidades previstas (la fuente del dry-run y de las pruebas)."""
    individuals = individualMeasurements()
    return {
        "usuarios": len(ACCOUNTS),
        "credenciales": len(ACCOUNTS),
        "consentimientos": 2 * len(ACCOUNTS),
        "grupos": 1,
        "vinculos_grupo": 1 + len(GROUP_MEMBERS),
        "dispositivos": len(DEVICES),
        "perfiles_individuales": len(ACCOUNTS),
        "mediciones_individuales": sum(len(items) for _, items in individuals),
    }


# --- Inventario: credenciales privadas e inventario público ----------------------------------------------------

PLACEHOLDER_NO_DISPONIBLE = "(no disponible: regenerar con --regenerar-contrasenas)"
CATEGORIAS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Usuarios individuales", ("individual-a",)),
    ("Integrantes del grupo familiar", ("grupo-admin", "grupo-integrante-1", "grupo-integrante-2", "grupo-integrante-3",
                                         "grupo-integrante-4", "grupo-integrante-5",
                                         "grupo-integrante-6", "grupo-integrante-7")),
)
PRIVACIDAD = ("Datos básicos", "Última medición", "Historial", "Avisos")


def _privacidad(key: str) -> str:
    for member, flags, _ in GROUP_MEMBERS:
        if member == key:
            return " · ".join(f"{label}: {'sí' if on else 'no'}" for label, on in zip(PRIVACIDAD, flags))
    if key == "grupo-admin":
        return "Sus datos no se comparten con el grupo (todas en no)"
    return "No aplica"


def _institucion(key: str) -> str:
    account = ACCOUNTS_BY_KEY[key]
    if account.key == "individual-a":
        return "Sin grupo familiar"
    return "Grupo familiar DEMO (administrador)" if key == "grupo-admin" else "Grupo familiar DEMO (integrante)"


def inventoryRows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for category, keys in CATEGORIAS:
        for key in keys:
            account = ACCOUNTS_BY_KEY[key]
            rows.append({
                "categoria": category,
                "clave": key,
                "nombre": f"{account.nombre} {account.apellido}",
                "correo": account.correo,
                "tipoCuenta": "Individual (CONSUMIDOR_FINAL)",
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
        f"Generado por `app/demo/seeder.py` para la fecha de ancla {anchor:%Y-%m-%d}. Todas las cuentas son sintéticas: los correos "
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


# --- Limpieza: solo datos demo ----------------------------------------------------------------------------------

TABLAS_PERMITIDAS = frozenset({
    "Medicion", "MedicionReferenciaCapilar", "MuestraSensor", "EnvioResultado", "AuditoriaTecnicaMedicion",
    "NotificacionUsuario", "SesionUsuario", "TokenCuenta", "ConsentimientoUsuario", "CredencialLocal",
    "CredencialLocalHistorial", "FactorMfa", "CodigoRecuperacionMfa", "IdentidadExterna", "PerfilMedicion", "VinculoCuentaDispositivo",
    "Dispositivo", "GrupoUsuario", "Grupo", "InstitucionUsuario", "Institucion", "Usuario", "TransferenciaPerfil",
})


class LimpiezaBloqueada(Exception):
    """La limpieza no puede completarse sin tocar datos que no son demo o auditoría. Nada se borró."""


@dataclass
class CleanupPlan:
    existentes: dict[str, set[uuid.UUID]] = field(default_factory=dict)  # tabla -> IDs a eliminar (incluye dependientes)
    orden: list[str] = field(default_factory=list)  # hijos antes que padres
    bloqueos: list[str] = field(default_factory=list)

    @property
    def bloqueada(self) -> bool:
        return bool(self.bloqueos)

    def resumen(self) -> dict[str, int]:
        return {tabla: len(self.existentes[tabla]) for tabla in self.orden if self.existentes.get(tabla)}


def _semillas() -> dict[str, set[uuid.UUID]]:
    """IDs fijos del catálogo, por tabla."""
    return {
        "Usuario": {a.id for a in ACCOUNTS},
        "Institucion": set(),  # el catálogo demo no tiene instituciones
        "Grupo": {demoId("grupo", GROUP_KEY)},
        "GrupoUsuario": {demoId("vinculo-grupo", k) for k in ["grupo-admin"] + [m[0] for m in GROUP_MEMBERS]},
        "InstitucionUsuario": set(),
        "Dispositivo": {d.id for d in DEVICES},
        "PerfilMedicion": {demoId("perfil", a.key) for a in ACCOUNTS if a.individual},
        "Medicion": {s.id for _, specs in individualMeasurements() for s in specs},
    }


def _table(name: str):
    """Tabla del modelo (el esquema es dbo: las claves de metadata llevan el prefijo)."""
    return Base.metadata.tables[f"dbo.{name}"]


def _pk(table):
    columns = list(table.primary_key.columns)
    if len(columns) != 1:
        raise LimpiezaBloqueada(f"La tabla {table.name} tiene clave compuesta: el procedimiento no la soporta.")
    return columns[0]


def _chunks(values: list, size: int = 500):
    for start in range(0, len(values), size):
        yield values[start:start + size]


def _existingPks(db: Session, table, ids: set[uuid.UUID]) -> set[uuid.UUID]:
    pk = _pk(table)
    found: set[uuid.UUID] = set()
    for chunk in _chunks(sorted(ids, key=str)):
        found.update(db.scalars(select(pk).where(pk.in_(chunk))).all())
    return found


def planificarLimpieza(db: Session) -> CleanupPlan:
    """Calcula qué se borraría. Solo lee."""
    result = CleanupPlan()
    tables = {table.name: table for table in Base.metadata.tables.values()}
    inspector = inspect(db.get_bind())
    present = {name for name, table in tables.items() if inspector.has_table(table.name, schema=table.schema)}
    found: dict[str, set[uuid.UUID]] = {}
    for name, ids in _semillas().items():
        existing = _existingPks(db, _table(name), ids)
        if existing:
            found[name] = existing

    changed = True
    while changed:  # cierre transitivo por claves foráneas (dependientes de dependientes)
        changed = False
        for parentName in list(found):
            for child in tables.values():
                if child.name not in present:  # la base no tiene esa tabla (p. ej., una base de prueba parcial): no puede tener datos
                    continue
                for fk in child.foreign_keys:
                    if fk.column.table.name != parentName or not fk.column.primary_key:
                        continue
                    childPk = _pk(child)
                    dependents: set[uuid.UUID] = set()
                    for chunk in _chunks(list(found[parentName])):
                        dependents.update(db.scalars(select(childPk).where(fk.parent.in_(chunk))).all())
                    new = dependents - found.get(child.name, set())
                    if new:
                        found.setdefault(child.name, set()).update(new)
                        changed = True
    result.existentes = found

    for name in found:
        if name not in TABLAS_PERMITIDAS:
            result.bloqueos.append(f"Hay {len(found[name])} registro(s) en {name} que el procedimiento no puede eliminar "
                                   f"(auditoría o tabla no prevista).")
    result.orden = _deleteOrder(found)
    return result


def _deleteOrder(found: dict[str, set[uuid.UUID]]) -> list[str]:
    """Orden seguro de borrado: una tabla se borra cuando ninguna tabla pendiente la referencia (hijas primero, padres después)."""
    parentsOf: dict[str, set[str]] = {name: set() for name in found}
    for name in found:
        for fk in _table(name).foreign_keys:
            parent = fk.column.table.name
            if parent in found and parent != name:
                parentsOf[name].add(parent)
    order: list[str] = []
    remaining = {name: set(parents) for name, parents in parentsOf.items()}
    while remaining:
        ready = sorted(name for name in remaining
                       if not any(name in parents for other, parents in remaining.items() if other != name))
        if not ready:
            raise LimpiezaBloqueada("Ciclo de claves foráneas entre tablas demo: no se puede ordenar la limpieza.")
        for name in ready:
            order.append(name)
            del remaining[name]
    return order


def ejecutarLimpieza(cleanup: CleanupPlan, sessionFactory: sessionmaker) -> dict[str, int]:
    """Borra el plan en una transacción. Ante cualquier error, deshace todo."""
    if cleanup.bloqueada:
        raise LimpiezaBloqueada("La limpieza está bloqueada:\n- " + "\n- ".join(cleanup.bloqueos))
    borrados: dict[str, int] = {}
    session = sessionFactory()
    try:
        for name in cleanup.orden:
            ids = cleanup.existentes.get(name)
            if not ids:
                continue
            table = _table(name)
            pk = _pk(table)
            total = 0
            for chunk in _chunks(sorted(ids, key=str)):
                total += session.execute(delete(table).where(pk.in_(chunk))).rowcount or 0
            borrados[name] = total
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    return borrados


# --- Seeder: plan de solo lectura, aplicación transaccional y verificación --------------------------------------

ESTADO_ACTIVO = "ACTIVO"
PASSWORD_ALPHABET = string.ascii_letters + string.digits + "!#%&*+-=?@"
PASSWORD_LENGTH = 20
ETAPAS = 5  # 1 usuarios · 2 grupo, dispositivos y credenciales · 3 vínculos · 4 perfiles · 5 mediciones


class SeedError(Exception):
    """Carga rechazada: nada se escribió. El mensaje es apto para mostrar al operador (nunca contiene contraseñas)."""


@dataclass
class PlanItem:
    entidad: str
    clave: str
    accion: str  # CREAR | YA_EXISTE | REGENERAR_CONTRASENA
    detalle: str = ""


@dataclass
class AuditEntry:
    """Evento que la aplicación registra al hacer la acción. En la carga histórica, la fecha es la del hecho, no la de la carga."""
    accion: str
    actor: uuid.UUID  # usuario que hizo la acción
    tabla: str
    idRegistro: uuid.UUID
    fecha: datetime
    datosNuevos: dict | None = None
    datosPrevios: dict | None = None
    tablaRelacionada: str | None = None
    idRelacionado: uuid.UUID | None = None


@dataclass
class Plan:
    anchor: datetime
    items: list[PlanItem] = field(default_factory=list)
    bloqueos: list[str] = field(default_factory=list)
    advertencias: list[str] = field(default_factory=list)
    etapas: list[list[object]] = field(default_factory=lambda: [[] for _ in range(ETAPAS)])
    auditorias: list[AuditEntry] = field(default_factory=list)
    cuentasACrear: list[str] = field(default_factory=list)
    cuentasARegenerar: list[str] = field(default_factory=list)

    @property
    def bloqueado(self) -> bool:
        return bool(self.bloqueos)

    def conteo(self) -> dict[str, dict[str, int]]:
        out: dict[str, dict[str, int]] = {}
        for item in self.items:
            bucket = out.setdefault(item.entidad, {})
            bucket[item.accion] = bucket.get(item.accion, 0) + 1
        return out


@dataclass
class CheckResult:
    cuenta: str
    correo: str
    ok: bool
    detalle: str


# --- Autorización, entorno y rutas -----------------------------------------------------------------------------------


def assertAllowed(*, autorizarProduccion: bool = False, confirmarBase: str | None = None) -> None:
    """En API_ENV=production la carga solo corre con --autorizar-produccion Y --confirmar-base igual al nombre de la base."""
    settings = getSettings()
    if settings.API_ENV != "production":
        return
    if not autorizarProduccion or confirmarBase is None or confirmarBase != settings.DB_NAME:
        raise SeedError("API_ENV=production: la carga demo está bloqueada. Solo se ejecuta con --autorizar-produccion y "
                        "--confirmar-base <nombre exacto de la base>, decisión explícita del responsable del sistema.")


def defaultAnchor() -> datetime:
    """Medianoche del último día del historial demo (DATA_END_DATE): los datos terminan ese día a las 17:00, siempre."""
    return datetime.combine(DATA_END_DATE, time(0, 0))


def repoRoots() -> list[Path]:
    """Carpetas que nunca pueden contener el archivo de credenciales: el paquete backend (también dentro de la imagen Docker, donde
    no hay .git) y, si existe, la raíz del repositorio git que lo contiene."""
    backend = Path(__file__).resolve().parents[2]
    roots = [backend]
    for candidate in (backend, *backend.parents):
        if (candidate / ".git").exists():
            roots.append(candidate)
            break
    return roots


def assertOutsideRepo(path: str | Path) -> None:
    """El archivo con contraseñas nunca se escribe dentro del repositorio (ni en su contexto de build de Docker)."""
    resolved = Path(path).expanduser().resolve()
    for root in repoRoots():
        if resolved == root or root in resolved.parents:
            raise SeedError("El archivo de credenciales no puede estar dentro del repositorio: elegí una carpeta privada fuera de él.")


def defaultCredentialsPath() -> Path:
    override = os.environ.get("GLUCOLUME_DEMO_CREDENCIALES")
    if override:
        return Path(override).expanduser()
    return Path.home() / "GlucoLumeDemo" / "credenciales-demo.txt"


# --- Contraseñas ------------------------------------------------------------------------------------------------------


DEMO_PASSWORD_ENV = "GLUCOLUME_DEMO_PASSWORD"


def _commonPasswordFor(account: Account, password: str) -> str:
    """Valida la contraseña común elegida por el responsable para todas las cuentas demo. El mensaje nunca incluye la contraseña."""
    errors = security.passwordPolicyErrors(password)
    if errors:
        raise SeedError(f"{DEMO_PASSWORD_ENV} no cumple la política de contraseñas: " + "; ".join(errors))
    identifiers = (account.key, account.correo.split("@", 1)[0], account.nombre, account.apellido)
    if security.passwordContainsPersonalData(password, *identifiers):
        raise SeedError(f"{DEMO_PASSWORD_ENV} contiene datos de la cuenta {account.key}: elegí otra contraseña.")
    return password


def generatePassword(account: Account) -> str:
    """Contraseña de la cuenta demo. Si está definida GLUCOLUME_DEMO_PASSWORD, todas las cuentas usan esa (validada con la política).
    Si no, se genera una temporal aleatoria que cumple la política real (security.passwordPolicyErrors), no es común y no contiene
    el correo ni el nombre de la cuenta. Solo se escribe en el archivo privado de credenciales; nunca en logs ni reportes."""
    common = os.environ.get(DEMO_PASSWORD_ENV)
    if common:
        return _commonPasswordFor(account, common)
    identifiers = (account.key, account.correo.split("@", 1)[0], account.nombre, account.apellido)
    while True:
        candidate = "".join(secrets.choice(PASSWORD_ALPHABET) for _ in range(PASSWORD_LENGTH))
        if security.passwordPolicyErrors(candidate):
            continue
        if security.isCommonPassword(candidate) or security.passwordContainsPersonalData(candidate, *identifiers):
            continue
        return candidate


# --- Plan (solo lectura) ---------------------------------------------------------------------------------------------


def _exists(db: Session, model, key) -> bool:
    return db.get(model, key) is not None


def _existingIds(db: Session, column, ids: list[uuid.UUID]) -> set[uuid.UUID]:
    found: set[uuid.UUID] = set()
    for start in range(0, len(ids), 500):
        found.update(db.scalars(select(column).where(column.in_(ids[start:start + 500]))).all())
    return found


def _collisions(db: Session, plan: Plan) -> None:
    for account in ACCOUNTS:
        other = db.scalar(select(User.idUsuario).where(User.correoElectronico == account.correo))
        if other is not None and other != account.id:
            plan.bloqueos.append(f"Ya existe una cuenta con el correo {account.correo} que no es demo.")
    for device in DEVICES:
        other = db.scalar(select(Device.idDispositivo).where(Device.codigoDispositivo == device.codigo))
        if other is not None and other != device.id:
            plan.bloqueos.append(f"Ya existe un dispositivo con el código {device.codigo} que no es demo.")


def buildPlan(db: Session, *, anchor: datetime | None = None, passwords: dict[str, str] | None = None,
              regenerarContrasenas: bool = False) -> Plan:
    """Calcula qué se crearía. Solo lee la base. Con `passwords` (modo aplicar) arma también los registros a insertar: cada cuenta
    que se crea o se regenera debe tener su contraseña en ese diccionario."""
    anchor = anchor or defaultAnchor()
    plan = Plan(anchor=anchor)
    _collisions(db, plan)
    if plan.bloqueado:
        return plan
    building = passwords is not None
    now = nowForDb()
    accounts = {account.key: account for account in ACCOUNTS}

    # Etapa 1 — usuarios; etapa 2 — credenciales.
    for account in ACCOUNTS:
        if _exists(db, User, account.id):
            plan.items.append(PlanItem("Usuario", account.key, "YA_EXISTE"))
            credential = db.get(LocalCredential, demoId("credencial", account.key))
            if regenerarContrasenas and credential is not None:
                plan.cuentasARegenerar.append(account.key)
                plan.items.append(PlanItem("Credencial", account.key, "REGENERAR_CONTRASENA"))
                if building:
                    credential.passwordHash = security.hashPassword(passwords[account.key])
                    credential.fechaUltimoCambioPassword = now
                    credential.fechaActualizacion = now
                    credential.intentosFallidosConsecutivos = 0
            else:
                plan.items.append(PlanItem("Credencial", account.key, "YA_EXISTE"))
            continue
        plan.cuentasACrear.append(account.key)
        plan.items.append(PlanItem("Usuario", account.key, "CREAR", account.rol))
        plan.items.append(PlanItem("Credencial", account.key, "CREAR"))
        if building:
            plan.etapas[0].append(User(
                idUsuario=account.id, nombre=account.nombre, apellido=account.apellido, correoElectronico=account.correo,
                usuario=USUARIOS_DEMO[account.key], tipoCuenta=account.tipoCuenta, estado=ESTADO_ACTIVO, fechaCreacion=now, fechaActualizacion=now,
                fechaEliminacion=None, fechaNacimiento=account.fechaNacimiento, sexo=account.sexo,
                notificarNuevoInicioSesion=False, fechaInicioGracia=None, fechaVencimientoGracia=None,
            ))
            plan.etapas[1].append(LocalCredential(
                idCredencialLocal=demoId("credencial", account.key), idUsuario=account.id,
                passwordHash=security.hashPassword(passwords[account.key]), requiereCambioPassword=False,
                intentosFallidosConsecutivos=0, fechaUltimoCambioPassword=now, fechaCreacion=now, fechaActualizacion=now,
            ))

    # Etapa 2 — grupo familiar y dispositivos.
    groupId = demoId("grupo", GROUP_KEY)
    if _exists(db, Group, groupId):
        plan.items.append(PlanItem("Grupo", GROUP_KEY, "YA_EXISTE"))
    else:
        plan.items.append(PlanItem("Grupo", GROUP_KEY, "CREAR", GROUP_NAME))
        if building:
            plan.etapas[1].append(Group(idGrupo=groupId, nombre=GROUP_NAME, descripcion=NOTA_GRUPO, estado="ACTIVO",
                                        fechaCreacion=HISTORY_START_DATETIME - timedelta(days=30), fechaActualizacion=now))
    for device in DEVICES:
        if _exists(db, Device, device.id):
            plan.items.append(PlanItem("Dispositivo", device.key, "YA_EXISTE"))
            continue
        plan.items.append(PlanItem("Dispositivo", device.key, "CREAR", device.codigo))
        if building:
            plan.etapas[1].append(Device(
                idDispositivo=device.id, codigoDispositivo=device.codigo, nombre=f"Dispositivo DEMO {device.key} (sintético)",
                modelo="GlucoLume DEMO", modeloSensor=SENSOR_DEMO, versionFirmware=VERSION_FIRMWARE_DEMO, estado="OPERATIVO",
                idInstitucionAsignada=None,
                idInstitucionUsuarioResponsable=None, fechaRegistro=HISTORY_START_DATETIME - timedelta(days=1),
            ))

    # Etapa 2 — cuenta individual ↔ dispositivo que usa en su historial (como la primera medición real: la cuenta queda vinculada a ese
    # dispositivo). Sin la tabla en la base instalada (GlucoLume_vinculo_cuenta_dispositivo.sql) se omite, como en la aplicación.
    _individualLinks(db, plan, building, accounts)

    # Etapa 3 — vínculos del grupo.
    memberships = [("grupo-admin", "PROPIETARIO", (False, False, False, False))]
    memberships += [(key, "MIEMBRO", flags) for key, flags, _ in GROUP_MEMBERS]
    for key, role, flags in memberships:
        linkId = demoId("vinculo-grupo", key)
        if _exists(db, GroupUser, linkId):
            plan.items.append(PlanItem("VinculoGrupo", key, "YA_EXISTE"))
            continue
        plan.items.append(PlanItem("VinculoGrupo", key, "CREAR", role))
        if building:
            perfil, ultima, historial, avisos = flags
            plan.etapas[2].append(GroupUser(
                idGrupoUsuario=linkId, idGrupo=groupId, idUsuario=accounts[key].id, rolGrupo=role, estadoRelacion="ACTIVO",
                nivelComparticion="NINGUNA", fechaInvitacion=HISTORY_START_DATETIME - timedelta(days=3),
                fechaIncorporacion=HISTORY_START_DATETIME - timedelta(days=2), visualiza=True, compartePerfil=perfil,
                comparteUltimaMedicion=ultima, comparteHistorial=historial, notificaMedicion=avisos,
            ))

    # Etapas 4 y 5 — perfiles de medición y mediciones.
    _profilesAndMeasurements(db, plan, building, now)
    return plan


def _individualLinks(db: Session, plan: Plan, building: bool, accounts) -> None:
    """Cada cuenta individual demo queda vinculada al dispositivo con el que midió, desde su primera medición (igual que en la aplicación)."""
    if not schemaCompat.hasTable(db, "VinculoCuentaDispositivo"):
        plan.advertencias.append("La base no tiene VinculoCuentaDispositivo: las cuentas demo individuales no quedan vinculadas a su "
                                 "dispositivo (aplicar antes GlucoLume_vinculo_cuenta_dispositivo.sql).")
        return
    for accountKey, specs in individualMeasurements():
        account = accounts[accountKey]
        linkId = demoId("vinculo-cuenta-dispositivo", accountKey)
        if _exists(db, AccountDeviceLink, linkId):
            plan.items.append(PlanItem("VinculoCuentaDispositivo", accountKey, "YA_EXISTE"))
            continue
        deviceKey = deviceKeyForIndividual(accountKey)
        plan.items.append(PlanItem("VinculoCuentaDispositivo", accountKey, "CREAR", deviceKey))
        if building:
            deviceId = next(device.id for device in DEVICES if device.key == deviceKey)
            first = min((spec.start(plan.anchor) for spec in specs), default=plan.anchor - timedelta(days=60))
            plan.etapas[2].append(AccountDeviceLink(idVinculo=linkId, idUsuario=account.id, idDispositivo=deviceId, fechaVinculo=first))


def _profilesAndMeasurements(db: Session, plan: Plan, building: bool, now: datetime) -> None:
    accounts = {account.key: account for account in ACCOUNTS}
    individuals = individualMeasurements()
    # Como la aplicación al iniciar una medición: la matriz global activa. Solo se referencia (las mediciones demo no reciben
    # estimación del servidor, así que la matriz solo clasifica la glucosa informada).
    globalMatrix = matrixService.resolveMatrix(db, None, plan.anchor.date())
    if globalMatrix is None:
        plan.advertencias.append("No hay una matriz global activa y vigente: la clasificación de glucosa de la demo mostrará SIN_MATRIZ.")
    existingMeasurements = _existingIds(db, Measurement.idMedicion, [spec.id for _, specs in individuals for spec in specs])

    for accountKey, specs in individuals:
        account = accounts[accountKey]
        profileId = demoId("perfil", accountKey)
        _profileItem(db, plan, building, accountKey, profileId, lambda pid, a=account, s=specs: MeasurementProfile(
            idPerfilMedicion=pid, tipoPerfil=PERFIL_CONSUMIDOR, idUsuario=a.id, nombre=a.nombre, apellido=a.apellido,
            fechaNacimiento=a.fechaNacimiento, sexoModelo=a.sexo, fechaCreacion=HISTORY_START_DATETIME,
            fechaUltimaMedicion=_lastCompletedEnd(s, plan.anchor)))
        _measurements(plan, building, specs, profileId, accountKey, account.fechaNacimiento, account.sexo,
                      existingMeasurements, deviceKeyForIndividual(accountKey),
                      globalMatrix.idMatriz if globalMatrix else None)


def _profileItem(db: Session, plan: Plan, building: bool, key: str, profileId: uuid.UUID, factory) -> bool:
    """Devuelve True si el perfil se crea en esta ejecución."""
    if _exists(db, MeasurementProfile, profileId):
        plan.items.append(PlanItem("PerfilMedicion", key, "YA_EXISTE"))
        return False
    plan.items.append(PlanItem("PerfilMedicion", key, "CREAR"))
    if building:
        plan.etapas[3].append(factory(profileId))
    return True


def _lastCompletedEnd(specs, anchor: datetime) -> datetime | None:
    """Como en la aplicación: la última medición completada fija fechaUltimaMedicion del perfil."""
    completed = [spec.start(anchor) for spec in specs if spec.estado == ESTADO_COMPLETADA]
    return max(completed) + timedelta(minutes=2) if completed else None


def _measurements(plan: Plan, building: bool, specs, profileId, key, birth, sex, existing, deviceKey: str,
                  matrixId: uuid.UUID | None) -> None:
    pending = [spec for spec in specs if spec.id not in existing]
    plan.items.append(PlanItem("Medicion", key, "CREAR" if pending else "YA_EXISTE", f"{len(pending)} de {len(specs)}"))
    if building:
        for spec in pending:
            plan.etapas[4].append(_measurementRecord(spec, profileId, birth, sex, plan.anchor, deviceKey, matrixId))


def _measurementRecord(spec: MeasurementSpec, profileId, birth: date | None, sex: str | None, anchor: datetime,
                       deviceKey: str, matrixId: uuid.UUID | None) -> Measurement:
    start = spec.start(anchor)
    completed = spec.estado == ESTADO_COMPLETADA
    glucose = spec.glucosa  # solo en mediciones de glucosa completadas (DEMO); la oximetría no informa glucosa
    lastMeal = start - timedelta(minutes=spec.minutosDesdeComida) if spec.minutosDesdeComida is not None else None
    deviceId = next(device.id for device in DEVICES if device.key == deviceKey)
    return Measurement(
        idMedicion=spec.id, idPerfilMedicion=profileId, idDispositivo=deviceId,
        idMatriz=matrixId if glucose is not None else None,
        modoMedicion=spec.modo, estadoMedicion=spec.estado, fechaHoraInicio=start, fechaHoraFin=start + timedelta(minutes=2),
        fechaHoraUltimaComida=lastMeal, condicionComida=spec.condicion,
        edadAlMomento=calculateAge(birth, start.date()) if birth else None, sexoModelo=sex,
        versionFirmwareAlMomento=VERSION_FIRMWARE_DEMO if completed else None, modeloSensorAlMomento=SENSOR_DEMO,
        versionAlgoritmo=ALGORITMO_DEMO if completed else None, calidadSenal=spec.calidadSenal, spo2=spec.spo2,
        frecuenciaCardiaca=spec.frecuenciaCardiaca, glucosaEstimada=None, observacion=NOTA_MEDICION,
        origenGlucosa=ORIGEN_DEMO if glucose is not None else None, glucosaDispositivo=glucose,
        unidadGlucosa="mg/dL" if glucose is not None else None, indiceOptico=spec.indiceOptico,
        lecturasEstabilizadas=spec.lecturas,
    )


# --- Aplicación ------------------------------------------------------------------------------------------------------


def apply(db: Session, plan: Plan) -> dict[str, int]:
    """Escribe el plan en una sola transacción por etapas. Devuelve lo creado por entidad. Ante cualquier error, deshace todo."""
    if plan.bloqueado:
        raise SeedError("La carga está bloqueada por colisiones con datos que no son demo:\n- " + "\n- ".join(plan.bloqueos))
    try:
        for index, records in enumerate(plan.etapas):
            if index == 1:
                _consents(db, plan)  # usuarios ya insertados: consentimientos del servicio real
            if records:
                db.add_all(records)
                db.flush()
        _writeAudits(db, plan)
        db.flush()
        db.commit()
    except Exception:
        db.rollback()
        raise
    created: dict[str, int] = {}
    for item in plan.items:
        if item.accion == "CREAR":
            created[item.entidad] = created.get(item.entidad, 0) + 1
    return created


def _writeAudits(db: Session, plan: Plan) -> None:
    """Escribe las auditorías con el servicio real. La fecha del evento es la del hecho (carga histórica), no la de la carga."""
    for entry in plan.auditorias:
        registerEvent(
            db, "CRUD", entry.accion, True, entry.actor, entry.tabla, entry.idRegistro,
            datosPrevios=entry.datosPrevios, datosNuevos=entry.datosNuevos,
            tablaRelacionada=entry.tablaRelacionada, idRelacionado=entry.idRelacionado,
        )
        # registerEvent deja la fila pendiente en la sesión (sin consultas posteriores): ahí se fija la fecha del evento.
        for row in db.new:
            if isinstance(row, Audit) and row.idRegistro == entry.idRegistro and row.accion == entry.accion and row.fechaHora is None:
                row.fechaHora = entry.fecha


def _consents(db: Session, plan: Plan) -> None:
    for key in plan.cuentasACrear:
        account = ACCOUNTS_BY_KEY[key]
        if account.individual:
            user = db.get(User, account.id)
            consentService.record(db, user, TipoConsentimiento.POLITICA_PRIVACIDAD, True)
            consentService.record(db, user, TipoConsentimiento.DATOS_EXPERIMENTALES, True)


# --- Verificación sin sesión -----------------------------------------------------------------------------------------


def verifyAccounts(db: Session, passwords: dict[str, str]) -> list[CheckResult]:
    """Por cuenta: existe, estado ACTIVO, tipo correcto, credencial que verifica con la contraseña del archivo privado, sin MFA
    habilitado y con su perfil o vínculo. No abre sesión ni escribe auditoría."""
    results: list[CheckResult] = []
    for account in ACCOUNTS:
        user = db.get(User, account.id)
        if user is None:
            results.append(CheckResult(account.key, account.correo, False, "la cuenta no existe"))
            continue
        problems: list[str] = []
        if user.estado != ESTADO_ACTIVO:
            problems.append(f"estado {user.estado}")
        if user.tipoCuenta != account.tipoCuenta:
            problems.append(f"tipoCuenta {user.tipoCuenta}")
        credential = db.get(LocalCredential, demoId("credencial", account.key))
        if credential is None:
            problems.append("sin credencial local")
        elif account.key not in passwords:
            problems.append("contraseña no disponible en el archivo privado (usar --regenerar-contrasenas)")
        elif not security.verifyPassword(passwords[account.key], credential.passwordHash)[0]:
            problems.append("la contraseña del archivo privado no coincide con la base")
        factor = db.scalar(select(MfaFactor).where(MfaFactor.idUsuario == user.idUsuario, MfaFactor.habilitado == True))
        if factor is not None:
            problems.append("MFA habilitado (la demo no lo configura)")
        if db.get(MeasurementProfile, demoId("perfil", account.key)) is None:
            problems.append("sin perfil de medición")
        results.append(CheckResult(account.key, account.correo, not problems, "OK" if not problems else "; ".join(problems)))
    return results


def countDemoRows(db: Session) -> dict[str, int]:
    """Cuántos registros demo hay (solo lectura), por entidad: la fuente de la verificación posterior a la carga."""
    ids = {
        "Usuario": (User.idUsuario, [a.id for a in ACCOUNTS]),
        "Grupo": (Group.idGrupo, [demoId("grupo", GROUP_KEY)]),
        "Dispositivo": (Device.idDispositivo, [d.id for d in DEVICES]),
        "PerfilMedicion": (MeasurementProfile.idPerfilMedicion, [demoId("perfil", a.key) for a in ACCOUNTS if a.individual]),
        "Medicion": (Measurement.idMedicion, [s.id for _, specs in individualMeasurements() for s in specs]),
    }
    if schemaCompat.hasTable(db, "VinculoCuentaDispositivo"):
        ids["VinculoCuentaDispositivo"] = (AccountDeviceLink.idVinculo,
                                           [demoId("vinculo-cuenta-dispositivo", a.key) for a in ACCOUNTS if a.individual])
    return {entidad: len(_existingIds(db, column, values)) for entidad, (column, values) in ids.items()}


__all__ = ["Plan", "PlanItem", "SeedError", "CheckResult", "assertAllowed", "defaultAnchor", "defaultCredentialsPath",
           "assertOutsideRepo", "generatePassword", "buildPlan", "apply", "verifyAccounts", "countDemoRows"]
