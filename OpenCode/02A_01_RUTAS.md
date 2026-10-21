# ETAPA 02A.1 - RUTAS DEL BACKEND

## FastAPI initialization
- File: `backend/app/main.py`.
- Creates `app = FastAPI(` near line 51.
- Title: `"GlucoLume API"`; `lifespan=maintenance.lifespan`.
- Docs only outside production: `/docs`, `/redoc`, `/openapi.json`.
- Health route: `GET /healthz`.
- Middleware: `SessionMiddleware`, `CORSMiddleware`, `SecurityHeadersMiddleware`, `RequestContextMiddleware`.
- Exception handlers: `authErrorHandler`, `validationErrorHandler`.
- Routers registered with prefix `/api/v1`: `authRouter`, `contactRouter`, `institutionsRouter`, `groupsRouter`, `measurementsRouter`, `acquisitionRouter`, `telemetryRouter`, `platformRouter`, `matricesRouter`, `auditRouter`, `devicesRouter`, `institutionDevicesRouter`, `institutionAuditRouter`.

## Auth router
- File: `backend/app/api/v1/auth.py`.
- Defines `router = APIRouter(prefix="/auth", tags=["auth"])`.
- All auth routes below are under `/api/v1/auth`.
- Auth dependency: `CurrentAuth`, `DbSession` imported from `backend/app/api/deps.py`.
- Services invoked: `authService`, `userService`, `emailService`, `mfaService`, `mfaRecoveryService`, `accountActivationService`, `accountDeletionService`, `consentService`, `googleOAuth`, `telemetryService`, `rateLimit`.

## Auth endpoints
| Final path | Function | Main service call |
|---|---|---|
| `POST /register` | `register` | `authService.registerLocal` |
| `GET /verify-email` | `verifyEmail` | `authService.verifyEmail` |
| `POST /verify-email/resend` | `resendVerification` | `authService.resendVerification` |
| `POST /login` | `login` | `authService.loginLocal` |
| `GET /google/login` | `googleLogin` | `googleOAuth.authorizeRedirect` |
| `GET /google/authorization-url` | `googleAuthorizationUrl` | `googleOAuth.prepareAuthorization` |
| `GET /google/callback` | `googleCallback` | `googleOAuth.fetchIdentity`, `authService.identifyGoogleUser`, `createGoogleExchangeCode` |
| `POST /google/exchange` | `googleExchange` | `authService.exchangeGoogleCode` |
| `POST /session-transfer` | `sessionTransfer` | `authService.createSessionTransferCode` |
| `POST /mfa/verify` | `mfaVerify` | `authService.verifyMfaChallenge` |
| `POST /mfa/recovery/start` | `mfaRecoveryStart` | `mfaRecoveryService.startRecovery` |
| `POST /mfa/recovery/verify` | `mfaRecoveryVerify` | `mfaRecoveryService.verifyRecovery` |
| `POST /mfa/setup` | `mfaSetup` | `mfaService.startSetup` |
| `POST /mfa/enable` | `mfaEnable` | `mfaService.enable` |
| `POST /me/mfa/recovery/start` | `accountMfaRecoveryStart` | `mfaRecoveryService.startAccountRecovery` |
| `POST /me/mfa/recovery/verify` | `accountMfaRecoveryVerify` | `mfaRecoveryService.completeAccountRecovery`, `authService.accountSummary` |
| `POST /mfa/disable` | `mfaDisable` | `mfaService.disable` |
| `POST /refresh` | `refresh` | `authService.refreshSession` |
| `POST /logout` | `logout` | `authService.logout`, `telemetryService.releaseOnLogout` |
| `GET /me` | `me` | `authService.accountSummary` |
| `PATCH /me/profile` | `updateMyProfile` | `userService.updateProfile`, `authService.accountSummary` |
| `POST /password` | `setPassword` | `authService.setLocalPassword` |
| `POST /password/forgot` | `forgotPassword` | `authService.requestPasswordReset` |
| `POST /password/reset` | `resetPassword` | `authService.resetPassword` |
| `POST /password/change` | `changePassword` | `authService.changeLocalPassword` |
| `PUT /me/notifications/new-login` | `updateNewLoginNotification` | `authService.setNewLoginNotification` |
| `POST /notifications/new-login/unsubscribe` | `unsubscribeNewLogin` | `authService.unsubscribeNewLogin` |
| `GET /account-deletion/preview` | `previewAccountDeletion` | `accountDeletionService.describeDeletion` |
| `POST /account-deletion/request` | `requestAccountDeletion` | `accountDeletionService.requestDeletion` |
| `POST /account-deletion/confirm` | `confirmAccountDeletion` | `accountDeletionService.confirmDeletion` |
| `POST /account-activation/check` | `checkAccountActivation` | `accountActivationService.checkActivation` |
| `POST /account-activation/complete` | `completeAccountActivation` | `accountActivationService.completeActivation` |
| `GET /consents` | `getConsents` | `consentService.status` |
| `PUT /consents/datos-experimentales` | `setExperimentalConsent` | `consentService.setExperimentalConsent` |

## Rate limits
- `rateLimit("register")`, `verification`, `resend`, `login`, `googleExchange`, `mfa`, `mfaRecovery`, `refresh`, `passwordForgot`, `passwordReset`, `unsubscribe`, `accountDeletion`, `activation`.

## Conclusions
- Auth router owns all authentication-related HTTP surface: local account, verification, login, Google OAuth, session transfer, MFA, password, account deletion, activation, and consents.
- HTTP layer translates request/response and calls services; rules remain outside this file.

## Unverified
- Service internals not inspected.
- Request bodies and response models inferred from schema imports and decorators.
- Security behavior not audited.

**ETAPA 02A.1 COMPLETA: Rutas del backend documentadas.**