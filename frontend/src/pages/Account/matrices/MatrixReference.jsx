// Referencia de una matriz: el nombre del lugar de donde se tomaron los criterios. Si la matriz tiene enlace, todo el nombre es el enlace
// (subrayado y con icono) y se abre en otra pestaña. Sin enlace es texto simple, sin clic, con «No disponible» al pasar el mouse.
// Se usa en todas las pantallas que muestran matrices.

import { ExternalLink } from 'lucide-react';

export function MatrixReference({ name, url }) {
  const text = name || 'Sin registrar';
  if (!url) return <span title="No disponible">{text}</span>;
  return (
    <a href={url} target="_blank" rel="noopener noreferrer" className="matrix-reference-link"
      aria-label={`Abrir la referencia ${text} en otra pestaña`} title="Abrir la referencia en otra pestaña">
      {text}
      <ExternalLink size={15} aria-hidden="true" />
    </a>
  );
}
