# Auth - Contratos de la API de autenticación (no corresponde a una tabla)

from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)

from app.core.security import (
    COMMON_PASSWORD_ERROR,
    isCommonPassword,
    passwordContainsPersonalData,
    passwordPolicyErrors,
)
from app.schemas.user import TipoCuentaPublica, UserCreate, UserRead, validateUsername
from app.utils.normalizers import normalizeEmail, normalizeUpper

# Las contraseñas no se normalizan: se conservan exactamente como se ingresan.
Password = Annotated[SecretStr, Field(min_length=1)]


def _checkPasswordPolicy(value: SecretStr) -> SecretStr:
    errors = passwordPolicyErrors(value.get_secret_value())
    if errors:
        raise ValueError("La contraseña debe tener " + ", ".join(errors) + ".")
    if isCommonPassword(value.get_secret_value()):
        raise ValueError(COMMON_PASSWORD_ERROR)
    return value


# Contraseña nueva (registro o alta): aplica la política. El login usa Password, sin política.
NewPassword = Annotated[SecretStr, AfterValidator(_checkPasswordPolicy)]
# Mensaje de error, no una contraseña (falso positivo de bandit B105).
PASSWORD_PERSONAL_DATA_ERROR = (  # nosec B105
    "La contraseña no puede contener tu nombre, apellido, nombre de usuario ni correo electrónico."
)


class RegisterRequest(UserCreate):
    password: NewPassword
    # Tipo de cuenta (CK_Usuario_tipoCuenta), solo los públicos:
    #   CONSUMIDOR_FINAL      uso personal: mediciones propias y grupo familiar;
    #   USUARIO_INSTITUCIONAL cuenta para trabajar con una o más instituciones. NO crea ninguna institución ni
    #                         vínculo: después crea una institución o la incorpora una existente.
    tipoCuenta: TipoCuentaPublica = "CONSUMIDOR_FINAL"
    # Confirmación de lectura de la Política de Privacidad. Sin ella el backend rechaza el registro
    # (POLITICA_NO_ACEPTADA): la validación no depende del frontend. Queda registrada en ConsentimientoUsuario.
    aceptaPoliticaPrivacidad: bool = False

    @field_validator("tipoCuenta", mode="before")
    @classmethod
    def normalizarTipoCuenta(cls, value):
        return normalizeUpper(value)

    @field_validator("usuario")
    @classmethod
    def validarUsuario(cls, value: str | None) -> str | None:
        return validateUsername(value)

    @model_validator(mode="after")
    def validarPasswordSinDatosPersonales(self):
        if passwordContainsPersonalData(
            self.password.get_secret_value(), self.usuario, self.correoElectronico, self.nombre, self.apellido
        ):
            raise ValueError(PASSWORD_PERSONAL_DATA_ERROR)
        return self


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Correo electrónico o nombre de usuario: si contiene "@" se busca por correo, si no por username.
    identificador: Annotated[
        str,
        Field(
            min_length=1,
            max_length=254,
            description='Correo electrónico o nombre de usuario de la cuenta. Con "@" se interpreta como correo.',
            examples=["persona@example.com", "victoria"],
        ),
    ]
    password: Password


class TokenPair(BaseModel):
    accessToken: str
    refreshToken: str
    tokenType: Literal["bearer"] = "bearer"
    expiresIn: int


class LoginResponse(BaseModel):
    """AUTENTICADO entrega la sesión; MFA_REQUERIDO entrega solo el token de desafío.

    requiereCompletarPerfil / camposFaltantes se informan con la sesión (estado AUTENTICADO):
    el frontend muestra la pantalla para completar el perfil propio de GlucoLume.
    """

    estado: Literal["AUTENTICADO", "MFA_REQUERIDO"]
    tokens: TokenPair | None = None
    challengeToken: str | None = None
    challengeExpiresIn: int | None = None
    requiereCompletarPerfil: bool | None = None
    camposFaltantes: list[str] = []


class RefreshRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refreshToken: Annotated[str, Field(min_length=1, max_length=512)]


class MfaVerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    challengeToken: Annotated[str, Field(min_length=1, max_length=2048)]
    codigo: Annotated[str, Field(max_length=10)] | None = None
    codigoRecuperacion: Annotated[str, Field(max_length=32)] | None = None

    @model_validator(mode="after")
    def validarUnFactor(self):
        if (self.codigo is None) == (self.codigoRecuperacion is None):
            raise ValueError("Indicar exactamente uno: codigo o codigoRecuperacion.")
        return self


class MfaRecoveryStartRequest(BaseModel):
    """Paso 1 de "perdí mi aplicación autenticadora": parte del desafío MFA del login."""

    model_config = ConfigDict(extra="forbid")

    challengeToken: Annotated[str, Field(min_length=1, max_length=2048)]
    # Obligatoria si la cuenta tiene contraseña local; una cuenta solo Google no la envía.
    password: Password | None = None


class MfaRecoveryStartResponse(BaseModel):
    recoveryToken: str
    # Solo una versión parcialmente oculta del correo registrado (p. ej. vi******@gmail.com).
    correoEnmascarado: str
    vigenciaMinutos: int


class MfaRecoveryVerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recoveryToken: Annotated[str, Field(min_length=1, max_length=2048)]
    codigo: Annotated[str, Field(pattern=r"^\s*\d{6}\s*$")]


class AccountMfaRecoveryStartRequest(BaseModel):
    """Desde Seguridad: perdió la aplicación y los códigos de recuperación. Exige la contraseña actual."""

    model_config = ConfigDict(extra="forbid")

    password: Password


class AccountMfaRecoveryStartResponse(BaseModel):
    correoEnmascarado: str
    vigenciaMinutos: int


class AccountMfaRecoveryVerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    codigo: Annotated[str, Field(pattern=r"^\s*\d{6}\s*$")]


class MfaCodeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    codigo: Annotated[str, Field(max_length=10)] | None = None
    codigoRecuperacion: Annotated[str, Field(max_length=32)] | None = None

    @model_validator(mode="after")
    def validarUnFactor(self):
        if (self.codigo is None) == (self.codigoRecuperacion is None):
            raise ValueError("Indicar exactamente uno: codigo o codigoRecuperacion.")
        return self


class MfaEnableRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    codigo: Annotated[str, Field(max_length=10)]


class MfaSetupResponse(BaseModel):
    # Se muestra una sola vez para cargarlo en la aplicación autenticadora.
    secreto: str
    otpauthUri: str


class MfaEnableResponse(BaseModel):
    # Se muestran una sola vez; en la base solo se guarda su hash.
    codigosRecuperacion: list[str]


class SetPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # El control contra el usuario/correo de la cuenta se hace en el servicio (conoce al usuario).
    password: NewPassword


class PasswordForgotRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    correoElectronico: Annotated[EmailStr, Field(max_length=254)]

    @field_validator("correoElectronico", mode="before")
    @classmethod
    def normalizarCorreo(cls, value):
        return normalizeEmail(value)


class PasswordResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Token opaco del enlace del correo (un solo uso) y la contraseña nueva, con la misma política que el registro.
    token: Annotated[str, Field(min_length=1, max_length=512)]
    password: NewPassword


class ChangePasswordRequest(BaseModel):
    """Cambio de contraseña con sesión: contraseña actual y, si la cuenta tiene MFA, un código."""

    model_config = ConfigDict(extra="forbid")

    passwordActual: Annotated[SecretStr, Field(min_length=1, max_length=128)]
    passwordNueva: NewPassword
    codigo: Annotated[str, Field(max_length=10)] | None = None
    codigoRecuperacion: Annotated[str, Field(max_length=32)] | None = None


class ResendVerificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    correoElectronico: Annotated[EmailStr, Field(max_length=254)]

    @field_validator("correoElectronico", mode="before")
    @classmethod
    def normalizarCorreo(cls, value):
        return normalizeEmail(value)


class GracePeriodRead(BaseModel):
    """Período de gracia de una cuenta institucional sin vinculaciones: vence el día indicado y entonces se elimina sola."""

    fechaInicio: datetime
    fechaVencimiento: datetime
    diasRestantes: int


class AccountResponse(BaseModel):
    usuario: UserRead
    tieneCredencialLocal: bool
    tieneGoogle: bool
    mfaHabilitado: bool
    # Aviso por correo en cada inicio de sesión (el titular puede desactivarlo).
    notificarNuevoInicioSesion: bool
    requiereCompletarPerfil: bool
    camposFaltantes: list[str]
    # Solo cuentas institucionales que perdieron su última vinculación activa (Usuario.fechaVencimientoGracia). None = sin plazo en curso.
    periodoGracia: GracePeriodRead | None = None


class GoogleExchangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Código de un solo uso recibido por el frontend en el fragmento de /auth/google/callback.
    code: Annotated[str, Field(min_length=1, max_length=512)]


class GoogleAuthorizationUrlResponse(BaseModel):
    # URL pública de Google (contiene state y code_challenge, nunca secretos ni el verificador PKCE).
    authorizationUrl: str


class ProfileUpdateResponse(AccountResponse):
    actualizado: bool
    detail: str


class MessageResponse(BaseModel):
    mensaje: str


class NewLoginNotificationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    habilitada: bool


class NewLoginUnsubscribeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: Annotated[str, Field(min_length=1, max_length=2048)]


class AccountDeletionRequestResponse(MessageResponse):
    fechaExpiracion: datetime
    vigenciaMinutos: int


class AccountDeletionPreview(BaseModel):
    """Consecuencias de eliminar la cuenta, antes de pedir la confirmación."""

    puedeEliminar: bool
    codigoBloqueo: str | None = None
    mensajeBloqueo: str | None = None
    datosEliminados: list[str]
    datosConservados: list[str]
    invitacionesPendientes: int
    periodoGracia: GracePeriodRead | None = None
    reautenticacion: str


class AccountDeletionConfirmRequest(BaseModel):
    """Confirmación de la eliminación (paso 2): token del enlace más la reautenticación.

    password: obligatoria solo si la cuenta tiene contraseña local (no se pide a una cuenta solo Google).
    codigo / codigoRecuperacion: obligatorio uno de los dos solo si la cuenta tiene MFA habilitado; nunca ambos.
    """

    model_config = ConfigDict(extra="forbid")

    token: Annotated[str, Field(min_length=1, max_length=512, description="Token del enlace recibido por correo.")]
    password: Annotated[
        Password | None, Field(description="Contraseña actual. Solo si la cuenta tiene contraseña local.")
    ] = None
    codigo: Annotated[
        str | None, Field(max_length=10, description="Código TOTP. Solo si la cuenta tiene MFA habilitado.")
    ] = None
    codigoRecuperacion: Annotated[
        str | None,
        Field(max_length=32, description="Código de recuperación MFA, en lugar de `codigo`."),
    ] = None

    @model_validator(mode="after")
    def validarUnFactor(self):
        if self.codigo is not None and self.codigoRecuperacion is not None:
            raise ValueError("Indicar solo uno: codigo o codigoRecuperacion.")
        return self


# --- Activación de una cuenta creada por una invitación institucional ------------------------


class AccountActivationTokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: Annotated[str, Field(min_length=1, max_length=512, description="Token del enlace de activación.")]


class AccountActivationCompleteRequest(AccountActivationTokenRequest):
    """La persona elige sus credenciales: nadie más las conoce ni las define."""

    usuario: Annotated[str, Field(max_length=50)]
    password: NewPassword
    # Activar una cuenta invitada equivale a registrarse: exige confirmar la lectura de la Política de Privacidad.
    aceptaPoliticaPrivacidad: bool = False

    @field_validator("usuario")
    @classmethod
    def validarUsuario(cls, value: str) -> str:
        return validateUsername(value)


class ConsentStatus(BaseModel):
    aceptado: bool  # aceptación vigente (última fila ACEPTADO y de la versión actual del texto)
    versionVigente: str
    versionAceptada: str | None = None
    estado: Literal["ACEPTADO", "REVOCADO"] | None = None
    fecha: datetime | None = None


class ConsentsResponse(BaseModel):
    POLITICA_PRIVACIDAD: ConsentStatus
    DATOS_EXPERIMENTALES: ConsentStatus


class ExperimentalConsentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    acepta: bool


class ActivationInvitation(BaseModel):
    nombreInstitucion: str
    rolInstitucion: str


class ActivationInfo(BaseModel):
    nombre: str | None
    apellido: str | None
    correoEnmascarado: str
    invitaciones: list[ActivationInvitation]
