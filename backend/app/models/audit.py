# Audit - Auditoria

import uuid
from datetime import datetime

from sqlalchemy import NVARCHAR, CheckConstraint, FetchedValue, ForeignKey, Index, text
from sqlalchemy.dialects.mssql import DATETIME2, UNIQUEIDENTIFIER
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.auditContext import AuditContext
from app.models.user import User


class Audit(Base):
    __tablename__ = "Auditoria"
    __table_args__ = (
        CheckConstraint("[datosNuevos] IS NULL OR isjson([datosNuevos])=(1)", name="CK_Auditoria_datosNuevosJson"),
        CheckConstraint(
            "[datosPrevios] IS NULL OR isjson([datosPrevios])=(1)",
            name="CK_Auditoria_datosPreviosJson",
        ),
        CheckConstraint("[detalle] IS NULL OR isjson([detalle])=(1)", name="CK_Auditoria_detalleJson"),
        CheckConstraint("[idRegistro] IS NULL OR [tablaAfectada] IS NOT NULL", name="CK_Auditoria_registro"),
        CheckConstraint(
            "[idRelacionado] IS NULL OR [tablaRelacionada] IS NOT NULL",
            name="CK_Auditoria_relacionado",
        ),
        CheckConstraint("[resultado]=N'FALLO' OR [resultado]=N'EXITO'", name="CK_Auditoria_resultado"),
        CheckConstraint(
            "[tipoEvento]=N'ACCESO' OR [tipoEvento]=N'PERMISO' OR [tipoEvento]=N'CRUD' OR [tipoEvento]=N'LOGIN'",
            name="CK_Auditoria_tipoEvento",
        ),
        # NULL o un tipo de cuenta.
        CheckConstraint(
            "[tipoCuentaActor] IS NULL OR [tipoCuentaActor]=N'CONSUMIDOR_FINAL' OR [tipoCuentaActor]=N'USUARIO_INSTITUCIONAL'"
            " OR [tipoCuentaActor]=N'ADMINISTRADOR_PLATAFORMA' OR [tipoCuentaActor]=N'MODERADOR_PLATAFORMA'",
            name="CK_Auditoria_tipoCuentaActor",
        ),
        Index("IX_Auditoria_institucion_fecha", "idInstitucion", "fechaHora"),
        Index("IX_Auditoria_modulo_fecha", "modulo", "fechaHora"),
        Index("IX_Auditoria_fecha", "fechaHora"),
        # Presentes en la base instalada y ausentes en v5 hasta el 19/10/2026 (consultas por acción y por cuenta).
        Index("IX_Auditoria_accion_fecha", "accion", "fechaHora", mssql_include=["idUsuario", "idInstitucion", "resultado"]),
        Index("IX_Auditoria_usuario_fecha", "idUsuario", "fechaHora", mssql_where=text("[idUsuario] IS NOT NULL"),
              sqlite_where=text("idUsuario IS NOT NULL")),
    )

    # tipoCuentaActor (tipo de cuenta de quien se autenticó, al generarse el evento; solo eventos LOGIN con cuenta identificable) está en el esquema
    # consolidado (GlucoLume_DB_v5.sql, DEC-02), pero una base instalada puede no tenerla todavía. Por eso la entidad nunca la nombra salvo que
    # registerEvent le asigne un valor (después de schemaCompat.auditAccountTypeReady): el valor viaja en el MISMO INSERT del evento, sin UPDATE
    # posterior (auditoría de solo inserción, GL-02). Para eso la columna es diferida (los SELECT de la entidad no la piden), FetchedValue la saca
    # de los INSERT cuando no tiene valor, y eager_defaults=False evita que el INSERT la pida de vuelta con OUTPUT/RETURNING. Los valores por
    # defecto del servidor (p. ej. fechaHora) se leen si alguien los consulta. services/authAccess.py la lee con Audit.__table__.c.
    __mapper_args__ = {"eager_defaults": False}

    idAuditoria: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), primary_key=True, server_default=text("newsequentialid()")
    )
    idUsuario: Mapped[uuid.UUID | None] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), ForeignKey("Usuario.idUsuario", name="FK_Auditoria_Usuario")
    )
    tipoEvento: Mapped[str] = mapped_column(NVARCHAR(20))
    accion: Mapped[str] = mapped_column(NVARCHAR(50))
    tablaAfectada: Mapped[str | None] = mapped_column(NVARCHAR(128))
    idRegistro: Mapped[uuid.UUID | None] = mapped_column(UNIQUEIDENTIFIER(as_uuid=True))
    tablaRelacionada: Mapped[str | None] = mapped_column(NVARCHAR(128))
    idRelacionado: Mapped[uuid.UUID | None] = mapped_column(UNIQUEIDENTIFIER(as_uuid=True))
    # idInstitucion: institución donde ocurrió el
    # evento (NULL: auditoría global, sin contexto institucional). modulo: módulo funcional del evento.
    idInstitucion: Mapped[uuid.UUID | None] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), ForeignKey("Institucion.idInstitucion", name="FK_Auditoria_Institucion")
    )
    modulo: Mapped[str | None] = mapped_column(NVARCHAR(30))
    datosPrevios: Mapped[str | None] = mapped_column(NVARCHAR(None))
    datosNuevos: Mapped[str | None] = mapped_column(NVARCHAR(None))
    resultado: Mapped[str] = mapped_column(NVARCHAR(10), server_default=text("N'EXITO'"))
    fechaHora: Mapped[datetime] = mapped_column(DATETIME2(precision=3), server_default=text("sysutcdatetime()"))
    observacion: Mapped[str | None] = mapped_column(NVARCHAR(1000))
    detalle: Mapped[str | None] = mapped_column(NVARCHAR(None))

    # Diferida y sin DEFAULT en la base: FetchedValue no genera DDL, solo indica al ORM que no la incluya en el INSERT si no tiene valor.
    tipoCuentaActor: Mapped[str | None] = mapped_column(NVARCHAR(40), deferred=True, server_default=FetchedValue())

    usuario: Mapped[User | None] = relationship()
    # Contexto de seguridad del evento (IP, cliente, correlación, motivo). Tabla AuditoriaContexto (esquema v5): solo se asigna al
    # registrar (services/audit.py, que antes comprueba que exista); nunca se carga por esta relación.
    contexto: Mapped["AuditContext | None"] = relationship(
        "AuditContext", uselist=False, lazy="raise", cascade="all, delete-orphan", passive_deletes=True)
