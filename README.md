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
| `database/reference/` | Esquema SQL consolidado `GlucoLume_DB_v5.sql` (DEC-02), matriz global `MATRIZ.SQL` y `BorrarRap.sql` (vacía datos: no es instalación) |
| `acquisition/` | Puente serie de Windows (`bridge/`) y dependencias |
| `firmware/` | Sketches de Arduino (`GlucoLume_MAX30100/` y variante optimizada) |
| `docker/`, `compose*.yaml` | Contenerización (Nginx, Caddy, SQL Server opcional, compilación de firmware) |
| `docs/` | Documentación |

## Inicio rápido

Requiere Docker y un `.env` (copiar `.env.example` y generar los secretos con los comandos que incluye). Docker no crea ni migra la base:
prepararla antes con el esquema v5 ([docs/BASE_DE_DATOS.md](docs/BASE_DE_DATOS.md)).

```bash
docker compose up --build -d              # backend + lifecycle + frontend → http://glucolume.local
docker compose up -d backend frontend     # sin el servicio lifecycle (que elimina y anonimiza cuentas vencidas)
docker compose logs -f backend
docker compose down
```

Desarrollo con recarga: `docker compose -f compose.yaml -f compose.dev.yaml up --build`. Producción, variables, `glucolume.local`, operación y
problemas frecuentes: [docs/DESPLIEGUE.md](docs/DESPLIEGUE.md). Pruebas: `cd backend && python -m pytest` y `cd frontend && npm test`.

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
| [docs/HISTORIAL.md](docs/HISTORIAL.md) | Cambios, correcciones, decisiones y pruebas, en orden cronológico |
| [docs/PENDIENTES.md](docs/PENDIENTES.md) | Problemas abiertos y validaciones necesarias |
| [docs/seguridad/auditorias/](docs/seguridad/auditorias/) | Auditorías de ciberseguridad (PDF, evidencia fechada) |
| [docs/evidencias/](docs/evidencias/) | Evidencias históricas (escaneo de imágenes, pruebas de concurrencia) |

**Cómo mantenerla:** cada funcionalidad nueva actualiza su documento; cada problema resuelto y verificado se registra en
[HISTORIAL.md](docs/HISTORIAL.md) y sale de [PENDIENTES.md](docs/PENDIENTES.md). No se crean documentos nuevos por cada corrección.
