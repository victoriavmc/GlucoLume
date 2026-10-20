import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

import { clearTokens, saveTokens } from '../../../../auth/tokenStore.js';
import { ACCOUNT, TOKENS, jsonResponse, mockApi } from '../../../../test/helpers.js';
import { renderAt } from '../../../../test/renderApp.jsx';

const INSTITUTIONAL = { ...ACCOUNT, usuario: { ...ACCOUNT.usuario, tipoCuenta: 'USUARIO_INSTITUCIONAL' } };
const ID = '9a000000-0000-4000-8000-000000000001';
const BASE = `/institutions/${ID}`;
const PERMISOS = ['CONSULTAR_INSTITUCION', 'CONSULTAR_PACIENTES', 'GESTIONAR_PACIENTES'];
const DETAIL = {
  idInstitucion: ID, nombre: 'Centro Médico', tipoInstitucion: 'CLINICA', estado: 'ACTIVA', rolInstitucion: 'OPERADOR', estadoRelacion: 'ACTIVO',
  permisos: PERMISOS, tipoIdentificadorLegal: 'CUIT', identificadorLegal: '30712345671', descripcion: null, fechaCreacion: '2026-10-01T10:00:00',
  fechaActualizacion: '2026-10-01T10:00:00', propietario: { nombre: 'Victoria', apellido: 'Cortés' }, cantidadModeradores: 1, cantidadOperadores: 1, cantidadPacientes: 2,
};

const AGES = ['0-12', '13-17', '18-30', '31-50', '51-70', '71+'];

/** Respuesta del análisis con `demo` mediciones DEMO y `experimentales` experimentales (todas completadas, de oximetría). */
function analytics({ origen, experimentales, demo }) {
  const shown = origen === 'EXPERIMENTAL' ? experimentales : origen === 'DEMO' ? demo : experimentales + demo;
  const exp = origen === 'DEMO' ? 0 : experimentales;
  const dem = origen === 'EXPERIMENTAL' ? 0 : demo;
  const missing = (campo) => ({ campo, sinDato: 0, sobre: shown });
  return {
    periodo: { dias: 30, desde: null, hasta: null },
    filtros: {
      idPerfilMedicion: null, sexo: null, edad: null, edadBase: 'ACTUAL', edadCortes: [12, 17, 30, 50, 70], alimentacion: null, modo: null, origen, estado: 'TODOS',
      calidad: null, calidadMinima: null, variable: 'spo2', granularidad: 'dia', segmentar: 'NINGUNA', compararMatriz: false,
    },
    kpis: {
      sinResultado: 1, pacientesEnAlcance: 2, pacientesConMediciones: shown ? 2 : 0, totalMediciones: shown, completadas: shown, experimentales: exp, demo: dem,
      porModo: { OXIMETRIA: shown, GLUCOSA_EXPERIMENTAL: 0 }, conSenalValida: 0,
      faltantes: ['spo2', 'frecuenciaCardiaca', 'glucosa', 'calidadSenal', 'alimentacion', 'edadAlMomento'].map(missing),
    },
    sexo: [{ categoria: 'MASCULINO', pacientes: 1, conMediciones: 1 }, { categoria: 'FEMENINO', pacientes: 0, conMediciones: 0 }, { categoria: 'SIN_INFORMAR', pacientes: 1, conMediciones: 1 }],
    edades: [...AGES, 'SIN_INFORMAR'].map((categoria) => ({ categoria, pacientes: categoria === '13-17' || categoria === 'SIN_INFORMAR' ? 1 : 0, conMediciones: 0 })),
    rangosEdad: [...AGES, 'SIN_INFORMAR'],
    segmentacion: [],
    porModoOrigen: [{ modo: 'OXIMETRIA', origen: 'EXPERIMENTAL', mediciones: exp }, { modo: 'OXIMETRIA', origen: 'DEMO', mediciones: dem }],
    alimentacion: [{ categoria: 'AYUNO', mediciones: 0 }, { categoria: 'POSTPRANDIAL', mediciones: 0 }, { categoria: 'NO_INFORMADA', mediciones: shown }],
    evolucion: shown ? [{ periodo: '2026-10-17', experimentales: exp, demo: dem }] : [],
    variable: { variable: 'spo2', unidad: '%', series: [] },
    calidad: { conValor: 0, sinInformar: shown, rangos: [], conLecturas: shown ? 1 : 0, lecturas: shown ? [{ lecturas: 5, experimentales: exp ? 1 : 0, demo: dem ? 1 : 0 }] : [] },
    pacientes: { items: [], total: 2, pagina: 1, tamanioPagina: 10 },
    paciente: null,
    truncado: false,
    edadBaseDemografia: 'ACTUAL',
    origenes: { experimentales, demo, sinResultado: 1 },
  };
}

let analyticsCalls;

function routes() {
  analyticsCalls = [];
  return mockApi({
    'GET /auth/me': jsonResponse(200, INSTITUTIONAL),
    [`GET ${BASE}`]: jsonResponse(200, DETAIL),
    [`GET ${BASE}/patients`]: jsonResponse(200, { items: [], total: 0, pagina: 1, tamanioPagina: 50 }),
    [`GET ${BASE}/analytics/patients`]: (_options, url) => {
      const params = new URL(url).searchParams;
      analyticsCalls.push(params);
      return jsonResponse(200, analytics({ origen: params.get('origen'), experimentales: 0, demo: 6 }));
    },
  });
}

beforeEach(() => {
  clearTokens();
  saveTokens(TOKENS, false);
});

describe('Análisis detallado de mediciones', () => {
  it('arranca con todas las fuentes y todos los estados: las DEMO no se excluyen en silencio', async () => {
    routes();
    renderAt(`/app/instituciones/${ID}/pacientes/analisis`);
    expect(await screen.findByText(/Con estos filtros:/)).toHaveTextContent('0 experimentales · 6 DEMO (sintéticas) · 1 sin resultado');
    expect(screen.getByRole('combobox', { name: 'Origen de los datos' })).toHaveValue('TODOS');
    expect(analyticsCalls[0].get('origen')).toBe('TODOS');
    expect(analyticsCalls[0].get('estado')).toBe('TODOS');
    expect(screen.getByText(/Se muestran separadas y nunca se promedian juntas/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'panel' })).toBeInTheDocument(); // el alcance se explica y se enlaza al panel
  });

  it('conserva el período y el origen que llegan del panel del operador', async () => {
    routes();
    renderAt(`/app/instituciones/${ID}/pacientes/analisis?dias=7&origen=TODOS`);
    await screen.findByText(/Con estos filtros:/);
    expect(analyticsCalls[0].get('dias')).toBe('7');
    expect(screen.getByRole('combobox', { name: 'Período' })).toHaveValue('7');
  });

  it('con «solo experimental» y únicamente DEMO explica los totales por origen y permite ver todas las fuentes', async () => {
    routes();
    renderAt(`/app/instituciones/${ID}/pacientes/analisis?origen=EXPERIMENTAL`);
    const notice = await screen.findByText(/los registros no desaparecieron/);
    expect(notice).toHaveTextContent('0 experimentales y 6 DEMO');
    await userEvent.click(screen.getByRole('button', { name: 'Ver todas las fuentes' }));
    await waitFor(() => expect(analyticsCalls.at(-1).get('origen')).toBe('TODOS'));
    expect(await screen.findByText(/Con estos filtros:/)).toHaveTextContent('0 experimentales · 6 DEMO');
    expect(screen.queryByText(/los registros no desaparecieron/)).not.toBeInTheDocument();
  });

  it('los filtros principales están a la vista y los secundarios en «Más filtros»', async () => {
    routes();
    renderAt(`/app/instituciones/${ID}/pacientes/analisis`);
    await screen.findByText(/Con estos filtros:/);
    for (const name of ['Período', 'Paciente', 'Origen de los datos', 'Modo de medición', 'Variable a analizar']) {
      expect(screen.getByRole('combobox', { name }).closest('details')).toBeNull();
    }
    const more = within(screen.getByText(/Más filtros/).closest('details'));
    for (const name of ['Estado', 'Alimentación', 'Agrupar por']) expect(more.getByRole('combobox', { name })).toBeInTheDocument();
  });

  it('sin calidad de señal explica que el equipo no la informa y muestra las lecturas estabilizadas aparte', async () => {
    routes();
    renderAt(`/app/instituciones/${ID}/pacientes/analisis`);
    expect(await screen.findByText(/no la informan, y no se inventa/)).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Lecturas estabilizadas por medición' })).toBeInTheDocument();
    expect(screen.getByText(/No es la calidad de señal/)).toBeInTheDocument();
  });
});
