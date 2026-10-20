// «Dispositivo de esta conexión»: el operador identifica el Arduino, lo registra la primera vez o lo reconoce, dentro de su institución.
//
// El backend se simula con el contenido que devuelve `readiness.identificacion` (ver backend/app/services/deviceConnection.py); lo que
// verifica la pantalla es que muestra lo que el servidor informa y que solo ofrece las acciones permitidas en cada situación.

import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import * as acquisitionApi from '../../../api/acquisitionApi.js';
import { ApiError } from '../../../api/client.js';
import { institutionSections } from '../institutions/institutionMenu.js';
import { DeviceIdentification } from './DeviceIdentification.jsx';

vi.mock('../../../api/acquisitionApi.js', () => ({
  registerConnectedDevice: vi.fn(),
  confirmConnectedDevice: vi.fn(),
  linkConnectedDevice: vi.fn(),
}));

const INSTITUTION = { idInstitucion: 'i-1', nombre: 'Hospital X' };
const DEVICE = { idDispositivo: 'd-1', codigoDispositivo: '3f2a9c1e-5b7d-4e21-8a9f-0123456789ab', nombre: 'Arduino Consultorio 1', modeloSensor: 'MAX30100',
  versionFirmware: '1.1.0', estado: 'OPERATIVO' };
const identification = (changes) => ({
  nivel: 'FISICA', codigo: DEVICE.codigoDispositivo, firmware: '1.1.0', medio: 'USB', institucion: INSTITUTION, situacion: 'NO_REGISTRADO', confirmada: true,
  dispositivo: null, usable: false, motivoNoDisponible: null, puedeRegistrar: true, puedeVincular: false, requiereConfirmacion: false,
  dispositivoDeclarado: null, candidatos: [], ...changes,
});

beforeEach(() => {
  vi.clearAllMocks();
});

describe('Dispositivo de esta conexión', () => {
  it('sin comunicación verificada no ofrece registrar nada y explica que un puerto no alcanza', () => {
    render(<DeviceIdentification identification={identification({ nivel: 'NINGUNA', codigo: null, situacion: 'SIN_COMUNICACION', puedeRegistrar: false })} />);
    expect(screen.getByRole('heading', { name: 'Dispositivo de esta conexión' })).toBeInTheDocument();
    expect(screen.getByText(/Un puerto COM o un emparejamiento Bluetooth solos no alcanzan/)).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('un Arduino nuevo se registra poniéndole un nombre: el código, el sensor y el firmware salen del dispositivo', async () => {
    const onChanged = vi.fn();
    const registered = identification({ situacion: 'DE_LA_INSTITUCION', dispositivo: { ...DEVICE }, usable: true, puedeRegistrar: false });
    acquisitionApi.registerConnectedDevice.mockResolvedValue({ creado: true, identificacion: registered });
    const user = userEvent.setup();
    render(<DeviceIdentification identification={identification()} onChanged={onChanged} />);

    expect(screen.getByText(/Es un dispositivo nuevo: todavía no está en el inventario de Hospital X/)).toBeInTheDocument();
    expect(screen.getByText(DEVICE.codigoDispositivo)).toBeInTheDocument();
    const button = screen.getByRole('button', { name: 'Registrar nuevo dispositivo' });
    expect(button).toBeDisabled(); // el nombre es lo único que se pide
    await user.type(screen.getByLabelText('Nombre del dispositivo'), '  Arduino Consultorio 1 ');
    await user.click(button);

    expect(acquisitionApi.registerConnectedDevice).toHaveBeenCalledWith({ idInstitucion: 'i-1', nombre: 'Arduino Consultorio 1' });
    expect(onChanged).toHaveBeenCalledWith({ creado: true, identificacion: registered });
    expect(await screen.findByText(/Registramos «Arduino Consultorio 1» en Hospital X/)).toBeInTheDocument();
  });

  it('muestra el rechazo del servidor al registrar sin ocultarlo', async () => {
    acquisitionApi.registerConnectedDevice.mockRejectedValue(new ApiError(409, 'DISPOSITIVO_NO_DISPONIBLE', 'El dispositivo ya está registrado y no pertenece al inventario de esta institución.'));
    const user = userEvent.setup();
    render(<DeviceIdentification identification={identification()} />);
    await user.type(screen.getByLabelText('Nombre del dispositivo'), 'Otro');
    await user.click(screen.getByRole('button', { name: 'Registrar nuevo dispositivo' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/no pertenece al inventario de esta institución/);
    expect(screen.getByRole('button', { name: 'Registrar nuevo dispositivo' })).toBeEnabled();
  });

  it('un dispositivo ya registrado se reconoce con su nombre y su institución, sin pedir registrarlo otra vez', () => {
    render(<DeviceIdentification identification={identification({ situacion: 'DE_LA_INSTITUCION', dispositivo: DEVICE, usable: true, puedeRegistrar: false })} />);
    expect(screen.getByText('Arduino Consultorio 1')).toBeInTheDocument();
    expect(screen.getByText('Se puede usar')).toBeInTheDocument();
    expect(screen.getAllByText(/Hospital X/).length).toBeGreaterThan(0);
    expect(screen.getByText('Operativo')).toBeInTheDocument();
    expect(screen.getByText(/el dispositivo no queda asociado a ninguno/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Registrar nuevo dispositivo' })).not.toBeInTheDocument();
  });

  it('en mantenimiento muestra por qué no se puede usar (estado administrativo, no de conexión)', () => {
    render(<DeviceIdentification identification={identification({ situacion: 'DE_LA_INSTITUCION', dispositivo: { ...DEVICE, estado: 'EN_MANTENIMIENTO' }, usable: false,
      motivoNoDisponible: 'El dispositivo no está operativo (mantenimiento o fuera de servicio).', puedeRegistrar: false })} />);
    expect(screen.getByText('No se puede usar')).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('no está operativo');
    expect(screen.getByText('En mantenimiento')).toBeInTheDocument();
  });

  it('uno de otra institución no se ofrece ni se registra: se pide el procedimiento administrativo', () => {
    render(<DeviceIdentification identification={identification({ situacion: 'DE_OTRA_INSTITUCION', puedeRegistrar: false, motivoNoDisponible: 'pertenece a otra institución' })} />);
    expect(screen.getByRole('alert')).toHaveTextContent(/No se transfiere automáticamente/);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('un dispositivo sin institución se vincula SOLO con una confirmación explícita y avisa qué implica', async () => {
    const onChanged = vi.fn();
    const shared = { ...DEVICE, nombre: 'Arduino GlucoLume (registro automático)' };
    const linked = identification({ situacion: 'DE_LA_INSTITUCION', dispositivo: DEVICE, usable: true, puedeRegistrar: false });
    acquisitionApi.linkConnectedDevice.mockResolvedValue({ creado: false, vinculado: true, identificacion: linked });
    const user = userEvent.setup();
    render(<DeviceIdentification onChanged={onChanged} identification={identification({ situacion: 'SIN_INSTITUCION', dispositivo: shared, usable: false,
      puedeRegistrar: false, puedeVincular: true, motivoNoDisponible: 'Todavía no pertenece al inventario de tu institución: vinculalo para medir con pacientes.' })} />);

    expect(screen.getByText(/ya existe en GlucoLume, pero no pertenece a ninguna institución/)).toBeInTheDocument();
    const button = screen.getByRole('button', { name: 'Vincular a la institución' });
    expect(button).toBeDisabled(); // sin confirmar no se puede
    expect(screen.getByText(/deja de estar disponible\s+para las cuentas individuales/)).toBeInTheDocument();
    await user.type(screen.getByLabelText('Nombre del dispositivo (opcional)'), ' Arduino Consultorio 1 ');
    await user.click(screen.getByRole('checkbox'));
    await user.click(button);
    expect(acquisitionApi.linkConnectedDevice).toHaveBeenCalledWith({
      idInstitucion: 'i-1', idDispositivo: 'd-1', nombre: 'Arduino Consultorio 1', confirmaVinculacion: true,
    });
    expect(await screen.findByText(/Vinculamos «Arduino Consultorio 1» a Hospital X: ya figura en su inventario/)).toBeInTheDocument();
    expect(onChanged).toHaveBeenCalled();
  });

  it('sin ID propio, cada opción exige confirmar además que el Arduino conectado es ese dispositivo', async () => {
    const declared = { ...DEVICE, codigoDispositivo: 'GL-0001', nombre: 'Arduino GlucoLume (registro automático)' };
    const confirmed = identification({ nivel: 'DECLARADA', situacion: 'DE_LA_INSTITUCION', dispositivo: DEVICE, usable: true, puedeRegistrar: false });
    acquisitionApi.linkConnectedDevice.mockResolvedValue({ creado: false, vinculado: true, identificacion: confirmed });
    acquisitionApi.registerConnectedDevice.mockResolvedValue({ creado: true, vinculado: false, identificacion: confirmed });
    const user = userEvent.setup();
    render(<DeviceIdentification identification={identification({ nivel: 'DECLARADA', codigo: 'GL-0001', situacion: 'IDENTIDAD_NO_CONFIRMADA', confirmada: false,
      puedeRegistrar: true, puedeVincular: true, requiereConfirmacion: true, dispositivoDeclarado: declared, candidatos: [] })} />);

    // Vincular: dos confirmaciones (la vinculación y la identidad).
    const link = screen.getByRole('button', { name: 'Vincular a la institución' });
    const [confirmLink, confirmIdentity] = within(screen.getByRole('form', { name: 'Vincular a la institución' })).getAllByRole('checkbox');
    expect(link).toBeDisabled();
    await user.click(confirmLink);
    expect(link).toBeDisabled(); // falta confirmar la identidad
    await user.click(confirmIdentity);
    await user.click(link);
    expect(acquisitionApi.linkConnectedDevice).toHaveBeenCalledWith({
      idInstitucion: 'i-1', idDispositivo: 'd-1', nombre: '', confirmaVinculacion: true, confirmaIdentidad: true,
    });

    // Registrar nuevo: nombre y confirmación de identidad.
    const register = screen.getByRole('button', { name: 'Registrar nuevo dispositivo' });
    await user.type(screen.getByLabelText('Nombre del dispositivo'), 'Consultorio viejo');
    expect(register).toBeDisabled();
    await user.click(within(screen.getByRole('form', { name: 'Registrar nuevo dispositivo' })).getByRole('checkbox'));
    await user.click(register);
    expect(acquisitionApi.registerConnectedDevice).toHaveBeenCalledWith({ idInstitucion: 'i-1', nombre: 'Consultorio viejo', confirmaIdentidad: true });
  });

  it('sin ID propio pide elegir y confirmar cuál dispositivo es (no asume que es el del puerto)', async () => {
    const onChanged = vi.fn();
    const candidates = [{ idDispositivo: 'd-1', codigoDispositivo: 'GL-0001', nombre: 'Consultorio 1', sugerido: false },
      { idDispositivo: 'd-2', codigoDispositivo: 'GL-0002', nombre: 'Consultorio 2', sugerido: true }];
    const confirmed = identification({ nivel: 'DECLARADA', situacion: 'DE_LA_INSTITUCION', dispositivo: DEVICE, usable: true, puedeRegistrar: false });
    acquisitionApi.confirmConnectedDevice.mockResolvedValue({ creado: false, identificacion: confirmed });
    const user = userEvent.setup();
    render(<DeviceIdentification onChanged={onChanged} identification={identification({ nivel: 'DECLARADA', codigo: 'GL-0002', situacion: 'IDENTIDAD_NO_CONFIRMADA',
      confirmada: false, puedeRegistrar: false, candidatos: candidates })} />);

    expect(screen.getByText(/No se pudo confirmar qué Arduino es/)).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /Consultorio 2 \(GL-0002\) — coincide con el código del puente/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Registrar nuevo dispositivo' })).not.toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText('Dispositivo de la institución'), 'd-1'); // elige otro distinto del sugerido
    await user.click(screen.getByRole('button', { name: 'Confirmar dispositivo' }));
    expect(acquisitionApi.confirmConnectedDevice).toHaveBeenCalledWith({ idInstitucion: 'i-1', idDispositivo: 'd-1' });
    expect(onChanged).toHaveBeenCalled();
  });

  it('sin ID propio y sin nada que confirmar, registrar o vincular manda al propietario/a', () => {
    render(<DeviceIdentification identification={identification({ nivel: 'DECLARADA', situacion: 'IDENTIDAD_NO_CONFIRMADA', confirmada: false, puedeRegistrar: false,
      requiereConfirmacion: true })} />);
    expect(screen.getByText(/Pedí al propietario\/a que lo registre desde el inventario/)).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });
});

describe('Menú de la institución', () => {
  const institution = (rolInstitucion, permisos) => ({ idInstitucion: 'i-1', rolInstitucion, permisos });

  it('el operador conecta dispositivos dentro de su institución; el propietario y el moderador no', () => {
    const labels = (role, permisos) => institutionSections(institution(role, permisos)).map((section) => section.label);
    expect(labels('OPERADOR', ['CONSULTAR_PACIENTES'])).toContain('Conectar dispositivo');
    expect(labels('MODERADOR', ['GESTIONAR_DISPOSITIVOS'])).not.toContain('Conectar dispositivo');
    expect(labels('PROPIETARIO', ['GESTIONAR_DISPOSITIVOS'])).not.toContain('Conectar dispositivo');
    expect(institutionSections(institution('OPERADOR', [])).find((section) => section.label === 'Conectar dispositivo').to).toBe('conectar-dispositivo');
  });
});
