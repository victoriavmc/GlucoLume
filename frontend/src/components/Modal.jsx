// Ventana modal accesible: se dibuja en <body> (portal), el resto de la página queda inerte y sin desplazamiento, el foco
// queda atrapado dentro (Tab y Mays+Tab dan la vuelta), Escape o un clic fuera la cierran y al cerrar el foco vuelve a
// quien la abrió. Se usa para avisos que la persona debe leer antes de seguir (no pide aceptar nada repetitivo).
//
// role="alertdialog" (por defecto): confirmaciones y avisos que interrumpen. role="dialog": formularios dentro de la ventana.

import { useEffect, useId, useRef } from 'react';
import { createPortal } from 'react-dom';

const FOCUSABLE = 'a[href], button:not(:disabled), input:not(:disabled):not([type="hidden"]), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])';

// Se descartan los controles ocultos (atributo hidden o visibility). No se usa getClientRects(): jsdom lo devuelve vacío.
function focusableIn(root) {
  return [...root.querySelectorAll(FOCUSABLE)].filter((element) => !element.closest('[hidden], [inert]') && getComputedStyle(element).visibility !== 'hidden');
}

export function Modal({ title, children, actions, onClose, role = 'alertdialog' }) {
  const titleId = useId();
  const bodyId = useId();
  const dialogRef = useRef(null);
  // La función de cierre suele llegar como flecha nueva en cada render: se guarda en una referencia para que el efecto
  // (foco inicial, trampa y restauración) se ejecute una sola vez por apertura.
  const closeRef = useRef(onClose);
  useEffect(() => {
    closeRef.current = onClose;
  });

  useEffect(() => {
    const dialog = dialogRef.current;
    const opener = document.activeElement;

    // Fondo inerte: todo lo que no sea esta ventana deja de recibir foco y de leerse con lector de pantalla.
    const inerted = [...document.body.children].filter((node) => !node.contains(dialog) && !node.hasAttribute('inert'));
    inerted.forEach((node) => node.setAttribute('inert', ''));
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    // Foco inicial: primer botón o enlace (así se comportaba antes); sin ninguno, el primer control; sin controles, la ventana.
    (dialog.querySelector('button:not(:disabled), a[href]') ?? focusableIn(dialog)[0] ?? dialog).focus();

    function onKeyDown(event) {
      if (event.key === 'Escape') {
        event.stopPropagation();
        closeRef.current?.();
        return;
      }
      if (event.key !== 'Tab') return;
      const items = focusableIn(dialog);
      if (items.length === 0) {
        event.preventDefault();
        dialog.focus();
        return;
      }
      const first = items[0];
      const last = items.at(-1);
      const active = document.activeElement;
      if (!dialog.contains(active)) {
        event.preventDefault();
        first.focus();
      } else if (event.shiftKey && (active === first || active === dialog)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      }
    }
    document.addEventListener('keydown', onKeyDown);

    return () => {
      document.removeEventListener('keydown', onKeyDown);
      inerted.forEach((node) => node.removeAttribute('inert'));
      document.body.style.overflow = overflow;
      opener?.focus?.();
    };
  }, []);

  return createPortal(
    <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && closeRef.current?.()}>
      <div
        className="modal"
        role={role}
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={role === 'alertdialog' ? bodyId : undefined}
        tabIndex={-1}
        ref={dialogRef}
      >
        <h2 id={titleId}>{title}</h2>
        <div className="modal-body" id={bodyId}>{children}</div>
        <div className="modal-actions">{actions}</div>
      </div>
    </div>,
    document.body,
  );
}
