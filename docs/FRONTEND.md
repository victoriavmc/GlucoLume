# Frontend

Aplicación React (Vite) en `frontend/`: estructura, sistema de diseño vigente, accesibilidad y cómo se valida. Lo pendiente está en
[PENDIENTES.md](PENDIENTES.md); la cronología de la modernización visual, en [HISTORIAL.md](HISTORIAL.md).

## 1. Estructura

| Elemento | Detalle |
|---|---|
| Estilos | CSS global plano (sin CSS Modules ni Tailwind): `styles/global.css` (tokens y base), `styles/components.css` (`ui-*`, `field-*`), `layouts/AuthenticatedLayout.css` y hojas por módulo |
| Íconos y gráficos | `lucide-react`; gráficos SVG propios en `components/*Chart.jsx`; `qrcode.react` para MFA |
| Pruebas | Vitest + Testing Library (`src/**/*.test.jsx`); simulador de API en `src/test/helpers.js` |
| Galería del sistema de diseño | `frontend/gallery.html` + `src/dev/gallery.jsx` (solo servidor de desarrollo, no entra en el build) |
| Autorización | La decide el backend; el menú solo oculta lo que el rol no puede usar |

| Layout | Archivo | Rutas |
|---|---|---|
| Público | Cada página trae su cabecera (`Navbar`/`SiteFooter` en la landing, `AuthShell` en el acceso) | `/`, `/login`, `/registro`, `/recuperar-contrasena`, `/restablecer-contrasena`, `/verificar-correo`, `/activar-cuenta`, `/privacidad`, `/cuenta/eliminar/confirmar`, `/auth/google/callback` |
| Espacio privado | `layouts/AuthenticatedLayout.jsx` + `Sidebar.jsx` | `/app/*` (sidebar fijo; drawer en pantallas angostas) |
| Plataforma | `layouts/PlatformLayout.jsx` | `/plataforma/*` (accesos propios `/plataforma/login|activar|recuperar|restablecer`; `/administracion/login|activar`) |
| Institución | `institutions/InstitutionLayout.jsx` + `InstitutionSubnav.jsx` | `/app/instituciones/:id/*` |
| Grupo | `groups/GroupLayout.jsx` | `/app/grupo/:id/*` |

Menú de `/app` por tipo de cuenta: Inicio, Perfil, Seguridad (todos); Instituciones (institucional); Mediciones, Conectar dispositivo, Grupo
(individual); Dispositivos y Matrices globales (plataforma); Auditoría (administrador). Secciones de institución por permiso: Panel, Personal,
Pacientes, Dispositivos, Conectar dispositivo (operador), Matrices, Administración, Actividad, Auditoría (propietario).

**Separación de orígenes** (`auth/OriginGuard.jsx`): `/login` en `FRONTEND_LOGIN_ORIGIN` y el resto en `FRONTEND_APP_ORIGIN` cuando están
definidos ([DESPLIEGUE.md](DESPLIEGUE.md) §3.1).

**Dispositivo compartido** (DEC-01): `api/acquisitionApi.js` (`takeDeviceControl`, `releaseDeviceControl`); «Usar dispositivo» y «Dejar de
usar» en `pages/Account/acquisition/BridgeSettings.jsx`; el diagnóstico usa `edadUltimaLectura` cuando la cuenta no tiene el control
(`connectModel.js`, `useDeviceReadiness.js`); las lecturas en vivo se muestran solo dentro de la sesión de medición (`DeviceSession.jsx`).

## 2. Sistema de diseño vigente

### 2.1 Tokens (`:root` de `global.css`)

| Grupo | Tokens | Valores |
|---|---|---|
| Rojo de marca | `--red-600` / `--red-700` / `--red-100` / `--red-50` | `#e3101e` / `#c20d19` / `#fde6e8` / `#fff4f5` |
| Azul | `--blue-700` / `--blue-600` / `--blue-100` / `--blue-50` | `#1d4ed8` / `#2563eb` / `#e3ecfd` / `#f3f7ff` |
| Texto | `--ink-900` / `--ink-700` / `--ink-500` / `--ink-400` | `#0f1730` / `#34405a` / `#5c6680` / `#667085` |
| Decoración (nunca texto) | `--ink-300` | `#a3abbd` (2,3:1) |
| Superficies y bordes | `--surface`, `--page`, `--line`, `--line-soft` | `#fff`, `#fbfbfd`, `#e7e9f0`, `#f1e6e8` |
| Estados | `--ok-50/200/700`, `--warn-50/500/700`, `--danger-50/200/700`, `--info-50/200/700` | `--warn-500` solo gráficos y bordes |
| Radios | `--radius-lg` / `--radius-md` / `--radius-sm` / `--radius-pill` | 22 / 14 / 12 / 999 px |
| Foco | `--focus-ring` | `3px solid var(--red-600)` |
| Sombras | `--shadow-card` / `--shadow-soft` | sobre `rgba(15,23,48,…)` |
| Tipografía y layout | `--font`, `--gutter`, `--max` | Inter/Segoe UI/system-ui; `clamp(16px,4vw,48px)`; 1240 px |
| Layout interno | `--sidebar-width`, `--content-max`, `--form-max`, `--gap-card`, `--gap-section`, `--pad-card` | 272, 1520, 1160, 20, 28 px, `clamp(20px,2vw,24px)` |
| Landing (acotado a `.landing`) | `--max`, `--nav-h`, `--section-y` | 1320 px, 80 px, `clamp(48px,5.5vw,80px)` |

Contraste (WCAG): `--ink-900` > 10:1; `--ink-700` 10:1; `--ink-500` 5,5–5,7:1; `--ink-400` 4,6–5,0:1; blanco sobre `--red-600` 4,8:1.
**`--red-600` sobre fondos rosados no alcanza para texto: usar `--red-700`** (5,3–5,8:1). `--ink-300` nunca para texto.

### 2.2 Componentes

| Componente | Archivo | Uso |
|---|---|---|
| `TextField`, `SelectField`, `TextAreaField` (contador), `CheckField`, `RadioField`, `Alert`, `SubmitButton` | `components/FormControls.jsx` | Campos con etiqueta, ayuda y error asociados (`aria-describedby`); casillas de 24 px |
| `Tabs` / `TabPanel` / `NavTabs` | `components/Tabs.jsx` | Patrón ARIA completo (flechas, Inicio/Fin, tabindex rotativo); variantes `pill`, `soft`, `underline` |
| `Modal` | `components/Modal.jsx` | Portal, fondo inerte, foco atrapado, Escape, foco devuelto; `alertdialog` o `dialog` |
| `Badge`, `OriginBadge` (y `DemoBadge` en `measurements/DeviceReadout.jsx`) | `components/Badge.jsx` | Tonos por significado (`success`, `warning`, `danger`, `info`, `brand`, `neutral`); el texto da el significado |
| `EmptyState` | `components/EmptyState.jsx` | Vacíos `center`, `framed`, `inline` |
| `PageHeader` | `components/PageHeader.jsx` | Título, descripción, acciones y «volver»; `as="h2"` dentro de una institución |
| `SkipLink` | `components/SkipLink.jsx` | «Saltar al contenido» en todos los layouts y páginas públicas |
| `Kpi`, `KpiGrid`, `ChartCard`, `PeriodFilter` | `components/dashboard.jsx` | Dashboards |

Clases base: `.btn*` (46 px, pill), `.alert*`, `.field*`, `.modal*`, `.check`, `.spinner`, `.skip-link`, `.visually-hidden`/`.sr-only`,
`.link-button` (44 px). Layout privado: `.page` (`.is-wide`, `.is-form`), `.page-head`, `.panel`, `.summary-grid`, `.data-list`,
`.table-scroll`, `.back-link`, `.breadcrumbs`; las grillas usan `minmax(0, 1fr)` para no desbordar.

Estados interactivos: foco `:focus-visible` sólido (4,8:1), campos con borde rojo y halo, `:disabled` con opacidad 0,6 y campos
deshabilitados en gris, `prefers-reduced-motion` respetado.

## 3. Accesibilidad

Resultados del barrido de 243 vistas (56 pantallas × 1440/768/390 px, cinco roles, datos sintéticos) al 17/10/2026: 0 fallos de contraste de
texto (eran 251), «Saltar al contenido» en todas las pantallas, un `h1` por pantalla, 0 desbordes horizontales a 390 px, 0 objetivos táctiles
< 24 px, 0 saltos de encabezado, 0 errores de consola. Se conservan justificados: 297 controles entre 24 y 44 px y el texto decorativo de la
maqueta de la landing (`aria-hidden`).

## 4. Validación

- **Vitest**: `npm test` (o en contenedor, [DESPLIEGUE.md](DESPLIEGUE.md) §3). Última suite completa: 677/677 (19/10/2026).
- **Capturas y métricas visuales**: se hicieron con herramientas externas al repositorio (API simulada con datos sintéticos, Chrome por CDP,
  comparador de píxeles y de métricas de accesibilidad). Ni las herramientas ni las capturas forman parte de este proyecto.
- **Build**: `vite build` (Vite 6.4.4 del proyecto; no usar `npx vite`, que puede descargar otra versión). El bundle inicial bajó de 1 137 kB a
  887 kB con `React.lazy` (plataforma, matrices, auditoría, dispositivos, analítica, grupos, transferencias, reasignaciones, actividad y
  ficha del personal se descargan al visitarlas); sigue por encima del aviso de 500 kB de Vite.
