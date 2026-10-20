/*
 GlucoLume | Matriz global y sus 27 reglas - TODO EN UNO, sobre el esquema consolidado GlucoLume_DB_v5.sql (DEC-02).
 Corrige el problema de ejecutar el cuerpo del procedimiento sin variables declaradas.
 SQL Server / SSMS: abrir el archivo completo y ejecutar F5, SIN SELECCIONAR TEXTO.
 Ensayado sobre v5 en una base descartable el 19/10/2026. No borra mediciones ni matrices institucionales.

 3 sexos: FEMENINO, MASCULINO, NO_INFORMADO.
 3 edades: 18-64, 65-130, NULL (edad desconocida).
 3 comidas: AYUNO, POSTPRANDIAL (60-120 min), NO_INFORMADA.
 TOTAL: 27 REGLAS.

 ADVERTENCIA: esta matriz es orientativa para adultos con diabetes no gestantes.
 No es diagnostica. DEMO es ficticio y nunca una glucemia real.
 CAMBIO DE ESQUEMA: edadDesde/edadHasta pasan a admitir NULL; se amplia
 CK_ReglaMatriz_sexo. Actualizar SQLAlchemy, Pydantic y resolucion de reglas
 antes de usar la matriz V2 desde el frontend/backend en produccion.
 Hacer respaldo antes de ejecutar. Verificar en una base de desarrollo.
*/

IF DB_ID(N'GlucoLume') IS NULL
    THROW 51000, 'No existe la base de datos GlucoLume.', 1;
USE [GlucoLume];
SET NOCOUNT ON;
SET XACT_ABORT ON;
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;

BEGIN TRY
    SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
    BEGIN TRANSACTION;

    IF OBJECT_ID(N'dbo.Matriz', N'U') IS NULL OR OBJECT_ID(N'dbo.ReglaMatriz', N'U') IS NULL
        THROW 51001, 'Faltan las tablas dbo.Matriz o dbo.ReglaMatriz.', 1;

    /* 1. Cambios compatibles con edades desconocidas (no aplica a perfiles). */
    IF EXISTS (SELECT 1 FROM sys.check_constraints
               WHERE parent_object_id=OBJECT_ID(N'dbo.ReglaMatriz') AND name=N'CK_ReglaMatriz_sexo')
        ALTER TABLE dbo.ReglaMatriz DROP CONSTRAINT CK_ReglaMatriz_sexo;
    IF EXISTS (SELECT 1 FROM sys.check_constraints
               WHERE parent_object_id=OBJECT_ID(N'dbo.ReglaMatriz') AND name=N'CK_ReglaMatriz_edad')
        ALTER TABLE dbo.ReglaMatriz DROP CONSTRAINT CK_ReglaMatriz_edad;

    IF EXISTS (SELECT 1 FROM sys.columns
               WHERE object_id=OBJECT_ID(N'dbo.ReglaMatriz') AND name=N'edadDesde' AND is_nullable=0)
        ALTER TABLE dbo.ReglaMatriz ALTER COLUMN edadDesde SMALLINT NULL;
    IF EXISTS (SELECT 1 FROM sys.columns
               WHERE object_id=OBJECT_ID(N'dbo.ReglaMatriz') AND name=N'edadHasta' AND is_nullable=0)
        ALTER TABLE dbo.ReglaMatriz ALTER COLUMN edadHasta SMALLINT NULL;

    ALTER TABLE dbo.ReglaMatriz WITH CHECK ADD CONSTRAINT CK_ReglaMatriz_sexo
        CHECK (sexoModelo IN (N'FEMENINO', N'MASCULINO', N'NO_INFORMADO'));
    ALTER TABLE dbo.ReglaMatriz WITH CHECK ADD CONSTRAINT CK_ReglaMatriz_edad
        CHECK ((edadDesde IS NULL AND edadHasta IS NULL)
            OR (edadDesde IS NOT NULL AND edadHasta IS NOT NULL
                AND edadDesde BETWEEN 0 AND 130 AND edadHasta BETWEEN edadDesde AND 130));

    /* 2. Crear la matriz si no existe. No requiere version 1 previa. */
    DECLARE @nombre NVARCHAR(100) = N'ADA 2026 - Seguimiento adulto no gestante';
    DECLARE @version NVARCHAR(50) = N'2';
    DECLARE @idMatriz UNIQUEIDENTIFIER = NULL;
    DECLARE @estado NVARCHAR(30) = NULL;
    DECLARE @cantidad INT = 0;

    SELECT TOP (1) @idMatriz = idMatriz, @estado = estado
    FROM dbo.Matriz WITH (UPDLOCK, HOLDLOCK)
    WHERE ambito=N'GLOBAL' AND idInstitucion IS NULL
      AND nombre=@nombre AND version=@version;

    IF @idMatriz IS NULL
    BEGIN
        SET @idMatriz=NEWID();
        INSERT INTO dbo.Matriz
            (idMatriz, idInstitucion, nombre, version, ambito, fechaVigenciaDesde,
             fechaVigenciaHasta, descripcion, estado)
        VALUES
            (@idMatriz, NULL, @nombre, @version, N'GLOBAL', CONVERT(DATE, SYSDATETIME()),
             NULL, N'Matriz orientativa para adultos con diabetes no gestantes. '
                 + N'27 reglas, incluye datos no informados. DEMO no representa una glucemia real.', N'BORRADOR');
        SET @estado=N'BORRADOR';
    END;

    IF @estado NOT IN (N'BORRADOR', N'INACTIVA', N'ACTIVA')
        THROW 51002, 'La matriz V2 existe pero esta archivada o en estado invalido.', 1;

    /* 3. Generar las 27 combinaciones de manera determinista. */
    DECLARE @reglas TABLE (
        codigo NVARCHAR(50) NOT NULL PRIMARY KEY,
        sexo NVARCHAR(30) NOT NULL,
        edadMin SMALLINT NULL,
        edadMax SMALLINT NULL,
        comida NVARCHAR(30) NOT NULL,
        minutosMin INT NULL,
        minutosMax INT NULL,
        glucosaMin DECIMAL(8,2) NOT NULL,
        glucosaMax DECIMAL(8,2) NOT NULL
    );

    INSERT INTO @reglas
      (codigo, sexo, edadMin, edadMax, comida, minutosMin, minutosMax, glucosaMin, glucosaMax)
    SELECT CONCAT(s.prefijo, N'_', c.codigo, CASE WHEN e.codigo=N'U' THEN N'_U' ELSE e.codigo END),
           s.sexo, e.edadMin, e.edadMax, c.comida, c.minutosMin, c.minutosMax,
           CASE WHEN e.edadMin IS NULL THEN CAST(70 AS DECIMAL(8,2))
                WHEN c.comida=N'AYUNO' THEN CAST(80 AS DECIMAL(8,2))
                ELSE CAST(70 AS DECIMAL(8,2)) END,
           CASE WHEN e.edadMin IS NULL THEN CAST(180 AS DECIMAL(8,2))
                WHEN c.comida=N'AYUNO' THEN CAST(130 AS DECIMAL(8,2))
                WHEN c.comida=N'POSTPRANDIAL' THEN CAST(179.99 AS DECIMAL(8,2))
                ELSE CAST(180 AS DECIMAL(8,2)) END
    FROM (VALUES (N'F',N'FEMENINO'), (N'M',N'MASCULINO'),
                 (N'NI',N'NO_INFORMADO')) AS s(prefijo, sexo)
    CROSS JOIN (VALUES
        (N'18',CAST(18 AS SMALLINT),CAST(64 AS SMALLINT)),
        (N'65',CAST(65 AS SMALLINT),CAST(130 AS SMALLINT)),
        (N'U',CAST(NULL AS SMALLINT),CAST(NULL AS SMALLINT))
    ) AS e(codigo, edadMin, edadMax)
    CROSS JOIN (VALUES
        (N'A',N'AYUNO',CAST(NULL AS INT),CAST(NULL AS INT)),
        (N'P',N'POSTPRANDIAL',CAST(60 AS INT),CAST(120 AS INT)),
        (N'N',N'NO_INFORMADA',CAST(NULL AS INT),CAST(NULL AS INT))
    ) AS c(codigo, comida, minutosMin, minutosMax);

    IF (SELECT COUNT(*) FROM @reglas)<>27
        THROW 51003, 'Error interno: no se generaron 27 reglas.', 1;

    /* Respetar inmutabilidad de una matriz previamente activada. */
    IF @estado=N'BORRADOR'
    BEGIN
        INSERT INTO dbo.ReglaMatriz
            (idReglaMatriz, idMatriz, codigoRegla, sexoModelo, edadDesde,
             edadHasta, condicionComida, minutosComidaMin, minutosComidaMax,
             glucosaMinReferencia, glucosaMaxReferencia)
        SELECT NEWID(), @idMatriz, r.codigo, r.sexo, r.edadMin, r.edadMax,
               r.comida, r.minutosMin, r.minutosMax, r.glucosaMin, r.glucosaMax
        FROM @reglas AS r
        WHERE NOT EXISTS (SELECT 1 FROM dbo.ReglaMatriz AS x WITH (UPDLOCK,HOLDLOCK)
                          WHERE x.idMatriz=@idMatriz AND x.codigoRegla=r.codigo);
    END;

    SELECT @cantidad=COUNT(*) FROM dbo.ReglaMatriz WHERE idMatriz=@idMatriz;
    IF @cantidad<>27
        THROW 51004, 'La matriz V2 no tiene exactamente 27 reglas; cambios revertidos.', 1;

    IF EXISTS (
        SELECT 1 FROM @reglas AS r
        JOIN dbo.ReglaMatriz AS x ON x.idMatriz=@idMatriz AND x.codigoRegla=r.codigo
        WHERE x.sexoModelo<>r.sexo
           OR NOT (x.edadDesde=r.edadMin OR (x.edadDesde IS NULL AND r.edadMin IS NULL))
           OR NOT (x.edadHasta=r.edadMax OR (x.edadHasta IS NULL AND r.edadMax IS NULL))
           OR x.condicionComida<>r.comida
           OR NOT (x.minutosComidaMin=r.minutosMin OR (x.minutosComidaMin IS NULL AND r.minutosMin IS NULL))
           OR NOT (x.minutosComidaMax=r.minutosMax OR (x.minutosComidaMax IS NULL AND r.minutosMax IS NULL))
           OR x.glucosaMinReferencia<>r.glucosaMin OR x.glucosaMaxReferencia<>r.glucosaMax
    ) THROW 51005, 'Las 27 reglas no coinciden con la version esperada; cambios revertidos.', 1;

    /* 4. Instalar procedimiento en un lote INTERNO mediante sp_executesql.
          Evita un GO intermedio y mantiene las variables declaradas dentro de la SP. */
    DECLARE @sqlProcedimiento NVARCHAR(MAX) = CAST(N'CREATE OR ALTER PROCEDURE dbo.usp_GlucoLume_CompararGlucosa
    @Glucosa DECIMAL(8,2),
    @Edad SMALLINT = NULL,
    @Sexo NVARCHAR(30) = NULL,
    @CondicionComida NVARCHAR(30) = N''NO_INFORMADA'',
    @MinutosComida INT = NULL,
    @TipoDato NVARCHAR(20) = N''DEMO'',
    @IdInstitucion UNIQUEIDENTIFIER = NULL
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @idMatriz UNIQUEIDENTIFIER = NULL,
            @idRegla UNIQUEIDENTIFIER = NULL,
            @min DECIMAL(8,2) = NULL,
            @max DECIMAL(8,2) = NULL,
            @condicionAplicada NVARCHAR(30) = NULL,
            @comparacion NVARCHAR(60) = N''SIN_COMPARACION'',
            @resultado NVARCHAR(60) = N''SIN_COMPARACION'',
            @origenReferencia NVARCHAR(70) = N''SIN_REGLA'',
            @sexoInformado BIT = 0,
            @edadInformada BIT = 0,
            @clasificacionHabilitada BIT = 0,
            @hoy DATE = CONVERT(DATE, SYSDATETIME());

    SET @Sexo = UPPER(LTRIM(RTRIM(COALESCE(@Sexo, N''''))));
    SET @CondicionComida = UPPER(LTRIM(RTRIM(COALESCE(@CondicionComida, N''''))));
    SET @TipoDato = UPPER(LTRIM(RTRIM(COALESCE(@TipoDato, N''DEMO''))));

    IF @TipoDato NOT IN (N''CAPILAR'', N''EXPERIMENTAL'', N''DEMO'')
        THROW 51007, ''TipoDato debe ser CAPILAR, EXPERIMENTAL o DEMO.'', 1;

    IF @Sexo IN (N''FEMENINO'', N''MASCULINO'') SET @sexoInformado = 1;
    ELSE SET @Sexo = N''NO_INFORMADO'';

    IF @Edad IS NOT NULL SET @edadInformada = 1;

    IF @CondicionComida NOT IN (N''AYUNO'', N''POSTPRANDIAL'', N''NO_INFORMADA'')
        SET @CondicionComida = N''NO_INFORMADA'';

    -- Prioridad institucional; en ausencia de matriz institucional, la global.
    IF @IdInstitucion IS NOT NULL
        SELECT TOP (1) @idMatriz = m.idMatriz
        FROM dbo.Matriz AS m
        WHERE m.ambito = N''INSTITUCION'' AND m.idInstitucion = @IdInstitucion
          AND m.estado = N''ACTIVA'' AND m.fechaVigenciaDesde <= @hoy
          AND (m.fechaVigenciaHasta IS NULL OR m.fechaVigenciaHasta >= @hoy);

    IF @idMatriz IS NULL
        SELECT TOP (1) @idMatriz = m.idMatriz
        FROM dbo.Matriz AS m
        WHERE m.ambito = N''GLOBAL'' AND m.idInstitucion IS NULL
          AND m.estado = N''ACTIVA'' AND m.fechaVigenciaDesde <= @hoy
          AND (m.fechaVigenciaHasta IS NULL OR m.fechaVigenciaHasta >= @hoy);

    IF @Glucosa IS NULL OR @Gluco' AS NVARCHAR(MAX))
        + N'sa <= 0
        SET @comparacion = N''VALOR_INVALIDO'';
    ELSE IF @idMatriz IS NULL
        SET @comparacion = N''SIN_MATRIZ'';
    ELSE IF @Edad IS NOT NULL AND (@Edad < 18 OR @Edad > 130)
        SET @comparacion = N''EDAD_FUERA_DE_ALCANCE'';
    ELSE
    BEGIN
        SELECT TOP (1)
               @idRegla = r.idReglaMatriz,
               @min = r.glucosaMinReferencia,
               @max = r.glucosaMaxReferencia,
               @condicionAplicada = r.condicionComida,
               @origenReferencia = CASE
                    WHEN @Edad IS NULL THEN N''REGLA_EDAD_NO_INFORMADA_SOLO_ORIENTATIVA''
                    WHEN @Sexo = N''NO_INFORMADO'' THEN N''REGLA_SEXO_NO_INFORMADO''
                    WHEN r.condicionComida = N''NO_INFORMADA'' THEN N''REGLA_COMIDA_NO_INFORMADA''
                    ELSE N''REGLA_DEL_PERFIL''
               END
        FROM dbo.ReglaMatriz AS r
        WHERE r.idMatriz = @idMatriz
          AND r.sexoModelo = @Sexo
          AND ((@Edad IS NULL AND r.edadDesde IS NULL AND r.edadHasta IS NULL)
               OR (@Edad IS NOT NULL AND r.edadDesde IS NOT NULL
                   AND @Edad BETWEEN r.edadDesde AND r.edadHasta))
          AND (r.condicionComida = @CondicionComida
               OR r.condicionComida = N''NO_INFORMADA'')
          AND (r.condicionComida <> N''POSTPRANDIAL''
               OR (@MinutosComida IS NOT NULL AND @MinutosComida >= 0
                   AND @MinutosComida BETWEEN COALESCE(r.minutosComidaMin, 0)
                                          AND COALESCE(r.minutosComidaMax, 2147483647)))
        ORDER BY CASE WHEN r.condicionComida = @CondicionComida THEN 0 ELSE 1 END,
                 r.codigoRegla;

        IF @idRegla IS NULL SET @comparacion = N''SIN_REGLA'';
    END;

    IF @Glucosa > 0 AND @min IS NOT NULL AND @max IS NOT NULL
    BEGIN
        IF @Glucosa < 54 SET @comparacion = N''MUY_BAJO'';
        ELSE IF @Glucosa < 70 SET @comparacion = N''BAJO'';
        ELSE IF @Glucosa < @min SET @comparacion = N''BAJO_OBJETIVO'';
        ELSE IF @Glucosa <= @max
            SET @comparacion = CASE WHEN @Edad IS NULL OR @condicionAplicada = N''NO_INFORMADA''
                                   THEN N''EN_RANGO_ORIENTATIVO'' ELSE N''EN_RANGO_REFERENCIA'' END;
        ELSE SET @comparacion = CASE WHEN @Edad IS NULL OR @condicionAplicada '
        + N'= N''NO_INFORMADA''
                                   THEN N''SOBRE_REFERENCIA_ORIENTATIVA'' ELSE N''ALTO_OBJETIVO'' END;
    END;

    SET @clasificacionHabilitada = CASE
        WHEN @TipoDato = N''CAPILAR'' AND @Edad BETWEEN 18 AND 130
         AND @condicionAplicada IN (N''AYUNO'', N''POSTPRANDIAL'')
         AND @idRegla IS NOT NULL THEN 1 ELSE 0 END;

    SET @resultado = CASE
        WHEN @comparacion IN (N''VALOR_INVALIDO'', N''SIN_MATRIZ'', N''EDAD_FUERA_DE_ALCANCE'', N''SIN_REGLA'')
            THEN @comparacion
        WHEN @TipoDato = N''DEMO'' THEN N''SIMULADO''
        WHEN @TipoDato = N''EXPERIMENTAL'' THEN N''NO_VALIDADO''
        WHEN @Edad IS NULL THEN N''REFERENCIA_ORIENTATIVA_SIN_EDAD''
        WHEN @condicionAplicada = N''NO_INFORMADA'' THEN N''REFERENCIA_ORIENTATIVA''
        ELSE @comparacion END;

    SELECT @Glucosa AS glucosaMgDl,
           @TipoDato AS tipoDato,
           @resultado AS resultadoPublicable,
           @comparacion AS comparacionNumericaDeEstudio,
           @min AS referenciaMinMgDl,
           @max AS referenciaMaxMgDl,
           @condicionAplicada AS condicionAplicada,
           @idMatriz AS idMatriz,
           @idRegla AS idReglaMatriz,
           @origenReferencia AS origenReferencia,
           @sexoInformado AS sexoInformado,
           @edadInformada AS edadInformada,
           @clasificacionHabilitada AS clasificacionHabilitada,
           N''Referencia orientativa para adultos con diabetes no gestantes, no diagnostica. ''
            + N''Sin edad no hay interpretacion clinica. DEMO es sintetico y EXPERIMENTAL no validado.'' AS advertencia;
END;';
    EXEC sys.sp_executesql @sqlProcedimiento;

    /* 5. Activar matriz principal SOLO tras validar reglas y procedimiento. */
    UPDATE dbo.Matriz SET estado=N'INACTIVA'
    WHERE ambito=N'GLOBAL' AND idInstitucion IS NULL
      AND estado=N'ACTIVA' AND idMatriz<>@idMatriz;

    IF @estado<>N'ACTIVA'
        UPDATE dbo.Matriz SET estado=N'ACTIVA'
        WHERE idMatriz=@idMatriz AND estado IN (N'BORRADOR',N'INACTIVA');

    COMMIT TRANSACTION;
    SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
    PRINT N'OK - Matriz global V2 activa, 27 reglas y procedimiento de comparacion actualizado.';
END TRY
BEGIN CATCH
    IF @@TRANCOUNT>0 ROLLBACK TRANSACTION;
    SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
    THROW;
END CATCH;

/* VERIFICACION - Ejecutar el archivo COMPLETO (sin seleccionar texto). */
SELECT m.idMatriz, m.idInstitucion, m.nombre, m.version, m.ambito, m.estado,
       COUNT(r.idReglaMatriz) AS cantidadReglas,
       SUM(CASE WHEN r.sexoModelo=N'NO_INFORMADO' THEN 1 ELSE 0 END) AS reglasSexoNoInformado,
       SUM(CASE WHEN r.edadDesde IS NULL AND r.edadHasta IS NULL THEN 1 ELSE 0 END) AS reglasEdadNoInformada
FROM dbo.Matriz AS m
LEFT JOIN dbo.ReglaMatriz AS r ON r.idMatriz=m.idMatriz
WHERE m.nombre=N'ADA 2026 - Seguimiento adulto no gestante'
  AND m.ambito=N'GLOBAL' AND m.version=N'2'
GROUP BY m.idMatriz,m.idInstitucion,m.nombre,m.version,m.ambito,m.estado;

EXEC dbo.usp_GlucoLume_CompararGlucosa
    @Glucosa=117, @Edad=NULL, @Sexo=NULL,
    @CondicionComida=N'NO_INFORMADA', @TipoDato=N'DEMO';
