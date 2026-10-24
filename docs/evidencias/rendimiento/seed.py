"""Datos SINTÉTICOS para medir rendimiento en la base descartable GlucoLume_perf (nunca en «GlucoLume»).

Corre dentro de la imagen del backend, con el código de app/ y las mismas reglas de negocio (servicios, no SQL a mano):
  - 1 cuenta individual (CONSUMIDOR_FINAL) con --propias mediciones completadas repartidas en un año (ocho de ellas con muestras del sensor);
  - 1 institución con propietaria, moderador y 2 operadores, --pacientes pacientes y --por-paciente mediciones cada uno;
  - 1 dispositivo operativo compartido.
Todas las contraseñas son la misma, sintética y pública (SEED_PASSWORD). Imprime un JSON con las cuentas y los identificadores.

    docker compose -f compose.yaml -f docs/evidencias/rendimiento/compose.rendimiento.yaml --profile db --profile perf run --rm --no-deps \
        -v ./docs/evidencias/rendimiento:/perf:ro backend-perf python /perf/seed.py --pacientes 600 --por-paciente 12 --propias 1500
"""

import argparse
import json
import os
import random
import sys
import uuid
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # ppg.py
sys.path.insert(0, os.getcwd())  # app/ (WORKDIR de la imagen)

assert os.environ.get("DB_NAME") == "GlucoLume_perf", "Este script solo corre contra la base descartable GlucoLume_perf."

from app.core import security  # noqa: E402
from app.db.session import getSessionFactory  # noqa: E402
from app.integrations.email import sender  # noqa: E402
from app.models.consent import TipoConsentimiento  # noqa: E402
from app.models.device import Device  # noqa: E402
from app.models.institutionUser import InstitutionUser  # noqa: E402
from app.models.localCredential import LocalCredential  # noqa: E402
from app.models.measurement import Measurement  # noqa: E402
from app.models.measurementProfile import MeasurementProfile  # noqa: E402
from app.models.user import User  # noqa: E402
from app.schemas.institution import InstitutionCreateRequest  # noqa: E402
from app.schemas.measurement import MeasurementFinish, MeasurementStart, SamplesRequest  # noqa: E402
from app.schemas.measurementProfile import PatientCreateRequest  # noqa: E402
from app.services import consent as consentService  # noqa: E402
from app.services import institution as institutions  # noqa: E402
from app.services import institutionPatients as patients  # noqa: E402
from app.services import measurement as measurementService  # noqa: E402
from app.utils.timeZone import nowForDb  # noqa: E402
from sqlalchemy import select  # noqa: E402

SEED_PASSWORD = "Glucolume#Perf2026"  # nosec B105 - contraseña sintética de la base descartable
NAMES = ["Ana", "Luis", "Marta", "Pedro", "Lucía", "Jorge", "Sofía", "Diego", "Carla", "Mateo", "Julia", "Bruno", "Paula", "Hugo", "Irene"]
SURNAMES = ["García", "Rodríguez", "López", "Martínez", "Pérez", "Gómez", "Díaz", "Fernández", "Ruiz", "Sosa", "Romero", "Torres", "Álvarez"]


def noMail(*args, **kwargs):  # el correo no forma parte de lo que se mide
    return None


sender.sendHtmlEmail = noMail


def makeUser(db, tipo, email, usuario, nombre, apellido):
    user = User(idUsuario=uuid.uuid4(), nombre=nombre, apellido=apellido, correoElectronico=email, usuario=usuario, tipoCuenta=tipo,
                estado="ACTIVO", fechaNacimiento=date(1985, 3, 9), sexo="FEMENINO")
    db.add(user)
    db.flush()
    db.add(LocalCredential(idUsuario=user.idUsuario, passwordHash=security.hashPassword(SEED_PASSWORD)))
    consentService.record(db, user, TipoConsentimiento.POLITICA_PRIVACIDAD, True)
    consentService.record(db, user, TipoConsentimiento.DATOS_EXPERIMENTALES, True)
    db.commit()
    return user


def bulkMeasurements(db, profileId, deviceId, count, rng, age, sex, years=1.0):
    """Mediciones COMPLETADAS ya procesadas (resultados fijos, sin muestras): lo que hay en una base con meses de uso."""
    now = nowForDb()
    batch = []
    for _ in range(count):
        start = now - timedelta(minutes=rng.randint(10, int(years * 365 * 24 * 60)))
        experimental = rng.random() < 0.35
        batch.append(Measurement(
            idMedicion=uuid.uuid4(), idPerfilMedicion=profileId, idDispositivo=deviceId, modoMedicion="OXIMETRIA", estadoMedicion="COMPLETADA",
            fechaHoraInicio=start, fechaHoraFin=start + timedelta(seconds=40), condicionComida="NO_INFORMADA", edadAlMomento=age,
            sexoModelo=sex, versionFirmwareAlMomento="1.2.0", modeloSensorAlMomento="MAX30102", versionAlgoritmo="oximetria-1",
            calidadSenal=round(rng.uniform(0.6, 0.99), 3), spo2=round(rng.uniform(93, 100), 2), frecuenciaCardiaca=rng.randint(55, 110),
            **({"origenGlucosa": "EXPERIMENTAL", "glucosaDispositivo": round(rng.uniform(75, 190), 2), "unidadGlucosa": "mg/dL"} if experimental else {}),
        ))
        if len(batch) == 1000:
            db.add_all(batch)
            db.commit()
            batch = []
    if batch:
        db.add_all(batch)
        db.commit()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pacientes", type=int, default=600)
    parser.add_argument("--por-paciente", type=int, default=12)
    parser.add_argument("--propias", type=int, default=1500)
    args = parser.parse_args()
    rng = random.Random(20261023)
    db = getSessionFactory()()

    device = Device(idDispositivo=uuid.uuid4(), codigoDispositivo="PERF-DEV-001", nombre="Oxímetro de prueba", modelo="HC-06",
                    modeloSensor="MAX30102", versionFirmware="1.2.0", estado="OPERATIVO")
    db.add(device)
    db.commit()

    consumer = makeUser(db, "CONSUMIDOR_FINAL", "perf.consumidor@example.com", "perfconsumidor", "Carolina", "Prueba")
    profile = measurementService.getOwnProfile(db, consumer)
    bulkMeasurements(db, profile.idPerfilMedicion, device.idDispositivo, args.propias, rng, 40, "FEMENINO")

    owner = makeUser(db, "USUARIO_INSTITUCIONAL", "perf.duenia@example.com", "perfduenia", "Dora", "Dueña")
    moderator = makeUser(db, "USUARIO_INSTITUCIONAL", "perf.moderador@example.com", "perfmoderador", "Mario", "Moderador")
    operators = [makeUser(db, "USUARIO_INSTITUCIONAL", f"perf.operador{i}@example.com", f"perfoperador{i}", f"Oscar{i}", "Operador") for i in (1, 2)]
    institution = institutions.createInstitution(db, owner, InstitutionCreateRequest(
        nombre="Clínica de Rendimiento", tipoInstitucion="CLINICA", identificadorLegal="30-71234567-1"))
    invitation = institutions.invite(db, owner, institution.idInstitucion, "MODERADOR", moderator.correoElectronico)
    institutions.respondInvitation(db, moderator, invitation.idInstitucionUsuario, accept=True)
    for operator in operators:
        invitation = institutions.invite(db, moderator, institution.idInstitucion, "OPERADOR", operator.correoElectronico,
                                         datos={"matriculaProfesional": "MP-123"})
        institutions.respondInvitation(db, operator, invitation.idInstitucionUsuario, accept=True)

    patientIds = []
    for number in range(args.pacientes):
        operator = operators[number % 2]
        read = patients.createPatient(db, operator, institution.idInstitucion, PatientCreateRequest(
            nombre=rng.choice(NAMES), apellido=f"{rng.choice(SURNAMES)} {number}", dni=f"{20000000 + number}",
            fechaNacimiento=date(1950 + rng.randint(0, 50), rng.randint(1, 12), rng.randint(1, 28)), sexoModelo=rng.choice(["masculino", "femenino"])))
        patientIds.append(read.idPerfilMedicion)
    for profileId in patientIds:
        stored = db.get(MeasurementProfile, profileId)
        bulkMeasurements(db, profileId, device.idDispositivo, args.por_paciente, rng, 45, (stored.sexoModelo or "FEMENINO"), years=0.5)

    # Mediciones completas con muestras del sensor (el flujo real: iniciar → muestras → cerrar) para la cuenta individual.
    from ppg import ppgSamples  # noqa: PLC0415 - copia de backend/tests/ppg.py montada junto a este script

    for index in range(8):
        started = measurementService.startMeasurement(db, consumer, MeasurementStart(idPerfilMedicion=profile.idPerfilMedicion,
                                                                                    idDispositivo=device.idDispositivo))
        samples = [{"numeroMuestra": n, "tiempoRelativoMs": t, "valorRed": red, "valorIR": ir}
                   for n, t, red, ir in ppgSamples(70 + index, 96.0, 20, dcIr=120000, dcRed=100000, seed=index)]
        measurementService.addSamples(db, consumer, started.idMedicion, SamplesRequest(muestras=samples))
        measurementService.finishMeasurement(db, consumer, started.idMedicion, MeasurementFinish())

    relation = lambda user: db.scalar(select(InstitutionUser).where(InstitutionUser.idUsuarioInvitado == user.idUsuario))  # noqa: E731
    print(json.dumps({
        "password": SEED_PASSWORD, "idDispositivo": str(device.idDispositivo), "idInstitucion": str(institution.idInstitucion),
        "consumidor": {"usuario": "perfconsumidor", "idPerfilMedicion": str(profile.idPerfilMedicion)},
        "propietaria": {"usuario": "perfduenia"}, "moderador": {"usuario": "perfmoderador"},
        "operadores": [{"usuario": op.usuario, "idInstitucionUsuario": str(relation(op).idInstitucionUsuario)} for op in operators],
        "pacientes": [str(p) for p in patientIds[:5]], "totalPacientes": len(patientIds),
    }))


main()
