# Salvaguardas de las depuraciones por política (H-04): aprobación, simulación, tope de volumen, confirmación por cantidad, auditoría de inicio,
# fin y falla, y conservación de lo que no venció. Todo con registros SINTÉTICOS en la base temporal; nada toca una base real ni programa purgas.

import json
from datetime import timedelta

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings, getSettings
from app.jobs import purgeInstitutionalRetention, retention
from app.models.audit import Audit
from app.models.institutionUser import InstitutionUser
from app.models.measurementProfile import MeasurementProfile
from app.services import auditRetention, measurementRetention, personnelRetention, retentionGuard
from app.services import institutionalRetention
from app.services.audit import registerEvent
from app.utils.timeZone import nowForDb
from tests.test_account_deletion import audits, db, engine, mails, makeUser, reload  # noqa: F401 - fixtures
from tests.test_account_lifecycle import forceExpiry, lastRelation, revokeOperator
from tests.test_audit_security import events, plant
from tests.test_institution_patients import deletion, patientData
from tests.test_institutions import freshLookupLimiter, institutional, team  # noqa: F401
from tests.test_retention_anonymization import measure, newPatient

BASE = {"_env_file": None, "DB_HOST": "h", "DB_NAME": "n", "DB_USER": "u", "DB_PASSWORD": "p", "JWT_SECRET": "j" * 40}
OLD = 40 * 30 * 24 * 60  # minutos: ~40 meses


@pytest.fixture(autouse=True)
def cleanGuard():
    retentionGuard.reset()
    yield
    retentionGuard.reset()
    getSettings.cache_clear()


def configure(monkeypatch, **values):
    for name, value in values.items():
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, str(value))
    getSettings.cache_clear()


def total(db, action=None):
    query = select(func.count()).select_from(Audit)
    if action:
        query = query.where(Audit.accion == action)
    return db.scalar(query)


# --- Configuración --------------------------------------------------------------------------------------------------------------------


def test_no_hay_plazos_ni_aprobacion_por_defecto_y_la_referencia_se_valida():
    defaults = Settings(**BASE)
    assert (defaults.AUDIT_RETENTION_MONTHS, defaults.PERSONNEL_RETENTION_MONTHS, defaults.RETENTION_APPROVAL_REFERENCE) == (0, 0, None)
    assert Settings(**BASE, RETENTION_APPROVAL_REFERENCE="  Dictamen 2026-117  ").RETENTION_APPROVAL_REFERENCE == "Dictamen 2026-117"
    for invalid in ("x", "a" * 201):
        with pytest.raises(ValueError):
            Settings(**BASE, RETENTION_APPROVAL_REFERENCE=invalid)
    for fraction in (0, -0.1, 1.5):
        with pytest.raises(ValueError):
            Settings(**BASE, RETENTION_MAX_DELETE_FRACTION=fraction)
    text = " ".join(Settings(**BASE, AUDIT_RETENTION_MONTHS=24).securityWarnings())
    assert "AUDIT_RETENTION_MONTHS" in text and "NO corre" in text
    assert "NO corre" not in " ".join(Settings(**BASE, AUDIT_RETENTION_MONTHS=24, RETENTION_APPROVAL_REFERENCE="Dictamen 117").securityWarnings())


# --- Auditoría ------------------------------------------------------------------------------------------------------------------------


def test_sin_aprobacion_un_plazo_configurado_no_elimina_nada(db, mails, monkeypatch):
    plant(db, "CREAR_GRUPO", resultado="EXITO", tipo="CRUD", modulo="GRUPOS", minutes=OLD)
    configure(monkeypatch, AUDIT_RETENTION_MONTHS=36, RETENTION_APPROVAL_REFERENCE=None)
    before = total(db)
    result = auditRetention.run(db)
    assert result["eventosEliminados"] == 0 and total(db) == before
    assert auditRetention.plan(db)["plazoTotalMesesEfectivo"] == 0 and auditRetention.plan(db)["plazoTotalMesesConfigurado"] == 36


def test_con_aprobacion_se_elimina_lo_vencido_se_conserva_lo_demas_y_queda_inicio_y_fin(db, mails, monkeypatch):
    old = plant(db, "CREAR_GRUPO", resultado="EXITO", tipo="CRUD", modulo="GRUPOS", minutes=OLD)
    recent = plant(db, "CREAR_GRUPO", resultado="EXITO", tipo="CRUD", modulo="GRUPOS", minutes=10 * 24 * 60)
    oldId, recentId = old.idAuditoria, recent.idAuditoria
    configure(monkeypatch, AUDIT_RETENTION_MONTHS=36, RETENTION_APPROVAL_REFERENCE="Dictamen 2026-117")
    result = auditRetention.run(db)
    db.expire_all()
    assert result["eventosEliminados"] == 1
    assert db.get(Audit, oldId) is None and db.get(Audit, recentId) is not None  # lo vigente se conserva
    [start] = events(db, auditRetention.ACCION_INICIO)
    [end] = events(db, "DEPURAR_AUDITORIA")
    assert start.fechaHora <= end.fechaHora and json.loads(start.datosNuevos)["previstos"] == 1
    policy = json.loads(end.datosNuevos)["politica"]
    assert policy["aprobacion"] == "Dictamen 2026-117" and policy["totalMeses"] == 36 and policy["confirmadaALaMano"] is False
    assert auditRetention.run(db)["eventosEliminados"] == 0  # idempotente


def test_la_simulacion_informa_sin_modificar_ni_registrar_nada(db, mails, monkeypatch):
    for index in range(3):
        plant(db, "CREAR_GRUPO", resultado="EXITO", tipo="CRUD", modulo="GRUPOS", minutes=OLD + index)
    configure(monkeypatch, AUDIT_RETENTION_MONTHS=36, RETENTION_APPROVAL_REFERENCE="Dictamen 2026-117")
    before = total(db)
    simulated = auditRetention.run(db, dryRun=True)
    assert simulated["simulacion"] is True and simulated["eventosAEliminar"] == 3 and simulated["bloqueadaPorVolumen"] is False
    assert total(db) == before and events(db, auditRetention.ACCION_INICIO) == []


def test_un_plazo_mal_tipeado_que_borraria_casi_todo_queda_frenado_por_el_tope_de_volumen(db, mails, monkeypatch):
    configure(monkeypatch, AUDIT_RETENTION_MONTHS=1, RETENTION_APPROVAL_REFERENCE="Dictamen 2026-117", RETENTION_GUARD_MIN_ROWS=5,
              RETENTION_MAX_DELETE_FRACTION=0.5)
    ids = [plant(db, "CREAR_GRUPO", resultado="EXITO", tipo="CRUD", modulo="GRUPOS", minutes=90 * 24 * 60 + n).idAuditoria for n in range(8)]
    recent = [plant(db, "CREAR_GRUPO", resultado="EXITO", tipo="CRUD", modulo="GRUPOS", minutes=n).idAuditoria for n in range(1, 3)]
    before = total(db, "CREAR_GRUPO")
    result = auditRetention.run(db)
    assert result["omitidaPorVolumen"] == 8 and result["eventosEliminados"] == 0 and total(db, "CREAR_GRUPO") == before  # no se borró nada
    [skipped] = events(db, auditRetention.ACCION_OMITIDA)
    assert skipped.resultado == "FALLO" and json.loads(skipped.datosNuevos)["previstos"] == 8
    auditRetention.run(db)  # el servicio revisa cada hora: no se inunda la auditoría de omisiones
    assert len(events(db, auditRetention.ACCION_OMITIDA)) == 1
    assert all(db.get(Audit, item) is not None for item in ids + recent)


def test_la_ejecucion_manual_exige_confirmar_la_cantidad_exacta(db, mails, monkeypatch):
    configure(monkeypatch, AUDIT_RETENTION_MONTHS=1, RETENTION_APPROVAL_REFERENCE="Dictamen 2026-117", RETENTION_GUARD_MIN_ROWS=5,
              RETENTION_MAX_DELETE_FRACTION=0.5)
    for n in range(8):
        plant(db, "CREAR_GRUPO", resultado="EXITO", tipo="CRUD", modulo="GRUPOS", minutes=90 * 24 * 60 + n)
    plant(db, "CREAR_GRUPO", resultado="EXITO", tipo="CRUD", modulo="GRUPOS", minutes=1)
    before = total(db)
    with pytest.raises(ValueError, match="no coincide"):
        auditRetention.run(db, confirmedDeletions=7)
    assert total(db) == before  # una cantidad equivocada no borra nada
    result = auditRetention.run(db, confirmedDeletions=8)
    assert result["eventosEliminados"] == 8
    [end] = events(db, "DEPURAR_AUDITORIA")
    assert json.loads(end.datosNuevos)["politica"]["confirmadaALaMano"] is True


def test_si_la_depuracion_falla_a_mitad_queda_registrado_lo_hecho_y_el_error(db, mails, monkeypatch):
    configure(monkeypatch, AUDIT_RETENTION_MONTHS=36, RETENTION_APPROVAL_REFERENCE="Dictamen 2026-117")
    for n in range(3):
        plant(db, "CREAR_GRUPO", resultado="EXITO", tipo="CRUD", modulo="GRUPOS", minutes=OLD + n)

    def broken(session, now, months):
        raise RuntimeError("falla simulada con dato-personal@example.com")

    monkeypatch.setattr(auditRetention, "purgeAll", broken)
    with pytest.raises(RuntimeError):
        auditRetention.run(db)
    assert len(events(db, auditRetention.ACCION_INICIO)) == 1
    [failure] = events(db, auditRetention.ACCION_FALLA)
    assert failure.resultado == "FALLO" and "RuntimeError" in failure.observacion
    assert "dato-personal" not in f"{failure.observacion} {failure.datosNuevos}"  # el mensaje de la excepción no se guarda
    assert total(db, "CREAR_GRUPO") == 3  # nada se perdió a medias


def test_la_minimizacion_de_ip_y_los_intentos_sin_cuenta_siguen_sin_aprobacion(db, mails, monkeypatch):
    # Son política ya publicada (90 días / 12 meses): no dependen de RETENTION_APPROVAL_REFERENCE.
    configure(monkeypatch, RETENTION_APPROVAL_REFERENCE=None)
    old = plant(db, "LOGIN_LOCAL", ip="203.0.113.7", motivo="PASSWORD_INCORRECTA", minutes=91 * 24 * 60)
    gone = plant(db, "LOGIN_LOCAL", ip="203.0.113.7", motivo="CUENTA_INEXISTENTE", fingerprint="f" * 32, minutes=13 * 30 * 24 * 60)
    goneId = gone.idAuditoria
    result = auditRetention.run(db)
    db.expire_all()
    assert result["contextosMinimizados"] >= 1 and result["intentosSinCuentaEliminados"] == 1
    assert db.get(Audit, goneId) is None and db.get(Audit, old.idAuditoria) is not None


# --- Personal histórico ---------------------------------------------------------------------------------------------------------------


def retiredRelation(db, team, years=11):
    operator = team.operator
    revokeOperator(db, team, operator)
    forceExpiry(db, operator)
    from app.services import accountLifecycle

    accountLifecycle.sweep(db)
    relation = lastRelation(db, team, operator)
    db.execute(update(InstitutionUser).where(InstitutionUser.idInstitucionUsuario == relation.idInstitucionUsuario).values(
        fechaBaja=nowForDb() - timedelta(days=366 * years)))
    db.commit()
    return relation


def test_el_personal_historico_no_se_minimiza_sin_aprobacion_y_con_ella_si(db, mails, team, monkeypatch):
    relation = retiredRelation(db, team)
    configure(monkeypatch, PERSONNEL_RETENTION_MONTHS=120, RETENTION_APPROVAL_REFERENCE=None)
    assert personnelRetention.minimizeExpired(db, 120, guarded=True) == 0
    assert reload(db, InstitutionUser, relation.idInstitucionUsuario).matriculaProfesional is not None  # conserva
    assert personnelRetention.plan(db, 120)["plazoMesesEfectivo"] == 0 and personnelRetention.plan(db, 120)["relacionesAMinimizar"] == 0
    configure(monkeypatch, PERSONNEL_RETENTION_MONTHS=120, RETENTION_APPROVAL_REFERENCE="Dictamen 2026-117")
    planned = personnelRetention.plan(db, 120)
    assert planned["relacionesAMinimizar"] == 1 and planned["aprobacion"] == "Dictamen 2026-117"
    assert personnelRetention.minimizeExpired(db, 120, guarded=True) == 1
    assert reload(db, InstitutionUser, relation.idInstitucionUsuario).matriculaProfesional is None
    [start] = audits(db, personnelRetention.ACCION_INICIO)
    [end] = audits(db, personnelRetention.ACCION)
    assert json.loads(end.datosNuevos)["aprobacion"] == "Dictamen 2026-117" and json.loads(start.datosNuevos)["previstas"] == 1
    assert personnelRetention.minimizeExpired(db, 120, guarded=True) == 0


def test_el_personal_dentro_del_plazo_se_conserva_y_el_tope_frena_una_pasada_masiva(db, mails, team, monkeypatch):
    relation = retiredRelation(db, team, years=2)
    configure(monkeypatch, PERSONNEL_RETENTION_MONTHS=120, RETENTION_APPROVAL_REFERENCE="Dictamen 2026-117")
    assert personnelRetention.minimizeExpired(db, 120, guarded=True) == 0  # baja hace 2 años: dentro de los 120 meses
    # Plazo mal tipeado (1 mes) con el tope en 1 fila: la relación vencería, pero el tope la frena y deja constancia.
    configure(monkeypatch, PERSONNEL_RETENTION_MONTHS=1, RETENTION_APPROVAL_REFERENCE="Dictamen 2026-117", RETENTION_GUARD_MIN_ROWS=0,
              RETENTION_MAX_DELETE_FRACTION=0.01)
    others = db.scalars(select(InstitutionUser).where(InstitutionUser.idInstitucionUsuario != relation.idInstitucionUsuario)).all()
    assert others and personnelRetention.plan(db, 1)["bloqueadaPorVolumen"] is True or len(others) == 0
    assert personnelRetention.minimizeExpired(db, 1, guarded=True) == 0
    assert reload(db, InstitutionUser, relation.idInstitucionUsuario).matriculaProfesional is not None
    assert len(audits(db, personnelRetention.ACCION_OMITIDA)) == 1
    with pytest.raises(ValueError, match="no coincide"):
        personnelRetention.minimizeExpired(db, 1, guarded=True, confirmed=99)
    assert personnelRetention.minimizeExpired(db, 1, guarded=True, confirmed=1) == 1


# --- Pacientes institucionales --------------------------------------------------------------------------------------------------------


def closedInstitution(db, team, count=2):
    from app.services import institution as institutions

    made = [newPatient(db, team, dni=f"2011{n}555", nombre=f"Sintetico{n}", apellido="Prueba") for n in range(count)]
    for patient in made:
        measure(db, patient.idPerfilMedicion, daysAgo=100)
    institutions.deleteInstitution(db, team.owner, team.id, deletion())
    end = reload(db, MeasurementProfile, made[0].idPerfilMedicion).fechaExpiracionDatosPersonales + timedelta(minutes=1)
    return made, end


def test_la_simulacion_de_pacientes_coincide_con_lo_que_despues_hace_el_job(db, mails, team):
    made, end = closedInstitution(db, team)
    planned = institutionalRetention.plan(db, end)
    assert planned["perfilesAAnonimizar"] == 2 and planned["medicionesAEliminar"] == 2
    assert institutionalRetention.plan(db, nowForDb() + timedelta(days=1)) == {"perfilesAAnonimizar": 0, "medicionesAEliminar": 0}  # dentro del plazo
    assert all(reload(db, MeasurementProfile, p.idPerfilMedicion).nombre is not None for p in made)  # simular no modifica
    deleted = measurementRetention.purgeExpiredMeasurements(db, now=end)
    anonymized = institutionalRetention.purgeExpiredPatientData(db, now=end)
    deleted += measurementRetention.purgeExpiredMeasurements(db, now=end)
    assert (anonymized, deleted) == (planned["perfilesAAnonimizar"], planned["medicionesAEliminar"])


def test_un_error_parcial_al_anonimizar_queda_en_la_auditoria_sin_identificadores(db, mails, team, monkeypatch):
    made, end = closedInstitution(db, team, count=3)
    original = measurementRetention.anonymizeProfile
    calls = []

    def flaky(session, idPerfil, moment):
        calls.append(idPerfil)
        if len(calls) == 2:
            raise RuntimeError("falla simulada de Sintetico1")
        return original(session, idPerfil, moment)

    monkeypatch.setattr(measurementRetention, "anonymizeProfile", flaky)
    assert institutionalRetention.purgeExpiredPatientData(db, now=end) == 2
    [partial] = audits(db, institutionalRetention.ACCION_PARCIAL)
    data = json.loads(partial.datosNuevos)
    assert partial.resultado == "FALLO" and data == {"perfilesConError": 1, "perfilesProcesados": 2}
    assert "Sintetico" not in f"{partial.observacion} {partial.datosNuevos}" and str(made[0].idPerfilMedicion) not in partial.datosNuevos


def test_el_job_de_pacientes_simula_y_solo_ejecuta_con_la_base_y_las_cantidades_confirmadas(db, engine, team, mails, monkeypatch, capsys):
    made, end = closedInstitution(db, team)
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(purgeInstitutionalRetention, "getJobsSessionFactory", lambda: sessions)
    monkeypatch.setattr(institutionalRetention, "nowForDb", lambda: end)
    monkeypatch.setattr(measurementRetention, "nowForDb", lambda: end)
    monkeypatch.setattr(purgeInstitutionalRetention, "nowForDb", lambda: end)
    base = getSettings().DB_NAME
    assert purgeInstitutionalRetention.main(["--simular"]) == 0
    simulated = json.loads(capsys.readouterr().out)
    assert simulated["simulacion"] is True and simulated["perfilesAAnonimizar"] == 2
    noop = [[], ["--confirmo-base", "OtraBase", "--confirmo-perfiles", "2", "--confirmo-mediciones", "2"], ["--confirmo-base", base],
            ["--confirmo-base", base, "--confirmo-perfiles", "2", "--confirmo-mediciones", "99"]]
    for arguments in noop:
        assert purgeInstitutionalRetention.main(arguments) == 2
    assert all(reload(db, MeasurementProfile, p.idPerfilMedicion).nombre is not None for p in made)  # ninguna combinación incompleta modifica
    assert purgeInstitutionalRetention.main(["--confirmo-base", base, "--confirmo-perfiles", "2",
                                             "--confirmo-mediciones", str(simulated["medicionesAEliminar"])]) == 0
    assert all(reload(db, MeasurementProfile, p.idPerfilMedicion).nombre is None for p in made)


# --- Herramienta manual ---------------------------------------------------------------------------------------------------------------


def test_la_herramienta_manual_previsualiza_y_ejecuta_solo_con_las_cantidades_exactas(db, engine, mails, monkeypatch, capsys):
    configure(monkeypatch, AUDIT_RETENTION_MONTHS=1, RETENTION_APPROVAL_REFERENCE="Dictamen 2026-117", RETENTION_GUARD_MIN_ROWS=2,
              RETENTION_MAX_DELETE_FRACTION=0.3)
    for n in range(4):
        plant(db, "CREAR_GRUPO", resultado="EXITO", tipo="CRUD", modulo="GRUPOS", minutes=90 * 24 * 60 + n)
    for n in range(2):
        plant(db, "CREAR_GRUPO", resultado="EXITO", tipo="CRUD", modulo="GRUPOS", minutes=n + 1)
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(retention, "getJobsSessionFactory", lambda: sessions)
    base = getSettings().DB_NAME
    before = total(db)
    assert retention.main(["previsualizar"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["simulacion"] is True and report["auditoria"]["eventosAEliminar"] == 4 and report["auditoria"]["bloqueadaPorVolumen"] is True
    assert report["aprobacion"] == "Dictamen 2026-117" and total(db) == before
    for arguments in (["ejecutar"], ["ejecutar", "--confirmo-base", "OtraBase", "--confirmo-eventos", "4", "--confirmo-personal", "0"],
                      ["ejecutar", "--confirmo-base", base, "--confirmo-eventos", "3", "--confirmo-personal", "0"]):
        assert retention.main(arguments) == 2
    assert total(db) == before
    assert retention.main(["ejecutar", "--confirmo-base", base, "--confirmo-eventos", "4", "--confirmo-personal", "0"]) == 0
    assert "eventosEliminados" in capsys.readouterr().out
    assert total(db, "CREAR_GRUPO") == 2
