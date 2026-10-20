import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { Modal } from './Modal.jsx';

function Host({ role, onClosed }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState('');
  return (
    <div id="app">
      <button type="button" onClick={() => setOpen(true)}>Abrir</button>
      <a href="/otra">Enlace de la página</a>
      {open && (
        // La función de cierre es una flecha nueva en cada render, como en las pantallas reales.
        <Modal title="Confirmar cambio" role={role} onClose={() => { setOpen(false); onClosed?.(); }}
          actions={<><button type="button" onClick={() => setOpen(false)}>Cancelar</button><button type="button">Confirmar</button></>}>
          <p>Esto no se puede deshacer.</p>
          <input aria-label="Motivo" value={text} onChange={(event) => setText(event.target.value)} />
        </Modal>
      )}
    </div>
  );
}

describe('Modal', () => {
  it('se dibuja en <body>, deja el resto inerte, enfoca el primer botón y bloquea el desplazamiento', async () => {
    render(<Host />);
    const user = userEvent.setup();
    const opener = screen.getByRole('button', { name: 'Abrir' });
    await user.click(opener);
    const dialog = screen.getByRole('alertdialog', { name: 'Confirmar cambio' });
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(dialog).toHaveAccessibleDescription('Esto no se puede deshacer.');
    expect(dialog.closest('.modal-backdrop').parentElement).toBe(document.body);
    expect(document.getElementById('app').parentElement).toHaveAttribute('inert');
    expect(document.body.style.overflow).toBe('hidden');
    expect(screen.getByRole('button', { name: 'Cancelar' })).toHaveFocus();
  });

  it('atrapa el foco: Tab y Mayús+Tab dan la vuelta dentro de la ventana', async () => {
    render(<Host />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Abrir' }));
    const cancel = screen.getByRole('button', { name: 'Cancelar' });
    const confirm = screen.getByRole('button', { name: 'Confirmar' });
    const field = screen.getByLabelText('Motivo');
    // Orden del DOM: campo → Cancelar → Confirmar. El foco inicial cae en el primer botón.
    expect(cancel).toHaveFocus();
    await user.tab();
    expect(confirm).toHaveFocus();
    await user.tab(); // del último al primero, sin salir a la página
    expect(field).toHaveFocus();
    await user.tab({ shift: true }); // del primero al último
    expect(confirm).toHaveFocus();
    await user.tab({ shift: true });
    expect(cancel).toHaveFocus();
    expect(screen.getByRole('link', { name: 'Enlace de la página' })).not.toHaveFocus();
  });

  it('Escape y el clic fuera cierran; al cerrar el foco vuelve a quien la abrió y se libera el fondo', async () => {
    const onClosed = vi.fn();
    render(<Host onClosed={onClosed} />);
    const user = userEvent.setup();
    const opener = screen.getByRole('button', { name: 'Abrir' });
    await user.click(opener);
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(onClosed).toHaveBeenCalledTimes(1);
    expect(opener).toHaveFocus();
    expect(document.getElementById('app').parentElement).not.toHaveAttribute('inert');
    expect(document.body.style.overflow).toBe('');

    await user.click(opener);
    await user.pointer({ keys: '[MouseLeft]', target: document.querySelector('.modal-backdrop') });
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(onClosed).toHaveBeenCalledTimes(2);
  });

  it('escribir dentro de la ventana no le roba el foco al campo aunque la función de cierre cambie en cada render', async () => {
    render(<Host />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Abrir' }));
    const field = screen.getByLabelText('Motivo');
    await user.click(field);
    await user.keyboard('revisión');
    expect(field).toHaveValue('revisión');
    expect(field).toHaveFocus();
  });

  it('admite role="dialog" para formularios', async () => {
    render(<Host role="dialog" />);
    await userEvent.setup().click(screen.getByRole('button', { name: 'Abrir' }));
    const dialog = screen.getByRole('dialog', { name: 'Confirmar cambio' });
    expect(dialog).not.toHaveAttribute('aria-describedby');
  });
});
