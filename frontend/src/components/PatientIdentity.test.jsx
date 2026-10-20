import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { PatientIdentity } from './PatientIdentity.jsx';

describe('PatientIdentity', () => {
  it('con autorización muestra el nombre con jerarquía y el identificador debajo', () => {
    render(<PatientIdentity name="Rosa Díaz" code="PAC-1" available />);
    expect(screen.getByText('Rosa Díaz')).toHaveClass('patient-name');
    expect(screen.getByText('PAC-1')).toBeInTheDocument();
  });

  it('autorizado pero sin datos informa que no están disponibles y conserva el identificador', () => {
    render(<PatientIdentity name={null} code="PAC-1" available={false} />);
    expect(screen.getByText('Datos identificativos no disponibles')).toBeInTheDocument();
    expect(screen.getByText('PAC-1')).toBeInTheDocument();
  });

  it('sin autorización muestra solo el identificador seudónimo', () => {
    render(<PatientIdentity name={null} code="PAC-1" available={null} />);
    expect(screen.getByText('PAC-1')).toBeInTheDocument();
    expect(screen.queryByText(/Identificador:/)).not.toBeInTheDocument();
  });
});
