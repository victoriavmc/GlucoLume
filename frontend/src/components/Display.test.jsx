// Badge, EmptyState y PageHeader: presentación compartida sin comportamiento propio.
import { render, screen } from '@testing-library/react';
import { Inbox, Plus } from 'lucide-react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import { Badge } from './Badge.jsx';
import { EmptyState } from './EmptyState.jsx';
import { PageHeader } from './PageHeader.jsx';

describe('Badge', () => {
  it('el significado lo da el texto y el tono agrega solo la clase; un tono desconocido cae en neutral', () => {
    const { rerender } = render(<Badge tone="success">Activa</Badge>);
    expect(screen.getByText('Activa')).toHaveClass('ui-badge', 'ui-badge--success');
    rerender(<Badge tone="inventado">Sin dato</Badge>);
    expect(screen.getByText('Sin dato')).toHaveClass('ui-badge--neutral');
  });

  it('pasa atributos como title al elemento', () => {
    render(<Badge tone="warning" title="Resultado de prueba">DEMO</Badge>);
    expect(screen.getByText('DEMO')).toHaveAttribute('title', 'Resultado de prueba');
  });

  it('el ícono y el punto son decorativos y no se leen', () => {
    const { container } = render(<Badge tone="warning" icon={Plus} dot size="sm">Pendiente</Badge>);
    expect(screen.getByText('Pendiente')).toHaveClass('ui-badge--sm');
    container.querySelectorAll('svg, .ui-badge-dot').forEach((node) => expect(node).toHaveAttribute('aria-hidden', 'true'));
  });
});

describe('EmptyState', () => {
  it('muestra título, descripción y acción, con el título como encabezado del nivel pedido', () => {
    render(<EmptyState icon={Inbox} title="Sin pacientes" description="Todavía no registraste ninguno." headingLevel={2}
      action={<button type="button">Registrar paciente</button>} />);
    expect(screen.getByRole('heading', { level: 2, name: 'Sin pacientes' })).toBeInTheDocument();
    expect(screen.getByText('Todavía no registraste ninguno.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Registrar paciente' })).toBeInTheDocument();
  });

  it('con headingLevel 0 el título es un párrafo y los atributos extra van al contenedor', () => {
    render(<EmptyState title="Sin datos de SpO₂" headingLevel={0} role="status" variant="framed" />);
    expect(screen.queryByRole('heading')).not.toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('Sin datos de SpO₂');
  });

  it('sin descripción ni acción solo dibuja el título; las variantes agregan su clase', () => {
    const { container } = render(<EmptyState title="Sin datos disponibles" variant="framed" />);
    expect(container.firstChild).toHaveClass('ui-empty', 'ui-empty--framed');
    expect(container.querySelector('.ui-empty-text')).toBeNull();
    expect(container.querySelector('.ui-empty-action')).toBeNull();
  });
});

describe('PageHeader', () => {
  const wrap = (node) => render(<MemoryRouter>{node}</MemoryRouter>);

  it('por defecto el título es el h1 de la pantalla, con descripción, acciones y enlace para volver', () => {
    wrap(<PageHeader title="Pacientes" description="Listado de la institución." actions={<button type="button">Nuevo paciente</button>}
      back={{ to: '/app/inicio', label: 'Volver al inicio' }} />);
    expect(screen.getByRole('heading', { level: 1, name: 'Pacientes' })).toBeInTheDocument();
    expect(screen.getByText('Listado de la institución.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Nuevo paciente' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Volver al inicio' })).toHaveAttribute('href', '/app/inicio');
  });

  it('con as="h2" no agrega un segundo h1 a una pantalla que ya lo tiene', () => {
    wrap(<><h1>Centro Médico</h1><PageHeader as="h2" title="Dispositivos" /></>);
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    expect(screen.getByRole('heading', { level: 2, name: 'Dispositivos' })).toBeInTheDocument();
  });

  it('las acciones aceptan una clase propia para conservar estilos de la pantalla', () => {
    const { container } = wrap(<PageHeader title="Mi dashboard" actions={<button type="button">Nueva</button>} actionsClassName="dash-actions" />);
    expect(container.querySelector('.ui-page-head-actions')).toHaveClass('dash-actions');
  });

  it('reutiliza las clases del encabezado actual para verse igual', () => {
    const { container } = wrap(<PageHeader title="Perfil" />);
    expect(container.querySelector('header')).toHaveClass('page-head');
  });
});
