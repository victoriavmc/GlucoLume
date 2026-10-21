# Etapa 02A.2: Autenticación local y gestionión de sesiones

Mark: `[C]` code, `[D]` docs, `[NV]` not verified.

## Sources
- [D] `OpenCode/02A_01_RUTAS.md` only for route conclusions.
- [C] `backend/app/api/deps.py` lines 1-71.
- [C] `backend/app/services/auth.py` targeted lines 502-596, 790-939, 1035-1073.
- [C] `backend/app/core/security.py` lines 135-249.
- [C] `backend/app/models/userSession.py` lines 1-32.

## Routes and HTTP context
- [D] From 02A.1: base `/api/v1/auth`; `POST /login` -> `authService.loginLocal`; `POST /refresh` -> `authService.refreshSession`; `POST /logout` -> `authService.logout(db, auth.session)` + `telemetryService.releaseOnLogout(db, auth.user)`.
- [C] `DbSession = Annotated[Session, Depends(getDb)]` injects SQLAlchemy session.
- [C] `_bearer = HTTPBearer(auto_error=False)` reads Bearer credential. `getAuthContext` raises `TOKEN_INVALIDO` if credential absent, decodes with `decodeAccessToken`, maps `ExpiredSignatureError` to `TOKEN_VENCIDO`, other `InvalidTokenError` to `TOKEN_MALFORMADO`, and calls `resolveAccessSession(db, claims)`.
- [C] `AuthContext` is frozen with `user` and `session`; `CurrentAuth` uses it as dependency.
- [C] `getStreamAuthContext` resolves identity and closes db for SSE streams.

## Local login: `loginLocal`
- [C] `loginLocal` receives `db`, `identificador`, password and optional `clientInfo`. It searches with `_findUserByIdentifier`.
- [C] If user missing, expired pending, or lacks local credential, it calls `verifyDummyPassword`, audits failure, commits and raises generic `CREDENCIALES_INVALIDAS`.
- [C] If credential locked, it does not verify password or increment counter; audits `CUENTA_BLOQUEADA` and raises lock error with `bloqueadoHasta`.
- [C] If lock expired, `_unlockIfExpired` resets state before evaluating attempt.
- [C] Password verification uses `security.verifyPassword(password, credential.passwordHash)`. Success calls `_registerSuccessfulPassword`; failure calls `_registerFailedPassword` and may activate lock.
- [C] If lock activates after failure, it registers security block event, sends `INTENTO_ACCESO_INUSUAL` notification and raises lock error.
- [C] If password invalid without lock, raises generic `CREDENCIALES_INVALIDAS`.
- [C] On success requires active account via `_requireActive`, then calls `_completePrimaryAuthentication` with `METHOD_PASSWORD`.
- [C] `_completePrimaryAuthentication`: if MFA enabled, returns `LoginResponse` estado `MFA_REQUERIDO` with `challengeToken` and `challengeExpiresIn`; otherwise returns `_authenticatedResponse`. If MFA enabled but server setting unavailable, raises `MFA_NO_DISPONIBLE`.
- [NV] Frontend login UX, DB persistence timing and actual HTTP runtime behavior not verified.

## Authenticated session creation
- [C] `_authenticatedResponse` calls `_createSession(db, user)`, optional email notification when `notificarNuevoInicioSesion`, and returns `LoginResponse` estado `AUTENTICADO` with `tokens`, `requiereCompletarPerfil`, `fieldsFaltantes`.
- [C] `_createSession` generates opaque refresh token with `generateOpaqueToken`, creates `UserSession` with `refreshTokenHash = hashOpaqueToken(refreshToken)` and `fechaExpiracion = now + REFRESH_TOKEN_EXPIRE_DAYS`, commits it, and returns `TokenPair` with `accessToken = createAccessToken(user.idUsuario, session.idSesion)`, raw `refreshToken`, and `expiresIn = JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60`.

## JWT access
- [C] `createAccessToken` sets claims `sub` user, `sid` session, `typ = TOKEN_TYPE_ACCESS`; `_encodeJwt` adds `iss`, `aud`, `iat`, `exp` and signs with `settings.JWT_SECRET.get_secret_value()` and `settings.JWT_ALGORITHM`. No secret value inspected.
- [C] `_decodeJwt` uses only configured algorithms list, audience, issuer, and requires `exp`, `iat`, `sub`, `typ`; rejects unexpected `typ`. `decodeAccessToken` also requires `sid`.
- [C] `resolveAccessSession` validates `sub`, `sid`, session owner, no revocation, expiration future, user active.

## Refresh rotation and reuse revocation
- [C] `refreshSession` finds `UserSession` by SHA-256 hash of submitted refresh token. Unknown token raises `SESION_INVALIDA`.
- [C] If found and not revoked, updates its `fechaRevocacion = now`. If update affects != 1 row, refresh was reused/already revoked; calls `_revokeAllSessions`, registers `REFRESH_REUTILIZADO`, commits and raises `REFRESH_REUTILIZADO`.
- [C] After valid first use, checks `fechaExpiracion > now`, user exists and `estado == ESTADO_ACTIVO`; invalid raises `SESION_INVALIDA`.
- [C] Valid refresh returns `_createSession(db, user)`, so access and refresh tokens rotate and new session is stored.

## Logout
- [C] `logout(db, session)` updates that `UserSession` where `fechaRevocacion is None`, setting `fechaRevocacion = now`, then commits. It marks revocation; it does not delete row or revoke all user sessions in that path.
- [D] Route `POST /logout` additionally releases telemetry per route doc.

## Session model
- [C] `UserSession` maps SQLAlchemy class to table `SesionUsuario`.
- Fields:
  - `idSesion` UUID PK default `newid()`
  - `idUsuario` FK to `Usuario.idUsuario`
  - `refreshTokenHash` `NVARCHAR(255)`
  - `fechaCreacion` DATETIME2 default `sysutcdatetime()`
  - `fechaExpiracion` DATETIME2
  - `fechaRevocacion` nullable DATETIME2
- Constraints: unique refresh hash `UQ_SesionUsuario_refreshTokenHash`; check `fechaExpiracion > fechaCreacion`.
- [C] Relationship: `usuario: User`.

## Limits of conclusions
- [NV] No frontend, no Google OAuth detail, no institutional/groups flows, no runtime tests, no SQL execution.
- [NV] MFA challenge verification flow only mentioned because local login can branch there; not documented as separate flow.
- [NV] Exact HTTP status mapping, database transaction behavior under concurrency and UI behavior not verified.

**ETAPA 02A.2 COMPLETA: Autenticación local y gestionión de sessions documentadas.**
