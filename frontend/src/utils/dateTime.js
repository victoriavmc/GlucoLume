// Instantes con zona (p. ej. "2026-10-09T14:32:16Z" o "...-03:00"): se convierten a la hora local de quien mira, sin
// rotularla como UTC. Los valores sin zona se interpretan como hora local.

const FORMAT = new Intl.DateTimeFormat('es-AR', {
  day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false,
});

export function formatInstant(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return FORMAT.format(date).replace(',', '');
}
