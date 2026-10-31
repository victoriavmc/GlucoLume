/*
 GlucoLume | Matriz global de referencia de glucosa, versión 1 de «ADA Diabetes Tests - objetivos adultos no gestantes» (v3).
 Reemplaza en el catálogo global a «ADA 2026 - Seguimiento adulto no gestante» (v2, DEMO, sin fuente clínica), que queda INACTIVA
 e intacta para la trazabilidad de las mediciones que la usaron. No se modifica ninguna fila de matrices activadas ni mediciones.

 Fuente única: ADA, Diabetes Tests (https://diabetes.org/living-with-diabetes/treatment-care/checking-your-blood-sugar).
   · Objetivo preprandial: 80–130 mg/dL («Before a meal»), regla AYUNO.
   · Objetivo posprandial: menor de 180 mg/dL, medido 1–2 horas desde el inicio de la comida, regla POSTPRANDIAL (60–120 min).
   · Comida no informada (NO_INFORMADA): no hay regla ni objetivo. La consulta muestra los dos objetivos sin elegir ninguno.
 Sin distinción por sexo (regla CUALQUIER_SEXO) ni por edad: el alcance es el de adultos 18–130 años.
 No es diagnóstico ni clasificación clínica. Los umbrales 54 y 70 mg/dL son de hipoglucemia y se marcan como pendientes de verificar
 con la Sección 6 de ADA (no accesible en la revisión).

 Cambios de esquema: CK_ReglaMatriz_sexo admite CUALQUIER_SEXO; ReglaMatriz.glucosaMinReferencia admite NULL (solo tope).
 Prerrequisito: GlucoLume_matriz_referencia.sql (columnas referenciaBase y urlReferencia).
 SQL Server / SSMS: abrir el archivo completo y ejecutar F5, SIN SELECCIONAR TEXTO. Hacer respaldo antes de ejecutar.
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
    IF COL_LENGTH(N'dbo.Matriz', N'urlReferencia') IS NULL OR COL_LENGTH(N'dbo.Matriz', N'referenciaBase') IS NULL
        THROW 51006, 'Falta ejecutar antes GlucoLume_matriz_referencia.sql (columnas referenciaBase y urlReferencia).', 1;

    /* 1. Cambios de esquema (idempotentes). */
    IF EXISTS (SELECT 1 FROM sys.check_constraints
               WHERE parent_object_id=OBJECT_ID(N'dbo.ReglaMatriz') AND name=N'CK_ReglaMatriz_sexo')
        ALTER TABLE dbo.ReglaMatriz DROP CONSTRAINT CK_ReglaMatriz_sexo;
    IF EXISTS (SELECT 1 FROM sys.check_constraints
               WHERE parent_object_id=OBJECT_ID(N'dbo.ReglaMatriz') AND name=N'CK_ReglaMatriz_edad')
        ALTER TABLE dbo.ReglaMatriz DROP CONSTRAINT CK_ReglaMatriz_edad;
    IF EXISTS (SELECT 1 FROM sys.check_constraints
               WHERE parent_object_id=OBJECT_ID(N'dbo.ReglaMatriz') AND name=N'CK_ReglaMatriz_glucosaReferencia')
        ALTER TABLE dbo.ReglaMatriz DROP CONSTRAINT CK_ReglaMatriz_glucosaReferencia;

    IF EXISTS (SELECT 1 FROM sys.columns
               WHERE object_id=OBJECT_ID(N'dbo.ReglaMatriz') AND name=N'edadDesde' AND is_nullable=0)
        ALTER TABLE dbo.ReglaMatriz ALTER COLUMN edadDesde SMALLINT NULL;
    IF EXISTS (SELECT 1 FROM sys.columns
               WHERE object_id=OBJECT_ID(N'dbo.ReglaMatriz') AND name=N'edadHasta' AND is_nullable=0)
        ALTER TABLE dbo.ReglaMatriz ALTER COLUMN edadHasta SMALLINT NULL;
    IF EXISTS (SELECT 1 FROM sys.columns
               WHERE object_id=OBJECT_ID(N'dbo.ReglaMatriz') AND name=N'glucosaMinReferencia' AND is_nullable=0)
        ALTER TABLE dbo.ReglaMatriz ALTER COLUMN glucosaMinReferencia DECIMAL(8,2) NULL;

    ALTER TABLE dbo.ReglaMatriz WITH CHECK ADD CONSTRAINT CK_ReglaMatriz_sexo
        CHECK (sexoModelo IN (N'FEMENINO', N'MASCULINO', N'NO_INFORMADO', N'CUALQUIER_SEXO'));
    ALTER TABLE dbo.ReglaMatriz WITH CHECK ADD CONSTRAINT CK_ReglaMatriz_edad
        CHECK ((edadDesde IS NULL AND edadHasta IS NULL)
            OR (edadDesde IS NOT NULL AND edadHasta IS NOT NULL
                AND edadDesde BETWEEN 0 AND 130 AND edadHasta BETWEEN edadDesde AND 130));
    ALTER TABLE dbo.ReglaMatriz WITH CHECK ADD CONSTRAINT CK_ReglaMatriz_glucosaReferencia
        CHECK ((glucosaMinReferencia IS NULL OR glucosaMinReferencia>=0) AND glucosaMaxReferencia>=0
            AND (glucosaMinReferencia IS NULL OR glucosaMaxReferencia>=glucosaMinReferencia));

    /* 2. Crear la versión 1 de la matriz ADA si no existe. */
    DECLARE @nombre NVARCHAR(100) = N'ADA Diabetes Tests - objetivos adultos no gestantes';
    DECLARE @version NVARCHAR(50) = N'1';
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
             fechaVigenciaHasta, descripcion, referenciaBase, urlReferencia, estado)
        VALUES
            (@idMatriz, NULL, @nombre, @version, N'GLOBAL', CONVERT(DATE, SYSDATETIME()),
             NULL,
             N'Objetivos de glucosa capilar de la guía ADA para adultos no gestantes con diabetes: preprandial 80–130 mg/dL y '
                 + N'posprandial menor de 180 mg/dL, medido 1–2 h desde el inicio de la comida. Sin distinción por sexo ni edad. '
                 + N'No es diagnóstico ni clasificación clínica.',
             N'ADA, Diabetes Tests: objetivos preprandial y posprandial para adultos no gestantes con diabetes',
             N'https://diabetes.org/living-with-diabetes/treatment-care/checking-your-blood-sugar',
             N'BORRADOR');
        SET @estado=N'BORRADOR';
    END;

    IF @estado NOT IN (N'BORRADOR', N'INACTIVA', N'ACTIVA')
        THROW 51002, 'La versión 1 de la matriz ADA existe pero está archivada o en estado inválido.', 1;

    /* 3. Las dos reglas (una por objetivo). Sin regla para «comida no informada»: no hay objetivo ADA para ese caso. */
    DECLARE @reglas TABLE (
        codigo NVARCHAR(50) NOT NULL PRIMARY KEY,
        sexo NVARCHAR(30) NOT NULL,
        edadMin SMALLINT NULL,
        edadMax SMALLINT NULL,
        comida NVARCHAR(30) NOT NULL,
        minutosMin INT NULL,
        minutosMax INT NULL,
        glucosaMin DECIMAL(8,2) NULL,
        glucosaMax DECIMAL(8,2) NOT NULL
    );

    INSERT INTO @reglas (codigo, sexo, edadMin, edadMax, comida, minutosMin, minutosMax, glucosaMin, glucosaMax)
    VALUES (N'R-001', N'CUALQUIER_SEXO', 18, 130, N'AYUNO', NULL, NULL, CAST(80.00 AS DECIMAL(8,2)), CAST(130.00 AS DECIMAL(8,2))),
           (N'R-002', N'CUALQUIER_SEXO', 18, 130, N'POSTPRANDIAL', 60, 120, NULL, CAST(179.99 AS DECIMAL(8,2)));

    IF (SELECT COUNT(*) FROM @reglas)<>2
        THROW 51003, 'Error interno: no se generaron 2 reglas.', 1;

    /* Respetar inmutabilidad: solo se completan reglas de un BORRADOR. */
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
    IF @cantidad<>2
        THROW 51004, 'La matriz no tiene exactamente 2 reglas; cambios revertidos.', 1;

    IF EXISTS (
        SELECT 1 FROM @reglas AS r
        JOIN dbo.ReglaMatriz AS x ON x.idMatriz=@idMatriz AND x.codigoRegla=r.codigo
        WHERE x.sexoModelo<>r.sexo
           OR NOT (x.edadDesde=r.edadMin OR (x.edadDesde IS NULL AND r.edadMin IS NULL))
           OR NOT (x.edadHasta=r.edadMax OR (x.edadHasta IS NULL AND r.edadMax IS NULL))
           OR x.condicionComida<>r.comida
           OR NOT (x.minutosComidaMin=r.minutosMin OR (x.minutosComidaMin IS NULL AND r.minutosMin IS NULL))
           OR NOT (x.minutosComidaMax=r.minutosMax OR (x.minutosComidaMax IS NULL AND r.minutosMax IS NULL))
           OR NOT (x.glucosaMinReferencia=r.glucosaMin OR (x.glucosaMinReferencia IS NULL AND r.glucosaMin IS NULL))
           OR x.glucosaMaxReferencia<>r.glucosaMax
    ) THROW 51005, 'Las 2 reglas no coinciden con la versión esperada; cambios revertidos.', 1;

    /* 4. Procedimiento de comparación: mismo criterio que matrix.py (resolveRule) y glucoseReference.py (position). */
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
            @sexoAplicado NVARCHAR(30) = NULL,
            @comparacion NVARCHAR(60) = N''SIN_COMPARACION'',
            @resultado NVARCHAR(60) = N''SIN_COMPARACION'',
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

    -- Prioridad institucional; en ausencia de matriz institucional, la global (igual que resolveMatrix en matrix.py).
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

    IF @Glucosa IS NULL OR @Glucosa <= 0
        SET @comparacion = N''VALOR_INVALIDO'';
    ELSE IF @idMatriz IS NULL
        SET @comparacion = N''SIN_MATRIZ'';
    ELSE IF @Edad IS NOT NULL AND (@Edad < 18 OR @Edad > 130)
        SET @comparacion = N''EDAD_FUERA_DE_ALCANCE'';
    ELSE
    BEGIN
        -- Sin edad no hay regla. Sin comida informada (NO_INFORMADA) tampoco: no se elige un objetivo (ver matrix.py, resolveRule).
        -- Una regla CUALQUIER_SEXO vale para cualquier sexo; una por sexo, solo para ese sexo.
        -- Posprandial: @MinutosComida = minutos desde el INICIO de la comida hasta el INICIO de la medición (igual que _minutes en glucoseReference.py).
        SELECT TOP (1)
' AS NVARCHAR(MAX))
        + N'               @idRegla = r.idReglaMatriz,
               @min = r.glucosaMinReferencia,
               @max = r.glucosaMaxReferencia,
               @condicionAplicada = r.condicionComida,
               @sexoAplicado = r.sexoModelo
        FROM dbo.ReglaMatriz AS r
        WHERE r.idMatriz = @idMatriz
          AND (r.sexoModelo = @Sexo OR r.sexoModelo = N''CUALQUIER_SEXO'')
          AND @Edad IS NOT NULL AND r.edadDesde IS NOT NULL AND @Edad BETWEEN r.edadDesde AND r.edadHasta
          AND r.condicionComida = @CondicionComida
          AND (r.condicionComida <> N''POSTPRANDIAL''
               OR (@MinutosComida IS NOT NULL AND @MinutosComida >= 0
                   AND @MinutosComida BETWEEN COALESCE(r.minutosComidaMin, 0)
                                          AND COALESCE(r.minutosComidaMax, 2147483647)))
        ORDER BY CASE WHEN r.sexoModelo = @Sexo THEN 0 ELSE 1 END, r.codigoRegla;

        IF @idRegla IS NULL SET @comparacion = N''SIN_REGLA'';
    END;

    -- Comparación con el objetivo: DENTRO / POR_DEBAJO / POR_ENCIMA, igual que position() en glucoseReference.py.
    -- Los umbrales 54 y 70 mg/dL son de hipoglucemia (no son objetivos); pendientes de verificar con la Sección 6 de ADA.
    IF @Glucosa > 0 AND @max IS NOT NULL AND @idRegla IS NOT NULL
    BEGIN
        IF @Glucosa < 54 SET @comparacion = N''MUY_BAJO'';
        ELSE IF @Glucosa < 70 SET @comparacion = N''BAJO'';
        ELSE IF @min IS NOT NULL AND @Glucosa < @min SET @comparacion = N''BAJO_OBJETIVO'';
        ELSE IF @Glucosa <= @max SET @comparacion = N''EN_OBJETIVO'';
        ELSE SET @comparacion = N''ALTO_OBJETIVO'';
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
        ELSE @comparacion END;

    SELECT @Glucosa AS glucosaMgDl,
           @TipoDato AS tipoDato,
           @resultado AS resultadoPublicable,
           @comparacion AS comparacionNumericaDeEstudio,
           @min AS referenciaMinMgDl,
           @max AS referenciaMaxMgDl,
           @condicionAplicada AS condicionAplicada,
           @sexoAplicado AS sexoAplicado,
           @idMatriz AS idMatriz,
           @idRegla AS idReglaMatriz,
           @sexoInformado AS sexoInformado,
           @edadInformada AS edadInformada,
           @clasificacionHabilitada AS clasificacionHabilitada,
           N''Objetivo de la guía ADA para adultos no gestantes con diabetes (preprandial y posprandial, no diagnóstico). ''
            + N''Sin edad o sin comida informada no hay clasificación. DEMO es simulado; EXPERIMENTAL no está validado.'' AS advertencia;
END;';
    EXEC sys.sp_executesql @sqlProcedimiento;

    /* 5. Activar la versión SOLO tras validar reglas y procedimiento. La activa anterior pasa a INACTIVA (queda para trazabilidad). */
    UPDATE dbo.Matriz SET estado=N'INACTIVA'
    WHERE ambito=N'GLOBAL' AND idInstitucion IS NULL
      AND estado=N'ACTIVA' AND idMatriz<>@idMatriz;

    IF @estado<>N'ACTIVA'
        UPDATE dbo.Matriz SET estado=N'ACTIVA'
        WHERE idMatriz=@idMatriz AND estado IN (N'BORRADOR',N'INACTIVA');

    COMMIT TRANSACTION;
    SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
    PRINT N'OK - Matriz ADA v1 (objetivos adultos no gestantes) activa, 2 reglas y procedimiento de comparación actualizado.';
END TRY
BEGIN CATCH
    IF @@TRANCOUNT>0 ROLLBACK TRANSACTION;
    SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
    THROW;
END CATCH;

/* VERIFICACIÓN - Ejecutar el archivo COMPLETO (sin seleccionar texto). */
SELECT m.idMatriz, m.idInstitucion, m.nombre, m.version, m.ambito, m.estado,
       COUNT(r.idReglaMatriz) AS cantidadReglas,
       SUM(CASE WHEN r.sexoModelo=N'CUALQUIER_SEXO' THEN 1 ELSE 0 END) AS reglasCualquierSexo,
       SUM(CASE WHEN r.glucosaMinReferencia IS NULL THEN 1 ELSE 0 END) AS reglasSinLimiteInferior
FROM dbo.Matriz AS m
LEFT JOIN dbo.ReglaMatriz AS r ON r.idMatriz=m.idMatriz
WHERE m.nombre=N'ADA Diabetes Tests - objetivos adultos no gestantes'
  AND m.ambito=N'GLOBAL' AND m.version=N'1'
GROUP BY m.idMatriz,m.idInstitucion,m.nombre,m.version,m.ambito,m.estado;

-- Ejemplos: preprandial 117 (en objetivo), posprandial 200 a 90 minutos (sobre el objetivo), sin comida (sin objetivo).
EXEC dbo.usp_GlucoLume_CompararGlucosa @Glucosa=117, @Edad=40, @Sexo=NULL, @CondicionComida=N'AYUNO', @TipoDato=N'DEMO';
EXEC dbo.usp_GlucoLume_CompararGlucosa @Glucosa=200, @Edad=40, @Sexo=N'FEMENINO', @CondicionComida=N'POSTPRANDIAL', @MinutosComida=90, @TipoDato=N'DEMO';
EXEC dbo.usp_GlucoLume_CompararGlucosa @Glucosa=117, @Edad=40, @Sexo=NULL, @CondicionComida=N'NO_INFORMADA', @TipoDato=N'DEMO';
