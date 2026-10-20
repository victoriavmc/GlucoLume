// Etiquetas y formatos de los datos de cuenta (valores del backend: app/schemas/user.py).

// Mismos valores que Sexo / CK_Usuario_sexo.
export const SEXO_OPTIONS = [
  { value: 'FEMENINO', label: 'Femenino' },
  { value: 'MASCULINO', label: 'Masculino' },
];

export const ACCOUNT_TYPES = {
  CONSUMIDOR_FINAL: 'Usuario individual',
  USUARIO_INSTITUCIONAL: 'Usuario institucional',
  ADMINISTRADOR_PLATAFORMA: 'Administración de la plataforma',
  MODERADOR_PLATAFORMA: 'Moderación de la plataforma',
};

export function sexoLabel(value) {
  return SEXO_OPTIONS.find((option) => option.value === value)?.label ?? null;
}

/** "1990-05-17" -> "17/05/1990" (sin conversiones de zona horaria: es una fecha, no un instante). */
export function formatDate(isoDate) {
  if (!isoDate) return null;
  const [year, month, day] = isoDate.split('-');
  return `${day}/${month}/${year}`;
}

/** Edad derivada de la fecha de nacimiento (no se guarda). */
export function ageFrom(isoDate, today = new Date()) {
  if (!isoDate) return null;
  const [year, month, day] = isoDate.split('-').map(Number);
  let age = today.getFullYear() - year;
  if (today.getMonth() + 1 < month || (today.getMonth() + 1 === month && today.getDate() < day)) age -= 1;
  return age;
}

/** Fecha local de hoy en formato AAAA-MM-DD (límite del selector de fecha de nacimiento). */
export function todayIso(today = new Date()) {
  const pad = (value) => String(value).padStart(2, '0');
  return `${today.getFullYear()}-${pad(today.getMonth() + 1)}-${pad(today.getDate())}`;
}
