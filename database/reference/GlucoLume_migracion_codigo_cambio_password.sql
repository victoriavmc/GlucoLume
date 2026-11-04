-- Migración: TokenCuenta admite el tipo CODIGO_CAMBIO_PASSWORD.
-- Lo usa el cambio de contraseña de una cuenta administrativa que todavía no tiene MFA: el código de 6 dígitos
-- llega al correo registrado (services/passwordChangeCode.py). Ejecutar una sola vez sobre la base instalada.
-- La lista de valores es la de v5 más el tipo nuevo (tests/test_reference_schema.py verifica que coincidan).

ALTER TABLE [dbo].[TokenCuenta] DROP CONSTRAINT [CK_TokenCuenta_tipo];
GO
ALTER TABLE [dbo].[TokenCuenta] WITH CHECK ADD CONSTRAINT [CK_TokenCuenta_tipo] CHECK
    (([tipo]=N'ACTIVACION_CUENTA' OR [tipo]=N'RECUPERACION_MFA' OR [tipo]=N'INTERCAMBIO_GOOGLE' OR [tipo]=N'ELIMINAR_CUENTA'
      OR [tipo]=N'RECUPERACION_PASSWORD' OR [tipo]=N'VERIFICACION_EMAIL' OR [tipo]=N'CODIGO_CAMBIO_PASSWORD'));
GO
