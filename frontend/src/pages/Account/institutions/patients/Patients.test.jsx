import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { clearTokens, saveTokens } from '../../../../auth/tokenStore.js';
import { ACCOUNT, TOKENS, jsonResponse, mockApi } from '../../../../test/helpers.js';
import { renderAt } from '../../../../test/renderApp.jsx';

const INSTITUTIONAL = { ...ACCOUNT, usuario: { ...ACCOUNT.usuario, tipoCuenta: 'USUARIO_INSTITUCIONAL' } };
const ID = '9a000000-0000-4000-8000-000000000001';
const BASE = `/institutions/${ID}`;
const PATIENTS_URL = `${BASE}/patients`;
const PERMISOS = {
  PROPIETARIO: ['CONSULTAR_INSTITUCION', 'MODIFICAR_INSTITUCION', 'GESTIONAR_MODERADORES', 'ADMINISTRAR_OPERADORES',
    'CONSULTAR_EQUIPO', 'ELIMINAR_INSTITUCION', 'CONSULTAR_PACIENTES', 'GESTIONAR_PACIENTES', 'BAJA_PACIENTES'],
  MODERADOR: ['CONSULTAR_INSTITUCION', 'INCORPORAR_OPERADORES', 'ADMINISTRAR_OPERADORES', 'CONSULTAR_EQUIPO',
    'CONSULTAR_PACIENTES', 'GESTIONAR_PACIENTES', 'BAJA_PACIENTES'],
  OPERADOR: ['CONSULTAR_INSTITUCION', 'CONSULTAR_PACIENTES', 'GESTIONAR_PACIENTES'],
};

function detail(rol, overrides = {}) {
  return {
    idInstitucion: ID, nombre: 'Centro Médico San José', tipoInstitucion: 'CLINICA', estado: 'ACTIVA', rolInstitucion: rol,
    estadoRelacion: 'ACTIVO', permisos: PERMISOS[rol], tipoIdentificadorLegal: 'CUIT', identificadorLegal: '30712345671',
    descripcion: null, fechaCreacion: '2026-10-01T10:00:00',
    fechaActualizacion: '2026-10-01T10:00:00', propietario: { nombre: 'Victoria', apellido: 'Cortés' },
    cantidadModeradores: 1, cantidadOperadores: 2, cantidadPacientes: 1, ...overrides,
  };
}

const OPERATORS = [
  { idInstitucionUsuario: 'op-1', nombre: 'Ana', apellido: 'Paz' },
  { idInstitucionUsuario: 'op-2', nombre: 'Bruno', apellido: 'Ríos' },
];

function patient(overrides = {}) {
  return {
    idPerfilMedicion: 'p-1', identificadorPseudonimo: 'PAC-ABC123', nombre: 'Juan', apellido: 'Pérez', dni: '20111222',
    fechaNacimiento: '1980-01-02', edad: 46, sexoModelo: 'MASCULINO', estado: 'ACTIVO',
    fechaCreacion: '2026-10-03T09:00:00', fechaUltimaMedicion: null, fechaExpiracionDatosPersonales: null,
    responsable: { idInstitucionUsuario: 'op-1', nombre: 'Ana', apellido: 'Paz', activo: true }, puedeModificar: true, esMio: true, medicionesAutorizadas: true,
    ...overrides,
  };
}

function page(items, total = items.length, pagina = 1) {
  return { items, total, pagina, tamanioPagina: 20 };
}

beforeEach(() => {
  clearTokens();
  saveTokens(TOKENS, false);
});

function routes(rol, extra = {}) {
  return mockApi({
    'GET /auth/me': jsonResponse(200, INSTITUTIONAL),
    [`GET ${BASE}`]: jsonResponse(200, detail(rol)),
    [`GET ${PATIENTS_URL}/assignable-operators`]: jsonResponse(200, OPERATORS),
    [`GET ${PATIENTS_URL}/p-1/measurements`]: () => jsonResponse(200, { items: [], total: 0, pagina: 1, tamanioPagina: 10 }),
    ...extra,
  });
}

describe('Listado de pacientes', () => {
  it('busca y filtra en el backend, y pagina', async () => {
    const many = Array.from({ length: 20 }, (_, index) => patient({ idPerfilMedicion: `p-${index}`, apellido: `Apellido ${index}` }));
    const { calls } = routes('PROPIETARIO', {
      [`GET ${PATIENTS_URL}`]: (options) => jsonResponse(200, page(many, 25)),
    });
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/pacientes`);
    expect(await screen.findByText('Página 1 de 2 · 25 pacientes')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Agregar paciente' })).toBeInTheDocument();

    await user.type(screen.getByLabelText('Buscar por nombre, apellido o documento'), 'pérez');
    await user.selectOptions(screen.getByLabelText('Operador responsable'), 'op-2');
    await user.click(screen.getByRole('button', { name: /Buscar/ }));
    await user.click(screen.getByRole('button', { name: /Siguiente/ }));

    await waitFor(() => {
      const last = new URL(calls.filter((call) => call.key === `GET ${PATIENTS_URL}`).at(-1).url);
      expect(Object.fromEntries(last.searchParams)).toEqual({
        busqueda: 'pérez', estado: 'ACTIVO', idResponsable: 'op-2', pagina: '2', tamanioPagina: '20',
      });
    }, { timeout: 5000 }); // con todos los archivos en paralelo, 1 s por defecto no siempre alcanza
  });

  it('una respuesta lenta de un filtro anterior no pisa la del filtro actual (condición de carrera)', async () => {
    // Estado ACTIVO responde enseguida; «Dados de baja» (la consulta más NUEVA) responde rápido y «Activos» (la ANTERIOR) responde tarde.
    let releaseSlow;
    const slow = new Promise((resolve) => { releaseSlow = resolve; });
    const active = patient({ idPerfilMedicion: 'p-act', apellido: 'Activo', nombre: 'Ana' });
    const discharged = patient({ idPerfilMedicion: 'p-baja', apellido: 'DeBaja', nombre: 'Beto', estado: 'BAJA', fechaExpiracionDatosPersonales: '2027-10-03T09:00:00' });
    let calls = 0;
    routes('PROPIETARIO', {
      [`GET ${PATIENTS_URL}`]: (options, url) => {
        calls += 1;
        const estado = new URL(url).searchParams.get('estado');
        if (estado === 'ACTIVO' && calls > 1) return slow.then(() => jsonResponse(200, page([active])));
        return jsonResponse(200, page(estado === 'BAJA' ? [discharged] : [active]));
      },
    });
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/pacientes`);
    expect(await screen.findByText('Activo, Ana')).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText('Estado'), 'BAJA');           // consulta 2: Dados de baja (rápida)
    expect(await screen.findByText('DeBaja, Beto')).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText('Estado'), 'ACTIVO');          // consulta 3: Activos (lenta)...
    await user.selectOptions(screen.getByLabelText('Estado'), 'BAJA');            // ...y se vuelve a elegir «baja» (consulta 4, rápida)
    expect(await screen.findByText('DeBaja, Beto')).toBeInTheDocument();
    releaseSlow();                                                                // llega tarde la respuesta de «Activos»
    await new Promise((resolve) => { setTimeout(resolve, 100); });
    expect(screen.getByText('DeBaja, Beto')).toBeInTheDocument();                 // no la pisa
    expect(screen.queryByText('Activo, Ana')).not.toBeInTheDocument();
  });

  it('el operador ve todos los pacientes de la institución, distingue los suyos y mide solo a los suyos', async () => {
    const mine = patient();
    const foreign = patient({ idPerfilMedicion: 'p-2', apellido: 'Gómez', nombre: 'Luis', dni: null, edad: null, sexoModelo: null, fechaNacimiento: null,
      responsable: { idInstitucionUsuario: 'op-9', nombre: 'Bruno', apellido: 'Ríos', activo: true }, puedeModificar: false, esMio: false, medicionesAutorizadas: false });
    const { calls } = routes('OPERADOR', { [`GET ${PATIENTS_URL}`]: () => jsonResponse(200, page([mine, foreign])) });
    renderAt(`/app/instituciones/${ID}/pacientes`);
    expect(await screen.findByRole('heading', { name: 'Pacientes' })).toBeInTheDocument();
    const rows = within(await screen.findByRole('list', { name: 'Listado de pacientes' })).getAllByRole('listitem');
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByText('Paciente asignado a mi cargo')).toBeInTheDocument();
    expect(within(rows[0]).getByRole('link', { name: /Medir a Pérez, Juan/ })).toBeInTheDocument();
    expect(within(rows[1]).getByText('Paciente registrado en la institución')).toBeInTheDocument();
    expect(within(rows[1]).getByText(/Operador responsable: Bruno Ríos/)).toBeInTheDocument();
    expect(within(rows[1]).queryByRole('link', { name: /Medir a/ })).not.toBeInTheDocument(); // sin mediciones ajenas
    // Entrar a un paciente: el suyo abre el dashboard; el ajeno (sin acceso a su salud) abre la ficha administrativa.
    expect(within(rows[0]).getByRole('link', { name: /Ver Pérez, Juan/ })).toHaveAttribute('href', expect.stringMatching(/\/p-1\/dashboard$/));
    expect(within(rows[1]).getByRole('link', { name: /^Ver / })).toHaveAttribute('href', expect.not.stringMatching(/dashboard$/));
    expect(within(rows[1]).queryByText(/DNI/)).not.toBeInTheDocument();
    expect(calls.find((call) => call.key === `GET ${PATIENTS_URL}`).url).not.toContain('soloMios');
  });

  it('el filtro «Mis pacientes» pasa al backend', async () => {
    const { calls } = routes('OPERADOR', { [`GET ${PATIENTS_URL}`]: () => jsonResponse(200, page([patient()])) });
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/pacientes`);
    await user.selectOptions(await screen.findByLabelText('Ver'), 'mios');
    await waitFor(() => {
      const last = new URL(calls.filter((call) => call.key === `GET ${PATIENTS_URL}`).at(-1).url);
      expect(last.searchParams.get('soloMios')).toBe('true');
    }, { timeout: 5000 });
  });

  it('desde «Nueva medición» llega a mis pacientes y se invita a elegir el paciente', async () => {
    const { calls } = routes('OPERADOR', { [`GET ${PATIENTS_URL}`]: () => jsonResponse(200, page([patient()])) });
    renderAt(`/app/instituciones/${ID}/pacientes?mios=1&medir=1`);
    expect(await screen.findByText(/Elegí el paciente al que vas a medir/)).toBeInTheDocument();
    await waitFor(() => expect(new URL(calls.find((call) => call.key === `GET ${PATIENTS_URL}`).url).searchParams.get('soloMios')).toBe('true'));
  });

  it('sin pacientes asignados, el operador ve un estado vacío claro con la acción de agregar', async () => {
    routes('OPERADOR', { [`GET ${PATIENTS_URL}`]: () => jsonResponse(200, page([])) });
    renderAt(`/app/instituciones/${ID}/pacientes?mios=1`);
    expect(await screen.findByText(/Todavía no tenés pacientes asignados/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Agregar paciente/ })).toBeInTheDocument();
  });

  it('propietario y moderador listan a todos con el filtro por operador responsable y sin «Medir»', async () => {
    routes('MODERADOR', { [`GET ${PATIENTS_URL}`]: () => jsonResponse(200, page([patient({ esMio: false, medicionesAutorizadas: false })])),
      [`GET ${PATIENTS_URL}/assignable-operators`]: jsonResponse(200, [{ idInstitucionUsuario: 'op-1', nombre: 'Ana', apellido: 'Paz' }]) });
    renderAt(`/app/instituciones/${ID}/pacientes`);
    expect(await screen.findByRole('heading', { name: 'Pacientes' })).toBeInTheDocument();
    expect(await screen.findByLabelText('Operador responsable')).toBeInTheDocument();
    expect(screen.queryByLabelText('Ver')).not.toBeInTheDocument(); // «mis pacientes» es del operador
    expect(screen.queryByRole('link', { name: /Medir a/ })).not.toBeInTheDocument();
    expect(await screen.findByText('Paciente registrado en la institución')).toBeInTheDocument();
  });
});

describe('Alta de paciente', () => {
  async function fill(user) {
    await user.type(await screen.findByLabelText('Nombre'), 'Juan');
    await user.type(screen.getByLabelText('Apellido'), 'Pérez');
    await user.type(screen.getByLabelText('Documento (DNI) (opcional)'), '20.111.222');
    await user.type(screen.getByLabelText('Fecha de nacimiento (opcional)'), '1980-01-02');
    await user.selectOptions(screen.getByLabelText('Sexo (opcional)'), 'MASCULINO');
  }

  it('un operador lo deja a su cargo y entra al detalle del paciente creado', async () => {
    const { calls } = routes('OPERADOR', {
      [`POST ${PATIENTS_URL}`]: jsonResponse(201, patient()),
      [`GET ${PATIENTS_URL}/p-1`]: jsonResponse(200, patient()),
    });
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/pacientes/nuevo`);
    await user.click(await screen.findByRole('button', { name: 'Agregar paciente' }));
    expect(screen.getByText('Ingresá el nombre.')).toBeInTheDocument();
    expect(calls.some((call) => call.key === `POST ${PATIENTS_URL}`)).toBe(false);

    await fill(user);
    // El operador no elige responsable: no hay selector, solo la aclaración de que queda a su cargo.
    expect(screen.queryByLabelText('Operador responsable')).not.toBeInTheDocument();
    expect(screen.getByRole('note')).toHaveTextContent('El paciente va a quedar a tu cargo');
    await user.click(screen.getByRole('button', { name: 'Agregar paciente' }));

    expect(await screen.findByText('Registramos al paciente.')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Pérez, Juan' })).toBeInTheDocument();
    // El cliente NO envía ningún operador responsable: el backend lo resuelve con la sesión.
    expect(calls.find((call) => call.key === `POST ${PATIENTS_URL}`).body).toEqual({
      nombre: 'Juan', apellido: 'Pérez', dni: '20111222', fechaNacimiento: '1980-01-02', sexoModelo: 'MASCULINO',
    });
    const beforePost = calls.slice(0, calls.findIndex((call) => call.key === `POST ${PATIENTS_URL}`));
    expect(beforePost.some((call) => call.key.includes('assignable-operators'))).toBe(false); // el formulario no pide la lista de operadores
  });

  it('documento, fecha de nacimiento y sexo son opcionales: se registra solo con nombre y apellido', async () => {
    const { calls } = routes('OPERADOR', {
      [`POST ${PATIENTS_URL}`]: jsonResponse(201, patient({ dni: null, fechaNacimiento: null, edad: null, sexoModelo: null })),
      [`GET ${PATIENTS_URL}/p-1`]: jsonResponse(200, patient({ dni: null, fechaNacimiento: null, edad: null, sexoModelo: null })),
    });
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/pacientes/nuevo`);
    await user.type(await screen.findByLabelText('Nombre'), 'Ana');
    await user.type(screen.getByLabelText('Apellido'), 'Paz');
    await user.click(screen.getByRole('button', { name: 'Agregar paciente' }));
    expect(await screen.findByText('Registramos al paciente.')).toBeInTheDocument();
    // Lo que no se completó no se envía.
    expect(calls.find((call) => call.key === `POST ${PATIENTS_URL}`).body).toEqual({ nombre: 'Ana', apellido: 'Paz' });
    expect(screen.getAllByText('Sin informar').length).toBeGreaterThanOrEqual(3);
  });

  it('si se completan, el documento y la fecha siguen validándose', async () => {
    const { calls } = routes('OPERADOR', {});
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/pacientes/nuevo`);
    await user.type(await screen.findByLabelText('Nombre'), 'Ana');
    await user.type(screen.getByLabelText('Apellido'), 'Paz');
    await user.type(screen.getByLabelText('Documento (DNI) (opcional)'), '12');
    await user.click(screen.getByRole('button', { name: 'Agregar paciente' }));
    expect(screen.getByText(/documento válido: entre 6 y 12/)).toBeInTheDocument();
    expect(calls.some((call) => call.key === `POST ${PATIENTS_URL}`)).toBe(false);
  });

  it('un moderador debe elegir el operador responsable', async () => {
    const { calls } = routes('MODERADOR', {
      [`POST ${PATIENTS_URL}`]: jsonResponse(201, patient({ responsable: { ...OPERATORS[1], activo: true } })),
      [`GET ${PATIENTS_URL}/p-1`]: jsonResponse(200, patient()),
    });
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/pacientes/nuevo`);
    await fill(user);
    await user.click(screen.getByRole('button', { name: 'Agregar paciente' }));
    expect(screen.getByText('Elegí el operador responsable del paciente.')).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText('Operador responsable'), 'op-2');
    await user.click(screen.getByRole('button', { name: 'Agregar paciente' }));
    await screen.findByText('Registramos al paciente.');
    expect(calls.find((call) => call.key === `POST ${PATIENTS_URL}`).body.idInstitucionUsuarioResponsable).toBe('op-2');
  });

  it('el moderador elige entre los operadores activos y queda claro que el alta no le da acceso a las mediciones', async () => {
    routes('MODERADOR', {});
    renderAt(`/app/instituciones/${ID}/pacientes/nuevo`);
    const select = await screen.findByLabelText('Operador responsable');
    await waitFor(() => expect(within(select).getAllByRole('option').length).toBe(OPERATORS.length + 1));
    expect(within(select).getAllByRole('option').slice(1).map((option) => option.textContent)).toEqual(OPERATORS.map((o) => `${o.nombre} ${o.apellido}`));
    expect(screen.getByText(/Vos quedás registrado\/a como autor\/a del alta/)).toBeInTheDocument();
  });

  it('sin operadores activos se explica y no se permite completar el alta', async () => {
    routes('MODERADOR', { [`GET ${PATIENTS_URL}/assignable-operators`]: jsonResponse(200, []) });
    renderAt(`/app/instituciones/${ID}/pacientes/nuevo`);
    expect(await screen.findByText(/todavía no tiene operadores activos/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Agregar paciente' })).toBeDisabled();
  });

  it('si el servidor rechaza al operador elegido (de baja u otra institución) se informa en el campo', async () => {
    routes('MODERADOR', { [`POST ${PATIENTS_URL}`]: jsonResponse(422, { codigo: 'OPERADOR_NO_DISPONIBLE', detail: 'El responsable debe ser un operador activo de esta institución.' }) });
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/pacientes/nuevo`);
    await fill(user);
    await user.selectOptions(await screen.findByLabelText('Operador responsable'), 'op-2');
    await user.click(screen.getByRole('button', { name: 'Agregar paciente' }));
    expect(await screen.findByText('El responsable debe ser un operador activo de esta institución.')).toBeInTheDocument();
  });

  it('un documento repetido se informa en el campo', async () => {
    routes('OPERADOR', {
      [`POST ${PATIENTS_URL}`]: jsonResponse(409, {
        codigo: 'PACIENTE_REGISTRADO', detail: 'Ya hay un paciente activo con ese documento en la institución.',
      }),
    });
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/pacientes/nuevo`);
    await fill(user);
    await user.click(screen.getByRole('button', { name: 'Agregar paciente' }));
    expect(await screen.findByText('Ya hay un paciente activo con ese documento en la institución.')).toBeInTheDocument();
    expect(screen.getByLabelText('Documento (DNI) (opcional)')).toHaveAttribute('aria-invalid', 'true');
  });
});

describe('Detalle de paciente', () => {
  it('edita, reasigna el responsable y da de baja con confirmación', async () => {
    const { calls } = routes('MODERADOR', {
      [`GET ${PATIENTS_URL}/p-1`]: jsonResponse(200, patient()),
      [`PATCH ${PATIENTS_URL}/p-1`]: jsonResponse(200, patient({ apellido: 'Pérez Gómez' })),
      [`PUT ${PATIENTS_URL}/p-1/responsible`]: jsonResponse(200, patient({
        apellido: 'Pérez Gómez', responsable: { ...OPERATORS[1], activo: true },
      })),
      [`POST ${PATIENTS_URL}/p-1/discharge`]: jsonResponse(200, patient({
        apellido: 'Pérez Gómez', estado: 'BAJA', fechaExpiracionDatosPersonales: '2027-10-08T10:00:00',
        puedeModificar: false,
      })),
    });
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/pacientes/p-1`);
    await user.click(await screen.findByRole('button', { name: /Editar/ }));
    const apellido = screen.getByLabelText('Apellido');
    await user.clear(apellido);
    await user.type(apellido, 'Pérez Gómez');
    await user.click(screen.getByRole('button', { name: 'Guardar cambios' }));
    expect(await screen.findByText('Guardamos los cambios del paciente.')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Pérez Gómez, Juan' })).toBeInTheDocument();

    await user.selectOptions(await screen.findByLabelText('Asignar a'), 'op-2');
    await user.click(screen.getByRole('button', { name: 'Cambiar responsable' }));
    expect(await screen.findByText('Cambiamos el operador responsable.')).toBeInTheDocument();
    expect(calls.find((call) => call.key === `PUT ${PATIENTS_URL}/p-1/responsible`).body).toEqual({
      idInstitucionUsuarioResponsable: 'op-2',
    });

    await user.click(screen.getByRole('button', { name: 'Dar de baja' }));
    expect(calls.some((call) => call.key === `POST ${PATIENTS_URL}/p-1/discharge`)).toBe(false);
    await user.click(screen.getByRole('button', { name: /Confirmar baja/ }));
    expect(await screen.findByText('El paciente quedó dado de baja.')).toBeInTheDocument();
    expect(screen.getByText('Dado de baja')).toBeInTheDocument();
    expect(screen.getByText('08/10/2027 10:00')).toBeInTheDocument(); // conservación de 12 meses
    expect(screen.queryByRole('button', { name: /Editar/ })).not.toBeInTheDocument();
  });

  it('avisa que reasignar a un paciente con responsable activo es una propuesta y no cambia al responsable', async () => {
    routes('MODERADOR', {
      [`GET ${PATIENTS_URL}/p-1`]: jsonResponse(200, patient()),
      [`PUT ${PATIENTS_URL}/p-1/responsible`]: jsonResponse(200, patient()), // el responsable sigue siendo el mismo
    });
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/pacientes/p-1`);
    await user.selectOptions(await screen.findByLabelText('Asignar a'), 'op-2');
    await user.click(screen.getByRole('button', { name: 'Cambiar responsable' }));
    expect(await screen.findByText('Enviamos la propuesta al operador. El responsable cambiará cuando la acepte.')).toBeInTheDocument();
    expect(screen.queryByText('Cambiamos el operador responsable.')).not.toBeInTheDocument();
  });

  it('muestra las mediciones asociadas al perfil, de la más reciente a la más antigua', async () => {
    routes('OPERADOR', {
      [`GET ${PATIENTS_URL}/p-1`]: jsonResponse(200, patient()),
      [`GET ${PATIENTS_URL}/p-1/measurements`]: jsonResponse(200, {
        items: [
          { idMedicion: 'm-2', fechaHoraInicio: '2026-10-07T08:30:00', fechaHoraFin: null, modoMedicion: 'OXIMETRIA',
            estadoMedicion: 'COMPLETADA', condicionComida: 'AYUNO', edadAlMomento: 46, glucosaEstimada: null, spo2: '98.00',
            frecuenciaCardiaca: 70, calidadSenal: null, observacion: null },
          { idMedicion: 'm-1', fechaHoraInicio: '2026-10-05T19:00:00', fechaHoraFin: null, modoMedicion: 'OXIMETRIA',
            estadoMedicion: 'COMPLETADA', condicionComida: 'POSTPRANDIAL', edadAlMomento: 46, glucosaEstimada: null,
            spo2: '95.00', frecuenciaCardiaca: 76, calidadSenal: null, observacion: null },
        ],
        total: 2, pagina: 1, tamanioPagina: 10,
      }),
      [`GET ${PATIENTS_URL}/p-1/measurements/evolution`]: jsonResponse(200, { puntos: [], truncado: false, desde: null, hasta: null, estadisticas: { experimental: null, demo: null }, resumen: null }),
    });
    renderAt(`/app/instituciones/${ID}/pacientes/p-1`);
    const list = await screen.findByRole('list', { name: 'Mediciones' });
    const items = within(list).getAllByRole('listitem');
    expect(items[0]).toHaveTextContent('07/10/2026 08:30');
    expect(items[0]).toHaveTextContent('En ayunas');
    expect(items[0]).toHaveTextContent('SpO₂ 98 %');
    expect(items[1]).toHaveTextContent('Después de comer');
  });

  it('un operador no modifica un paciente que no está a su cargo ni puede darlo de baja', async () => {
    routes('OPERADOR', { [`GET ${PATIENTS_URL}/p-1`]: jsonResponse(200, patient({ puedeModificar: false })) });
    renderAt(`/app/instituciones/${ID}/pacientes/p-1`);
    expect(await screen.findByText(/Solo el operador responsable, un moderador o el propietario/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Editar/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Cambiar responsable' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Dar de baja' })).not.toBeInTheDocument();
  });

  it('un paciente de otra institución se informa como inexistente', async () => {
    routes('OPERADOR', {
      [`GET ${PATIENTS_URL}/p-x`]: jsonResponse(404, { codigo: 'PACIENTE_NO_ENCONTRADO', detail: 'No encontramos ese paciente en la institución.' }),
    });
    renderAt(`/app/instituciones/${ID}/pacientes/p-x`);
    expect(await screen.findByText('No encontramos ese paciente en la institución.')).toBeInTheDocument();
  });
});

describe('Datos de la institución', () => {
  it('el propietario edita y la vista muestra lo persistido', async () => {
    const { calls } = mockApi({
      'GET /auth/me': jsonResponse(200, INSTITUTIONAL),
      [`GET ${BASE}`]: [
        jsonResponse(200, detail('PROPIETARIO')),
        jsonResponse(200, detail('PROPIETARIO', { nombre: 'Centro Médico San José Norte', tipoInstitucion: 'HOSPITAL' })),
      ],
      [`PATCH ${BASE}`]: jsonResponse(200, detail('PROPIETARIO')),
    });
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/datos`);
    const legal = await screen.findByRole('region', { name: 'Identificación legal' }, { timeout: 5000 });
    expect(legal).toHaveTextContent('30-71234567-1');
    expect(screen.queryByRole('region', { name: /contacto|Ubicación/i })).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /Editar datos/ }));
    const nombre = screen.getByLabelText('Nombre de la institución');
    await user.clear(nombre);
    await user.click(screen.getByRole('button', { name: 'Guardar cambios' }));
    expect(screen.getByText('Ingresá el nombre de la institución.')).toBeInTheDocument();

    await user.type(nombre, 'Centro Médico San José Norte');
    await user.selectOptions(screen.getByLabelText('Tipo de institución'), 'HOSPITAL');
    await user.click(screen.getByRole('button', { name: 'Guardar cambios' }));

    expect(await screen.findByText('Guardamos los cambios de la institución.')).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Información general' })).toHaveTextContent('Centro Médico San José Norte');
    expect(calls.find((call) => call.key === `PATCH ${BASE}`).body).toEqual({
      nombre: 'Centro Médico San José Norte', tipoInstitucion: 'HOSPITAL', descripcion: null,
    });
  });
});

describe('Acceso a las mediciones del paciente', () => {
  const NOTICE = 'Las mediciones de este paciente están disponibles únicamente para su operador responsable autorizado.';
  const FOREIGN = { dni: null, edad: null, sexoModelo: null, fechaNacimiento: null, puedeModificar: false, esMio: false, medicionesAutorizadas: false,
    responsable: { idInstitucionUsuario: 'op-9', nombre: 'Bruno', apellido: 'Ríos', activo: true } };

  it('el operador que abre un paciente ajeno ve solo su información administrativa y el aviso, sin pedir mediciones', async () => {
    const { calls } = routes('OPERADOR', { [`GET ${PATIENTS_URL}/p-1`]: jsonResponse(200, patient(FOREIGN)) });
    renderAt(`/app/instituciones/${ID}/pacientes/p-1`);
    expect(await screen.findByRole('heading', { name: 'Pérez, Juan' })).toBeInTheDocument();
    expect(screen.getByText('Paciente registrado en la institución')).toBeInTheDocument();
    expect(screen.getByText(NOTICE)).toBeInTheDocument();
    const data = within(screen.getByRole('heading', { name: 'Pérez, Juan' }).closest('section'));
    expect(data.getByText('Bruno Ríos')).toBeInTheDocument(); // operador responsable
    expect(data.getByText('Registrado el')).toBeInTheDocument();
    for (const hidden of ['Documento', 'Fecha de nacimiento', 'Sexo', 'Última medición']) expect(data.queryByText(hidden)).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Nueva medición/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: /Mediciones/ })).not.toBeInTheDocument();
    expect(calls.some((call) => call.key.includes('/measurements'))).toBe(false); // ni siquiera se consultan
  });

  it('la ficha muestra quién registró al paciente, distinto de su operador responsable', async () => {
    routes('MODERADOR', { [`GET ${PATIENTS_URL}/p-1`]: jsonResponse(200, patient({ ...FOREIGN, registradoPor: { nombre: 'Mara', apellido: 'Gil', rolInstitucion: 'MODERADOR' } })) });
    renderAt(`/app/instituciones/${ID}/pacientes/p-1`);
    const data = within((await screen.findByRole('heading', { name: 'Pérez, Juan' })).closest('section'));
    expect(data.getByText('Mara Gil (Moderador/a)')).toBeInTheDocument();
    expect(data.getByText('Bruno Ríos')).toBeInTheDocument();
  });

  it('el moderador ve la ficha administrativa y gestiona la asignación, pero no las mediciones', async () => {
    const { calls } = routes('MODERADOR', { [`GET ${PATIENTS_URL}/p-1`]: jsonResponse(200, patient({ ...FOREIGN, dni: '20111222', puedeModificar: true })) });
    renderAt(`/app/instituciones/${ID}/pacientes/p-1`);
    expect(await screen.findByText(NOTICE)).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Operador responsable' })).toBeInTheDocument(); // asignación
    expect(calls.some((call) => call.key.includes('/measurements'))).toBe(false);
  });

  it('el operador responsable ve su paciente completo con mediciones, nueva medición y edición', async () => {
    const { calls } = routes('OPERADOR', { [`GET ${PATIENTS_URL}/p-1`]: jsonResponse(200, patient()),
      [`GET ${PATIENTS_URL}/p-1/measurements/evolution`]: jsonResponse(200, { puntos: [], truncado: false, desde: null, hasta: null, estadisticas: { experimental: null, demo: null }, resumen: null }) });
    renderAt(`/app/instituciones/${ID}/pacientes/p-1`);
    expect(await screen.findByText('Paciente asignado a mi cargo')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Dashboard' })).not.toBeInTheDocument(); // el dashboard del paciente se quitó: la ficha lo reúne todo
    expect(screen.getByRole('link', { name: /Nueva medición/ })).toHaveAttribute('href', `/app/instituciones/${ID}/pacientes/p-1/medir`);
    expect(screen.getByRole('button', { name: /Editar/ })).toBeInTheDocument();
    expect(screen.queryByText(NOTICE)).not.toBeInTheDocument();
    expect(await screen.findByText('Documento')).toBeInTheDocument();
    await waitFor(() => expect(calls.some((call) => call.key.includes('/measurements'))).toBe(true));
  });

  it('un paciente con solo mediciones DEMO ve sus gráficos identificados, con resumen y última medición', async () => {
    const stat = (values) => ({
      cantidad: values.length, ultimo: values.length ? { valor: values.at(-1), fecha: '2026-10-17T17:00:00' } : null,
      promedio: values.length ? values.reduce((a, b) => a + b, 0) / values.length : null, minimo: values.length ? Math.min(...values) : null, maximo: values.length ? Math.max(...values) : null,
    });
    const demoStats = { mediciones: 2, frecuenciaCardiaca: stat([70, 80]), spo2: stat([95, 97]), glucosa: stat([110, 120]), indiceOptico: stat([]), calidadSenal: stat([0.5]) };
    const evolution = {
      origen: 'TODOS', desde: '2026-09-17T00:00:00', hasta: null, truncado: false,
      puntos: [
        { idMedicion: 'm-1', fecha: '2026-10-15T20:00:00', modoMedicion: 'OXIMETRIA', origen: 'DEMO', esDemo: true, frecuenciaCardiaca: 70, spo2: 95, glucosa: 110, indiceOptico: null, calidadSenal: 0.5 },
        { idMedicion: 'm-2', fecha: '2026-10-17T17:00:00', modoMedicion: 'GLUCOSA_EXPERIMENTAL', origen: 'DEMO', esDemo: true, frecuenciaCardiaca: 80, spo2: 97, glucosa: 120, indiceOptico: null, calidadSenal: null },
      ],
      estadisticas: { experimental: { ...demoStats, mediciones: 0, frecuenciaCardiaca: stat([]), spo2: stat([]), glucosa: stat([]), calidadSenal: stat([]) }, demo: demoStats },
      resumen: { total: 2, experimentales: 0, demo: 2, porModo: { OXIMETRIA: 1, GLUCOSA_EXPERIMENTAL: 1 }, ultima: { fecha: '2026-10-17T17:00:00', modoMedicion: 'GLUCOSA_EXPERIMENTAL', esDemo: true } },
    };
    routes('OPERADOR', { [`GET ${PATIENTS_URL}/p-1`]: jsonResponse(200, patient()), [`GET ${PATIENTS_URL}/p-1/measurements/evolution`]: jsonResponse(200, evolution) });
    renderAt(`/app/instituciones/${ID}/pacientes/p-1`);
    const panel = within((await screen.findByRole('heading', { name: 'Gráficos y estadísticas' })).closest('section'));
    // Con todas las fuentes y sin datos experimentales se muestran las series DEMO, identificadas, en vez de un panel vacío.
    expect(await panel.findByRole('heading', { name: /Glucosa estimada — DEMO \(datos simulados\)/ })).toBeInTheDocument();
    expect(panel.queryByText('No hay mediciones completadas en este período.')).not.toBeInTheDocument();
    expect(panel.getByText(/no representan resultados clínicos/)).toBeInTheDocument();
    // Cada variable registrada tiene su gráfico (ambos modos aportan SpO₂, frecuencia cardíaca, glucosa y calidad de señal).
    for (const name of [/Frecuencia cardíaca — DEMO/, /Saturación de oxígeno \(SpO₂\) — DEMO/, /Calidad de señal — DEMO/]) {
      expect(panel.getByRole('heading', { name })).toBeInTheDocument();
    }
    expect(panel.getByRole('button', { name: /15\/10\/2026 20:00: 70 lpm \(DEMO\)/ })).toBeInTheDocument();
    expect(panel.getByRole('button', { name: /17\/10\/2026 17:00: 80 lpm \(DEMO\)/ })).toBeInTheDocument();
    const cards = within(panel.getByRole('list', { name: 'Resumen de las mediciones del paciente' }));
    expect(cards.getByText('Total de mediciones').closest('li')).toHaveTextContent(/2.*2 DEMO.*0 experimentales/);
    expect(cards.getByText('SpO₂ promedio').closest('li')).toHaveTextContent(/96\s*%.*2 valores.*DEMO/);
    expect(cards.getByText('Frecuencia cardíaca promedio').closest('li')).toHaveTextContent(/75.*lpm/);
    expect(cards.getByText('Calidad de señal').closest('li')).toHaveTextContent(/0,5.*1 valor.*Sin dato: 1/); // la que no la registró no cuenta como 0
    expect(panel.getByText(/Última medición:.*17\/10\/2026.*Glucosa \(experimental\), DEMO simulada/)).toBeInTheDocument();
    // «Variable» elige una sola, con sus estadísticas aparte de las experimentales.
    await userEvent.selectOptions(panel.getByLabelText('Variable'), 'frecuenciaCardiaca');
    expect(await panel.findByRole('heading', { name: /Frecuencia cardíaca: estadísticas de pruebas/ })).toBeInTheDocument();
  });

  it('si el backend rechaza igualmente la consulta de mediciones, se informa el motivo', async () => {
    routes('OPERADOR', { [`GET ${PATIENTS_URL}/p-1`]: jsonResponse(200, patient()),
      [`GET ${PATIENTS_URL}/p-1/measurements`]: jsonResponse(403, { codigo: 'MEDICIONES_NO_AUTORIZADAS', detail: NOTICE }),
      [`GET ${PATIENTS_URL}/p-1/measurements/evolution`]: jsonResponse(403, { codigo: 'MEDICIONES_NO_AUTORIZADAS', detail: NOTICE }) });
    renderAt(`/app/instituciones/${ID}/pacientes/p-1`);
    expect((await screen.findAllByText(new RegExp(NOTICE.slice(0, 40)))).length).toBeGreaterThan(0);
  });
});

// Exportar pacientes: el archivo lo devuelve la API; la UI solo ofrece las opciones que corresponden a cada rol.
const csvResponse = () => ({
  ok: true, status: 200, headers: new Headers({ 'Content-Disposition': 'attachment; filename="pacientes-institucion-prueba.csv"' }),
  blob: async () => new Blob(['csv'], { type: 'text/csv' }),
});

describe('Exportar pacientes', () => {
  beforeEach(() => {
    URL.createObjectURL = vi.fn(() => 'blob:pacientes');
    URL.revokeObjectURL = vi.fn();
  });

  const foreign = () => patient({ idPerfilMedicion: 'p-2', apellido: 'Gómez', nombre: 'Luis', dni: null, edad: null, sexoModelo: null,
    fechaNacimiento: null, responsable: { idInstitucionUsuario: 'op-9', nombre: 'Bruno', apellido: 'Ríos', activo: true },
    puedeModificar: false, esMio: false, medicionesAutorizadas: false });

  it('el propietario exporta los pacientes marcados y, con «todos», el listado completo con sus filtros', async () => {
    const { calls } = routes('PROPIETARIO', {
      [`GET ${PATIENTS_URL}`]: () => jsonResponse(200, page([patient(), foreign()], 2)),
      [`POST ${PATIENTS_URL}/export`]: csvResponse,
    });
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/pacientes`);
    expect(await screen.findByRole('button', { name: 'Exportar seleccionados' })).toBeDisabled();
    await user.click(screen.getByRole('checkbox', { name: 'Seleccionar a Pérez, Juan' }));
    await user.click(screen.getByRole('button', { name: 'Exportar seleccionados (1)' }));
    expect(await screen.findByText('Exportación lista: pacientes-institucion-prueba.csv.')).toBeInTheDocument();
    expect(calls.filter((call) => call.key === `POST ${PATIENTS_URL}/export`).at(-1).body)
      .toEqual({ alcance: 'SELECCION', idsPerfilMedicion: ['p-1'] });

    await user.click(screen.getByRole('button', { name: 'Exportar todos (2)' }));
    await waitFor(() => expect(calls.filter((call) => call.key === `POST ${PATIENTS_URL}/export`)).toHaveLength(2));
    expect(calls.filter((call) => call.key === `POST ${PATIENTS_URL}/export`).at(-1).body)
      .toEqual({ alcance: 'TODOS', busqueda: null, estado: 'ACTIVO', idResponsable: null });
  });

  it('una persona se exporta sola desde su fila', async () => {
    const { calls } = routes('MODERADOR', {
      [`GET ${PATIENTS_URL}`]: () => jsonResponse(200, page([patient(), foreign()], 2)),
      [`POST ${PATIENTS_URL}/export`]: csvResponse,
    });
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/pacientes`);
    await user.click(await screen.findByRole('button', { name: 'Exportar los datos de Gómez, Luis' }));
    await screen.findByText(/Exportación lista/);
    expect(calls.find((call) => call.key === `POST ${PATIENTS_URL}/export`).body).toEqual({ alcance: 'SELECCION', idsPerfilMedicion: ['p-2'] });
  });

  it('el operador solo puede exportar los pacientes a su cargo: las casillas y la acción aparecen solo en los suyos', async () => {
    const { calls } = routes('OPERADOR', {
      [`GET ${PATIENTS_URL}`]: () => jsonResponse(200, page([patient(), foreign()], 2)),
      [`POST ${PATIENTS_URL}/export`]: csvResponse,
    });
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/pacientes`);
    await screen.findByRole('list', { name: 'Listado de pacientes' });
    expect(screen.getByRole('checkbox', { name: 'Seleccionar a Pérez, Juan' })).toBeInTheDocument();
    expect(screen.queryByRole('checkbox', { name: 'Seleccionar a Gómez, Luis' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Exportar los datos de Gómez, Luis' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Exportar mis pacientes' }));
    await screen.findByText(/Exportación lista/);
    expect(calls.find((call) => call.key === `POST ${PATIENTS_URL}/export`).body).toEqual({ alcance: 'TODOS', busqueda: null, estado: 'ACTIVO', idResponsable: null });
  });

  it('si la API rechaza la exportación, muestra el motivo y no descarga nada', async () => {
    routes('PROPIETARIO', {
      [`GET ${PATIENTS_URL}`]: () => jsonResponse(200, page([patient()], 1)),
      [`POST ${PATIENTS_URL}/export`]: jsonResponse(409, { codigo: 'DATOS_INVALIDOS', detail: 'Alguno de los pacientes seleccionados no está disponible para tu usuario.' }),
    });
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/pacientes`);
    await user.click(await screen.findByRole('button', { name: 'Exportar los datos de Pérez, Juan' }));
    expect(await screen.findByText('Alguno de los pacientes seleccionados no está disponible para tu usuario.')).toBeInTheDocument();
    expect(URL.createObjectURL).not.toHaveBeenCalled();
  });
});
