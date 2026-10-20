// Mensajes amigables para los códigos estables del backend (backend/app/api/errors.py).
// Si un código no está aquí se muestra el `detail` del backend, que ya está redactado para el usuario.

import { ApiError } from '../api/client.js';

const MESSAGES = {
  INSTITUCION_PAUSADA: 'Esta institución está pausada por la administración de GlucoLume. Tus datos se conservan; comunicate con el soporte para más información.',
  CREDENCIALES_INVALIDAS: 'El correo, el usuario o la contraseña no son correctos.',
  CUENTA_BLOQUEADA: 'Por seguridad bloqueamos el acceso tras varios intentos fallidos. Probá de nuevo en unos minutos.',
  CORREO_NO_VERIFICADO:
    'Tenés que verificar tu correo electrónico antes de iniciar sesión. Revisá tu bandeja de entrada o spam.',
  CUENTA_NO_ACTIVA: 'Esta cuenta no está activa.',
  CODIGO_INVALIDO: 'El código no es correcto. Revisalo e intentá de nuevo.',
  MFA_BLOQUEADO: 'Demasiados códigos incorrectos. Esperá unos minutos antes de volver a intentar.',
  MFA_NO_DISPONIBLE: 'La verificación en dos pasos no está disponible en este momento. Intentá más tarde.',
  GOOGLE_NO_DISPONIBLE: 'El acceso con Google no está disponible en este momento.',
  VINCULACION_RECHAZADA:
    'No pudimos usar esa cuenta de Google. Si ya tenés una cuenta con ese correo, iniciá sesión con tu contraseña.',
  CUENTA_OTRO_TIPO:
    'Ese correo ya está registrado con otro tipo de cuenta, por lo que no podés registrarte de nuevo. Iniciá sesión con tu cuenta existente.',
  POLITICA_NO_ACEPTADA: 'Para continuar tenés que confirmar que leíste la Política de Privacidad.',
  CONSENTIMIENTO_REQUERIDO:
    'Para medir tenés que autorizar el tratamiento de tus mediciones experimentales desde «Mis mediciones».',
  CUENTA_NO_REGISTRADA:
    'No hay una cuenta de GlucoLume asociada a esa cuenta de Google. Registrate primero para poder ingresar con Google.',
  TOKEN_INVALIDO: 'La sesión o el enlace venció. Volvé a iniciar sesión.',
  CORREO_REGISTRADO: 'Ya existe una cuenta con ese correo electrónico. Iniciá sesión o usá otro correo.',
  USUARIO_REGISTRADO: 'Ese nombre de usuario ya está en uso. Elegí otro.',
  INSTITUCION_REGISTRADA: 'Ya existe una institución activa registrada con este CUIT.',
  CUENTA_YA_VERIFICADA: 'Esta cuenta ya está verificada: podés iniciar sesión.',
  VERIFICACION_EXPIRADA: 'El plazo para verificar la cuenta venció. Registrate nuevamente.',
  USUARIO_NO_DISPONIBLE: 'Ese nombre de usuario ya está en uso.',
  MFA_YA_HABILITADO: 'La verificación en dos pasos ya está activada.',
  MFA_NO_CONFIGURADO: 'La verificación en dos pasos no está activada.',
  CREDENCIAL_EXISTENTE: 'Tu cuenta ya tiene una contraseña.',
  PASSWORD_INCORRECTA: 'La contraseña es incorrecta.',
  PASSWORD_REPETIDA: 'La contraseña nueva tiene que ser distinta de la actual.',
  CREDENCIAL_LOCAL_INEXISTENTE: 'Tu cuenta todavía no tiene contraseña: creala primero.',
  PASSWORD_REQUERIDA: 'Ingresá tu contraseña actual.',
  CODIGO_MFA_REQUERIDO: 'Ingresá el código de verificación en dos pasos.',
  TOKEN_VENCIDO: 'El enlace venció. Solicitá la eliminación de la cuenta nuevamente.',
  TOKEN_YA_UTILIZADO: 'El enlace ya fue utilizado.',
};

// Códigos que llegan en el fragmento del callback de Google (sin `detail`).
const GOOGLE_CALLBACK_MESSAGES = {
  ...MESSAGES,
  TOKEN_INVALIDO: 'No se pudo completar el acceso con Google. Intentá nuevamente.',
  ERROR_SERVIDOR: 'Tuvimos un problema al completar el acceso. Intentá nuevamente en unos minutos.',
};

function lockedMessage(seconds) {
  const minutes = Math.ceil(seconds / 60);
  const wait = minutes <= 1 ? 'en 1 minuto' : `en ${minutes} minutos`;
  return `Por seguridad bloqueamos el acceso tras varios intentos fallidos. Podés volver a intentar ${wait}.`;
}

export function friendlyError(error) {
  if (error instanceof ApiError && error.codigo === 'CUENTA_BLOQUEADA' && error.retryAfterSeconds) {
    return lockedMessage(error.retryAfterSeconds);
  }
  if (error instanceof ApiError) return MESSAGES[error.codigo] ?? error.message;
  return 'Ocurrió un error inesperado. Intentá de nuevo.';
}

export function googleCallbackError(codigo) {
  return GOOGLE_CALLBACK_MESSAGES[codigo] ?? 'No se pudo completar el acceso con Google. Intentá nuevamente.';
}
