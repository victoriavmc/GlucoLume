import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it } from 'vitest';

import { CheckField, RadioField, SelectField, TextAreaField, TextField } from './FormControls.jsx';

describe('TextField (ayuda opcional)', () => {
  it('asocia la ayuda y el error al control con aria-describedby y marca la invalidez', () => {
    render(<TextField label="Correo" hint="Usá el de tu trabajo." error="Ingresá un correo válido." aria-describedby="extra" />);
    const input = screen.getByLabelText('Correo');
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(input).toHaveAccessibleDescription('Usá el de tu trabajo. Ingresá un correo válido.');
    expect(input.getAttribute('aria-describedby').split(' ')).toContain('extra'); // conserva el id que pase la pantalla
  });

  it('sin ayuda ni error no agrega descripciones', () => {
    render(<TextField label="Nombre" />);
    const input = screen.getByLabelText('Nombre');
    expect(input).not.toHaveAttribute('aria-describedby');
    expect(input).not.toHaveAttribute('aria-invalid');
  });
});

describe('SelectField', () => {
  it('renderiza las opciones, cambia de valor y asocia ayuda y error', async () => {
    function Demo() {
      const [value, setValue] = useState('ACTIVO');
      return <SelectField label="Estado" hint="Filtra el listado." error={value === 'BAJA' ? 'Los dados de baja no se editan.' : undefined}
        value={value} onChange={(event) => setValue(event.target.value)}
        options={[{ value: 'ACTIVO', label: 'Activos' }, { value: 'BAJA', label: 'Dados de baja' }, { value: 'X', label: 'No disponible', disabled: true }]} />;
    }
    render(<Demo />);
    const select = screen.getByLabelText('Estado');
    expect(select).toHaveClass('field-input', 'field-select');
    expect(screen.getAllByRole('option').map((option) => option.textContent)).toEqual(['Activos', 'Dados de baja', 'No disponible']);
    expect(screen.getByRole('option', { name: 'No disponible' })).toBeDisabled();
    expect(select).toHaveAccessibleDescription('Filtra el listado.');
    await userEvent.setup().selectOptions(select, 'BAJA');
    expect(select).toHaveAttribute('aria-invalid', 'true');
    expect(select).toHaveAccessibleDescription('Filtra el listado. Los dados de baja no se editan.');
  });

  it('acepta <option> como hijos', () => {
    render(<SelectField label="Rol" defaultValue="b"><option value="a">A</option><option value="b">B</option></SelectField>);
    expect(screen.getByLabelText('Rol')).toHaveValue('b');
  });
});

describe('TextAreaField', () => {
  it('con maxLength muestra el contador, que no se lee, y limita la escritura', async () => {
    function Demo() {
      const [value, setValue] = useState('');
      return <TextAreaField label="Observaciones" hint="Opcional." maxLength={10} value={value} onChange={(event) => setValue(event.target.value)} />;
    }
    const { container } = render(<Demo />);
    const area = screen.getByLabelText('Observaciones');
    expect(container.querySelector('.field-counter')).toHaveTextContent('0 / 10');
    expect(container.querySelector('.field-counter')).toHaveAttribute('aria-hidden', 'true');
    await userEvent.setup().type(area, 'abcdefghijklmnop');
    expect(area).toHaveValue('abcdefghij');
    expect(container.querySelector('.field-counter')).toHaveTextContent('10 / 10');
    expect(area).toHaveAccessibleDescription('Opcional.');
  });

  it('sin maxLength no hay contador y el error queda asociado', () => {
    const { container } = render(<TextAreaField label="Motivo" value="" onChange={() => {}} error="Escribí un motivo." />);
    expect(container.querySelector('.field-counter')).toBeNull();
    expect(screen.getByLabelText('Motivo')).toHaveAccessibleDescription('Escribí un motivo.');
  });
});

describe('CheckField', () => {
  it('la etiqueta marca la casilla y la ayuda y el error se leen junto al control', async () => {
    function Demo() {
      const [checked, setChecked] = useState(false);
      return <CheckField label="Recordarme" hint="Solo en este equipo." error={checked ? undefined : 'Es obligatorio.'}
        checked={checked} onChange={(event) => setChecked(event.target.checked)} />;
    }
    render(<Demo />);
    const box = screen.getByRole('checkbox', { name: 'Recordarme' });
    expect(box).toHaveAccessibleDescription('Solo en este equipo. Es obligatorio.');
    await userEvent.setup().click(screen.getByText('Recordarme'));
    expect(box).toBeChecked();
    expect(box).toHaveAccessibleDescription('Solo en este equipo.');
  });
});

describe('RadioField', () => {
  it('forma un grupo con la etiqueta clicable y deja una sola opción marcada', async () => {
    function Demo() {
      const [medium, setMedium] = useState('BLUETOOTH');
      return (
        <fieldset aria-label="Medio">
          <RadioField name="medio" label="Bluetooth (9600 baudios)" hint="Para el HC-05." checked={medium === 'BLUETOOTH'} onChange={() => setMedium('BLUETOOTH')} />
          <RadioField name="medio" label="USB (115200 baudios)" checked={medium === 'USB'} onChange={() => setMedium('USB')} />
        </fieldset>
      );
    }
    render(<Demo />);
    const user = userEvent.setup();
    const bluetooth = screen.getByRole('radio', { name: 'Bluetooth (9600 baudios)' });
    expect(bluetooth).toBeChecked();
    expect(bluetooth).toHaveAccessibleDescription('Para el HC-05.');
    await user.click(screen.getByText('USB (115200 baudios)'));
    expect(screen.getByRole('radio', { name: 'USB (115200 baudios)' })).toBeChecked();
    expect(bluetooth).not.toBeChecked();
  });
});
