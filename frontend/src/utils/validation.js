// Validaciones de formularios. Replican las del backend para avisar antes de enviar; el backend vuelve a
// validar siempre (backend/app/core/security.py, backend/app/schemas).

export const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

// app/schemas/user.py: USERNAME_MIN_LENGTH
export const USERNAME_MIN_LENGTH = 4;

// app/core/security.py: passwordPolicyErrors
export const PASSWORD_RULES = [
  { id: 'length', label: 'Al menos 8 caracteres', test: (value) => value.length >= 8 && value.length <= 128 },
  { id: 'upper', label: 'Una letra mayúscula', test: (value) => /\p{Lu}/u.test(value) },
  { id: 'lower', label: 'Una letra minúscula', test: (value) => /\p{Ll}/u.test(value) },
  { id: 'digit', label: 'Un número', test: (value) => /\d/.test(value) },
  { id: 'symbol', label: 'Un símbolo (! @ # $ % & * . _ -)', test: (value) => /[^\p{L}\p{N}\s]/u.test(value) },
];

export function passwordMeetsPolicy(value) {
  return PASSWORD_RULES.every((rule) => rule.test(value));
}

export function usernameError(value) {
  const trimmed = value.trim();
  if (!trimmed) return 'Elegí un nombre de usuario.';
  if (trimmed.includes('@')) return 'El nombre de usuario no puede contener «@».';
  if (trimmed.length < USERNAME_MIN_LENGTH) return `El nombre de usuario debe tener al menos ${USERNAME_MIN_LENGTH} caracteres.`;
  return '';
}

// app/schemas/institution.py: CUIT_FORMAT + isValidCuit
const CUIT_WEIGHTS = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2];
// Formato argentino: XX-XXXXXXXX-X u 11 dígitos (sin otros separadores).
const CUIT_FORMAT = /^(\d{2}-\d{8}-\d|\d{11})$/;

export function normalizeCuit(value) {
  return value.trim().replace(/-/g, '');
}

export function isValidCuit(value) {
  if (!CUIT_FORMAT.test(value.trim())) return false;
  const digits = normalizeCuit(value);
  const sum = CUIT_WEIGHTS.reduce((total, weight, index) => total + Number(digits[index]) * weight, 0);
  const remainder = 11 - (sum % 11);
  const expected = remainder === 11 ? 0 : remainder === 10 ? 9 : remainder;
  return Number(digits[10]) === expected;
}
