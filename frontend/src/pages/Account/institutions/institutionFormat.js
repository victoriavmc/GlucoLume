// Etiquetas del módulo Institución (valores del backend: app/schemas/institution.py y institutionUser.py).

// Mismos valores que TipoInstitucion.
export const INSTITUTION_TYPES = [
  { value: 'CONSULTORIO', label: 'Consultorio' },
  { value: 'CLINICA', label: 'Clínica' },
  { value: 'HOSPITAL', label: 'Hospital' },
  { value: 'LABORATORIO', label: 'Laboratorio' },
  { value: 'OTRO', label: 'Otro' },
];

export const ROLE_LABELS = { PROPIETARIO: 'Propietario/a', MODERADOR: 'Moderador/a', OPERADOR: 'Operador/a' };

export function typeLabel(value) {
  return INSTITUTION_TYPES.find((type) => type.value === value)?.label ?? value;
}

export function personName(person) {
  return [person.nombre, person.apellido].filter(Boolean).join(' ') || (person.usuario ? `@${person.usuario}` : 'Cuenta');
}

/** "30712345671" -> "30-71234567-1". */
export function formatCuit(value) {
  return /^\d{11}$/.test(value ?? '') ? `${value.slice(0, 2)}-${value.slice(2, 10)}-${value.slice(10)}` : value;
}

/** El backend guarda la hora de Argentina sin zona (AAAA-MM-DDTHH:MM:SS): se muestra tal cual. */
export function formatDateTime(value) {
  if (!value) return '';
  const [date, time = ''] = String(value).split('T');
  const [year, month, day] = date.split('-');
  return `${day}/${month}/${year}${time ? ` ${time.slice(0, 5)}` : ''}`;
}

export function can(institution, permission) {
  return Boolean(institution?.permisos?.includes(permission));
}

/** "1980-01-02" -> "02/01/1980" (fecha sin hora: sin conversión de zona). */
export function formatDate(value) {
  if (!value) return '';
  const [year, month, day] = String(value).slice(0, 10).split('-');
  return `${day}/${month}/${year}`;
}

export const SEXO_LABELS = { FEMENINO: 'Femenino', MASCULINO: 'Masculino' };
