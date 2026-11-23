# AccountDeviceLink - VinculoCuentaDispositivo
#
# Dispositivo vinculado a una cuenta individual. Una cuenta tiene UN solo dispositivo (UQ sobre idUsuario); un dispositivo puede estar
# vinculado a varias cuentas, sin mezclar mediciones (cada medición guarda su cuenta y su dispositivo). Es independiente de la asignación
# institucional (Dispositivo.idInstitucionAsignada), que no se toca.
# Si la base instalada todavía no tiene la tabla (database/reference/GlucoLume_vinculo_cuenta_dispositivo.sql), no se vincula nada
# (schemaCompat.hasTable en services/individualDevice.py).

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, UniqueConstraint, text
from sqlalchemy.dialects.mssql import DATETIME2, UNIQUEIDENTIFIER
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AccountDeviceLink(Base):
    __tablename__ = "VinculoCuentaDispositivo"
    __table_args__ = (
        UniqueConstraint("idUsuario", name="UQ_VinculoCuentaDispositivo_usuario"),
    )

    idVinculo: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), primary_key=True, server_default=text("newid()"))
    idUsuario: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), ForeignKey("Usuario.idUsuario", name="FK_VinculoCuentaDispositivo_Usuario"))
    idDispositivo: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), ForeignKey("Dispositivo.idDispositivo", name="FK_VinculoCuentaDispositivo_Dispositivo"))
    fechaVinculo: Mapped[datetime] = mapped_column(DATETIME2(precision=3), server_default=text("sysutcdatetime()"))
