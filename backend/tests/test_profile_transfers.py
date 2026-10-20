# Pruebas de transferencia de pacientes institucionales entre operadores (RF32, TransferenciaPerfil).
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_profile_transfers.py -v
#
# Usan el esquema SQLite temporal de test_account_deletion.py y el escenario `team` de test_institutions.py.

import threading
from datetime import timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.core.exceptions import AuthError
from app.models.institutionUser import InstitutionUser
from app.models.measurement import Measurement
from app.models.measurementProfile import MeasurementProfile
from app.models.profileTransfer import ProfileTransfer
from app.models.user import User
from app.services import institution as institutions
from app.services import institutionPatients as patients
from app.services import profileTransfers as transfers
from app.utils.timeZone import nowForDb
from tests.legacy_offboarding import legacyRevoke
from tests.test_account_deletion import (  # noqa: F401 - fixtures
    audits,
    db,
    engine,
    mails,
    makeUser,
    reload,
)
from tests.test_institution_patients import addOperator, otherInstitution, patientData
from tests.test_institutions import (  # noqa: F401 - fixtures
    expectError,
    freshLookupLimiter,
    institutional,
    relationOf,
    team,
)


@pytest.fixture
def scene(db, mails, team):
    """A (operadora del escenario) tiene un paciente con 2 mediciones; B es otro operador activo."""
    patient = patients.createPatient(db, team.operator, team.id, patientData())
    profile = db.get(MeasurementProfile, patient.idPerfilMedicion)
    from tests.test_groups import addReading  # mediciones históricas del paciente
    addReading(db, profile, 5, 96)
    addReading(db, profile, 1, 98)
    second = addOperator(db, team)
    mails.clear()

    class Scene:
        pass

    scene = Scene()
    scene.team, scene.id = team, team.id
    scene.a = relationOf(db, team, team.operator)
    scene.b = second
    scene.bUser = db.get(User, second.idUsuarioInvitado)
    scene.profile = patient.idPerfilMedicion
    return scene


def request(db, scene, observacion="Cambio de turno", actor=None, destino=None, profile=None):
    return transfers.requestTransfer(db, actor or scene.team.operator, scene.id, profile or scene.profile,
                                     destino or scene.b.idInstitucionUsuario, observacion)


def responsible(db, scene) -> InstitutionUser | None:
    db.expire_all()
    return db.get(MeasurementProfile, scene.profile).idInstitucionUsuarioResponsable


def measurementCount(db, scene) -> int:
    return db.scalar(select(func.count()).select_from(Measurement).where(Measurement.idPerfilMedicion == scene.profile))


# --- 1-5. Solicitar y aceptar ---------------------------------------------------------------------------------


def test_a_solicita_y_el_perfil_sigue_con_a_hasta_que_b_acepta(db, mails, scene):
    item = request(db, scene)
    assert (item.estado, item.puedeCancelar, item.puedeAceptar) == ("PENDIENTE", True, False)
    assert item.origen.idInstitucionUsuario == scene.a.idInstitucionUsuario
    assert item.destino.idInstitucionUsuario == scene.b.idInstitucionUsuario
    assert responsible(db, scene) == scene.a.idInstitucionUsuario  # sin cambios mientras está pendiente
    stored = reload(db, ProfileTransfer, item.idTransferenciaPerfil)
    assert stored.estado == "PENDIENTE" and stored.fechaTransferencia is None and stored.observacion == "Cambio de turno"
    assert mails[-1]["to"] == scene.bUser.correoElectronico and "transferencia" in mails[-1]["subject"].lower()
    assert [a.resultado for a in audits(db, "SOLICITAR_TRANSFERENCIA_PERFIL")] == ["EXITO"]


def test_b_acepta_el_perfil_pasa_a_b_y_las_mediciones_siguen_intactas(db, mails, scene):
    item = request(db, scene)
    before = measurementCount(db, scene)
    mails.clear()
    accepted = transfers.acceptTransfer(db, scene.bUser, scene.id, item.idTransferenciaPerfil)
    assert accepted.estado == "ACEPTADA" and accepted.fechaTransferencia >= accepted.fechaPeticion
    assert responsible(db, scene) == scene.b.idInstitucionUsuario
    assert db.get(MeasurementProfile, scene.profile).idPerfilMedicion == scene.profile  # mismo idPerfilMedicion
    assert measurementCount(db, scene) == before == 2
    # El paciente desaparece de los de A y aparece entre los de B.
    mine = lambda actor: {p.idPerfilMedicion for p in patients.listPatients(db, actor, scene.id, soloMios=True).items}
    assert scene.profile not in mine(scene.team.operator) and scene.profile in mine(scene.bUser)
    # Auditoría del cambio de responsable (sin datos personales) y aviso a A.
    [change] = audits(db, "CAMBIAR_RESPONSABLE_PERFIL")
    assert str(scene.a.idInstitucionUsuario) in change.datosPrevios and str(scene.b.idInstitucionUsuario) in change.datosNuevos
    assert "Juan" not in change.datosNuevos
    assert mails[-1]["to"] == scene.team.operator.correoElectronico


def test_la_solicitud_no_expone_datos_identificatorios(db, mails, scene):
    item = request(db, scene)
    dumped = item.model_dump_json()
    for secret in ("20111222", "20.111.222", "1980-01-02"):  # nunca documento ni fecha de nacimiento
        assert secret not in dumped
    assert item.paciente.identificadorPseudonimo is not None and item.paciente.edad is not None
    # El solicitante tiene al paciente a cargo: ve su nombre. El destinatario, todavía no.
    assert (item.paciente.nombre, item.paciente.apellido) == ("Juan", "Pérez") and item.paciente.datosIdentificativos
    asRecipient = transfers.listTransfers(db, scene.bUser, scene.id, direccion="recibidas").items[0]
    assert asRecipient.paciente.nombre is None and asRecipient.paciente.datosIdentificativos is None
    assert asRecipient.paciente.identificadorPseudonimo == item.paciente.identificadorPseudonimo


# --- 6-7. Rechazar y cancelar ----------------------------------------------------------------------------------


def test_b_rechaza_y_no_cambia_el_responsable(db, mails, scene):
    item = request(db, scene)
    mails.clear()
    rejected = transfers.rejectTransfer(db, scene.bUser, scene.id, item.idTransferenciaPerfil)
    assert rejected.estado == "RECHAZADA" and rejected.fechaTransferencia is None
    assert responsible(db, scene) == scene.a.idInstitucionUsuario
    assert mails[-1]["to"] == scene.team.operator.correoElectronico  # se avisa al solicitante
    assert audits(db, "RECHAZAR_TRANSFERENCIA_PERFIL")


def test_a_cancela_una_pendiente_y_no_puede_cancelar_una_aceptada(db, mails, scene):
    item = request(db, scene)
    mails.clear()
    cancelled = transfers.cancelTransfer(db, scene.team.operator, scene.id, item.idTransferenciaPerfil)
    assert cancelled.estado == "CANCELADA" and responsible(db, scene) == scene.a.idInstitucionUsuario
    assert mails[-1]["to"] == scene.bUser.correoElectronico  # se informa al destinatario
    # Una aceptada no se "des-hace": cancelar responde que ya no está pendiente.
    second = request(db, scene)
    transfers.acceptTransfer(db, scene.bUser, scene.id, second.idTransferenciaPerfil)
    expectError("PERMISO_INSUFICIENTE", transfers.cancelTransfer, db, scene.bUser, scene.id, second.idTransferenciaPerfil)
    assert reload(db, ProfileTransfer, second.idTransferenciaPerfil).estado == "ACEPTADA"


def test_solo_el_solicitante_cancela_y_solo_el_destino_responde(db, mails, scene):
    item = request(db, scene)
    third = addOperator(db, scene.team, "tercero@example.com", "tercero")
    thirdUser = db.get(User, third.idUsuarioInvitado)
    expectError("PERMISO_INSUFICIENTE", transfers.cancelTransfer, db, scene.bUser, scene.id, item.idTransferenciaPerfil)
    expectError("PERMISO_INSUFICIENTE", transfers.acceptTransfer, db, scene.team.operator, scene.id, item.idTransferenciaPerfil)
    expectError("PERMISO_INSUFICIENTE", transfers.rejectTransfer, db, scene.team.operator, scene.id, item.idTransferenciaPerfil)
    # Un tercer operador ni siquiera ve que existe.
    expectError("TRANSFERENCIA_NO_ENCONTRADA", transfers.acceptTransfer, db, thirdUser, scene.id, item.idTransferenciaPerfil)
    assert transfers.listTransfers(db, thirdUser, scene.id).total == 0
    assert responsible(db, scene) == scene.a.idInstitucionUsuario


# --- Validaciones de la solicitud ----------------------------------------------------------------------------


def test_no_se_transfiere_a_uno_mismo_ni_a_quien_no_es_operador_activo(db, mails, scene):
    expectError("TRANSFERENCIA_MISMO_RESPONSABLE", request, db, scene, destino=scene.a.idInstitucionUsuario)
    moderator = relationOf(db, scene.team, scene.team.moderator)
    expectError("OPERADOR_NO_DISPONIBLE", request, db, scene, destino=moderator.idInstitucionUsuario)
    owner = relationOf(db, scene.team, scene.team.owner)
    expectError("OPERADOR_NO_DISPONIBLE", request, db, scene, destino=owner.idInstitucionUsuario)
    institutions.revokeMember(db, scene.team.moderator, scene.id, "OPERADOR", scene.b.idInstitucionUsuario)
    expectError("OPERADOR_NO_DISPONIBLE", request, db, scene)
    assert db.scalar(select(func.count()).select_from(ProfileTransfer)) == 0


def test_solo_el_responsable_actual_solicita(db, mails, scene):
    # B no es el responsable del paciente; el moderador y el propietario tampoco solicitan transferencias.
    expectError("PERMISO_INSUFICIENTE", request, db, scene, actor=scene.bUser, destino=scene.a.idInstitucionUsuario)
    expectError("PERMISO_INSUFICIENTE", request, db, scene, actor=scene.team.moderator)
    expectError("PERMISO_INSUFICIENTE", request, db, scene, actor=scene.team.owner)


def test_no_hay_dos_solicitudes_pendientes_sobre_el_mismo_perfil(db, mails, scene):
    request(db, scene)
    third = addOperator(db, scene.team, "tercero@example.com", "tercero")
    expectError("TRANSFERENCIA_PENDIENTE", request, db, scene, destino=third.idInstitucionUsuario)
    expectError("TRANSFERENCIA_PENDIENTE", request, db, scene)
    pending = db.scalar(select(func.count()).select_from(ProfileTransfer).where(ProfileTransfer.estado == "PENDIENTE"))
    assert pending == 1


def test_no_se_transfiere_un_paciente_dado_de_baja(db, mails, scene):
    patients.dischargePatient(db, scene.team.moderator, scene.id, scene.profile)
    expectError("PACIENTE_NO_ENCONTRADO", request, db, scene)  # la baja lo anonimiza: ya no es un paciente de la institución


def test_no_se_transfieren_perfiles_individuales(db, mails, scene):
    from tests.test_account_deletion import addMeasurement
    own, _ = addMeasurement(db, makeUser(db, email="solo@example.com", usuario="solo"))
    expectError("PACIENTE_NO_ENCONTRADO", request, db, scene, profile=own.idPerfilMedicion)


# --- 8. Entre instituciones -------------------------------------------------------------------------------------


def test_no_se_permiten_transferencias_entre_instituciones(db, mails, scene):
    other, otherOperator, otherRelation = otherInstitution(db)
    expectError("OPERADOR_NO_DISPONIBLE", request, db, scene, destino=otherRelation.idInstitucionUsuario)
    # Un operador de otra institución no ve ni responde nada de esta.
    item = request(db, scene)
    expectError("INSTITUCION_NO_ENCONTRADA", transfers.acceptTransfer, db, otherOperator, scene.id, item.idTransferenciaPerfil)
    expectError("TRANSFERENCIA_NO_ENCONTRADA", transfers.acceptTransfer, db, otherOperator, other.idInstitucion,
                item.idTransferenciaPerfil)
    assert responsible(db, scene) == scene.a.idInstitucionUsuario


# --- 9-10. Doble aceptación, vigencia y concurrencia ---------------------------------------------------------


def test_no_se_acepta_dos_veces_la_misma_solicitud(db, mails, scene):
    item = request(db, scene)
    transfers.acceptTransfer(db, scene.bUser, scene.id, item.idTransferenciaPerfil)
    expectError("TRANSFERENCIA_NO_PENDIENTE", transfers.acceptTransfer, db, scene.bUser, scene.id, item.idTransferenciaPerfil)
    expectError("TRANSFERENCIA_NO_PENDIENTE", transfers.rejectTransfer, db, scene.bUser, scene.id, item.idTransferenciaPerfil)
    assert len(audits(db, "ACEPTAR_TRANSFERENCIA_PERFIL")) == 1


def test_el_gestor_no_pisa_una_transferencia_pendiente_ni_cambia_al_responsable_activo(db, mails, scene):
    item = request(db, scene)
    # Con una solicitud pendiente, el propietario/moderador no reasigna a un tercero por encima: el responsable activo no cambia unilateralmente.
    third = addOperator(db, scene.team, "tercero@example.com", "tercero")
    expectError("TRANSFERENCIA_PENDIENTE", patients.assignResponsible, db, scene.team.moderator, scene.id, scene.profile,
                third.idInstitucionUsuario)
    assert reload(db, ProfileTransfer, item.idTransferenciaPerfil).estado == "PENDIENTE"
    assert responsible(db, scene) == scene.a.idInstitucionUsuario  # el responsable actual no se toca


def test_si_el_origen_ya_no_es_responsable_la_aceptacion_se_rechaza_como_obsoleta(db, mails, scene):
    item = request(db, scene)
    third = addOperator(db, scene.team, "tercero@example.com", "tercero")
    # Cambio de responsable por una vía que no cancela la solicitud (SQL directo): la aceptación debe detectarlo.
    profile = db.get(MeasurementProfile, scene.profile)
    profile.idInstitucionUsuarioResponsable = third.idInstitucionUsuario
    db.commit()
    expectError("TRANSFERENCIA_OBSOLETA", transfers.acceptTransfer, db, scene.bUser, scene.id, item.idTransferenciaPerfil)
    assert responsible(db, scene) == third.idInstitucionUsuario
    assert reload(db, ProfileTransfer, item.idTransferenciaPerfil).estado == "CANCELADA"


def test_aceptaciones_y_cancelaciones_simultaneas_dejan_un_solo_resultado(engine, db, mails, scene):
    item = request(db, scene)
    makeSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    barrier = threading.Barrier(2)
    results, failures = [], []

    def run(action, userId):
        session = makeSession()
        try:
            user = session.get(User, userId)
            barrier.wait()
            action(session, user, scene.id, item.idTransferenciaPerfil)
            results.append("OK")
        except AuthError as error:
            results.append(error.code)
        except Exception as error:  # pragma: no cover - diagnóstico
            failures.append(error)
        finally:
            session.close()

    threads = [
        threading.Thread(target=run, args=(transfers.acceptTransfer, scene.bUser.idUsuario)),
        threading.Thread(target=run, args=(transfers.cancelTransfer, scene.team.operator.idUsuario)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert failures == []
    assert results.count("OK") == 1
    state = reload(db, ProfileTransfer, item.idTransferenciaPerfil).estado
    expected = scene.b.idInstitucionUsuario if state == "ACEPTADA" else scene.a.idInstitucionUsuario
    assert state in ("ACEPTADA", "CANCELADA") and responsible(db, scene) == expected


# --- Historial y listados ------------------------------------------------------------------------------------


def test_listados_recibidas_enviadas_e_historial(db, mails, scene):
    first = request(db, scene)
    transfers.rejectTransfer(db, scene.bUser, scene.id, first.idTransferenciaPerfil)
    second = request(db, scene)
    transfers.acceptTransfer(db, scene.bUser, scene.id, second.idTransferenciaPerfil)

    sent = transfers.listTransfers(db, scene.team.operator, scene.id, direccion="enviadas")
    received = transfers.listTransfers(db, scene.bUser, scene.id, direccion="recibidas")
    assert sent.total == received.total == 2
    assert {i.estado for i in sent.items} == {"RECHAZADA", "ACEPTADA"}
    assert all(i.esEnviada and not i.esRecibida for i in sent.items)
    assert all(i.esRecibida and not i.puedeAceptar for i in received.items)  # ya respondidas
    assert transfers.listTransfers(db, scene.bUser, scene.id, direccion="recibidas", estado="ACEPTADA").total == 1

    # Historial: operador anterior y nuevo, fecha de solicitud y fecha efectiva.
    accepted = next(i for i in received.items if i.estado == "ACEPTADA")
    assert accepted.origen.idInstitucionUsuario == scene.a.idInstitucionUsuario
    assert accepted.destino.idInstitucionUsuario == scene.b.idInstitucionUsuario
    assert accepted.fechaPeticion is not None and accepted.fechaTransferencia is not None
    # El propietario y el moderador ven el historial completo de la institución; no pueden responder.
    everything = transfers.listTransfers(db, scene.team.owner, scene.id)
    assert everything.total == 2 and not any(i.puedeAceptar or i.puedeCancelar for i in everything.items)


def test_la_propuesta_de_un_gestor_queda_pendiente_en_el_historial_con_su_origen(db, mails, scene):
    patients.assignResponsible(db, scene.team.moderator, scene.id, scene.profile, scene.b.idInstitucionUsuario)
    [entry] = transfers.listTransfers(db, scene.team.owner, scene.id).items
    assert entry.estado == "PENDIENTE"
    assert entry.origen.idInstitucionUsuario == scene.a.idInstitucionUsuario
    assert entry.destino.idInstitucionUsuario == scene.b.idInstitucionUsuario
    assert responsible(db, scene) == scene.a.idInstitucionUsuario


def test_la_asignacion_directa_de_un_paciente_huerfano_queda_en_el_historial_con_su_origen(db, mails, scene):
    legacyRevoke(db, scene.team.moderator, scene.id, scene.a.idInstitucionUsuario)  # el responsable deja de estar activo
    patients.assignResponsible(db, scene.team.moderator, scene.id, scene.profile, scene.b.idInstitucionUsuario)
    [entry] = transfers.listTransfers(db, scene.team.owner, scene.id).items
    assert entry.estado == "ACEPTADA"
    assert entry.origen.idInstitucionUsuario == scene.a.idInstitucionUsuario
    assert entry.destino.idInstitucionUsuario == scene.b.idInstitucionUsuario


def test_el_perfil_permanece_en_la_institucion_si_el_operador_se_desvincula(db, mails, scene):
    # Regla esencial: el paciente y sus mediciones se conservan en la institución, nunca viajan a otra.
    legacyRevoke(db, scene.team.moderator, scene.id, scene.a.idInstitucionUsuario)
    page = patients.listPatients(db, scene.team.moderator, scene.id)
    assert [p.idPerfilMedicion for p in page.items] == [scene.profile] and not page.items[0].responsable.activo
    assert measurementCount(db, scene) == 2
    patients.assignResponsible(db, scene.team.moderator, scene.id, scene.profile, scene.b.idInstitucionUsuario)
    assert responsible(db, scene) == scene.b.idInstitucionUsuario
