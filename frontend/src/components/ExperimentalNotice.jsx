// Aviso de uso experimental: un único texto, reutilizado en la página de inicio, en el módulo de mediciones y junto a
// los resultados de estimación de glucosa. Es informativo (no pide aceptación ni abre ventanas emergentes).

import { FlaskConical } from 'lucide-react';

export const EXPERIMENTAL_NOTICE_TEXT =
  'GlucoLume es un prototipo tecnológico desarrollado con fines exclusivamente académicos y experimentales. ' +
  'Las estimaciones obtenidas no constituyen resultados clínicos, no permiten establecer diagnósticos y no deben ' +
  'utilizarse para tomar decisiones médicas o modificar tratamientos.';

/** variant: 'block' (cuadro destacado) o 'inline' (línea discreta debajo de un resultado). */
export function ExperimentalNotice({ variant = 'block', className = '' }) {
  return (
    <div className={`experimental-notice is-${variant} ${className}`.trim()} role="note" aria-label="Aviso de uso experimental">
      <FlaskConical size={variant === 'inline' ? 16 : 22} aria-hidden="true" />
      <p>
        {variant === 'block' && <b>Aviso de uso experimental. </b>}
        {EXPERIMENTAL_NOTICE_TEXT}
      </p>
    </div>
  );
}
