// «Saltar al contenido» (WCAG 2.4.1): primer elemento enfocable de los layouts. Queda fuera de pantalla hasta recibir el foco
// con el teclado. Mueve el foco al <main> sin tocar la URL (un hash cambiaría la ruta del router).

export function SkipLink({ targetId = 'contenido', children = 'Saltar al contenido' }) {
  function skip(event) {
    const target = document.getElementById(targetId);
    if (!target) return;
    event.preventDefault();
    target.focus();
    target.scrollIntoView?.({ block: 'start' });
  }

  return (
    <a className="skip-link" href={`#${targetId}`} onClick={skip}>
      {children}
    </a>
  );
}
