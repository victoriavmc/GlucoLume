import os
import sys, uuid
sys.path.insert(0, os.environ["BACKEND_DIR"])
import hostenv  # noqa
from sqlalchemy import select
from app.core import security
from app.db.session import getSessionFactory
from app.models.localCredential import LocalCredential
from app.models.user import User
from app.models.consent import TipoConsentimiento
from app.services import consent as consentService
PW = "Glucolume#Prueba2026"
with getSessionFactory()() as db:
    if not db.scalar(select(User).where(User.usuario == "carla")):
        db.add(User(idUsuario=uuid.UUID("33333333-3333-4333-8333-333333333333"), nombre="Carla", apellido="Prueba", correoElectronico="carla.sintetica@example.com", usuario="carla"))
        db.commit()
    for user in db.scalars(select(User).where(User.usuario.in_(["ana", "beto", "carla"]))):
        if not db.get(LocalCredential, user.idUsuario) and not db.scalar(select(LocalCredential).where(LocalCredential.idUsuario == user.idUsuario)):
            db.add(LocalCredential(idUsuario=user.idUsuario, passwordHash=security.hashPassword(PW)))
            db.flush()
            consentService.record(db, user, TipoConsentimiento.POLITICA_PRIVACIDAD, True)
            consentService.record(db, user, TipoConsentimiento.DATOS_EXPERIMENTALES, True)
            db.commit()
        print(user.usuario, user.tipoCuenta, user.estado)
