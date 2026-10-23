# Deps - Dependencias HTTP compartidas

from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.api.rateLimit import checkAuthenticated
from app.core.exceptions import AuthError
from app.core.security import decodeAccessToken
from app.db.session import getDb
from app.models.user import User
from app.models.userSession import UserSession
from app.services import auth as authService
from app.services import platform as platformService

_bearer = HTTPBearer(auto_error=False)

DbSession = Annotated[Session, Depends(getDb)]


@dataclass(frozen=True)
class AuthContext:
    user: User
    session: UserSession


def getAuthContext(
    request: Request,
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> AuthContext:
    if credentials is None:
        raise AuthError("TOKEN_INVALIDO", "Se requiere autenticación.", motivo="SIN_CREDENCIALES")
    checkAuthenticated(request)  # H-11: límite por IP también para quien presenta un token (un token robado no extrae datos sin tope)
    try:
        claims = decodeAccessToken(credentials.credentials)
    except jwt.ExpiredSignatureError as error:  # uso normal: el cliente renueva la sesión
        raise AuthError("TOKEN_INVALIDO", "Token inválido.", motivo="TOKEN_VENCIDO") from error
    except jwt.InvalidTokenError as error:
        raise AuthError("TOKEN_INVALIDO", "Token inválido.", motivo="TOKEN_MALFORMADO") from error
    user, session = authService.resolveAccessSession(db, claims)
    return AuthContext(user=user, session=session)


CurrentAuth = Annotated[AuthContext, Depends(getAuthContext)]


def getStreamAuthContext(
    request: Request,
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> AuthContext:
    """Igual que getAuthContext para los flujos SSE (minutos u horas): una vez resuelta la identidad cierra la sesión de base para
    devolver la conexión al pool. Sin esto, cada stream retendría una conexión durante toda su vida y unos pocos agotarían el pool.
    El usuario y la sesión quedan cargados (desasociados); el stream no vuelve a usar esta sesión de base."""
    context = getAuthContext(request, db, credentials)
    db.close()
    return context


StreamAuth = Annotated[AuthContext, Depends(getStreamAuthContext)]


def platformMfaGate(auth: CurrentAuth, db: DbSession) -> None:
    """Rutas globales de plataforma (auditoría, dispositivos, matrices): una cuenta administrativa sin MFA no opera.
    No afecta a las demás cuentas: sus permisos siguen siendo los de cada módulo."""
    if platformService.isPlatformAccount(auth.user):
        platformService.requireMfaEnabled(db, auth.user)


PlatformMfaGate = Depends(platformMfaGate)
