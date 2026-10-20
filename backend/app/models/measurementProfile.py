# MeasurementProfile - PerfilMedicion

import uuid
from datetime import date, datetime

from sqlalchemy import NVARCHAR, CheckConstraint, Date, ForeignKey, Index, SmallInteger, text
from sqlalchemy.dialects.mssql import DATETIME2, UNIQUEIDENTIFIER
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.institutionUser import InstitutionUser
from app.models.user import User


class MeasurementProfile(Base):
    __tablename__ = "PerfilMedicion"
    __table_args__ = (
        # 031 agrega COHORTE_ANONIMA: perfil sin persona (uno por institución) que agrupa las mediciones de pacientes ya anonimizados.
        CheckConstraint(
            "[tipoPerfil]=N'CONSUMIDOR_FINAL' AND [idUsuario] IS NOT NULL"
            " AND [idInstitucionUsuarioResponsable] IS NULL"
            " OR [tipoPerfil]=N'INSTITUCIONAL' AND [idUsuario] IS NULL"
            " AND [idInstitucionUsuarioResponsable] IS NOT NULL AND [identificadorPseudonimo] IS NOT NULL"
            " OR [tipoPerfil]=N'COHORTE_ANONIMA' AND [idUsuario] IS NULL AND [idInstitucionUsuarioResponsable] IS NULL"
            " AND [identificadorPseudonimo] IS NULL AND [nombre] IS NULL AND [apellido] IS NULL AND [dni] IS NULL"
            " AND [fechaNacimiento] IS NULL AND [edadDeclarada] IS NULL AND [idInstitucion] IS NOT NULL",
            name="CK_PerfilMedicion_coherenciaTipo",
        ),
        # La fecha de nacimiento (o edad) y el sexo son OPCIONALES en todos los perfiles (023_perfil_datos_opcionales.sql quitó
        # CK_PerfilMedicion_datoEdad y CK_PerfilMedicion_sexoObligatorio). Se recomiendan: mejoran la estimación experimental.
        CheckConstraint(
            "[edadDeclarada] IS NULL OR [edadDeclarada]>=(0) AND [edadDeclarada]<=(130)",
            name="CK_PerfilMedicion_edad",
        ),
        CheckConstraint("[sexoModelo]=N'MASCULINO' OR [sexoModelo]=N'FEMENINO'", name="CK_PerfilMedicion_sexo"),
        CheckConstraint(
            "[tipoPerfil]=N'INSTITUCIONAL' OR [tipoPerfil]=N'CONSUMIDOR_FINAL' OR [tipoPerfil]=N'COHORTE_ANONIMA'",
            name="CK_PerfilMedicion_tipo",
        ),
        # El documento se guarda normalizado (sin puntos, guiones ni
        # espacios), así la unicidad por institución no se esquiva con otro formato. (En SQLite el patrón [^...] no se interpreta.)
        CheckConstraint("[dni] IS NULL OR [dni] NOT LIKE N'%[^A-Z0-9]%'", name="CK_PerfilMedicion_dniNormalizado"),
        # Correo para recibir resultados, con su autorización y vencimiento
        # (12 meses). Los tres datos van juntos: o están los tres o ninguno.
        CheckConstraint(
            "[correoResultados] IS NULL AND [fechaAutorizacionCorreo] IS NULL AND [fechaExpiracionCorreo] IS NULL"
            " OR [correoResultados] IS NOT NULL AND [fechaAutorizacionCorreo] IS NOT NULL AND [fechaExpiracionCorreo] IS NOT NULL",
            name="CK_PerfilMedicion_correoResultados",
        ),
        # Un perfil propio por consumidor.
        Index(
            "UX_PerfilMedicion_consumidor", "idUsuario", unique=True,
            mssql_where=text("[tipoPerfil]=N'CONSUMIDOR_FINAL'"),
        ),
    )

    # Un solo paciente ACTIVO por documento y por institución, también ante altas simultáneas. La institución de un paciente sale de su
    # responsable (un JOIN), y un índice no puede cruzar tablas: por eso 031 guarda idInstitucion en el perfil. Quedan fuera del índice los
    # pacientes sin documento, los dados de baja y los anonimizados (dni NULL).
    _DNI_UNICO = (
        "[idInstitucion] IS NOT NULL AND [dni] IS NOT NULL AND [tipoPerfil]=N'INSTITUCIONAL'"
        " AND [fechaExpiracionDatosPersonales] IS NULL AND [fechaDepuracionDatosPersonales] IS NULL"
    )
    _UNA_COHORTE = "[tipoPerfil]=N'COHORTE_ANONIMA'"
    __table_args__ = (
        *__table_args__,
        # (SQLite, usado en las pruebas, no admite el prefijo N'...' de los literales.)
        Index("UX_PerfilMedicion_dniInstitucion", "idInstitucion", "dni", unique=True,
              mssql_where=text(_DNI_UNICO), sqlite_where=text(_DNI_UNICO.replace("N'", "'"))),
        # Una sola cohorte anónima por institución, aunque dos pasadas del job la necesiten a la vez.
        Index("UX_PerfilMedicion_cohorte", "idInstitucion", unique=True,
              mssql_where=text(_UNA_COHORTE), sqlite_where=text(_UNA_COHORTE.replace("N'", "'"))),
    )

    # correoResultados, fechaAutorizacionCorreo y fechaExpiracionCorreo se agregan con la migración 030, e idInstitucion con la 031: no se
    # mapean como atributos para que el backend siga funcionando si todavía no se aplicaron. Se leen y escriben con Core solo si existen
    # (services/resultEmailStore.py y services/measurementRetention.py).
    __mapper_args__ = {"exclude_properties": ["correoResultados", "fechaAutorizacionCorreo", "fechaExpiracionCorreo", "idInstitucion"]}

    idPerfilMedicion: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), primary_key=True, server_default=text("newid()")
    )
    tipoPerfil: Mapped[str] = mapped_column(NVARCHAR(30))
    idUsuario: Mapped[uuid.UUID | None] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), ForeignKey("Usuario.idUsuario", name="FK_PerfilMedicion_Usuario")
    )
    idInstitucionUsuarioResponsable: Mapped[uuid.UUID | None] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True),
        ForeignKey("InstitucionUsuario.idInstitucionUsuario", name="FK_PerfilMedicion_Responsable"),
    )
    identificadorPseudonimo: Mapped[str | None] = mapped_column(NVARCHAR(100))
    nombre: Mapped[str | None] = mapped_column(NVARCHAR(100))
    apellido: Mapped[str | None] = mapped_column(NVARCHAR(100))
    dni: Mapped[str | None] = mapped_column(NVARCHAR(20))
    fechaNacimiento: Mapped[date | None] = mapped_column(Date)
    edadDeclarada: Mapped[int | None] = mapped_column(SmallInteger)
    sexoModelo: Mapped[str | None] = mapped_column(NVARCHAR(30))
    fechaCreacion: Mapped[datetime] = mapped_column(DATETIME2(precision=3), server_default=text("sysutcdatetime()"))
    fechaUltimaMedicion: Mapped[datetime | None] = mapped_column(DATETIME2(precision=3))
    fechaExpiracionDatosPersonales: Mapped[datetime | None] = mapped_column(DATETIME2(precision=3))
    fechaDepuracionDatosPersonales: Mapped[datetime | None] = mapped_column(DATETIME2(precision=3))
    idInstitucion: Mapped[uuid.UUID | None] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), ForeignKey("Institucion.idInstitucion", name="FK_PerfilMedicion_Institucion")
    )
    correoResultados: Mapped[str | None] = mapped_column(NVARCHAR(254))
    fechaAutorizacionCorreo: Mapped[datetime | None] = mapped_column(DATETIME2(precision=3))
    fechaExpiracionCorreo: Mapped[datetime | None] = mapped_column(DATETIME2(precision=3))

    usuario: Mapped[User | None] = relationship()
    institucionUsuarioResponsable: Mapped[InstitutionUser | None] = relationship()
