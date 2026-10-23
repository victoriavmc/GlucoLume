# H-09 — verificación de la cookie del refresh token en un Chromium real

Resultado del 23/10/2026: **24 de 24 comprobaciones correctas** (Chromium 1194 con Playwright, frontend en el servidor de desarrollo de Vite
en `http://localhost:5173`, API real en `http://localhost:8000`, SQLite temporal con una persona sintética; ni SQL Server ni Google ni correo).

Comprueba, con y sin «Recordarme»: el cuerpo del login trae `refreshToken: null`; la cookie `glucolume_refresh` existe, es `HttpOnly`,
`SameSite=Strict`, `Path=/api/v1/auth`, y persistente solo con «Recordarme»; `document.cookie` no la ve; el valor no aparece en `localStorage` ni
`sessionStorage` (solo la marca `glucolume.sessionHint`); recargar recupera la sesión y rota la cookie conservando el modo; cerrar sesión borra la cookie;
desde otro *site* (`127.0.0.1`) un `fetch` con credenciales queda bloqueado por CORS y un formulario no lleva la cookie y es rechazado, sin afectar la sesión legítima.

**Límites:** no es el build de producción ni HTTPS (el atributo `Secure` lo cubre `backend/tests/test_refresh_cookie.py`), no usa Nginx, no prueba Google
ni MFA en el navegador (sí en las pruebas HTTP) ni el flujo `VITE_LOGIN_ORIGIN`.

Para repetirla (solo datos sintéticos): `servidor_sintetico.py` (desde un entorno con las dependencias del backend; reemplazar `BACKEND` por la ruta de
`backend/`), `VITE_API_BASE_URL=http://localhost:8000 npx vite --port 5173` en `frontend/`, y `verificar_navegador.py` con `pip install playwright`
(ajustar `executable_path` al Chromium instalado).
