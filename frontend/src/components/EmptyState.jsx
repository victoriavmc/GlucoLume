// Estado vacío: qué falta, por qué y, si corresponde, qué hacer. Nunca simula datos ni muestra ceros.
// variant: «center» (tarjeta o sección sin contenido), «framed» (con borde punteado) o «inline» (una línea dentro de un panel).
// headingLevel: nivel del título (2 a 6); con 0 el título es un párrafo, para mensajes breves que no deben sumar encabezados.
// Los atributos extra (p. ej. role="status") van al contenedor.

export function EmptyState({ icon: Icon, title, description, action, variant = 'center', headingLevel = 3, className = '', ...rest }) {
  const Heading = headingLevel ? `h${Math.min(6, Math.max(2, headingLevel))}` : 'p';
  const modifier = variant === 'inline' ? ' ui-empty--inline' : variant === 'framed' ? ' ui-empty--framed' : '';
  return (
    <div className={`ui-empty${modifier} ${className}`.trim()} {...rest}>
      {Icon && <Icon size={variant === 'inline' ? 28 : 44} aria-hidden="true" />}
      <Heading className="ui-empty-title">{title}</Heading>
      {description && <p className="ui-empty-text">{description}</p>}
      {action && <div className="ui-empty-action">{action}</div>}
    </div>
  );
}
