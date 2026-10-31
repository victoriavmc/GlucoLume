# Pruebas de la marca «analizado» de los eventos de auditoría (services/auditQuery.setGlobalReview, PUT /audit/events/{id}/review).
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_audit_review.py -v
#
# La marca vive en AuditoriaRevision: el evento y su registro original no cambian. Solo el administrador de la plataforma la pone o la quita,
# y cada cambio queda en la auditoría (MARCAR_EVENTO_REVISADO).
import uuid

import pytest
from sqlalchemy import select

from app.core.exceptions import AuthError
from app.models.audit import Audit
from app.models.auditReview import AuditReview
from app.services import audit as auditService
from app.services import auditQuery
from tests.test_account_deletion import audits, db, engine, mails, makeUser  # noqa: F401 - fixtures
from tests.test_audit import admin, api  # noqa: F401 - fixtures
from tests.test_institutions import team  # noqa: F401 - fixtures


@pytest.fixture
def event(db, admin):
    """Un evento cualquiera de la auditoría general (y su registro tal como quedó)."""
    auditService.registerEvent(db, "CRUD", "PRUEBA_REVISION", True, admin.idUsuario, "Usuario", admin.idUsuario,
                               observacion="Evento de prueba")
    db.commit()
    return db.scalar(select(Audit).where(Audit.accion == "PRUEBA_REVISION"))


def record(db, idAuditoria) -> tuple:
    db.expire_all()
    audit = db.get(Audit, idAuditoria)
    return audit.accion, audit.resultado, audit.observacion, audit.datosNuevos, audit.fechaHora


def revisionOf(db, admin, idAuditoria):
    page = auditQuery.listGlobal(db, admin, tamanioPagina=100)
    return next(item.revision for item in page.items if item.idAuditoria == idAuditoria)


def test_marcar_y_desmarcar_no_cambia_el_evento(db, mails, admin, event):
    before = record(db, event.idAuditoria)

    marked = auditQuery.setGlobalReview(db, admin, event.idAuditoria, True)
    assert marked.revisado and marked.fechaRevision is not None and marked.revisor
    assert revisionOf(db, admin, event.idAuditoria).revisado is True
    assert record(db, event.idAuditoria) == before

    cleared = auditQuery.setGlobalReview(db, admin, event.idAuditoria, False)
    assert cleared.revisado is False and cleared.fechaRevision is None
    assert db.get(AuditReview, event.idAuditoria) is None
    assert revisionOf(db, admin, event.idAuditoria).revisado is False
    assert record(db, event.idAuditoria) == before


def test_cada_cambio_queda_en_la_auditoria_y_marcar_dos_veces_no_duplica(db, mails, admin, event):
    auditQuery.setGlobalReview(db, admin, event.idAuditoria, True)
    first = db.get(AuditReview, event.idAuditoria).fechaRevision
    auditQuery.setGlobalReview(db, admin, event.idAuditoria, True)  # ya estaba marcado: no cambia quién ni cuándo
    db.expire_all()
    assert db.get(AuditReview, event.idAuditoria).fechaRevision == first
    assert len(audits(db, "MARCAR_EVENTO_REVISADO")) == 1

    auditQuery.setGlobalReview(db, admin, event.idAuditoria, False)
    assert [a.datosNuevos for a in audits(db, "MARCAR_EVENTO_REVISADO")] == ['{"revisado": true}', '{"revisado": false}']


def test_la_marca_no_aparece_en_la_auditoria_institucional(db, mails, team, admin, event):
    auditQuery.setGlobalReview(db, admin, event.idAuditoria, True)
    page = auditQuery.listInstitution(db, team.owner, team.id, tamanioPagina=100)
    assert page.items and all(item.revision is None for item in page.items)
    assert auditQuery.detailInstitution(db, team.owner, team.id, event.idAuditoria) if event.idInstitucion == team.id else True


def test_solo_el_administrador_puede_marcar(db, mails, team, admin, event):
    with pytest.raises(AuthError):
        auditQuery.setGlobalReview(db, team.owner, event.idAuditoria, True)
    with pytest.raises(AuthError):
        auditQuery.setGlobalReview(db, team.moderator, event.idAuditoria, True)
    db.expire_all()
    assert db.get(AuditReview, event.idAuditoria) is None


def test_un_evento_inexistente_no_se_puede_marcar(db, mails, admin):
    with pytest.raises(AuthError) as error:
        auditQuery.setGlobalReview(db, admin, uuid.uuid4(), True)
    assert error.value.code == "EVENTO_NO_ENCONTRADO"


def test_sin_la_tabla_la_auditoria_sigue_sin_marca_y_no_se_puede_marcar(db, mails, admin, event, monkeypatch):
    monkeypatch.setattr(auditQuery.schemaCompat, "auditReviewReady", lambda _db: False)
    assert revisionOf(db, admin, event.idAuditoria) is None
    with pytest.raises(AuthError) as error:
        auditQuery.setGlobalReview(db, admin, event.idAuditoria, True)
    assert error.value.code == "ESQUEMA_DESACTUALIZADO"


def test_codigos_http_de_la_marca(db, mails, team, admin, event, api):
    path = f"/api/v1/audit/events/{event.idAuditoria}/review"
    marked = api(admin).put(path, json={"revisado": True})
    assert marked.status_code == 200 and marked.json()["revisado"] is True
    assert api(admin).get(f"/api/v1/audit/events/{event.idAuditoria}").json()["revision"]["revisado"] is True
    assert api(team.owner).put(path, json={"revisado": False}).status_code == 403
    assert api(admin).put(path, json={"revisado": "quizas"}).status_code == 422
    assert api(admin).put(f"/api/v1/audit/events/{uuid.uuid4()}/review", json={"revisado": True}).status_code == 404
    assert api(admin).put(path, json={"revisado": False}).json()["revisado"] is False
