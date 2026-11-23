# Demo - Catálogo determinista de los datos de demostración académica
#
# Solo describe QUÉ se carga (cuentas, instituciones, grupo, dispositivos, pacientes y mediciones sintéticas). No toca la base:
# app/demo/seeder.py lo convierte en registros mediante los modelos y servicios existentes.
#
# Reglas del catálogo:
#   - Ningún dato corresponde a personas, instituciones ni dispositivos reales. Correos en example.com (dominio reservado),
#     documentos con el prefijo DEMO (normalizados A-Z0-9 como exige la base), dispositivos DEMO-DISP-*.
#   - Todo identificador sale de una clave fija (uuid5). Ejecutar la carga dos veces produce los mismos IDs (idempotencia) y la
#     limpieza encuentra exactamente lo que creó la carga, sin tocar nada más.
#   - Los datos de glucosa son DEMO (valor sintético del firmware, excluido de indicadores clínicos por la propia aplicación).
#     Cada medición lleva además una observación que la identifica como sintética.
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
NOTA_INSTITUCION = "Institución sintética de demostración académica. No corresponde a una institución real."
NOTA_GRUPO = "Grupo familiar sintético de demostración académica."
HISTORY_START = date(2022, 1, 1)  # primera medición del historial demo de las cuentas individuales
DATA_END_DATE = date(2026, 11, 23)  # último día del historial: la última medición de cada cuenta individual es ese día a las 17:00
DATA_END_HOUR = 17
HISTORY_DAYS = (DATA_END_DATE - HISTORY_START).days
HISTORY_START_DATETIME = datetime.combine(HISTORY_START, time(0, 0))  # ventana de mediciones individuales hacia atrás desde la fecha de ancla
PATIENT_HISTORY_DAYS = 60  # ventana de mediciones de los pacientes institucionales (altas y transferencias son recientes)

# Tipos de cuenta, estados y valores permitidos (los mismos literales que usan los modelos).
CONSUMIDOR_FINAL = "CONSUMIDOR_FINAL"
USUARIO_INSTITUCIONAL = "USUARIO_INSTITUCIONAL"
PERFIL_INSTITUCIONAL = "INSTITUCIONAL"
PERFIL_CONSUMIDOR = "CONSUMIDOR_FINAL"
ROL_PROPIETARIO, ROL_MODERADOR, ROL_OPERADOR = "PROPIETARIO", "MODERADOR", "OPERADOR"
MODO_GLUCOSA, MODO_OXIMETRIA = "GLUCOSA_EXPERIMENTAL", "OXIMETRIA"
ESTADO_COMPLETADA, ESTADO_CANCELADA, ESTADO_INVALIDA = "COMPLETADA", "CANCELADA", "INVALIDA"
ORIGEN_DEMO = "DEMO"
SENSOR_DEMO = "MAX30100"
VERSION_FIRMWARE_DEMO = "demo-1.0"
ALGORITMO_DEMO = "firmware-glucolume-max30100-v1"


def demoId(kind: str, key: str) -> uuid.UUID:
    """Identificador determinista de un registro demo (misma clave, mismo ID en cada ejecución)."""
    return uuid.uuid5(DEMO_NAMESPACE, f"{kind}:{key}")


# --- Cuentas ---------------------------------------------------------------------------------------------------------


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
    # Escenario A — individual sin grupo.
    Account("individual-a", "Valeria", "Soto", CONSUMIDOR_FINAL, "FEMENINO", "Individual sin grupo",
            "A: perfil propio con mediciones en distintos días, estadísticas, historial y última medición. Sin vínculos institucionales.",
            date(1990, 3, 14)),
    # Escenario B — administrador de grupo familiar y cinco integrantes con permisos distintos.
    Account("grupo-admin", "Tomás", "Herrera", CONSUMIDOR_FINAL, "MASCULINO", "Individual - administrador de grupo familiar",
            "B: administra el grupo. Sus propios datos no están compartidos: el grupo no los ve.", date(1982, 7, 2)),
    Account("grupo-integrante-1", "Sofía", "Castro", CONSUMIDOR_FINAL, "FEMENINO", "Integrante del grupo familiar 1",
            "B - Integrante 1: solo datos básicos (edad y sexo). No comparte última medición, historial ni avisos.", date(2001, 11, 20)),
    Account("grupo-integrante-2", "Nicolás", "Vega", CONSUMIDOR_FINAL, "MASCULINO", "Integrante del grupo familiar 2",
            "B - Integrante 2: solo la última medición. No comparte datos básicos ni historial.", date(1975, 1, 9)),
    Account("grupo-integrante-3", "Julieta", "Pardo", CONSUMIDOR_FINAL, "FEMENINO", "Integrante del grupo familiar 3",
            "B - Integrante 3: solo el historial (incluye gráficos y estadísticas). No comparte última medición ni avisos.",
            date(1968, 5, 30)),
    Account("grupo-integrante-4", "Mateo", "Ríos", CONSUMIDOR_FINAL, "MASCULINO", "Integrante del grupo familiar 4",
            "B - Integrante 4: solo avisos (fecha y hora de cada medición, nunca valores).", date(1996, 2, 25)),
    Account("grupo-integrante-5", "Carla", "Núñez", CONSUMIDOR_FINAL, "FEMENINO", "Integrante del grupo familiar 5",
            "B - Integrante 5: comparte datos básicos, última medición, historial y avisos.", date(1959, 12, 4)),
    Account("grupo-integrante-6", "Lucas", "Ferrari", CONSUMIDOR_FINAL, "MASCULINO", "Integrante del grupo familiar 6",
            "B - Integrante 6: comparte datos básicos, última medición, historial y avisos.", date(1989, 8, 17)),
    Account("grupo-integrante-7", "Julia", "Bravo", CONSUMIDOR_FINAL, "FEMENINO", "Integrante del grupo familiar 7",
            "B - Integrante 7: comparte datos básicos, última medición, historial y avisos.", date(1973, 4, 22)),
    # Personal institucional (14 cuentas: 2 propietarios, 4 moderadores, 8 operadores).
    Account("propietario-a", "Gabriel", "Montes", USUARIO_INSTITUCIONAL, "MASCULINO", "Propietario",
            "C: propietario de la Institución Demo A y de la Institución Demo C (administra más de una institución)."),
    Account("propietario-b", "Patricia", "Lencina", USUARIO_INSTITUCIONAL, "FEMENINO", "Propietario",
            "C: propietaria de la Institución Demo B. No ve datos de la Institución Demo A."),
    Account("moderador-a-1", "Lorena", "Acosta", USUARIO_INSTITUCIONAL, "FEMENINO", "Moderador",
            "C: gestiona operadores y ve el panel institucional de la Institución Demo A; no administra moderadores."),
    Account("moderador-a-2", "Diego", "Salinas", USUARIO_INSTITUCIONAL, "MASCULINO", "Moderador",
            "C: segundo moderador de la Institución Demo A."),
    Account("moderador-b-1", "Ezequiel", "Funes", USUARIO_INSTITUCIONAL, "MASCULINO", "Moderador",
            "C: gestiona operadores de la Institución Demo B."),
    Account("moderador-b-2", "Romina", "Ledesma", USUARIO_INSTITUCIONAL, "FEMENINO", "Moderador",
            "C: segundo moderador de la Institución Demo B."),
    Account("operador-a-1", "Camila", "Ortiz", USUARIO_INSTITUCIONAL, "FEMENINO", "Operador",
            "D: opera solo sus pacientes asignados en la Institución Demo A."),
    Account("operador-a-2", "Federico", "Luna", USUARIO_INSTITUCIONAL, "MASCULINO", "Operador",
            "D: opera solo sus pacientes asignados en la Institución Demo A."),
    Account("operador-a-3", "Irene", "Paz", USUARIO_INSTITUCIONAL, "FEMENINO", "Operador",
            "D: opera solo sus pacientes asignados en la Institución Demo A."),
    Account("operador-a-4", "Hernán", "Quiroga", USUARIO_INSTITUCIONAL, "MASCULINO", "Operador",
            "D: opera solo sus pacientes asignados en la Institución Demo A."),
    Account("operador-b-1", "Sabrina", "Dávila", USUARIO_INSTITUCIONAL, "FEMENINO", "Operador",
            "D: opera solo sus pacientes asignados en la Institución Demo B."),
    Account("operador-b-2", "Matías", "Benítez", USUARIO_INSTITUCIONAL, "MASCULINO", "Operador",
            "D: opera solo sus pacientes asignados en la Institución Demo B."),
    Account("operador-b-3", "Noelia", "Sosa", USUARIO_INSTITUCIONAL, "FEMENINO", "Operador",
            "D: opera solo sus pacientes asignados en la Institución Demo B."),
    Account("operador-b-4", "Ignacio", "Correa", USUARIO_INSTITUCIONAL, "MASCULINO", "Operador",
            "D: opera solo sus pacientes asignados en la Institución Demo B."),
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


# --- Instituciones ---------------------------------------------------------------------------------------------------


def cuitDigits(seq: int) -> str:
    """CUIT sintético con dígito verificador válido (módulo 11). Base 3099999XXX: no pertenece a una persona física."""
    base = f"3099999{seq:03d}"
    weights = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
    remainder = 11 - sum(int(d) * w for d, w in zip(base, weights)) % 11
    if remainder == 10:
        raise ValueError(f"Base de CUIT sin dígito verificador válido: {base}")
    check = 0 if remainder == 11 else remainder
    return f"{base}{check}"


@dataclass(frozen=True)
class Institution:
    key: str
    nombre: str
    tipoInstitucion: str
    seq: int
    propietario: str  # clave de la cuenta propietaria

    @property
    def id(self) -> uuid.UUID:
        return demoId("institucion", self.key)

    @property
    def cuit(self) -> str:
        return cuitDigits(self.seq)


INSTITUTIONS: tuple[Institution, ...] = (
    Institution("a", "Institución Demo A", "CONSULTORIO", 1, "propietario-a"),
    Institution("b", "Institución Demo B", "CLINICA", 2, "propietario-b"),
    Institution("c", "Institución Demo C", "CONSULTORIO", 3, "propietario-a"),
)
INSTITUTIONS_BY_KEY = {institution.key: institution for institution in INSTITUTIONS}
MAIN_INSTITUTIONS = ("a", "b")  # las dos con personal, pacientes y mediciones; C solo demuestra un propietario con dos instituciones


@dataclass(frozen=True)
class StaffLink:
    """Vínculo de una cuenta institucional con una institución."""
    institution: str
    account: str
    rol: str
    invitadoPor: str | None  # clave de la cuenta que la incorporó (None para el propietario que la creó)
    funcionProfesional: str | None = None
    matricula: str | None = None
    legajo: str | None = None

    @property
    def id(self) -> uuid.UUID:
        return demoId("vinculo-institucional", f"{self.institution}:{self.account}")


def _staff() -> tuple[StaffLink, ...]:
    links: list[StaffLink] = [
        StaffLink("a", "propietario-a", ROL_PROPIETARIO, None),
        StaffLink("b", "propietario-b", ROL_PROPIETARIO, None),
        StaffLink("c", "propietario-a", ROL_PROPIETARIO, None),
    ]
    for inst, owner in (("a", "propietario-a"), ("b", "propietario-b")):
        for n in (1, 2):
            links.append(StaffLink(inst, f"moderador-{inst}-{n}", ROL_MODERADOR, owner))
        functions = ("OPERADOR", "ENFERMERO", "MEDICO", "OPERADOR")
        for n in (1, 2, 3, 4):
            # Cada moderador incorpora a dos operadores: el 1 a los operadores 1 y 2, el 2 a los operadores 3 y 4.
            invitedBy = f"moderador-{inst}-{1 if n <= 2 else 2}"
            links.append(StaffLink(inst, f"operador-{inst}-{n}", ROL_OPERADOR, invitedBy,
                                   funcionProfesional=functions[n - 1], legajo=f"DEMO-LEG-{inst.upper()}{n}",
                                   matricula=f"DEMO-MAT-{inst.upper()}{n}" if functions[n - 1] != "OPERADOR" else None))
    return tuple(links)


STAFF: tuple[StaffLink, ...] = _staff()


# --- Dispositivos ----------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class DemoDevice:
    key: str
    codigo: str
    institution: str | None  # None: sin institución (uso individual)

    @property
    def id(self) -> uuid.UUID:
        return demoId("dispositivo", self.key)


DEVICES: tuple[DemoDevice, ...] = (
    # Un dispositivo propio por cada cuenta individual (ind-01 … ind-09): nadie comparte dispositivo.
    DemoDevice("ind-01", "DEMO-DISP-IND-01", None),
    DemoDevice("ind-02", "DEMO-DISP-IND-02", None),
    DemoDevice("ind-03", "DEMO-DISP-IND-03", None),
    DemoDevice("ind-04", "DEMO-DISP-IND-04", None),
    DemoDevice("ind-05", "DEMO-DISP-IND-05", None),
    DemoDevice("ind-06", "DEMO-DISP-IND-06", None),
    DemoDevice("ind-07", "DEMO-DISP-IND-07", None),
    DemoDevice("ind-08", "DEMO-DISP-IND-08", None),
    DemoDevice("ind-09", "DEMO-DISP-IND-09", None),
    DemoDevice("a-01", "DEMO-DISP-A-01", "a"),
    DemoDevice("a-02", "DEMO-DISP-A-02", "a"),
    DemoDevice("b-01", "DEMO-DISP-B-01", "b"),
    DemoDevice("b-02", "DEMO-DISP-B-02", "b"),
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


# --- Pacientes institucionales ---------------------------------------------------------------------------------------

# Pacientes por operador (en el orden operador-x-1 … operador-x-4): entre 3 y 5 por operador, 32 en total.
PATIENTS_PER_OPERATOR = {"a": (3, 5, 4, 4), "b": (4, 3, 5, 4)}
# Cantidad de mediciones por paciente (ciclo): entre 1 y 4, como en el seguimiento real de un paciente asignado.
PATIENT_MEASUREMENT_CYCLE = (1, 2, 3, 4, 2, 1, 4, 3)
# Cómo llegó cada paciente a su operador actual (ciclo por número de paciente dentro de la institución). Cada caso deja el rastro que
# deja la aplicación: el alta del operador, el alta de un moderador con asignación, o una transferencia entre operadores aceptada.
ALTA_OPERADOR = "ALTA_OPERADOR"
ALTA_MODERADOR = "ALTA_MODERADOR"
TRANSFERENCIA = "TRANSFERENCIA"
ALTA_CYCLE = (ALTA_OPERADOR, ALTA_MODERADOR, TRANSFERENCIA)
# Hace cuántos días se aceptó la transferencia. Las mediciones anteriores a esa fecha son del operador de origen (historial).
CAMBIO_DIAS = 25
FIRST_NAMES = ("Lucía", "Mateo", "Valentina", "Joaquín", "Renata", "Benjamín", "Agustina", "Santiago", "Victoria", "Lautaro",
               "Florencia", "Facundo", "Milagros", "Tobías", "Pilar", "Bruno", "Abril", "Thiago", "Catalina", "Ignacio")
LAST_NAMES = ("Quiroga", "Ferreyra", "Molina", "Aguirre", "Palacios", "Gómez", "Barrios", "Cabrera", "Figueroa", "Ibarra",
              "Medina", "Rojas", "Sandoval", "Trejo", "Villalba", "Zárate", "Ojeda", "Peralta", "Robledo", "Vázquez")


@dataclass(frozen=True)
class Patient:
    institution: str
    operator: str  # clave de la cuenta operadora responsable (asignación única: el modelo admite un responsable por paciente)
    seq: int  # número dentro de la institución
    nombre: str
    apellido: str
    dni: str | None
    fechaNacimiento: date | None
    sexoModelo: str | None
    mediciones: int
    alta: str  # ALTA_OPERADOR | ALTA_MODERADOR | TRANSFERENCIA
    registrante: str  # clave de la cuenta que dio de alta al paciente (operador o moderador de la institución)
    origen: str | None  # solo en TRANSFERENCIA: operador que lo tuvo antes (y que lo solicitó transferir)

    @property
    def key(self) -> str:
        return f"paciente-{self.institution}-{self.seq:02d}"

    @property
    def id(self) -> uuid.UUID:
        """ID del PerfilMedicion del paciente (mismo criterio que los perfiles individuales: demoId('perfil', clave))."""
        return demoId("perfil", self.key)

    @property
    def pseudonimo(self) -> str:
        return f"DEMO-PAC-{self.institution.upper()}-{self.seq:03d}"

    @property
    def relationKey(self) -> str:
        return f"{self.institution}:{self.operator}"


def _patients() -> tuple[Patient, ...]:
    out: list[Patient] = []
    for inst in MAIN_INSTITUTIONS:
        seq = 0
        for position, count in enumerate(PATIENTS_PER_OPERATOR[inst], start=1):
            for _ in range(count):
                seq += 1
                operator = f"operador-{inst}-{position}"
                alta = ALTA_CYCLE[(seq - 1) % len(ALTA_CYCLE)]
                if alta == ALTA_OPERADOR:
                    registrante, origen = operator, None
                elif alta == ALTA_MODERADOR:
                    registrante, origen = f"moderador-{inst}-{1 if position <= 2 else 2}", None
                else:  # lo dio de alta el operador anterior (el siguiente en la institución) y luego se transfirió
                    registrante = origen = f"operador-{inst}-{position % 4 + 1}"
                out.append(Patient(
                    institution=inst,
                    operator=operator,
                    seq=seq,
                    alta=alta,
                    registrante=registrante,
                    origen=origen,
                    nombre=FIRST_NAMES[(seq * 5) % len(FIRST_NAMES)],
                    apellido=LAST_NAMES[(seq * 3 + (1 if inst == "b" else 0)) % len(LAST_NAMES)],
                    # Documento sintético: prefijo DEMO, solo A-Z0-9 (CK_PerfilMedicion_dniNormalizado). Sin documento en algunos.
                    dni=None if seq % 9 == 8 else f"DEMO{inst.upper()}{seq:03d}",
                    fechaNacimiento=None if seq % 5 == 4 else date(1945 + (seq * 7) % 60, (seq % 12) + 1, (seq % 27) + 1),
                    sexoModelo=None if seq % 6 == 5 else ("FEMENINO" if seq % 2 else "MASCULINO"),
                    mediciones=PATIENT_MEASUREMENT_CYCLE[(seq - 1) % len(PATIENT_MEASUREMENT_CYCLE)],
                ))
    return tuple(out)


PATIENTS: tuple[Patient, ...] = _patients()


def patientDeviceKey(patient: Patient) -> str:
    position = int(patient.operator.rsplit("-", 1)[1])
    return f"{patient.institution}-{'01' if position <= 2 else '02'}"


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
        profileKey=profileKey,
        index=index,
        dayOffset=dayOffset,
        hour=hour,
        minute=minute,
        modo=modo,
        estado=estado,
        condicion=condicion,
        minutosDesdeComida=minutosComida,
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
    `activity` (%), y ese día 1, 2 o 3 mediciones en horas distintas. El último día (DATA_END_DATE) termina con una medición a las 17:00."""
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


def patientMeasurements() -> tuple[tuple[Patient, tuple[MeasurementSpec, ...]], ...]:
    """Mediciones de los pacientes: cantidad fija por paciente, repartidas en PATIENT_HISTORY_DAYS."""
    out = []
    for patient in PATIENTS:
        rng = random.Random(f"demo-mediciones:{patient.key}")
        count = patient.mediciones
        uniqueDays = sorted(rng.sample(range(1, PATIENT_HISTORY_DAYS + 1), k=max(1, min(PATIENT_HISTORY_DAYS, round(count * 0.75)))))
        specs = []
        for index in range(count):
            hour, minute = rng.randint(7, 22), rng.randint(0, 59)
            specs.append(_spec(patient.key, index, uniqueDays[index % len(uniqueDays)], hour, minute, _estado(rng), rng,
                               70 + (patient.seq * 2) % 12))
        out.append((patient, tuple(specs)))
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
    patients = patientMeasurements()
    return {
        "usuarios": len(ACCOUNTS),
        "usuarios_individuales": sum(1 for account in ACCOUNTS if account.individual),
        "usuarios_institucionales": sum(1 for account in ACCOUNTS if not account.individual),
        "credenciales": len(ACCOUNTS),
        "consentimientos": 2 * sum(1 for account in ACCOUNTS if account.individual),
        "instituciones": len(INSTITUTIONS),
        "vinculos_institucionales": len(STAFF),
        "propietarios": 2,
        "moderadores": 4,
        "operadores": 8,
        "pacientes_asignados": len(PATIENTS),
        "grupos": 1,
        "vinculos_grupo": 1 + len(GROUP_MEMBERS),
        "dispositivos": len(DEVICES),
        "perfiles_individuales": sum(1 for account in ACCOUNTS if account.individual),
        "mediciones_individuales": sum(len(items) for _, items in individuals),
        "mediciones_pacientes": sum(len(items) for _, items in patients),
    }
