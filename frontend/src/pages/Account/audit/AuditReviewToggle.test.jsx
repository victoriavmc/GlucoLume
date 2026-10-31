import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { setGlobalAuditReview } from '../../../api/auditApi.js';
import { AuditReviewToggle } from './AuditReviewToggle.jsx';

vi.mock('../../../api/auditApi.js', () => ({ setGlobalAuditReview: vi.fn() }));

const SIN_ANALIZAR = { revisado: false, fechaRevision: null, revisor: null };
const ANALIZADO = { revisado: true, fechaRevision: '2026-10-31T19:40:00', revisor: 'Victoria Cortés' };

describe('AuditReviewToggle', () => {
  beforeEach(() => {
    setGlobalAuditReview.mockReset();
  });

  it('marca el evento, informa la marca resultante y no cambia nada más', async () => {
    setGlobalAuditReview.mockResolvedValue(ANALIZADO);
    const onChange = vi.fn();
    render(<AuditReviewToggle idAuditoria="e-1" revision={SIN_ANALIZAR} name="Sesión reutilizada" onChange={onChange} />);

    await userEvent.click(screen.getByRole('checkbox', { name: 'Analizado: Sesión reutilizada' }));

    expect(setGlobalAuditReview).toHaveBeenCalledWith('e-1', true);
    expect(onChange).toHaveBeenCalledWith(ANALIZADO);
  });

  it('desmarca un evento ya analizado', async () => {
    setGlobalAuditReview.mockResolvedValue(SIN_ANALIZAR);
    const onChange = vi.fn();
    render(<AuditReviewToggle idAuditoria="e-1" revision={ANALIZADO} name="Sesión reutilizada" onChange={onChange} />);

    expect(screen.getByRole('checkbox', { name: 'Analizado: Sesión reutilizada' })).toBeChecked();
    await userEvent.click(screen.getByRole('checkbox', { name: 'Analizado: Sesión reutilizada' }));

    expect(setGlobalAuditReview).toHaveBeenCalledWith('e-1', false);
    expect(onChange).toHaveBeenCalledWith(SIN_ANALIZAR);
  });

  it('si no se pudo guardar, avisa y deja la marca como estaba', async () => {
    setGlobalAuditReview.mockRejectedValue(new Error('sin conexión'));
    const onChange = vi.fn();
    render(<AuditReviewToggle idAuditoria="e-1" revision={SIN_ANALIZAR} name="Sesión reutilizada" onChange={onChange} />);

    await userEvent.click(screen.getByRole('checkbox', { name: 'Analizado: Sesión reutilizada' }));

    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByRole('checkbox', { name: 'Analizado: Sesión reutilizada' })).not.toBeChecked();
  });
});
