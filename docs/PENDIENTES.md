# Pendientes

Solo problemas abiertos, riesgos sin resolver, pruebas faltantes y funcionalidades incompletas. Cuando algo se resuelve y se verifica, se
registra en [HISTORIAL.md](HISTORIAL.md) y se quita de aquí. Prioridad: **P0** antes de cualquier uso con datos reales; **P1** antes de
producción; **P2** próxima iteración; **P3** planificado. Estado de los hallazgos de seguridad: [SEGURIDAD.md](SEGURIDAD.md) §2; los
procedimientos preparados que requieren autorización están en [SEGURIDAD.md](SEGURIDAD.md) §5.1.

## Seguridad y configuración

| Prioridad | Pendiente | Referencia |
|---|---|---|
| P1 | Copia externa de los respaldos (`GlucoLume_respaldo.ps1 -CopiaExterna`) y custodia de la frase fuera del equipo; probar la restauración desde esa copia. Requiere elegir el destino | H-01 |
| P1 | Aplicar `GlucoLume_permisos.sql` en la instancia real (SEGURIDAD §5.1 paso 3) | H-02 |
| P1 | Fijar con asesoría legal `AUDIT_RETENTION_MONTHS` y `PERSONNEL_RETENTION_MONTHS`; producción advierte mientras estén en 0 | H-04 |
| P2 | Rotar los secretos reales con el procedimiento de SEGURIDAD §5.1 (`JWT_PREVIOUS_SECRET`, `BRIDGE_PREVIOUS_TOKEN_UNTIL`) | H-08, GL-20 |
| P2 | Firma por línea del firmware / PIN Bluetooth por unidad / BLE (riesgo declarado en SEGURIDAD §4 punto 9, pendiente de aceptación expresa). **Requiere el hardware** | H-05 |
| P2 | Evaluar refresh token en cookie `HttpOnly` (impacto en CORS, CSRF y orígenes de login) | H-09 |
| P3 | Mejoras para una instalación productiva (no requeridas para el prototipo local): certificado de servidor en SQL Server con `DB_SERVER_CERTIFICATE`, BitLocker y copia de la clave de respaldos fuera del equipo (SEGURIDAD §5.1 pasos 4 y 5) | GL-07 |
| P3 | Antes de una instalación productiva: rotar `JWT_SECRET`, `SESSION_SECRET`, `BRIDGE_TOKEN` y credenciales de base y SMTP; no compartir la carpeta con los `.env` | GL-20 |
| P3 | Reconstruir la imagen del backend cuando Debian publique la corrección de `zlib` (1 vulnerabilidad alta sin parche); repetir los escaneos antes de publicar | GL-13 |
| P3 | Token por puente (hoy uno compartido, con rotación): requiere una tabla nueva | GL-11 |
| P3 | Plazo de conservación total de la auditoría aprobado con asesoría legal (propuesta 24–36 meses) | GL-16 |
| P3 | Redis para límites y monitor si hay más de una réplica; WAF delante de Nginx; MFA obligatoria para propietarios (decisión funcional y de costos) | GL-15, auditoría 18/10 |
| P3 | SQL Server Audit para cambios de límites y vigencia hechos fuera de la aplicación | Auditoría 18/10 |

## Base de datos (DEC-02)

| Prioridad | Pendiente | Referencia |
|---|---|---|
| P2 | Versionar la carpeta con Git y conservar el historial | GL-09 |

## Dispositivo y adquisición (DEC-01)

| Prioridad | Pendiente |
|---|---|
| P1 | Verificar con el Arduino real (USB y Bluetooth): adquisición sostenida, reconexión con el sensor activo, guardado completo, control temporal entre dos cuentas. **Requiere el hardware** |
| P2 | El control vive en memoria: un reinicio del backend lo libera; evaluar avisar a la cuenta afectada |
| P3 | Calidad de la señal PPG y de las estimaciones experimentales sobre personas (validación clínica, fuera del alcance del software) |

## Pruebas y entorno

| Prioridad | Pendiente | Referencia |
|---|---|---|
| P2 | Probar en el entorno final el envío SMTP real con certificado verificado y el circuito de confirmación del correo de resultados | GL-04, GL-08 |

## Privacidad y legal

| Prioridad | Pendiente |
|---|---|
| P1 | Revisión del texto de la política (versión 1.1) por la cátedra o el tutor y, si corresponde, por asesoría legal; base legal del envío de resultados por correo; comité de ética o inscripción de la base |
| P2 | Decidir si las mediciones de cuentas individuales eliminadas se anonimizan como las de pacientes (hoy quedan desidentificadas sin plazo) |
| P2 | Programar `purgeInstitutionalRetention` (hoy a mano, con `--confirmo-base`): programarlo sobre datos reales requiere autorización |
| P3 | Minimización del personal histórico (`PERSONNEL_RETENTION_MONTHS`, referencia de 120 meses a validar) |
| P3 | Nombres de personal minimizado en `Auditoria.detalle`: hoy se ocultan al leer. Una purga física solo con la política anterior aprobada, y la haría la cuenta de conservación (la API no modifica la auditoría, GL-03) |

## Funcionalidades incompletas

| Prioridad | Pendiente |
|---|---|
| P2 | Estimador de glucosa del servidor (`glucoseEstimator` es solo un punto de integración) |
| P3 | Suscripciones y pagos («Próximamente») |
| P3 | Exportaciones: deben usar `auditedExport`; `test_toda_exportacion_futura_pasa_por_audited_export` lo exige |
| P3 | Interfaz administrativa avanzada para la política de retención (la creación de una institución ya informa consentimiento y conservación) |

## Frontend

| Prioridad | Pendiente |
|---|---|
| P3 | Escala de espaciado, tipografía, radios y breakpoints; ~420 colores hex sueltos por migrar a tokens |
| P3 | `AppShell` compartido (sidebar, drawer y foco duplicados en `AuthenticatedLayout` y `PlatformLayout`), `Breadcrumbs`, `LoadingState`, variantes de `Kpi` |
| P3 | Mover las clases base (`.page-head`, `.panel`, `.data-list`) a una hoja global; dividir `AuthenticatedLayout.css` por módulo |
| P3 | Bundle inicial de ~887 kB tras la carga diferida; lo que queda son las pantallas de cuenta, mediciones, pacientes y adquisición |
| P3 | Exports usados solo en su propio archivo (candidatos de limpieza sin revisar uno por uno) |
| P3 | Cobertura visual pendiente: estados de error simulados, modales abiertos, formularios con validación e interacción con teclado |
