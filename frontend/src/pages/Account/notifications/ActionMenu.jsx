// Menú de acciones desplegable (patrón WAI-ARIA «menu button»): un botón con aria-haspopup abre una lista de acciones.
// Teclado: Enter, Espacio o Flecha abajo abren y llevan al primer ítem; Flechas, Inicio y Fin se mueven entre ítems; Escape cierra y devuelve el foco
// al botón; Tab cierra. Un clic fuera también cierra. Los grupos se separan con una línea (p. ej. leer / eliminar) y un ítem puede ser `danger`.
//
// items: [{ key, label, icon?, onSelect, disabled?, danger?, groupStart? }]. `groupStart` dibuja la línea antes del ítem.

import { useEffect, useId, useRef, useState } from 'react';

export function ActionMenu({ label, trigger, items, align = 'right', className = '' }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);
  const buttonRef = useRef(null);
  const menuId = useId();

  useEffect(() => {
    if (!open) return undefined;
    function onPointerDown(event) {
      if (!rootRef.current?.contains(event.target)) setOpen(false);
    }
    document.addEventListener('mousedown', onPointerDown);
    return () => document.removeEventListener('mousedown', onPointerDown);
  }, [open]);

  useEffect(() => {
    if (open) rootRef.current?.querySelector('[role="menuitem"]:not(:disabled)')?.focus();
  }, [open]);

  function itemsEnabled() {
    return [...(rootRef.current?.querySelectorAll('[role="menuitem"]:not(:disabled)') ?? [])];
  }

  function close(restoreFocus = true) {
    setOpen(false);
    if (restoreFocus) buttonRef.current?.focus();
  }

  function onButtonKeyDown(event) {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setOpen(true);
    }
  }

  function onMenuKeyDown(event) {
    const enabled = itemsEnabled();
    const index = enabled.indexOf(document.activeElement);
    if (event.key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      close();
    } else if (event.key === 'Tab') {
      close(false);
    } else if (event.key === 'ArrowDown') {
      event.preventDefault();
      enabled[(index + 1) % enabled.length]?.focus();
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      enabled[(index - 1 + enabled.length) % enabled.length]?.focus();
    } else if (event.key === 'Home') {
      event.preventDefault();
      enabled[0]?.focus();
    } else if (event.key === 'End') {
      event.preventDefault();
      enabled.at(-1)?.focus();
    }
  }

  return (
    <div className={`action-menu ${className}`.trim()} ref={rootRef}>
      <button type="button" ref={buttonRef} className="action-menu-button" aria-label={label} aria-haspopup="menu" aria-expanded={open}
        aria-controls={open ? menuId : undefined} onClick={() => setOpen((current) => !current)} onKeyDown={onButtonKeyDown}>
        {trigger}
      </button>
      {open && (
        <ul id={menuId} role="menu" aria-label={label} className={`action-menu-list is-${align}`} onKeyDown={onMenuKeyDown}>
          {items.map(({ key, label: text, icon: Icon, onSelect, disabled, danger, groupStart }) => (
            <li key={key} role="none" className={groupStart ? 'action-menu-group' : undefined}>
              <button type="button" role="menuitem" disabled={disabled} className={`action-menu-item${danger ? ' is-danger' : ''}`}
                onClick={() => {
                  close();
                  onSelect();
                }}>
                {Icon && <Icon size={18} aria-hidden="true" />}
                {text}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
