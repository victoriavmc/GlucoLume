// Insignia de estado o categoría. El significado lo da el TEXTO (nunca solo el color); el tono refuerza la lectura:
//   success (vigente, correcto) · warning (atención, pendiente) · danger (error, rechazado) · info (informativo)
//   brand (rol o etiqueta de GlucoLume) · neutral (inactivo, sin dato). Contraste del texto ≥4,5:1 en todos los tonos.

const TONES = ['neutral', 'success', 'warning', 'danger', 'info', 'brand'];

export function Badge({ tone = 'neutral', size = 'md', icon: Icon, dot = false, className = '', children, ...rest }) {
  const safeTone = TONES.includes(tone) ? tone : 'neutral';
  return (
    <span className={`ui-badge ui-badge--${safeTone}${size === 'sm' ? ' ui-badge--sm' : ''} ${className}`.trim()} {...rest}>
      {dot && <span className="ui-badge-dot" aria-hidden="true" />}
      {Icon && <Icon size={size === 'sm' ? 14 : 16} aria-hidden="true" />}
      {children}
    </span>
  );
}

// Origen de un valor de glucosa: experimental (calibrado) = verde, DEMO (simulado) = ámbar, sin calibrar = neutro.
const ORIGIN_TONES = { EXPERIMENTAL: 'success', DEMO: 'warning', SIN_CALIBRAR: 'neutral' };

export function OriginBadge({ origin, ...rest }) {
  return <Badge tone={ORIGIN_TONES[String(origin).toUpperCase()] ?? 'neutral'} {...rest} />;
}

// Los helpers de estado de cada módulo (`stateInfo`, `stateBadge`…) devuelven todavía las clases heredadas `is-on`, `is-off`…:
// esta tabla las traduce al tono del `Badge` para no tocar la lógica de datos al migrar las pantallas.
const CLASS_TONES = { 'is-on': 'success', 'is-off': 'neutral', 'is-warn': 'warning', 'is-denied': 'danger', 'is-role': 'info', 'is-demo': 'warning' };

export const toneFromClass = (className) => CLASS_TONES[className] ?? 'neutral';
