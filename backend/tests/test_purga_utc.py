# Purga por antigüedad de la auditoría (AUDIT_RETENTION_MONTHS): el corte se compara contra fechas UTC almacenadas. Hallazgo independiente
# del vencimiento de IP: antes, el corte se calculaba con la hora de Argentina y la purga llegaba 3 horas tarde.
from datetime import datetime

from app.models.audit import Audit
from app.models.auditContext import AuditContext
from app.services import auditRetention
from tests.test_account_deletion import db, engine, mails  # noqa: F401 - fixtures


def test_la_purga_mensual_vence_al_instante_utc_y_no_3_horas_despues(db, mails):
    stored = datetime(2026, 1, 15, 12, 0, 0)  # instante UTC guardado por la base
    row = Audit(tipoEvento="LOGIN", accion="LOGIN_LOCAL", resultado="FALLO", fechaHora=stored, modulo="AUTENTICACION")
    db.add(row)
    db.flush()
    db.add(AuditContext(idAuditoria=row.idAuditoria, ipOrigen="203.0.113.7", agenteUsuario="prueba"))
    db.commit()
    # Un mes después en UTC es 15/02 12:00 UTC = 15/02 09:00 en Argentina.
    assert auditRetention._cutoffUtc(datetime(2026, 2, 15, 8, 59, 59), 1) < stored  # todavía no vence
    assert auditRetention.purgeAll(db, datetime(2026, 2, 15, 8, 59, 59), 1) == 0
    # La purga borra los eventos ESTRICTAMENTE anteriores al corte (la anulación de IP usa «días cumplidos»): en el instante exacto no borra.
    assert auditRetention.purgeAll(db, datetime(2026, 2, 15, 9, 0, 0), 1) == 0
    assert auditRetention.purgeAll(db, datetime(2026, 2, 15, 9, 0, 1), 1) == 1
