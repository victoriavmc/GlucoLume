# Auditoría institucional y datos de personal suprimidos por el plazo de conservación (fechaMinimizacionDatos).
#
#     python -m pytest tests/test_audit_minimized_names.py -v
#
# Hallazgo (candidato menor de la auditoría Cloudflare): la minimización borra nombre/legajo/matrícula del vínculo, pero cada evento guarda en
# `detalle` el nombre de las personas y del actor AL MOMENTO de la operación; la auditoría del propietario lo seguía mostrando.

import json

from app.models.institutionUser import InstitutionUser
from app.services import auditQuery
from app.services import institutionPatients as patients
from app.utils.timeZone import nowForDb
from tests.test_account_deletion import audits, db, engine, mails, makeUser, reload  # noqa: F401 - fixtures
from tests.test_audit_names import named
from tests.test_institution_patients import patientData
from tests.test_institutions import freshLookupLimiter, institutional, relationOf, team  # noqa: F401


def everything(db, team, action):
    items = auditQuery.listInstitution(db, team.owner, team.id, accion=action, tamanioPagina=100).items
    details = [auditQuery.detailInstitution(db, team.owner, team.id, i.idAuditoria) for i in items]
    return json.dumps([[i.model_dump(mode="json") for i in items], [d.model_dump(mode="json") for d in details]], default=str, ensure_ascii=False)


def test_el_nombre_guardado_en_el_evento_deja_de_mostrarse_cuando_el_personal_fue_minimizado(db, mails, team):
    named(db, team.operator, "Juan", "Pérez")
    patients.createPatient(db, team.operator, team.id, patientData())
    assert "Juan Pérez" in everything(db, team, "CREAR_PACIENTE"), "antes de la minimización el nombre del evento sí se ve"

    relation = relationOf(db, team, team.operator)
    relation.fechaMinimizacionDatos = nowForDb()  # vencido el plazo de conservación (personnelRetention.minimizeExpired)
    relation.nombreProfesionalHistorico = relation.apellidoProfesionalHistorico = None
    db.commit()
    reload(db, InstitutionUser, relation.idInstitucionUsuario)

    after = everything(db, team, "CREAR_PACIENTE")
    assert "Juan" not in after and "Pérez" not in after, "ni el actor ni el responsable del evento se nombran tras la minimización"
    assert auditQuery.listInstitution(db, team.owner, team.id, accion="CREAR_PACIENTE").items[0].usuario  # el evento sigue existiendo
