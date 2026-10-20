# Pruebas del módulo de matrices de estimación: ámbitos GLOBAL e institucional, roles, versionado, activación
# transaccional, validación de reglas, selección automática para las mediciones y auditoría.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_matrices.py -v

import threading
import uuid
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.core.exceptions import AuthError
from app.models.institution import Institution
from app.models.matrix import Matrix
from app.models.matrixRule import MatrixRule
from app.models.measurement import Measurement
from app.models.user import User
from app.schemas.matrix import (
    MatrixCreateRequest,
    MatrixDraftUpdateRequest,
    MatrixRuleInput,
    MatrixRuleUpdateRequest,
)
from app.services import institution as institutions
from app.services import matrix as matrices
from app.services import measurement as measurements
from app.services import institutionPatients as patients
from app.utils.timeZone import nowForDb
from tests.test_account_deletion import (  # noqa: F401 - fixtures
    audits,
    db,
    engine,
    mails,
    makeUser,
    reload,
)
from tests.test_institution_patients import patientData
from tests.test_institutions import (  # noqa: F401 - fixtures
    expectError,
    freshLookupLimiter,
    institutional,
    newInstitution,
    relationOf,
    team,
)
from tests.test_measurements import device, glucose, samples


def rule(**overrides) -> MatrixRuleInput:
    data = {"sexoModelo": "FEMENINO", "edadDesde": 18, "edadHasta": 60, "condicionComida": "AYUNO",
            "glucosaMinReferencia": "70", "glucosaMaxReferencia": "110"}
    return MatrixRuleInput(**{**data, **overrides})


@pytest.fixture
def platform(db, mails):
    return makeUser(db, tipoCuenta="MODERADOR_PLATAFORMA", email="moderacion@example.com", usuario="moderacion")


def newMatrix(db, actor, ambito="GLOBAL", idInstitucion=None, nombre="Matriz GlucoLume", rules=(None,)):
    created = matrices.createMatrix(db, actor, MatrixCreateRequest(ambito=ambito, idInstitucion=idInstitucion, nombre=nombre))
    for item in rules:
        matrices.addRule(db, actor, created.idMatriz, item or rule())
    return matrices.getMatrix(db, actor, created.idMatriz)


def activeMatrix(db, actor, **kwargs):
    created = newMatrix(db, actor, **kwargs)
    return matrices.activate(db, actor, created.idMatriz)


@pytest.fixture
def north(db, mails):
    """Segunda institución (Clínica Norte) con propietaria, moderador y operadora activos."""
    owner = institutional(db, "norte-duenia@example.com", "norteduenia")
    moderator = institutional(db, "norte-moderador@example.com", "nortemoderador")
    operator = institutional(db, "norte-operadora@example.com", "norteoperadora")
    institution = newInstitution(db, owner, "87654321", "Clínica Norte")
    invitation = institutions.invite(db, owner, institution.idInstitucion, "MODERADOR", moderator.correoElectronico)
    institutions.respondInvitation(db, moderator, invitation.idInstitucionUsuario, accept=True)
    invitation = institutions.invite(db, moderator, institution.idInstitucion, "OPERADOR", operator.correoElectronico)
    institutions.respondInvitation(db, operator, invitation.idInstitucionUsuario, accept=True)
    mails.clear()

    class North:
        pass

    north = North()
    north.owner, north.moderator, north.operator, north.id = owner, moderator, operator, institution.idInstitucion
    return north


# --- Matriz global (moderación de la plataforma) -----------------------------------------------------------


@pytest.mark.parametrize("tipo", ["MODERADOR_PLATAFORMA", "ADMINISTRADOR_PLATAFORMA"])
def test_las_cuentas_de_plataforma_gestionan_las_matrices_globales(db, mails, tipo):
    actor = makeUser(db, tipoCuenta=tipo, email="p@example.com", usuario="plataforma")
    created = newMatrix(db, actor)
    assert (created.estado, created.version, created.ambito, created.cantidadReglas) == ("BORRADOR", "1", "GLOBAL", 1)
    assert created.permisos.puedeEditar and created.permisos.puedeActivar
    # La auditoría de las globales la consulta solo el administrador del sistema, no la moderación.
    assert created.permisos.puedeVerAuditoria == (tipo == "ADMINISTRADOR_PLATAFORMA")
    updated = matrices.updateDraft(db, actor, created.idMatriz, MatrixDraftUpdateRequest(descripcion="Referencia 2026"))
    assert updated.descripcion == "Referencia 2026"
    active = matrices.activate(db, actor, created.idMatriz)
    assert active.estado == "ACTIVA" and not active.permisos.puedeEditar and active.permisos.puedeDesactivar
    assert [m.idMatriz for m in matrices.listGlobal(db, actor)] == [created.idMatriz]
    assert matrices.deactivate(db, actor, created.idMatriz).estado == "INACTIVA"
    assert matrices.archive(db, actor, created.idMatriz).estado == "ARCHIVADA"
    expectError("MATRIZ_ESTADO_INVALIDO", matrices.activate, db, actor, created.idMatriz)  # terminal


def test_solo_la_plataforma_lista_y_crea_matrices_globales(db, mails, team, platform):
    for actor in (team.owner, team.moderator, team.operator, makeUser(db, email="c@example.com", usuario="c")):
        expectError("PERMISO_INSUFICIENTE", matrices.listGlobal, db, actor)
        expectError("PERMISO_INSUFICIENTE", matrices.createMatrix, db, actor, MatrixCreateRequest(ambito="GLOBAL", nombre="Intento"))
    assert db.scalar(select(func.count()).select_from(Matrix)) == 0


def test_un_propietario_no_edita_una_matriz_global_pero_ve_la_activa(db, mails, team, platform):
    draft = newMatrix(db, platform)
    expectError("MATRIZ_NO_ENCONTRADA", matrices.getMatrix, db, team.owner, draft.idMatriz)  # borrador: privado
    active = matrices.activate(db, platform, draft.idMatriz)
    seen = matrices.getMatrix(db, team.owner, active.idMatriz)
    assert seen.cantidadReglas == 1 and not any([seen.permisos.puedeEditar, seen.permisos.puedeActivar,
                                                seen.permisos.puedeVerAuditoria])
    assert seen.creadaPor is None and seen.ultimaModificacion is None
    for action in (matrices.deactivate, matrices.archive, matrices.newVersion, matrices.activate):
        expectError("PERMISO_INSUFICIENTE", action, db, team.owner, active.idMatriz)
    expectError("PERMISO_INSUFICIENTE", matrices.addRule, db, team.owner, active.idMatriz, rule(edadDesde=61, edadHasta=70))
    expectError("MATRIZ_NO_ENCONTRADA", matrices.getMatrix, db, team.operator, active.idMatriz)
    assert reload(db, Matrix, active.idMatriz).estado == "ACTIVA"


# --- Matrices institucionales y permisos --------------------------------------------------------------------


def test_el_propietario_crea_su_matriz_y_el_moderador_edita_el_borrador_y_la_activa(db, mails, team):
    created = newMatrix(db, team.owner, "INSTITUCION", team.id, "Matriz Hospital X")
    assert (created.ambito, created.idInstitucion, created.nombreInstitucion) == ("INSTITUCION", team.id, "Hospital X")
    extra = matrices.addRule(db, team.moderator, created.idMatriz, rule(sexoModelo="MASCULINO"))
    assert extra.cantidadReglas == 2
    rule0 = extra.reglas[0]
    edited = matrices.updateRule(db, team.moderator, created.idMatriz, rule0.idReglaMatriz,
                                 MatrixRuleUpdateRequest(glucosaMaxReferencia="115"))
    assert next(r for r in edited.reglas if r.idReglaMatriz == rule0.idReglaMatriz).glucosaMaxReferencia == Decimal("115")
    active = matrices.activate(db, team.moderator, created.idMatriz)
    assert active.estado == "ACTIVA"
    overview = matrices.institutionOverview(db, team.moderator, team.id)
    assert overview.institucionActiva.idMatriz == created.idMatriz and overview.efectiva.ambito == "INSTITUCION"


def test_un_operador_no_modifica_matrices_solo_consulta_cual_se_aplica(db, mails, team, platform):
    created = newMatrix(db, team.owner, "INSTITUCION", team.id)
    expectError("PERMISO_INSUFICIENTE", matrices.createMatrix, db, team.operator,
                MatrixCreateRequest(ambito="INSTITUCION", idInstitucion=team.id, nombre="Intento"))
    expectError("MATRIZ_NO_ENCONTRADA", matrices.getMatrix, db, team.operator, created.idMatriz)
    expectError("MATRIZ_NO_ENCONTRADA", matrices.updateDraft, db, team.operator, created.idMatriz, MatrixDraftUpdateRequest(nombre="X1"))
    expectError("PERMISO_INSUFICIENTE", matrices.institutionOverview, db, team.operator, team.id)
    assert matrices.effectiveForInstitution(db, team.operator, team.id) is None  # sin global ni propia
    activeMatrix(db, platform)
    assert matrices.effectiveForInstitution(db, team.operator, team.id).ambito == "GLOBAL"


def test_una_institucion_no_ve_ni_modifica_las_matrices_de_otra(db, mails, team, north, platform):
    mine = newMatrix(db, team.owner, "INSTITUCION", team.id, "Matriz Hospital X")
    for actor in (north.owner, north.moderator, north.operator, platform):
        expectError("MATRIZ_NO_ENCONTRADA", matrices.getMatrix, db, actor, mine.idMatriz)
        expectError("MATRIZ_NO_ENCONTRADA", matrices.activate, db, actor, mine.idMatriz)
        expectError("MATRIZ_NO_ENCONTRADA", matrices.addRule, db, actor, mine.idMatriz, rule(edadDesde=70, edadHasta=80))
        expectError("MATRIZ_NO_ENCONTRADA", matrices.auditTrail, db, actor, mine.idMatriz)
    # Tampoco se puede crear una matriz a nombre de otra institución.
    expectError("INSTITUCION_NO_ENCONTRADA", matrices.createMatrix, db, north.owner,
                MatrixCreateRequest(ambito="INSTITUCION", idInstitucion=team.id, nombre="Intrusa"))
    expectError("INSTITUCION_NO_ENCONTRADA", matrices.institutionOverview, db, north.owner, team.id)
    assert reload(db, Matrix, mine.idMatriz).estado == "BORRADOR"


def test_la_plataforma_no_administra_matrices_privadas_de_una_institucion(db, mails, team, platform):
    with pytest.raises(AuthError) as error:
        matrices.createMatrix(db, platform, MatrixCreateRequest(ambito="INSTITUCION", idInstitucion=team.id, nombre="Privada"))
    assert error.value.code in ("INSTITUCION_NO_ENCONTRADA", "PERMISO_INSUFICIENTE")
    assert db.scalar(select(func.count()).select_from(Matrix)) == 0


def test_el_esquema_exige_coherencia_entre_ambito_e_institucion():
    with pytest.raises(ValidationError):
        MatrixCreateRequest(ambito="GLOBAL", idInstitucion=uuid.uuid4(), nombre="Global con institución")
    with pytest.raises(ValidationError):
        MatrixCreateRequest(ambito="INSTITUCION", nombre="Institucional sin institución")


# --- Una sola activa por ámbito --------------------------------------------------------------------------


def test_activar_una_version_desactiva_la_anterior_del_mismo_ambito(db, mails, platform):
    first = activeMatrix(db, platform)
    second = newMatrix(db, platform)
    assert (first.version, second.version) == ("1", "2")
    matrices.activate(db, platform, second.idMatriz)
    db.expire_all()
    assert reload(db, Matrix, first.idMatriz).estado == "INACTIVA" and reload(db, Matrix, second.idMatriz).estado == "ACTIVA"
    actives = db.scalar(select(func.count()).select_from(Matrix).where(Matrix.ambito == "GLOBAL", Matrix.estado == "ACTIVA"))
    assert actives == 1
    # Se puede volver a elegir la versión anterior: intercambian estados.
    matrices.activate(db, platform, first.idMatriz)
    assert reload(db, Matrix, second.idMatriz).estado == "INACTIVA"


def test_la_base_impide_dos_activas_en_el_mismo_ambito(db, mails, team, north, platform):
    activeMatrix(db, platform)
    for ambito, institution in (("GLOBAL", None), ("INSTITUCION", team.id)):
        if ambito == "INSTITUCION":
            activeMatrix(db, team.owner, ambito="INSTITUCION", idInstitucion=team.id)
        duplicate = Matrix(nombre="Duplicada", version="9", ambito=ambito, idInstitucion=institution, estado="ACTIVA",
                           fechaVigenciaDesde=nowForDb().date())
        db.add(duplicate)
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()


def test_dos_instituciones_tienen_cada_una_su_matriz_activa(db, mails, team, north, platform):
    own = activeMatrix(db, team.owner, ambito="INSTITUCION", idInstitucion=team.id, nombre="Hospital X")
    other = activeMatrix(db, north.owner, ambito="INSTITUCION", idInstitucion=north.id, nombre="Hospital X")
    assert own.estado == other.estado == "ACTIVA" and own.idMatriz != other.idMatriz
    assert matrices.institutionOverview(db, team.owner, team.id).institucionActiva.idMatriz == own.idMatriz
    assert matrices.institutionOverview(db, north.owner, north.id).institucionActiva.idMatriz == other.idMatriz
    # Activar otra versión en una no toca la de la otra.
    newer = newMatrix(db, team.owner, "INSTITUCION", team.id, "Hospital X")
    matrices.activate(db, team.owner, newer.idMatriz)
    assert reload(db, Matrix, other.idMatriz).estado == "ACTIVA" and reload(db, Matrix, own.idMatriz).estado == "INACTIVA"


def test_activaciones_simultaneas_dejan_una_sola_activa(engine, db, mails, platform):
    ids = [newMatrix(db, platform, nombre=f"Concurrente {i}").idMatriz for i in range(2)]
    makeSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    barrier = threading.Barrier(2)
    failures = []

    def run(idMatriz):
        session = makeSession()
        try:
            actor = session.get(User, platform.idUsuario)
            barrier.wait()
            matrices.activate(session, actor, idMatriz)
        except AuthError:
            pass
        except Exception as error:  # pragma: no cover - diagnóstico
            failures.append(error)
        finally:
            session.close()

    threads = [threading.Thread(target=run, args=(i,)) for i in ids]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert failures == []
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(Matrix).where(Matrix.ambito == "GLOBAL", Matrix.estado == "ACTIVA")) == 1


# --- Selección de la matriz para las mediciones ---------------------------------------------------------------


def test_una_institucion_sin_matriz_propia_usa_la_global_y_con_matriz_propia_usa_la_suya(db, mails, team, north, platform):
    today = nowForDb().date()
    globalActive = activeMatrix(db, platform)
    assert matrices.resolveMatrix(db, team.id, today).idMatriz == globalActive.idMatriz
    assert matrices.resolveMatrix(db, None, today).idMatriz == globalActive.idMatriz  # individuales
    own = activeMatrix(db, team.owner, ambito="INSTITUCION", idInstitucion=team.id)
    assert matrices.resolveMatrix(db, team.id, today).idMatriz == own.idMatriz
    assert matrices.resolveMatrix(db, north.id, today).idMatriz == globalActive.idMatriz  # nunca la de otra institución
    assert matrices.resolveMatrix(db, None, today).idMatriz == globalActive.idMatriz
    matrices.deactivate(db, team.moderator, own.idMatriz)
    assert matrices.resolveMatrix(db, team.id, today).idMatriz == globalActive.idMatriz  # vuelve a la global


def test_la_medicion_individual_usa_la_global_y_la_institucional_prioriza_la_propia(db, mails, team, platform):
    globalActive = activeMatrix(db, platform)
    consumer = makeUser(db, email="persona@example.com", usuario="persona")
    profileId = measurements.getOwnProfile(db, consumer).idPerfilMedicion
    individual = glucose(db, consumer, profileId, device(db), condicionComida="AYUNO")
    assert (individual.matriz.idMatriz, individual.matriz.ambito) == (globalActive.idMatriz, "GLOBAL")
    assert measurements.matrixPreview(db, consumer, profileId).idMatriz == globalActive.idMatriz

    patient = patients.createPatient(db, team.operator, team.id, patientData(sexoModelo="femenino"))
    dev = device(db, institucion=team.id)
    fallback = glucose(db, team.operator, patient.idPerfilMedicion, dev, condicionComida="AYUNO")
    assert fallback.matriz.idMatriz == globalActive.idMatriz  # sin matriz propia
    measurements.cancelMeasurement(db, team.operator, fallback.idMedicion)
    own = activeMatrix(db, team.owner, ambito="INSTITUCION", idInstitucion=team.id)
    assert measurements.matrixPreview(db, team.operator, patient.idPerfilMedicion).idMatriz == own.idMatriz
    owned = glucose(db, team.operator, patient.idPerfilMedicion, dev, condicionComida="AYUNO")
    assert (owned.matriz.idMatriz, owned.matriz.ambito) == (own.idMatriz, "INSTITUCION")
    assert owned.matriz.version == own.version


def test_si_la_matriz_propia_no_tiene_regla_no_se_cae_a_la_global_ni_se_inventa_un_valor(db, mails, team, platform):
    activeMatrix(db, platform)
    activeMatrix(db, team.owner, ambito="INSTITUCION", idInstitucion=team.id, rules=(rule(sexoModelo="MASCULINO"),))
    patient = patients.createPatient(db, team.operator, team.id, patientData(sexoModelo="femenino"))
    expectError("SIN_REGLA_APLICABLE", glucose, db, team.operator, patient.idPerfilMedicion,
                device(db, institucion=team.id), condicionComida="AYUNO")
    assert db.scalar(select(func.count()).select_from(Measurement)) == 0


def test_el_cliente_no_puede_enviar_un_idmatriz():
    from app.schemas.measurement import MeasurementStart
    with pytest.raises(ValidationError):
        MeasurementStart(idPerfilMedicion=uuid.uuid4(), idDispositivo=uuid.uuid4(), idMatriz=uuid.uuid4())


# --- Versionado e inmutabilidad ----------------------------------------------------------------------------


def test_cambiar_de_version_no_altera_las_mediciones_historicas(db, mails, team):
    v1 = activeMatrix(db, team.owner, ambito="INSTITUCION", idInstitucion=team.id, nombre="Hospital X")
    patient = patients.createPatient(db, team.operator, team.id, patientData(sexoModelo="femenino"))
    dev = device(db, institucion=team.id)
    historic = glucose(db, team.operator, patient.idPerfilMedicion, dev, condicionComida="AYUNO")
    assert historic.matriz.version == "1"

    v2 = matrices.newVersion(db, team.owner, v1.idMatriz)
    assert (v2.version, v2.estado, v2.cantidadReglas) == ("2", "BORRADOR", v1.cantidadReglas)
    matrices.addRule(db, team.owner, v2.idMatriz, rule(sexoModelo="MASCULINO"))
    matrices.activate(db, team.owner, v2.idMatriz)
    db.expire_all()
    assert reload(db, Matrix, v1.idMatriz).estado == "INACTIVA"
    # La medición ya registrada sigue apuntando a la versión 1; la siguiente usa la 2.
    assert measurements.getMeasurement(db, team.operator, historic.idMedicion).matriz.version == "1"
    assert reload(db, Measurement, historic.idMedicion).idMatriz == v1.idMatriz
    measurements.cancelMeasurement(db, team.operator, historic.idMedicion)
    assert glucose(db, team.operator, patient.idPerfilMedicion, dev, condicionComida="AYUNO").matriz.version == "2"
    assert matrices.getMatrix(db, team.owner, v1.idMatriz).medicionesRegistradas == 1


def test_una_version_activada_no_se_edita_y_su_historial_se_conserva(db, mails, team):
    active = activeMatrix(db, team.owner, ambito="INSTITUCION", idInstitucion=team.id)
    ruleId = active.reglas[0].idReglaMatriz
    for fn, args in (
        (matrices.updateDraft, (MatrixDraftUpdateRequest(descripcion="x"),)),
        (matrices.addRule, (rule(edadDesde=70, edadHasta=80),)),
        (matrices.updateRule, (ruleId, MatrixRuleUpdateRequest(edadHasta=70))),
        (matrices.deleteRule, (ruleId,)),
    ):
        expectError("MATRIZ_NO_EDITABLE", fn, db, team.owner, active.idMatriz, *args)
    matrices.deactivate(db, team.owner, active.idMatriz)
    expectError("MATRIZ_NO_EDITABLE", matrices.deleteRule, db, team.owner, active.idMatriz, ruleId)
    assert matrices.getMatrix(db, team.owner, active.idMatriz).cantidadReglas == 1
    expectError("MATRIZ_ESTADO_INVALIDO", matrices.newVersion, db, team.owner, matrices.newVersion(db, team.owner, active.idMatriz).idMatriz)


def test_no_se_archiva_una_activa_y_nada_se_borra(db, mails, team):
    active = activeMatrix(db, team.owner, ambito="INSTITUCION", idInstitucion=team.id)
    expectError("MATRIZ_ESTADO_INVALIDO", matrices.archive, db, team.owner, active.idMatriz)
    matrices.deactivate(db, team.owner, active.idMatriz)
    matrices.archive(db, team.owner, active.idMatriz)
    assert db.scalar(select(func.count()).select_from(Matrix)) == 1
    assert db.scalar(select(func.count()).select_from(MatrixRule)) == 1


# --- Reglas ---------------------------------------------------------------------------------------------


def test_se_puede_agregar_una_regla_para_sexo_y_comida_no_informados(db, mails):
    # La base admite NO_INFORMADO como sexo de una regla; antes el esquema de entrada lo rechazaba y el formulario no hacía nada.
    actor = makeUser(db, tipoCuenta="MODERADOR_PLATAFORMA", email="p@example.com", usuario="plataforma")
    created = newMatrix(db, actor)
    detail = matrices.addRule(db, actor, created.idMatriz, rule(sexoModelo="no_informado", condicionComida="NO_INFORMADA",
                                                                edadDesde=1, edadHasta=90, glucosaMinReferencia="87",
                                                                glucosaMaxReferencia="112"))
    assert detail.cantidadReglas == 2
    assert any(r.sexoModelo == "NO_INFORMADO" and r.condicionComida == "NO_INFORMADA" for r in detail.reglas)


def test_validaciones_de_rangos_de_una_regla():
    for bad in ({"edadDesde": 50, "edadHasta": 40}, {"minutosComidaMin": 120, "minutosComidaMax": 30},
                {"glucosaMinReferencia": "150", "glucosaMaxReferencia": "100"}, {"edadHasta": 200},
                {"glucosaMinReferencia": "-1"}, {"condicionComida": "CENA"}, {"sexoModelo": "OTRO"}):
        with pytest.raises(ValidationError):
            rule(**bad)
    assert rule(minutosComidaMin="", minutosComidaMax="").minutosComidaMin is None


def test_no_se_permiten_reglas_duplicadas_ni_solapadas(db, mails, team):
    created = newMatrix(db, team.owner, "INSTITUCION", team.id)
    expectError("REGLA_DUPLICADA", matrices.addRule, db, team.owner, created.idMatriz, rule())
    expectError("REGLA_SOLAPADA", matrices.addRule, db, team.owner, created.idMatriz, rule(edadDesde=50, edadHasta=70))
    expectError("REGLA_SOLAPADA", matrices.addRule, db, team.owner, created.idMatriz, rule(edadDesde=0, edadHasta=18))
    # Cambian el sexo, la condición o las edades sin tocarse: son reglas distintas.
    for other in (rule(sexoModelo="MASCULINO"), rule(condicionComida="NO_INFORMADA"), rule(edadDesde=61, edadHasta=90)):
        matrices.addRule(db, team.owner, created.idMatriz, other)
    # Postprandial: los tiempos desde la comida también deben ser disjuntos.
    post = {"condicionComida": "POSTPRANDIAL"}
    matrices.addRule(db, team.owner, created.idMatriz, rule(minutosComidaMin=0, minutosComidaMax=59, **post))
    matrices.addRule(db, team.owner, created.idMatriz, rule(minutosComidaMin=60, minutosComidaMax=180, **post))
    expectError("REGLA_SOLAPADA", matrices.addRule, db, team.owner, created.idMatriz,
                rule(minutosComidaMin=100, minutosComidaMax=200, **post))
    expectError("REGLA_SOLAPADA", matrices.addRule, db, team.owner, created.idMatriz, rule(**post))  # sin tope: abarca todo
    assert matrices.getMatrix(db, team.owner, created.idMatriz).cantidadReglas == 6
    assert matrices.validateMatrix(db, team.owner, created.idMatriz).valida


def test_editar_una_regla_revalida_los_solapamientos(db, mails, team):
    created = newMatrix(db, team.owner, "INSTITUCION", team.id, rules=(rule(edadDesde=0, edadHasta=17), rule()))
    second = next(r for r in created.reglas if r.edadDesde == 18)
    expectError("REGLA_SOLAPADA", matrices.updateRule, db, team.owner, created.idMatriz, second.idReglaMatriz,
                MatrixRuleUpdateRequest(edadDesde=10))
    expectError("REGLA_INCOHERENTE", matrices.updateRule, db, team.owner, created.idMatriz, second.idReglaMatriz,
                MatrixRuleUpdateRequest(edadDesde=90))
    ok = matrices.updateRule(db, team.owner, created.idMatriz, second.idReglaMatriz, MatrixRuleUpdateRequest(edadDesde=20))
    assert next(r for r in ok.reglas if r.idReglaMatriz == second.idReglaMatriz).edadDesde == 20
    expectError("REGLA_NO_ENCONTRADA", matrices.deleteRule, db, team.owner, created.idMatriz, uuid.uuid4())
    assert matrices.deleteRule(db, team.owner, created.idMatriz, second.idReglaMatriz).cantidadReglas == 1


def test_no_se_activa_una_matriz_invalida_o_fuera_de_vigencia(db, mails, team):
    empty = newMatrix(db, team.owner, "INSTITUCION", team.id, "Vacía", rules=())
    expectError("SIN_REGLAS", matrices.activate, db, team.owner, empty.idMatriz)
    assert not matrices.validateMatrix(db, team.owner, empty.idMatriz).valida
    # Un solapamiento que llegó por otra vía (carga directa) también frena la activación.
    created = newMatrix(db, team.owner, "INSTITUCION", team.id, "Rota")
    db.add(MatrixRule(idMatriz=created.idMatriz, codigoRegla="X", sexoModelo="FEMENINO", edadDesde=30, edadHasta=40,
                      condicionComida="AYUNO", glucosaMinReferencia=70, glucosaMaxReferencia=110))
    db.commit()
    expectError("REGLA_SOLAPADA", matrices.activate, db, team.owner, created.idMatriz)
    report = matrices.validateMatrix(db, team.owner, created.idMatriz)
    assert not report.valida and report.problemas[0].codigo == "REGLA_SOLAPADA"
    future = matrices.createMatrix(db, team.owner, MatrixCreateRequest(
        ambito="INSTITUCION", idInstitucion=team.id, nombre="Futura", fechaVigenciaDesde=nowForDb().date().replace(year=2099)))
    matrices.addRule(db, team.owner, future.idMatriz, rule())
    expectError("MATRIZ_FUERA_DE_VIGENCIA", matrices.activate, db, team.owner, future.idMatriz)
    assert db.scalar(select(func.count()).select_from(Matrix).where(Matrix.estado == "ACTIVA")) == 0


# --- Institución cerrada ----------------------------------------------------------------------------------


def test_una_institucion_cerrada_no_modifica_sus_matrices(db, mails, team):
    draft = newMatrix(db, team.owner, "INSTITUCION", team.id)
    institution = db.get(Institution, team.id)
    institution.estado = "CERRADA"
    db.commit()
    for fn, args in ((matrices.activate, ()), (matrices.addRule, (rule(edadDesde=70, edadHasta=80),)),
                     (matrices.updateDraft, (MatrixDraftUpdateRequest(descripcion="x"),))):
        expectError("MATRIZ_NO_ENCONTRADA", fn, db, team.owner, draft.idMatriz, *args)
    expectError("INSTITUCION_NO_ENCONTRADA", matrices.createMatrix, db, team.owner,
                MatrixCreateRequest(ambito="INSTITUCION", idInstitucion=team.id, nombre="Nueva"))
    assert reload(db, Matrix, draft.idMatriz).estado == "BORRADOR"  # nada se perdió


# --- Auditoría ----------------------------------------------------------------------------------------------


def test_la_auditoria_institucional_solo_la_consulta_el_propietario(db, mails, team, north, platform):
    created = newMatrix(db, team.moderator, "INSTITUCION", team.id)  # el moderador modifica
    matrices.activate(db, team.moderator, created.idMatriz)
    trail = matrices.auditTrail(db, team.owner, created.idMatriz)
    actions = {entry.accion for entry in trail}
    assert {"CREAR_MATRIZ", "CREAR_REGLA_MATRIZ", "ACTIVAR_MATRIZ"} <= actions
    assert all(entry.resultado == "EXITO" and entry.usuario for entry in trail)
    for actor in (team.moderator, team.operator):
        with pytest.raises(AuthError) as error:
            matrices.auditTrail(db, actor, created.idMatriz)
        assert error.value.code in ("PERMISO_INSUFICIENTE", "MATRIZ_NO_ENCONTRADA")
    for actor in (north.owner, platform):
        expectError("MATRIZ_NO_ENCONTRADA", matrices.auditTrail, db, actor, created.idMatriz)
    # El propietario ve quién modificó; el moderador, aunque administre la matriz, no accede a esa información.
    assert matrices.getMatrix(db, team.owner, created.idMatriz).ultimaModificacion.por
    assert matrices.getMatrix(db, team.moderator, created.idMatriz).ultimaModificacion is None
    assert matrices.getMatrix(db, team.moderator, created.idMatriz).permisos.puedeVerAuditoria is False


def test_la_auditoria_global_queda_separada_de_la_institucional(db, mails, team, platform):
    globalMatrix = activeMatrix(db, platform)
    mine = activeMatrix(db, team.owner, ambito="INSTITUCION", idInstitucion=team.id)
    admin = makeUser(db, tipoCuenta="ADMINISTRADOR_PLATAFORMA", email="admin@example.com", usuario="admin")
    globalTrail = matrices.auditTrail(db, admin, globalMatrix.idMatriz)
    assert globalTrail and all(entry.usuario for entry in globalTrail)
    expectError("PERMISO_INSUFICIENTE", matrices.auditTrail, db, platform, globalMatrix.idMatriz)  # moderación: sin acceso
    expectError("MATRIZ_NO_ENCONTRADA", matrices.auditTrail, db, admin, mine.idMatriz)
    expectError("PERMISO_INSUFICIENTE", matrices.auditTrail, db, team.owner, globalMatrix.idMatriz)
    # Las entradas institucionales llevan la institución como dato relacionado; las globales, ninguna.
    assert {a.idRelacionado for a in audits(db, "CREAR_MATRIZ") if a.idRegistro == mine.idMatriz} == {team.id}
    assert {a.idRelacionado for a in audits(db, "CREAR_MATRIZ") if a.idRegistro == globalMatrix.idMatriz} == {None}


def test_un_intento_sin_permiso_queda_auditado_como_fallo(db, mails, team, platform):
    active = activeMatrix(db, platform)
    expectError("PERMISO_INSUFICIENTE", matrices.deactivate, db, team.owner, active.idMatriz)
    failed = [a for a in audits(db, "DESACTIVAR_MATRIZ") if a.resultado == "FALLO"]
    assert len(failed) == 1 and failed[0].idUsuario == team.owner.idUsuario
