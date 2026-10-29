import { describe, expect, it } from 'vitest';

import { agruparPorDia, destinoSeguro, EVENTOS, filtrosVisibles, grupoDeDia } from './notificationsCopy.js';

describe('destinoSeguro', () => {
  it.each(['/app/seguridad', '/app/grupo', '/app/grupo/abc', '/app/mediciones', '/app/notificaciones'])('acepta %s', (url) => {
    expect(destinoSeguro(url)).toBe(url);
  });

  it.each([
    null, undefined, '', 'https://malo.example', '//malo.example', '/app/ruta-inventada', '/app/seguridad?x=1', '/app//seguridad',
    'javascript:alert(1)', '/app/seguridad\\..', '/otra/cosa', '/app/grupofalso',
  ])('rechaza %s', (url) => {
    expect(destinoSeguro(url)).toBeNull();
  });
});

describe('agrupación por día', () => {
  const ahora = new Date(2026, 9, 29, 15, 0, 0);

  it('separa Hoy, Ayer y Anteriores según el día', () => {
    expect(grupoDeDia(new Date(2026, 9, 29, 1, 0).toISOString(), ahora)).toBe('HOY');
    expect(grupoDeDia(new Date(2026, 9, 28, 23, 59).toISOString(), ahora)).toBe('AYER');
    expect(grupoDeDia(new Date(2026, 9, 27, 12, 0).toISOString(), ahora)).toBe('ANTERIORES');
    expect(grupoDeDia('no es una fecha', ahora)).toBe('ANTERIORES');
  });

  it('conserva el orden y omite los grupos vacíos', () => {
    const items = [
      { id: 1, fechaCreacion: new Date(2026, 9, 29, 9, 0).toISOString() },
      { id: 2, fechaCreacion: new Date(2026, 9, 20, 9, 0).toISOString() },
      { id: 3, fechaCreacion: new Date(2026, 9, 19, 9, 0).toISOString() },
    ];
    const groups = agruparPorDia(items, ahora);
    expect(groups.map((group) => group.key)).toEqual(['HOY', 'ANTERIORES']);
    expect(groups[1].items.map((item) => item.id)).toEqual([2, 3]);
  });
});

describe('catálogo', () => {
  it('conoce los nueve avisos del backend y las cuentas institucionales solo ven seguridad', () => {
    expect(Object.keys(EVENTOS).sort()).toEqual([
      'ACTIVIDAD_SOSPECHOSA', 'AGREGADO_GRUPO', 'CAMBIO_CONTRASENA', 'CAMBIO_MFA', 'INICIO_SESION', 'INVITACION_GRUPO',
      'MEDICION_GRUPO', 'NUEVA_ACCION_GRUPO', 'RECORDATORIO_MEDICION',
    ]);
    expect(filtrosVisibles('USUARIO_INSTITUCIONAL').map((filtro) => filtro.key)).toEqual(['TODAS', 'NO_LEIDAS', 'SEGURIDAD']);
  });
});
