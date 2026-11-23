# Demo - Catálogo determinista de los datos de demostración
#
# Solo describe QUÉ se carga: 9 cuentas individuales (sin instituciones ni personal institucional), un grupo familiar con sus
# permisos, 9 dispositivos propios (uno por cuenta) y el historial de mediciones sintéticas desde HISTORY_START hasta DATA_END_DATE.
# No toca la base: app/demo/seeder.py lo convierte en registros mediante los modelos y servicios existentes.
#
# Reglas del catálogo:
#   - Ningún dato corresponde a personas ni dispositivos reales. Correos en example.com (dominio reservado) y dispositivos DEMO-DISP-*.
#   - Todo identificador sale de una clave fija (uuid5). Ejecutar la carga dos veces produce los mismos IDs (idempotencia) y la
#     limpieza encuentra exactamente lo que creó la carga, sin tocar nada más.
#   - Los datos de glucosa son DEMO (valor sintético, excluido de indicadores clínicos por la propia aplicación). Cada medición
#     lleva además una observación que la identifica como sintética.
#   - Las mediciones se generan con un generador pseudoaleatorio sembrado con la clave de cada perfil: la misma fecha de ancla
#     produce siempre los mismos valores.

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal

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
