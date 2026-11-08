# Purga por antigüedad de la auditoría (AUDIT_RETENTION_MONTHS). La aplicación escribe Auditoria.fechaHora en HORA DE ARGENTINA (hook
# before_flush de app/db/base.py), y el corte de la purga se compara en esa misma escala. Antes se restaba en UTC y la purga llegaba
# 3 horas antes de lo previsto para los eventos de la aplicación (auditoría del 08/11/2026, punto 1 de la retención).
from datetime import datetime, timedelta

from app.models.audit import Audit
from app.models.auditContext import AuditContext
from app.services import auditRetention
from app.utils.timeZone import nowForDb
from tests.test_account_deletion import db, engine, mails  # noqa: F401 - fixtures


def test_un_evento_escrito_por_la_aplicacion_se_guarda_en_hora_argentina(db, mails):
    row = Audit(tipoEvento="LOGIN", accion="LOGIN_LOCAL", resultado="FALLO", modulo="AUTENTICACION")  # sin fechaHora: la completa la app
    db.add(row)
    db.commit()
    db.refresh(row)
    assert abs(row.fechaHora - nowForDb()) < timedelta(minutes=1)  # hora de Argentina, no UTC


def test_la_purga_mensual_vence_al_instante_que_guarda_la_aplicacion(db, mails):
    stored = datetime(2026, 1, 15, 9, 0, 0)  # hora de Argentina como la escribe la aplicación (equivale a 12:00 UTC)
    row = Audit(tipoEvento="LOGIN", accion="LOGIN_LOCAL", resultado="FALLO", fechaHora=stored, modulo="AUTENTICACION")
    db.add(row)
    db.flush()
    db.add(AuditContext(idAuditoria=row.idAuditoria, ipOrigen="203.0.113.7", agenteUsuario="prueba"))
    db.commit()
    # Un mes después, en hora de Argentina, es 15/02 09:00:00.
    assert auditRetention._cutoffUtc(datetime(2026, 2, 15, 8, 59, 59), 1) < stored  # todavía no vence
    assert auditRetention.purgeAll(db, datetime(2026, 2, 15, 8, 59, 59), 1) == 0
    # La purga borra los eventos ESTRICTAMENTE anteriores al corte: en el instante exacto no borra.
    assert auditRetention.purgeAll(db, datetime(2026, 2, 15, 9, 0, 0), 1) == 0
    assert auditRetention.purgeAll(db, datetime(2026, 2, 15, 9, 0, 1), 1) == 1
