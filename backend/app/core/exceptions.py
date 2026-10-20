# Exceptions - Errores de dominio comunes
#
# Los servicios lanzan AuthError con un código estable; la capa HTTP traduce el código
# a un status (backend/app/api/errors.py). Los servicios no conocen HTTP.


class AuthError(Exception):
    def __init__(self, code: str, message: str, *, retryAfterSeconds: int | None = None, motivo: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        # Motivo técnico normalizado del rechazo (código estable, nunca texto libre): lo usa el monitor de seguridad para distinguir, p. ej.,
        # un token vencido (uso normal) de uno malformado. No viaja en la respuesta.
        self.motivo = motivo
        # Segundos hasta poder reintentar (bloqueos temporales); la capa HTTP lo envía como Retry-After.
        self.retryAfterSeconds = retryAfterSeconds
