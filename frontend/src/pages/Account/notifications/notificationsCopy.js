// Textos de «Notificaciones» y qué avisos corresponden a cada tipo de cuenta. Los eventos vienen del backend
// (services/userNotifications.py): aquí solo se decide cómo se muestran.

export const CUENTA_INDIVIDUAL = 'CONSUMIDOR_FINAL';

export const EVENTOS = {
  INICIO_SESION: {
    titulo: 'Inicio de sesión',
    descripcion: 'Cada vez que alguien inicia sesión en tu cuenta. Las alertas de actividad sospechosa se envían siempre.',
    individual: false,
  },
  AGREGADO_GRUPO: {
    titulo: 'Me agregan a un grupo',
    descripcion: 'Cuando te suman a un grupo familiar.',
    individual: true,
  },
  RECORDATORIO_MEDICION: {
    titulo: 'Recordatorio para medirme',
    descripcion: 'Te recordamos medirte en el horario que elijas más abajo.',
    individual: true,
  },
  NUEVA_ACCION_GRUPO: {
    titulo: 'Novedades de mi grupo',
    descripcion: 'Cuando alguien del grupo se suma, abandona o se midió y eligió avisar al grupo. Nunca incluye el resultado.',
    individual: true,
  },
};

/** Avisos que se muestran a esta cuenta: los de grupo y de medición son solo para cuentas individuales. */
export function eventosVisibles(tipoCuenta) {
  return Object.keys(EVENTOS).filter((evento) => !EVENTOS[evento].individual || tipoCuenta === CUENTA_INDIVIDUAL);
}
