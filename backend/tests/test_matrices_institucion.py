# Matrices institucionales: la matriz global es consultable (con todas sus reglas, también las de «edad no especificada») y de solo
# lectura para la institución; alta de una matriz con sus reglas (todo o nada) sin activarla; revisión previa con advertencias de
# cobertura; activar, volver a la global sin borrar versiones y mediciones históricas intactas.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_matrices_institucion.py -v

from decimal import Decimal

from sqlalchemy import func, select

from app.models.matrix import Matrix
from app.models.matrixRule import MatrixRule
from app.models.measurement import Measurement
from app.schemas.matrix import MatrixCreateRequest
from app.services import institutionPatients as patients
from app.services import matrix as matrices
from tests.test_account_deletion import audits, db, engine, mails, makeUser, reload  # noqa: F401 - fixtures
from tests.test_audit import api  # noqa: F401 - fixture
from tests.test_institution_patients import patientData
from tests.test_institutions import expectError, freshLookupLimiter, institutional, relationOf, team  # noqa: F401
from tests.test_matrices import activeMatrix, newMatrix, north, platform, rule  # noqa: F401 - fixtures y ayudas
from tests.test_measurements import device, glucose


def countMatrices(db, institution=None):
    query = select(func.count()).select_from(Matrix)
    return db.scalar(query.where(Matrix.idInstitucion == institution) if institution else query)


def globalWithGeneralRules(db, platform):
    """Global activa con reglas por edad y reglas de «edad no especificada» (NULL), como la matriz real de GlucoLume."""
    active = activeMatrix(db, platform)
    for sexo in ("FEMENINO", "MASCULINO"):
        db.add(MatrixRule(idMatriz=active.idMatriz, codigoRegla=f"{sexo[0]}_N_U", sexoModelo=sexo, edadDesde=None, edadHasta=None,
                          condicionComida="NO_INFORMADA", glucosaMinReferencia=Decimal("70"), glucosaMaxReferencia=Decimal("180")))
    db.commit()
    return matrices.getMatrix(db, platform, active.idMatriz)


# --- La matriz global se consulta desde la institución --------------------------------------------------------------


def test_la_institucion_sin_matriz_propia_ve_la_global_activa_con_todas_sus_reglas(db, mails, team, platform):
    seeded = globalWithGeneralRules(db, platform)
    overview = matrices.institutionOverview(db, team.owner, team.id)
    assert overview.institucionActiva is None and overview.versiones == []
    assert overview.efectiva.ambito == "GLOBAL" and overview.efectiva.idMatriz == seeded.idMatriz
    for viewer in (team.owner, team.moderator):
        detail = matrices.getMatrix(db, viewer, overview.efectiva.idMatriz)
        assert detail.cantidadReglas == 3 and len(detail.reglas) == 3
        general = [r for r in detail.reglas if r.edadDesde is None]
        assert len(general) == 2 and all(r.edadHasta is None for r in general)  # «edad no especificada», no un rango
        assert detail.descripcion == seeded.descripcion and detail.fechaCreacion is not None


def test_la_matriz_global_es_de_solo_lectura_para_la_institucion(db, mails, team, platform):
    seeded = globalWithGeneralRules(db, platform)
    seen = matrices.getMatrix(db, team.owner, seeded.idMatriz)
    assert not any([seen.permisos.puedeEditar, seen.permisos.puedeActivar, seen.permisos.puedeDesactivar,
                    seen.permisos.puedeArchivar, seen.permisos.puedeCrearVersion])
    for actor in (team.owner, team.moderator):
        expectError("PERMISO_INSUFICIENTE", matrices.addRule, db, actor, seeded.idMatriz, rule(edadDesde=61, edadHasta=70))
        expectError("PERMISO_INSUFICIENTE", matrices.deactivate, db, actor, seeded.idMatriz)
    expectError("MATRIZ_NO_ENCONTRADA", matrices.getMatrix, db, team.operator, seeded.idMatriz)  # el operador no consulta reglas
    assert db.scalar(select(func.count()).select_from(MatrixRule).where(MatrixRule.idMatriz == seeded.idMatriz)) == 3


def test_validar_y_revisar_una_matriz_con_reglas_de_edad_no_especificada_no_falla(db, mails, platform):
    seeded = globalWithGeneralRules(db, platform)
    assert matrices.validateMatrix(db, platform, seeded.idMatriz).valida
    # Las «generales» (sin edad) no se pisan con las que tienen rango, pero dos generales iguales sí son duplicadas.
    db.add(MatrixRule(idMatriz=seeded.idMatriz, codigoRegla="X_DUP", sexoModelo="FEMENINO", edadDesde=None, edadHasta=None,
                      condicionComida="NO_INFORMADA", glucosaMinReferencia=Decimal("60"), glucosaMaxReferencia=Decimal("100")))
    db.commit()
    assert [p.codigo for p in matrices.validateMatrix(db, platform, seeded.idMatriz).problemas] == ["REGLA_DUPLICADA"]


# --- Alta con reglas, sin activar ------------------------------------------------------------------------------------


def test_se_crea_una_matriz_institucional_con_sus_reglas_en_borrador_sin_reemplazar_a_la_global(db, mails, team, platform):
    seeded = globalWithGeneralRules(db, platform)
    created = matrices.createMatrix(db, team.moderator, MatrixCreateRequest(
        ambito="INSTITUCION", idInstitucion=team.id, nombre="Hospital X", descripcion="Rangos del servicio",
        reglas=[rule(), rule(sexoModelo="MASCULINO"), rule(edadDesde=61, edadHasta=90)]))
    assert (created.estado, created.version, created.cantidadReglas, created.ambito) == ("BORRADOR", "1", 3, "INSTITUCION")
    assert [r.codigoRegla for r in created.reglas] == ["R-001", "R-002", "R-003"]
    # Guardar no activa: la global sigue siendo la que se usa.
    overview = matrices.institutionOverview(db, team.owner, team.id)
    assert overview.institucionActiva is None and overview.efectiva.idMatriz == seeded.idMatriz
    assert [v.idMatriz for v in overview.versiones] == [created.idMatriz]
    assert overview.versiones[0].descripcion == "Rangos del servicio" and overview.versiones[0].cantidadReglas == 3


def test_el_alta_es_todo_o_nada_si_una_regla_es_duplicada_o_se_solapa(db, mails, team):
    before = countMatrices(db), db.scalar(select(func.count()).select_from(MatrixRule))
    for bad, code in (([rule(), rule()], "REGLA_DUPLICADA"), ([rule(), rule(edadDesde=50, edadHasta=70)], "REGLA_SOLAPADA")):
        expectError(code, matrices.createMatrix, db, team.owner,
                    MatrixCreateRequest(ambito="INSTITUCION", idInstitucion=team.id, nombre="Mala", reglas=bad))
    assert (countMatrices(db), db.scalar(select(func.count()).select_from(MatrixRule))) == before


def test_solo_el_equipo_de_la_institucion_crea_matrices_con_reglas(db, mails, team, north):
    request = MatrixCreateRequest(ambito="INSTITUCION", idInstitucion=team.id, nombre="Hospital X", reglas=[rule()])
    expectError("PERMISO_INSUFICIENTE", matrices.createMatrix, db, team.operator, request)
    expectError("INSTITUCION_NO_ENCONTRADA", matrices.createMatrix, db, north.owner, request)
    assert countMatrices(db, team.id) == 0


# --- Revisión previa y advertencias ----------------------------------------------------------------------------------


def test_la_revision_previa_informa_problemas_y_huecos_sin_guardar_nada(db, mails, team):
    before = countMatrices(db)
    result = matrices.checkRules(db, team.owner, [rule(), rule(edadDesde=70, edadHasta=90), rule(sexoModelo="FEMENINO", edadDesde=20, edadHasta=30)])
    assert not result.valida and [p.codigo for p in result.problemas] == ["REGLA_SOLAPADA"]
    assert "Regla 3" in result.problemas[0].mensaje and "Regla 1" in result.problemas[0].mensaje
    messages = " ".join(w.mensaje for w in result.advertencias)
    assert "edades de 61 a 69" in messages and "masculino" in messages  # hueco entre 18-60 y 70-90; sin reglas masculinas
    assert matrices.checkRules(db, team.owner, []).problemas[0].codigo == "SIN_REGLAS"
    ok = matrices.checkRules(db, team.moderator, [rule(), rule(sexoModelo="MASCULINO")])
    assert ok.valida and ok.advertencias == []
    assert countMatrices(db) == before


def test_la_revision_previa_exige_ser_del_equipo(db, mails, team):
    expectError("PERMISO_INSUFICIENTE", matrices.checkRules, db, team.operator, [rule()])
    stranger = institutional(db, "ajena-matriz@example.com", "ajenamatriz")
    expectError("PERMISO_INSUFICIENTE", matrices.checkRules, db, stranger, [rule()])


# --- Activar, volver a la global y conservar versiones ---------------------------------------------------------------


def test_activar_una_institucional_y_volver_a_la_global_conserva_todas_las_versiones(db, mails, team, platform):
    seeded = globalWithGeneralRules(db, platform)
    v1 = matrices.createMatrix(db, team.owner, MatrixCreateRequest(ambito="INSTITUCION", idInstitucion=team.id, nombre="Hospital X", reglas=[rule()]))
    matrices.activate(db, team.owner, v1.idMatriz)
    v2 = matrices.newVersion(db, team.owner, v1.idMatriz)
    matrices.addRule(db, team.owner, v2.idMatriz, rule(sexoModelo="MASCULINO"))
    matrices.activate(db, team.moderator, v2.idMatriz)
    db.expire_all()
    overview = matrices.institutionOverview(db, team.owner, team.id)
    assert overview.institucionActiva.idMatriz == v2.idMatriz and overview.efectiva.idMatriz == v2.idMatriz
    states = {v.version: v.estado for v in overview.versiones}
    assert states == {"1": "INACTIVA", "2": "ACTIVA"}  # la anterior queda como versión histórica; una sola activa
    assert db.scalar(select(func.count()).select_from(Matrix).where(Matrix.idInstitucion == team.id, Matrix.estado == "ACTIVA")) == 1

    # «Utilizar matriz global» = desactivar la institucional vigente: no se borra nada.
    back = matrices.deactivate(db, team.owner, v2.idMatriz)
    assert back.estado == "INACTIVA" and back.cantidadReglas == 2
    overview = matrices.institutionOverview(db, team.owner, team.id)
    assert overview.institucionActiva is None and overview.efectiva.idMatriz == seeded.idMatriz
    assert len(overview.versiones) == 2 and countMatrices(db, team.id) == 2
    assert reload(db, Matrix, seeded.idMatriz).estado == "ACTIVA"
    # Y se puede volver a una versión institucional guardada.
    assert matrices.activate(db, team.owner, v1.idMatriz).estado == "ACTIVA"


def test_el_moderador_no_activa_ni_desactiva_la_matriz_de_otra_institucion(db, mails, team, north, platform):
    created = matrices.createMatrix(db, team.owner, MatrixCreateRequest(ambito="INSTITUCION", idInstitucion=team.id, nombre="Hospital X", reglas=[rule()]))
    expectError("MATRIZ_NO_ENCONTRADA", matrices.activate, db, north.owner, created.idMatriz)
    expectError("MATRIZ_NO_ENCONTRADA", matrices.deactivate, db, north.moderator, created.idMatriz)


def test_cambiar_a_la_global_no_modifica_las_mediciones_historicas(db, mails, team, platform):
    globalActive = activeMatrix(db, platform)
    v1 = matrices.createMatrix(db, team.owner, MatrixCreateRequest(ambito="INSTITUCION", idInstitucion=team.id, nombre="Hospital X", reglas=[rule()]))
    matrices.activate(db, team.owner, v1.idMatriz)
    patient = patients.createPatient(db, team.operator, team.id, patientData(sexoModelo="femenino"))
    dev = device(db, institucion=team.id)
    historic = glucose(db, team.operator, patient.idPerfilMedicion, dev, condicionComida="AYUNO")
    stored = reload(db, Measurement, historic.idMedicion)
    snapshot = (stored.idMatriz, stored.glucosaEstimada, stored.edadAlMomento, stored.condicionComida)
    assert stored.idMatriz == v1.idMatriz

    matrices.deactivate(db, team.owner, v1.idMatriz)  # Utilizar matriz global
    db.expire_all()
    again = reload(db, Measurement, historic.idMedicion)
    assert (again.idMatriz, again.glucosaEstimada, again.edadAlMomento, again.condicionComida) == snapshot
    assert matrices.getMatrix(db, team.owner, v1.idMatriz).medicionesRegistradas == 1
    assert matrices.institutionOverview(db, team.owner, team.id).efectiva.idMatriz == globalActive.idMatriz


# --- HTTP --------------------------------------------------------------------------------------------------------------


def test_http_revision_alta_con_reglas_y_permisos(db, mails, team, platform, api):
    body = {"ambito": "INSTITUCION", "idInstitucion": str(team.id), "nombre": "Hospital X",
            "reglas": [{"sexoModelo": "FEMENINO", "edadDesde": 18, "edadHasta": 60, "condicionComida": "AYUNO",
                        "glucosaMinReferencia": "70", "glucosaMaxReferencia": "110"}]}
    checked = api(team.moderator).post("/api/v1/matrices/check-rules", json={"reglas": body["reglas"]})
    assert checked.status_code == 200 and checked.json()["valida"] is True and checked.json()["advertencias"]
    overlap = {"reglas": body["reglas"] + [{**body["reglas"][0], "edadDesde": 30, "edadHasta": 40}]}
    assert api(team.owner).post("/api/v1/matrices/check-rules", json=overlap).json()["problemas"][0]["codigo"] == "REGLA_SOLAPADA"
    assert api(team.operator).post("/api/v1/matrices/check-rules", json=overlap).status_code == 403
    created = api(team.owner).post("/api/v1/matrices", json=body)
    assert created.status_code == 201 and created.json()["estado"] == "BORRADOR" and len(created.json()["reglas"]) == 1
    assert api(team.operator).post("/api/v1/matrices", json=body).status_code == 403
    bad = api(team.owner).post("/api/v1/matrices", json={**body, "nombre": "Otra", "reglas": overlap["reglas"]})
    assert bad.status_code in (409, 422) and "solapa" in bad.text.lower()
    assert countMatrices(db, team.id) == 1
