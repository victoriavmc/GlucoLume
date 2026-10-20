# Privacidad de los dashboards: ninguna vista entrega el valor de salud de una medición individual a quien no es el operador responsable.
#
#     python -m pytest tests/test_dashboard_privacy.py -v
#
# Cubre dos fugas halladas por la auditoría Cloudflare (run-1): la serie diaria institucional con un solo paciente en el día y
# «realizadas» del operador anterior tras una transferencia. Datos sintéticos, SQLite temporal.

from datetime import timedelta

import pytest

from app.services import dashboard as dashboards
from app.services import institutionPatients as patients
from app.services import patientAccess
from app.services import profileTransfers as transfers
from app.utils.timeZone import nowForDb
from tests.test_account_deletion import db, engine, mails  # noqa: F401 - fixtures
from tests.test_dashboards import backdate, institutionData, measure
from tests.test_institution_patients import patientData
from tests.test_institutions import team  # noqa: F401
from tests.test_measurements import device  # noqa: F401


def _fivePatients(db, team, dev):
    """Un paciente mide solo hace 3 días; otros cuatro miden hoy: 5 pacientes distintos en el período."""
    isolated = patients.createPatient(db, team.operator, team.id, patientData(nombre="aislado", apellido="uno", dni="10000001"))
    backdate(db, measure(db, team.operator, isolated.idPerfilMedicion, dev, "91", 88).idMedicion, 3)
    for i in range(4):
        other = patients.createPatient(db, team.operator, team.id, patientData(nombre=f"p{i}", apellido="x", dni=f"2000000{i}"))
        measure(db, team.operator, other.idPerfilMedicion, dev, "98", 70)
    return (nowForDb() - timedelta(days=3)).date()


def test_la_serie_diaria_institucional_omite_dias_con_menos_de_k_pacientes(db, mails, team):
    day = _fivePatients(db, team, device(db, institucion=team.id))
    for viewer in (team.moderator, team.owner):
        view = dashboards.institutionDashboard(db, viewer, team.id, 30)
        assert not view.agregadosProtegidos and view.estadisticas.cantidadMediciones == 5  # el agregado del período se informa
        assert day not in [p.fecha for p in view.estadisticas.serieDiaria], "el día con un solo paciente expondría su medición"
        assert all(p.mediciones >= patientAccess.MIN_AGGREGATE_PATIENTS for p in view.estadisticas.serieDiaria)


def test_la_serie_diaria_conserva_los_dias_con_k_pacientes(db, mails, team):
    dev = device(db, institucion=team.id)
    for i in range(patientAccess.MIN_AGGREGATE_PATIENTS):
        p = patients.createPatient(db, team.operator, team.id, patientData(nombre=f"k{i}", apellido="y", dni=f"3000000{i}"))
        measure(db, team.operator, p.idPerfilMedicion, dev, "97", 72)
    view = dashboards.institutionDashboard(db, team.moderator, team.id, 30)
    assert [p.mediciones for p in view.estadisticas.serieDiaria] == [patientAccess.MIN_AGGREGATE_PATIENTS]


def test_el_operador_anterior_no_recibe_valores_de_pacientes_que_ya_no_tiene(db, mails, team):
    second, secondUser, dev = institutionData(db, team)
    patient = patients.createPatient(db, team.operator, team.id, patientData(nombre="rosa", apellido="diaz", dni="30111222"))
    measure(db, team.operator, patient.idPerfilMedicion, dev, "93", 91)
    before = dashboards.operatorDashboard(db, team.operator, team.id, "me")
    assert [r.spo2 for r in before.realizadas] == [pytest.approx(93, abs=1)]  # mientras es el responsable, sí los ve
    sent = transfers.requestTransfer(db, team.operator, team.id, patient.idPerfilMedicion, second.idInstitucionUsuario, None)
    transfers.acceptTransfer(db, secondUser, team.id, sent.idTransferenciaPerfil)
    after = dashboards.operatorDashboard(db, team.operator, team.id, "me")
    assert after.pacientesAsignados == 0 and after.realizadas == []
    assert after.medicionesRealizadas == 1  # el conteo histórico no lleva valores y se conserva
    new = dashboards.operatorDashboard(db, secondUser, team.id, "me")
    assert len(new.ultimasDePacientes) == 1  # el nuevo responsable sí las ve
