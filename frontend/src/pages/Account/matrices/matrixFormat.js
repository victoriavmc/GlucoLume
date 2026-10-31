// Etiquetas del módulo de matrices (valores de CK_Matriz_estado, CK_Matriz_ambito y de ReglaMatriz).

import { MEALS, formatDate, formatDateTime } from '../groups/groupFormat.js';

export { MEALS, formatDate, formatDateTime };

export const MATRIX_STATES = { BORRADOR: 'Borrador', ACTIVA: 'Activa', INACTIVA: 'Inactiva', ARCHIVADA: 'Archivada' };
export const MATRIX_SCOPES = { GLOBAL: 'Global de GlucoLume', INSTITUCION: 'Institucional' };
export const RULE_SEX = {
  FEMENINO: 'Femenino', MASCULINO: 'Masculino', NO_INFORMADO: 'Sexo no informado', CUALQUIER_SEXO: 'Cualquier sexo',
};

export const AUDIT_ACTIONS = {
  CREAR_MATRIZ: 'Creó la matriz', CREAR_VERSION_MATRIZ: 'Creó una versión nueva', MODIFICAR_MATRIZ: 'Modificó el borrador',
  CREAR_REGLA_MATRIZ: 'Agregó una regla', MODIFICAR_REGLA_MATRIZ: 'Modificó una regla', ELIMINAR_REGLA_MATRIZ: 'Eliminó una regla',
  ACTIVAR_MATRIZ: 'Activó la versión', DESACTIVAR_MATRIZ: 'Desactivó la versión', ARCHIVAR_MATRIZ: 'Archivó la versión',
};

export function stateBadge(state) {
  return state === 'ACTIVA' ? 'is-on' : 'is-off';
}

/** «Desde 30 hasta 120 min» / «Sin límite» según los topes informados. */
export function minutesLabel(rule) {
  const { minutosComidaMin: min, minutosComidaMax: max } = rule;
  if (min === null && max === null) return 'Sin límite';
  if (min !== null && max !== null) return `${min} a ${max} min`;
  return min !== null ? `Desde ${min} min` : `Hasta ${max} min`;
}

/** «80 – 130 mg/dL»; sin mínimo (solo tope, p. ej. posprandial menor de 180) es «Hasta 179,99 mg/dL». */
export function glucoseRange(rule) {
  const format = (value) => Number(value).toLocaleString('es-AR', { maximumFractionDigits: 2 });
  if (rule.glucosaMinReferencia === null || rule.glucosaMinReferencia === undefined) return `Hasta ${format(rule.glucosaMaxReferencia)} mg/dL`;
  return `${format(rule.glucosaMinReferencia)} – ${format(rule.glucosaMaxReferencia)} mg/dL`;
}

/**
 * Criterios de aplicación de una regla, solo los que corresponden: [{ key, label, value }]. Una regla que no restringe sexo, edad ni
 * comida es «general». Nada de esto se inventa: todo sale de las columnas reales de ReglaMatriz.
 */
export function ruleCriteria(rule) {
  const criteria = [];
  if (rule.sexoModelo !== 'NO_INFORMADO') criteria.push({ key: 'sexo', label: 'Sexo', value: RULE_SEX[rule.sexoModelo] ?? rule.sexoModelo });
  else criteria.push({ key: 'sexo', label: 'Sexo', value: 'No informado' });
  criteria.push({ key: 'edad', label: 'Edad', value: rule.edadDesde === null || rule.edadDesde === undefined ? 'No especificada' : `${rule.edadDesde} a ${rule.edadHasta} años` });
  if (rule.condicionComida === 'NO_INFORMADA') criteria.push({ key: 'comida', label: 'Alimentación', value: 'Sin dato de comida' });
  else {
    const present = (value) => value !== null && value !== undefined;
    const hasMinutes = present(rule.minutosComidaMin) || present(rule.minutosComidaMax);
    criteria.push({ key: 'comida', label: 'Alimentación', value: `${MEALS[rule.condicionComida] ?? rule.condicionComida}${hasMinutes ? ` (${minutesLabel(rule)})` : ''}` });
  }
  return criteria;
}

export const isGeneralRule = (rule) => rule.sexoModelo === 'NO_INFORMADO' && (rule.edadDesde === null || rule.edadDesde === undefined)
  && rule.condicionComida === 'NO_INFORMADA';

const SEX_ORDER = { FEMENINO: 0, MASCULINO: 1, NO_INFORMADO: 2, CUALQUIER_SEXO: 3 };
const MEAL_ORDER = { AYUNO: 0, POSTPRANDIAL: 1, NO_INFORMADA: 2 };

/** Orden de lectura: sexo, alimentación y edad (las reglas sin edad al final de cada grupo). */
export function sortRules(rules) {
  return [...rules].sort((a, b) => (SEX_ORDER[a.sexoModelo] ?? 9) - (SEX_ORDER[b.sexoModelo] ?? 9)
    || (MEAL_ORDER[a.condicionComida] ?? 9) - (MEAL_ORDER[b.condicionComida] ?? 9)
    || (a.edadDesde ?? 1e9) - (b.edadDesde ?? 1e9) || String(a.codigoRegla).localeCompare(String(b.codigoRegla)));
}

const hasAge = (rule) => rule.edadDesde !== null && rule.edadDesde !== undefined && rule.edadHasta !== null && rule.edadHasta !== undefined;
const span = (min, max) => [min ?? 0, max ?? Infinity];

/**
 * Misma validación que el backend (duplicadas y solapadas) para dar el aviso al instante, antes de guardar. La validación
 * definitiva la hace FastAPI. Devuelve un mensaje o null.
 */
export function ruleProblem(candidate, others) {
  for (const other of others) {
    const sameSex = other.sexoModelo === candidate.sexoModelo || other.sexoModelo === 'CUALQUIER_SEXO'
      || candidate.sexoModelo === 'CUALQUIER_SEXO';
    if (!sameSex || other.condicionComida !== candidate.condicionComida) continue;
    if (hasAge(candidate) !== hasAge(other)) continue;
    const sameMinutes = (other.minutosComidaMin ?? null) === (candidate.minutosComidaMin ?? null)
      && (other.minutosComidaMax ?? null) === (candidate.minutosComidaMax ?? null);
    if (sameMinutes && other.edadDesde === candidate.edadDesde && other.edadHasta === candidate.edadHasta) {
      return `Ya existe una regla con las mismas condiciones (${other.codigoRegla}).`;
    }
    if (hasAge(candidate) && (candidate.edadDesde > other.edadHasta || other.edadDesde > candidate.edadHasta)) continue;
    const [aLow, aHigh] = span(candidate.minutosComidaMin, candidate.minutosComidaMax);
    const [bLow, bHigh] = span(other.minutosComidaMin, other.minutosComidaMax);
    if (aLow > bHigh || bLow > aHigh) continue;
    return `La regla se solapa con ${other.codigoRegla}: mismo sexo y condición con edades y tiempos desde la comida que se pisan.`;
  }
  return null;
}
