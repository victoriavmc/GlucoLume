// Capturas reales de dónde tocar, junto a cada paso de la guía (public/ayuda/). El texto del paso ya describe la acción,
// por eso la imagen va con texto alternativo corto y el pie repite solo dónde está.

import { ChevronLeft, ChevronRight } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import { Modal } from '../../../components/Modal.jsx';

// Espejo del menú de layouts/Sidebar.jsx para cada tipo de cuenta: si cambia un nombre o una ruta, cambiarlo también aquí
// (y volver a capturar: scripts en public/ayuda/ se generan con la app local).
const MENU = {
  CLIENTE: [
    { to: '/app/inicio', label: 'Inicio' },
    { to: '/app/mediciones', label: 'Mediciones' },
    { to: '/app/conectar-dispositivo', label: 'Conectar dispositivo' },
    { to: '/app/grupo', label: 'Grupo' },
    { to: '/app/consejos', label: 'Consejos' },
    { to: '/app/notificaciones', label: 'Notificaciones' },
    { to: '/app/perfil', label: 'Perfil' },
    { to: '/app/seguridad', label: 'Seguridad' },
    { to: '/app/ayuda', label: 'Ayuda' },
  ],
  INSTITUCIONAL: [
    { to: '/app/inicio', label: 'Inicio' },
    { to: '/app/instituciones', label: 'Instituciones' },
    { to: '/app/consejos', label: 'Consejos' },
    { to: '/app/notificaciones', label: 'Notificaciones' },
    { to: '/app/perfil', label: 'Perfil' },
    { to: '/app/seguridad', label: 'Seguridad' },
    { to: '/app/ayuda', label: 'Ayuda' },
  ],
};

const PREFIJO = { CLIENTE: 'cliente', INSTITUCIONAL: 'institucional' };

// La sección del menú que contiene la ruta destino (p. ej. /app/mediciones/perfil cae en Mediciones).
function seccionDe(tipo, destino) {
  return MENU[tipo]
    .filter(({ to }) => destino === to || destino.startsWith(`${to}/`))
    .sort((a, b) => b.to.length - a.to.length)[0];
}

// Datos de la captura de la barra lateral de ese tipo de cuenta, con la sección del paso marcada (o null si no hay).
export function menuDe(tipo, destino) {
  const seccion = seccionDe(tipo, destino);
  if (!seccion) return null;
  return {
    captura: `${PREFIJO[tipo]}-menu-${seccion.to.replace('/app/', '')}.png`,
    alt: `Menú lateral con «${seccion.label}» marcado`,
    pie: `Menú lateral: tocá «${seccion.label}».`,
  };
}

export function PasoMenu({ tipo, destino }) {
  const menu = menuDe(tipo, destino);
  return menu && <PasoImagen {...menu} />;
}

// Imagen de una pantalla de la app (`captura` es un archivo de public/ayuda/) con su pie. Al tocarla se abre ampliada
// en el modal de la app (Escape o clic afuera la cierran). El visor recorre todas las capturas de la guía que están en
// pantalla, en orden, con las flechas (o las teclas ← y →).
export function PasoImagen({ captura, alt, pie }) {
  const [visor, setVisor] = useState(null);
  const figuraRef = useRef(null);
  // El visor amplía el original (`src`); la miniatura en la guía es una versión WebP de hasta 840 px (2× el ancho máximo de 420 px).
  const src = `/ayuda/${captura}`;
  const miniatura = `/ayuda/miniaturas/${captura.replace(/\.png$/, '.webp')}`;

  function abrir() {
    const figuras = [...document.querySelectorAll('figure.help-captura')];
    const lista = figuras.map((figura) => ({ src: figura.dataset.src, miniatura: figura.dataset.miniatura, alt: figura.dataset.alt, titulo: figura.dataset.titulo }));
    setVisor({ lista, indice: Math.max(0, figuras.indexOf(figuraRef.current)) });
  }

  return (
    <figure className="help-captura" ref={figuraRef} data-src={src} data-miniatura={miniatura} data-alt={alt} data-titulo={pie ?? alt}>
      <button type="button" className="help-captura-boton" aria-label={`Ampliar imagen: ${alt}`} onClick={abrir}>
        <img src={miniatura} alt="" loading="lazy" decoding="async" />
      </button>
      {pie && <figcaption>{pie}</figcaption>}
      {visor && <VisorCapturas lista={visor.lista} indice={visor.indice} onCambiar={(indice) => setVisor({ ...visor, indice })} onClose={() => setVisor(null)} />}
    </figure>
  );
}

// Ventana grande con una captura y flechas para pasar a la anterior o a la siguiente (dan la vuelta al llegar al final).
function VisorCapturas({ lista, indice, onCambiar, onClose }) {
  const total = lista.length;
  const actual = lista[indice];

  useEffect(() => {
    const anterior = () => onCambiar((indice - 1 + total) % total);
    const siguiente = () => onCambiar((indice + 1) % total);
    function onKeyDown(event) {
      if (event.key === 'ArrowLeft') anterior();
      else if (event.key === 'ArrowRight') siguiente();
    }
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [indice, total, onCambiar]);

  return (
    <Modal role="dialog" visor title={actual.titulo} onClose={onClose}>
      <div className="help-visor-cuerpo">
        {/* Mientras llega el original (sin caché en la primera apertura) se ve la miniatura de fondo en el mismo marco. */}
        <div className="help-visor-marco" style={{ backgroundImage: `url(${actual.miniatura})` }}>
          <img className="help-visor-img" src={actual.src} alt={actual.alt} />
        </div>
        <button type="button" className="help-visor-flecha is-anterior" aria-label="Captura anterior" onClick={() => onCambiar((indice - 1 + total) % total)}>
          <ChevronLeft size={28} aria-hidden="true" />
        </button>
        <button type="button" className="help-visor-flecha is-siguiente" aria-label="Captura siguiente" onClick={() => onCambiar((indice + 1) % total)}>
          <ChevronRight size={28} aria-hidden="true" />
        </button>
      </div>
      {total > 1 && <p className="help-visor-contador">{indice + 1} de {total}</p>}
    </Modal>
  );
}

// `pie` reemplaza el texto por defecto cuando la pantalla no muestra el botón en ese momento (p. ej. hace falta un
// dispositivo conectado).
export function PasoBoton({ texto, captura, pie }) {
  return <PasoImagen captura={captura} alt={`Pantalla donde está el botón «${texto}»`} pie={pie ?? `Tocá «${texto}».`} />;
}
