// Nombres que la interfaz de auditoría muestra en lugar de los códigos del sistema.

export const AUDIT_MODULES = {
  CUENTA: 'Cuenta y acceso', GRUPOS: 'Grupos', INSTITUCIONES: 'Instituciones', PERFILES: 'Perfiles y transferencias',
  MEDICIONES: 'Mediciones', DISPOSITIVOS: 'Dispositivos', MATRICES: 'Matrices y reglas', PLATAFORMA: 'Plataforma',
  AUDITORIA: 'Auditoría', SEGURIDAD: 'Seguridad', SISTEMA: 'Sistema',
};

/** Respaldo para una acción sin nombre funcional en el backend: «CREAR_INSTITUCION» → «Crear institución». */
export function actionLabel(action) {
  const text = action.toLowerCase().replace(/_/g, ' ');
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** Nombre funcional de la acción: el que informa el backend o, si no hay, el respaldo. */
export const eventName = (item) => item.accionEtiqueta ?? actionLabel(item.accion);

/** Resultado tal como lo guarda el sistema (EXITO/FALLO); un fallo por falta de permiso se presenta como «Rechazado». */
export function resultInfo(item) {
  if (item.resultado === 'EXITO') return { label: 'Exitoso', tone: 'is-on' };
  if (item.rechazado) return { label: 'Rechazado', tone: 'is-denied' };
  return { label: 'Fallido', tone: 'is-denied' };
}

/** Tipos de evento (filtro): agrupan las acciones del sistema por lo que significan para quien audita. */
export const AUDIT_CATEGORIES = {
  ACCESOS_FALLIDOS: 'Accesos fallidos', AUTENTICACION: 'Inicio de sesión y credenciales', CUENTAS: 'Altas, bajas y reactivaciones de cuentas',
  INSTITUCIONES: 'Instituciones', PERMISOS: 'Permisos y privilegios', EXPORTACIONES: 'Exportaciones de datos', SEGURIDAD: 'Eventos de seguridad',
};

/** Clasificación de seguridad. Un error aislado es «operativo»; solo los patrones son «sospechosos» y solo los controles aplicados, «confirmados». */
export const AUDIT_CLASSIFICATIONS = {
  INFORMATIVO: 'Informativo', OPERATIVO: 'Error operativo', SOSPECHOSO: 'Actividad sospechosa', CONFIRMADO: 'Control activado',
};
export const CLASSIFICATION_HELP = {
  INFORMATIVO: 'Operación exitosa o consulta normal.',
  OPERATIVO: 'Fallo o rechazo individual del uso normal (contraseña mal escrita, permiso insuficiente). No es un ataque por sí solo.',
  SOSPECHOSO: 'Patrón anómalo detectado por un control técnico. Es una señal para investigar, no una conclusión.',
  CONFIRMADO: 'El sistema aplicó un control (bloqueo, límite, sesión reutilizada). El hecho está comprobado; que alguien atacara, no.',
};

/** Quién obró, según el ámbito que se mira. */
export const ACTOR_ORIGINS = { PLATAFORMA: 'Administración de GlucoLume', USUARIO: 'Personal o usuario de la cuenta', SISTEMA: 'Sistema o sin cuenta identificable' };

/** Colores semánticos del backend: verde = exitoso, naranja = advertencia/sospechoso, rojo = error o crítico, gris = informativo. */
const SEVERITY_TONES = { EXITO: 'success', ADVERTENCIA: 'warning', CRITICO: 'danger', INFO: 'neutral' };
const SEVERITY_LABELS = { EXITO: 'Exitoso', ADVERTENCIA: 'Advertencia', CRITICO: 'Crítico', INFO: 'Informativo' };

/** Severidad del evento (la calcula el backend). Sin ella (respuesta antigua) se infiere solo del resultado, sin inventar sospechas. */
export function severityInfo(item) {
  const key = item.severidad ?? (item.resultado === 'EXITO' ? 'EXITO' : 'ADVERTENCIA');
  return { key, tone: SEVERITY_TONES[key] ?? 'neutral', label: SEVERITY_LABELS[key] ?? key };
}
