# GlucoLume

Plataforma experimental para la adquisición, el almacenamiento y el análisis de señales ópticas (oximetría y estimación de glucosa no
invasiva), desarrollada como trabajo de titulación de la Licenciatura en Sistemas de Información.

> **Aviso:** GlucoLume es un prototipo académico. Sus resultados son experimentales, no tienen validez diagnóstica y no reemplazan una
> medición clínica certificada. La seguridad del software no implica una validación clínica del dispositivo.

## Qué hace

- **Adquisición:** un Arduino UNO con sensor MAX30100/MAX30102 envía por USB o Bluetooth sus métricas (frecuencia cardíaca, SpO₂, índice óptico
  y glucosa experimental o DEMO) a un puente de Windows, que las entrega al backend.
- **Mediciones:** sesión de medición con validación de estabilidad, historial, gráficos y matrices de referencia de glucosa.
- **Cuentas:** usuarios individuales, grupos familiares con privacidad por integrante, instituciones (propietario, moderador y operador) con
  pacientes, y administración de la plataforma.
- **Seguridad:** Argon2id, JWT con sesiones revocables, MFA TOTP, Google OAuth con PKCE, autorización centralizada, aislamiento institucional y
  auditoría.
- **Dispositivo compartido (DEC-01):** el único equipo experimental lo usan todas las cuentas habilitadas, de a una por vez y sin compartir datos.

## Arquitectura

```text
Arduino + MAX30100 ──USB/Bluetooth──▶ Puente (Windows, Python) ──HTTP + token──┐
                                                                                ▼
Navegador ──HTTPS──▶ Caddy (opcional) ──▶ Nginx + React (SPA) ──/api──▶ FastAPI ──ODBC──▶ SQL Server
```

| Carpeta | Contenido |
|---|---|
| `backend/` | API FastAPI + SQLAlchemy (SQL Server); servicios, trabajos programados (`app/jobs`), CLI de administración (`app/cli`) y pruebas |
| `frontend/` | Aplicación React (Vite) servida por Nginx |
| `database/reference/` | Esquema SQL consolidado `GlucoLume_DB_v5.sql` (DEC-02, 34 tablas), matriz global `MATRIZ.SQL`, scripts de permisos (H-02) y de actualización de bases instaladas, y `BorrarRap.sql` (vacía datos: no es instalación) |
| `acquisition/` | Puente serie de Windows (`bridge/`) y dependencias |
| `firmware/` | Sketches de Arduino (`GlucoLume_MAX30100/` y variante optimizada) |
| `docker/`, `compose*.yaml` | Contenerización (Nginx, Caddy, SQL Server y Redis opcionales, compilación de firmware) |
| `docs/` | Documentación |

## Inicio rápido

Requiere Docker y un `.env` (copiar `.env.example` y generar los secretos con los comandos que incluye). Docker no crea ni migra la base:
prepararla antes con el esquema v5 ([docs/BASE_DE_DATOS.md](docs/BASE_DE_DATOS.md) §2: instalación nueva; §3: actualización sin pérdida de datos).
**Guía paso a paso para Windows (PowerShell, Docker Desktop):** [docs/DESPLIEGUE.md](docs/DESPLIEGUE.md) §3.0.

```bash
docker compose up --build -d              # backend + lifecycle + frontend → http://glucolume.local
docker compose up -d backend frontend     # SIN lifecycle (que elimina y anonimiza cuentas vencidas): recomendado mientras se prepara una instalación
docker compose --profile db up -d db      # opcional: SQL Server en contenedor, con volumen persistente y sin puertos publicados
docker compose logs -f backend
docker compose down
```

Redis opcional para los límites compartidos: `compose.redis.yaml`. Desarrollo con recarga: `docker compose -f compose.yaml -f compose.dev.yaml up --build`. Producción, variables, `glucolume.local`, operación y
problemas frecuentes: [docs/DESPLIEGUE.md](docs/DESPLIEGUE.md). Pruebas: `cd backend && python -m pytest` y `cd frontend && npm test`.

## Estado (23/10/2026)

La remediación del informe de ciberseguridad del 21/10/2026 (H-01 a H-17) está integrada en `master`; **la auditoría no se considera aprobada**: siguen abiertos H-03 (cifrado en reposo), H-05 (canal Bluetooth) y H-10 (`zlib` sin corrección publicada), y quedan verificaciones que solo pueden hacerse en Windows, con la placa real o con decisión legal.
Detalle por hallazgo: [docs/SEGURIDAD.md](docs/SEGURIDAD.md) §2.0.1–§2.0.3; pendientes: [docs/PENDIENTES.md](docs/PENDIENTES.md).

## Documentación

| Documento | Contenido |
|---|---|
| [docs/DISPOSITIVOS_Y_ADQUISICION.md](docs/DISPOSITIVOS_Y_ADQUISICION.md) | Dispositivo compartido (DEC-01), control temporal, puente, protocolo serie, identidad e inventario |
| [docs/BASE_DE_DATOS.md](docs/BASE_DE_DATOS.md) | Esquema consolidado (DEC-02), instalación, bases existentes, respaldo y permisos |
| [docs/DESPLIEGUE.md](docs/DESPLIEGUE.md) | Docker, variables, desarrollo, producción y operación |
| [docs/SEGURIDAD.md](docs/SEGURIDAD.md) | Controles, auditoría de la aplicación y estado de los hallazgos |
| [docs/PRIVACIDAD_Y_RETENCION.md](docs/PRIVACIDAD_Y_RETENCION.md) | Consentimientos, política de privacidad, retención y anonimización |
| [docs/FRONTEND.md](docs/FRONTEND.md) | Estructura, sistema de diseño y accesibilidad |
| [docs/funcional/](docs/funcional/) | Especificación por modalidad: [individual](docs/funcional/INDIVIDUAL.md), [grupo familiar](docs/funcional/GRUPO_FAMILIAR.md), [institución](docs/funcional/INSTITUCION.md), [plataforma](docs/funcional/PLATAFORMA.md) |
| [docs/MANUAL_USUARIO.md](docs/MANUAL_USUARIO.md) | Manual de uso por tipo de cuenta |
| [docs/RENDIMIENTO.md](docs/RENDIMIENTO.md) | Revisión de rendimiento del 23/10/2026: mediciones antes/después, causas, correcciones y limitaciones |
| [docs/HISTORIAL.md](docs/HISTORIAL.md) | Cambios, correcciones, decisiones y pruebas, en orden cronológico |
| [docs/PENDIENTES.md](docs/PENDIENTES.md) | Problemas abiertos y validaciones necesarias |
| [docs/seguridad/auditorias/](docs/seguridad/auditorias/) | Auditorías de ciberseguridad (PDF, evidencia fechada) |
| [docs/seguridad/VERIFICACIONES_PENDIENTES_WINDOWS.md](docs/seguridad/VERIFICACIONES_PENDIENTES_WINDOWS.md) | Qué se verificó (entorno, resultado, evidencia) y qué falta en Windows |
| [docs/evidencias/](docs/evidencias/) | Evidencias: escaneo de imágenes, pruebas de concurrencia y la [validación integral del 23/10/2026](docs/evidencias/validacion_integral/README.md) (scripts reproducibles y resultados) |

**Cómo mantenerla:** cada funcionalidad nueva actualiza su documento; cada problema resuelto y verificado se registra en
[HISTORIAL.md](docs/HISTORIAL.md) y sale de [PENDIENTES.md](docs/PENDIENTES.md). No se crean documentos nuevos por cada corrección.
