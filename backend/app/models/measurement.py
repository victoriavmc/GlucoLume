# Measurement - Medicion

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DECIMAL, NVARCHAR, BigInteger, CheckConstraint, Computed, ForeignKey, Index, Integer, SmallInteger, or_, text
from sqlalchemy.dialects.mssql import DATETIME2, UNIQUEIDENTIFIER
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.device import Device
from app.models.matrix import Matrix
from app.models.measurementProfile import MeasurementProfile


class Measurement(Base):
    __tablename__ = "Medicion"
    __table_args__ = (
        CheckConstraint("[calidadSenal] IS NULL OR [calidadSenal]>=(0)", name="CK_Medicion_calidad"),
        CheckConstraint(
            "[condicionComida]=N'NO_INFORMADA' OR [condicionComida]=N'POSTPRANDIAL' OR [condicionComida]=N'AYUNO'",
            name="CK_Medicion_condicionComida",
        ),
        CheckConstraint("[edadAlMomento]>=(0) AND [edadAlMomento]<=(130)", name="CK_Medicion_edad"),
        CheckConstraint(
            "[estadoMedicion]=N'CANCELADA' OR [estadoMedicion]=N'INVALIDA' OR [estadoMedicion]=N'COMPLETADA'"
            " OR [estadoMedicion]=N'PROCESANDO' OR [estadoMedicion]=N'ADQUIRIENDO' OR [estadoMedicion]=N'PENDIENTE'",
            name="CK_Medicion_estado",
        ),
        CheckConstraint("[frecuenciaCardiaca] IS NULL OR [frecuenciaCardiaca]>(0)", name="CK_Medicion_fc"),
        CheckConstraint("[fechaHoraFin] IS NULL OR [fechaHoraFin]>=[fechaHoraInicio]", name="CK_Medicion_fechas"),
        CheckConstraint(
            "NOT ([modoMedicion]=N'GLUCOSA_EXPERIMENTAL' AND [estadoMedicion]=N'COMPLETADA')"
            " OR [glucosaEstimada] IS NOT NULL OR [glucosaDispositivo] IS NOT NULL",
            name="CK_Medicion_glucosaCompletada",
        ),
        CheckConstraint("[glucosaEstimada] IS NULL OR [glucosaEstimada]>=(0)", name="CK_Medicion_glucosaRango"),
        CheckConstraint(
            "[glucosaEstimada] IS NULL OR [idMatriz] IS NOT NULL AND [versionAlgoritmo] IS NOT NULL",
            name="CK_Medicion_glucosaTrazable",
        ),
        CheckConstraint(
            "[modeloSensorAlMomento] IS NULL"
            " OR ([modeloSensorAlMomento]=N'MAX30102' OR [modeloSensorAlMomento]=N'MAX30100')",
            name="CK_Medicion_modeloSensor",
        ),
        CheckConstraint(
            "[modoMedicion]=N'GLUCOSA_EXPERIMENTAL' OR [modoMedicion]=N'OXIMETRIA'",
            name="CK_Medicion_modo",
        ),
        CheckConstraint(
            "[modoMedicion]<>N'OXIMETRIA' OR [glucosaEstimada] IS NULL",
            name="CK_Medicion_oximetriaSinGlucosa",
        ),
        CheckConstraint("[sexoModelo]=N'MASCULINO' OR [sexoModelo]=N'FEMENINO'", name="CK_Medicion_sexo"),
        CheckConstraint("[spo2] IS NULL OR [spo2]>=(0) AND [spo2]<=(100)", name="CK_Medicion_spo2"),
        # Datos informados por el dispositivo: origen de la glucosa del firmware y valores asociados.
        CheckConstraint(
            "[origenGlucosa] IS NULL OR [origenGlucosa]=N'DEMO' OR [origenGlucosa]=N'EXPERIMENTAL'"
            " OR [origenGlucosa]=N'SIN_CALIBRAR'",
            name="CK_Medicion_origenGlucosa",
        ),
        CheckConstraint(
            "[glucosaDispositivo] IS NULL OR COALESCE([origenGlucosa],N'')=N'DEMO'"
            " OR COALESCE([origenGlucosa],N'')=N'EXPERIMENTAL'",
            name="CK_Medicion_glucosaDispositivoOrigen",
        ),
        CheckConstraint(
            "[origenGlucosa] IS NULL OR [origenGlucosa]=N'SIN_CALIBRAR' OR [glucosaDispositivo] IS NOT NULL",
            name="CK_Medicion_origenConGlucosa",
        ),
        CheckConstraint("[glucosaDispositivo] IS NULL OR [glucosaDispositivo]>=(0)", name="CK_Medicion_glucosaDispositivoRango"),
        CheckConstraint(
            "[glucosaDispositivo] IS NULL OR COALESCE([unidadGlucosa],N'')=N'mg/dL'", name="CK_Medicion_unidadGlucosa"
        ),
        CheckConstraint("[indiceOptico] IS NULL OR [indiceOptico]>=(0)", name="CK_Medicion_indiceOptico"),
        CheckConstraint("[lecturasEstabilizadas] IS NULL OR [lecturasEstabilizadas]>(0)", name="CK_Medicion_lecturas"),
        # El origen del dato del firmware ya no depende del modo: una medición de glucosa también lo informa. Lo que no se
        # mezcla: un valor DEMO jamás se copia a la estimación del servidor.
        CheckConstraint(
            "[origenGlucosa] IS NULL OR [origenGlucosa]<>N'DEMO' OR [glucosaEstimada] IS NULL", name="CK_Medicion_demoSinEstimacion"
        ),
        # Presente en la base instalada y ausente en v5 hasta el 19/10/2026 (mantenimiento de mediciones abandonadas o vencidas).
        Index("IX_Medicion_estado_fin", "estadoMedicion", "fechaHoraFin", mssql_include=["idPerfilMedicion", "fechaHoraInicio"]),
        Index("IX_Medicion_vencimientoRetencion", "fechaVencimientoRetencion",
              mssql_where=text("[fechaVencimientoRetencion] IS NOT NULL"), sqlite_where=text("[fechaVencimientoRetencion] IS NOT NULL")),
    )

    __mapper_args__ = {"exclude_properties": ["idReglaMatriz", "fechaVencimientoRetencion"]}

    # Fin de la conservación de una medición ya ANONIMIZADA: última medición de esa persona + 12 meses, calculado una vez antes de
    # separarla de su identidad. Es lo que permite seguir controlando el vencimiento cuando ya no se sabe de quién era. NULL = no anonimizada
    # (su vencimiento, si corresponde, sale de las fechas del perfil). Como idReglaMatriz, no se mapea: se usa con Core y solo si existe
    # (services/measurementRetention.py).
    fechaVencimientoRetencion: Mapped[datetime | None] = mapped_column(DATETIME2(precision=3))

    idMedicion: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), primary_key=True, server_default=text("newid()")
    )
    idPerfilMedicion: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), ForeignKey("PerfilMedicion.idPerfilMedicion", name="FK_Medicion_Perfil")
    )
    idDispositivo: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), ForeignKey("Dispositivo.idDispositivo", name="FK_Medicion_Dispositivo")
    )
    idMatriz: Mapped[uuid.UUID | None] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), ForeignKey("Matriz.idMatriz", name="FK_Medicion_Matriz")
    )
    # Regla de esa matriz que se aplicó en una ESTIMACIÓN del servidor. NULL si la matriz solo se asoció como referencia.
    # La columna existe en la TABLA pero NO se mapea en el ORM (ver __mapper_args__): así los INSERT/SELECT de la entidad no la mencionan y
    # la aplicación sigue funcionando si la base instalada todavía no tiene la columna. Se lee y escribe con Core, solo si existe
    # (services/schemaCompat.py: ruleIdOf / setRuleId).
    idReglaMatriz: Mapped[uuid.UUID | None] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), ForeignKey("ReglaMatriz.idReglaMatriz", name="FK_Medicion_ReglaMatriz")
    )
    modoMedicion: Mapped[str] = mapped_column(NVARCHAR(30), server_default=text("N'OXIMETRIA'"))
    estadoMedicion: Mapped[str] = mapped_column(NVARCHAR(30), server_default=text("N'PENDIENTE'"))
    fechaHoraInicio: Mapped[datetime] = mapped_column(
        DATETIME2(precision=3), server_default=text("sysutcdatetime()")
    )
    fechaHoraFin: Mapped[datetime | None] = mapped_column(DATETIME2(precision=3))
    fechaHoraUltimaComida: Mapped[datetime | None] = mapped_column(DATETIME2(precision=3))
    condicionComida: Mapped[str] = mapped_column(NVARCHAR(30), server_default=text("N'NO_INFORMADA'"))
    # Opcionales: un paciente institucional puede medirse sin definirlos; la glucosa los exige.
    edadAlMomento: Mapped[int | None] = mapped_column(SmallInteger)
    sexoModelo: Mapped[str | None] = mapped_column(NVARCHAR(30))
    versionFirmwareAlMomento: Mapped[str | None] = mapped_column(NVARCHAR(50))
    modeloSensorAlMomento: Mapped[str | None] = mapped_column(NVARCHAR(20))
    versionAlgoritmo: Mapped[str | None] = mapped_column(NVARCHAR(50))
    calidadSenal: Mapped[Decimal | None] = mapped_column(DECIMAL(6, 3))
    spo2: Mapped[Decimal | None] = mapped_column(DECIMAL(5, 2))
    frecuenciaCardiaca: Mapped[int | None] = mapped_column(SmallInteger)
    glucosaEstimada: Mapped[Decimal | None] = mapped_column(DECIMAL(8, 2))
    observacion: Mapped[str | None] = mapped_column(NVARCHAR(500))
    # Valores informados YA PROCESADOS por el firmware (telemetría del puente serie). `origenGlucosa` NULL: medición
    # calculada por el servidor sobre MuestraSensor. DEMO: la glucosa es sintética y la medición no entra en indicadores.
    origenGlucosa: Mapped[str | None] = mapped_column(NVARCHAR(20))
    glucosaDispositivo: Mapped[Decimal | None] = mapped_column(DECIMAL(8, 2))
    unidadGlucosa: Mapped[str | None] = mapped_column(NVARCHAR(10))
    indiceOptico: Mapped[Decimal | None] = mapped_column(DECIMAL(10, 5))
    lecturasEstabilizadas: Mapped[int | None] = mapped_column(SmallInteger)
    # Columnas calculadas por SQL Server (solo lectura).
    minutosDesdeUltimaComida: Mapped[int | None] = mapped_column(
        Integer, Computed("datediff(minute,[fechaHoraUltimaComida],[fechaHoraInicio])")
    )
    duracionMs: Mapped[int | None] = mapped_column(
        BigInteger, Computed("datediff_big(millisecond,[fechaHoraInicio],[fechaHoraFin])")
    )

    perfilMedicion: Mapped[MeasurementProfile] = relationship()
    dispositivo: Mapped[Device] = relationship()
    matriz: Mapped[Matrix | None] = relationship()


ORIGEN_DEMO = "DEMO"

# Condición reutilizable para indicadores clínicos, estadísticas y recomendaciones: los datos DEMO (valor sintético
# del firmware, solo para probar la integración) nunca entran. Las mediciones sin origen (calculadas por el servidor)
# y las de origen EXPERIMENTAL / SIN_CALIBRAR sí.
NOT_DEMO = or_(Measurement.origenGlucosa.is_(None), Measurement.origenGlucosa != ORIGEN_DEMO)
