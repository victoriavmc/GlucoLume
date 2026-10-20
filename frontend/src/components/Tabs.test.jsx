import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import { NavTabs, TabPanel, Tabs } from './Tabs.jsx';

const ITEMS = [
  { key: 'glucosa', label: 'Glucosa' },
  { key: 'frecuencia', label: 'Frecuencia cardíaca' },
  { key: 'spo2', label: 'SpO₂' },
];

function Demo({ activation, items = ITEMS, onChange }) {
  const [value, setValue] = useState('glucosa');
  return (
    <>
      <button type="button">Antes</button>
      <Tabs label="Variable" idBase="v" items={items} value={value} activation={activation}
        onChange={(key) => { setValue(key); onChange?.(key); }} />
      <TabPanel idBase="v" value={value}>Contenido de {value}</TabPanel>
      <button type="button">Después</button>
    </>
  );
}

describe('Tabs', () => {
  it('expone tablist, tabs y tabpanel enlazados, con una sola pestaña en el orden de Tab', async () => {
    render(<Demo />);
    expect(screen.getByRole('tablist', { name: 'Variable' })).toBeInTheDocument();
    const tabs = screen.getAllByRole('tab');
    expect(tabs.map((tab) => tab.getAttribute('aria-selected'))).toEqual(['true', 'false', 'false']);
    expect(tabs.map((tab) => tab.tabIndex)).toEqual([0, -1, -1]);
    const panel = screen.getByRole('tabpanel', { name: 'Glucosa' });
    expect(tabs[0]).toHaveAttribute('aria-controls', panel.id);
    expect(panel).toHaveAttribute('aria-labelledby', tabs[0].id);

    const user = userEvent.setup();
    await user.tab(); // Antes
    await user.tab(); // la pestaña activa
    expect(tabs[0]).toHaveFocus();
    await user.tab(); // salta las demás pestañas
    expect(screen.getByRole('button', { name: 'Después' })).toHaveFocus();
  });

  it('las flechas, Inicio y Fin mueven entre pestañas (con vuelta) y seleccionan en modo automático', async () => {
    const onChange = vi.fn();
    render(<Demo onChange={onChange} />);
    const user = userEvent.setup();
    const [glucosa, frecuencia, spo2] = screen.getAllByRole('tab');
    glucosa.focus();
    await user.keyboard('{ArrowRight}');
    expect(frecuencia).toHaveFocus();
    expect(frecuencia).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tabpanel', { name: 'Frecuencia cardíaca' })).toHaveTextContent('Contenido de frecuencia');
    await user.keyboard('{End}');
    expect(spo2).toHaveFocus();
    await user.keyboard('{ArrowRight}');
    expect(glucosa).toHaveFocus(); // vuelta al inicio
    await user.keyboard('{ArrowLeft}');
    expect(spo2).toHaveFocus(); // vuelta al final
    await user.keyboard('{Home}');
    expect(glucosa).toHaveFocus();
    expect(onChange).toHaveBeenLastCalledWith('glucosa');
  });

  it('en modo manual las flechas solo mueven el foco y Enter selecciona', async () => {
    const onChange = vi.fn();
    render(<Demo activation="manual" onChange={onChange} />);
    const user = userEvent.setup();
    const [glucosa, frecuencia] = screen.getAllByRole('tab');
    glucosa.focus();
    await user.keyboard('{ArrowRight}');
    expect(frecuencia).toHaveFocus();
    expect(frecuencia).toHaveAttribute('aria-selected', 'false');
    expect(onChange).not.toHaveBeenCalled();
    await user.keyboard('{Enter}');
    expect(frecuencia).toHaveAttribute('aria-selected', 'true');
    expect(onChange).toHaveBeenCalledWith('frecuencia');
  });

  it('las pestañas deshabilitadas se saltan con las flechas y el clic selecciona', async () => {
    render(<Demo items={[ITEMS[0], { ...ITEMS[1], disabled: true }, ITEMS[2]]} />);
    const user = userEvent.setup();
    const [glucosa, frecuencia, spo2] = screen.getAllByRole('tab');
    expect(frecuencia).toBeDisabled();
    glucosa.focus();
    await user.keyboard('{ArrowRight}');
    expect(spo2).toHaveFocus();
    await user.click(glucosa);
    expect(glucosa).toHaveAttribute('aria-selected', 'true');
  });

  it('con un valor desconocido deja la primera pestaña habilitada como entrada del teclado', () => {
    render(<Tabs label="X" idBase="x" items={ITEMS} value="otra" onChange={() => {}} />);
    expect(screen.getAllByRole('tab').map((tab) => tab.tabIndex)).toEqual([0, -1, -1]);
  });
});

describe('NavTabs', () => {
  function renderAt(path) {
    return render(
      <MemoryRouter initialEntries={[path]}>
        <NavTabs label="Secciones del personal" items={[{ to: '/p', label: 'Todos' }, { to: '/p/moderadores', label: 'Moderadores', end: false }]} />
      </MemoryRouter>,
    );
  }

  it('es una navegación con enlaces y marca la ruta actual con aria-current', () => {
    renderAt('/p/moderadores/detalle');
    expect(screen.getByRole('navigation', { name: 'Secciones del personal' })).toBeInTheDocument();
    expect(screen.queryByRole('tab')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Moderadores' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('link', { name: 'Todos' })).not.toHaveAttribute('aria-current');
  });

  it('por defecto exige coincidencia exacta de la ruta', () => {
    renderAt('/p/moderadores');
    expect(screen.getByRole('link', { name: 'Todos' })).not.toHaveAttribute('aria-current');
  });
});
