// «Información sobre tus mediciones»: apartado discreto y expandible que explica los estados y qué se conserva. Las reglas reales las aplica el
// backend (conservación y visibilidad por estado); acá solo se explican. Incluye el aviso de uso experimental.

import { Info } from 'lucide-react';

import { ExperimentalNotice } from '../../../components/ExperimentalNotice.jsx';

const STATES_INFO = [
  ['Pendiente', 'La medición fue iniciada, pero todavía no comenzó la adquisición.', 'Temporal'],
  ['Adquiriendo', 'El dispositivo está recibiendo lecturas.', 'Temporal'],
  ['Procesando', 'El sistema está procesando las lecturas.', 'Temporal'],
  ['Completada', 'La medición terminó correctamente y sus resultados fueron guardados.', 'Permanece en el historial'],
  ['Cancelada', 'El usuario decidió cancelar la medición.', 'Se oculta después de 30 minutos'],
  ['Inválida', 'La medición no cumplió las condiciones necesarias.', 'Se oculta después de 30 minutos'],
];

export const STORAGE_NOTE = 'Las mediciones completadas permanecen disponibles en tu historial. Las mediciones canceladas, inválidas o interrumpidas '
  + 'se ocultan automáticamente después de 30 minutos. El sistema conserva únicamente la información técnica necesaria para auditoría, '
  + 'sin identificar personalmente al usuario.';

export function MeasurementsInfo() {
  return (
    <details className="measurements-info">
      <summary><Info size={16} aria-hidden="true" /> Información sobre tus mediciones</summary>
      <div className="measurements-info-body">
        <table className="info-table">
          <caption className="sr-only">Estados de una medición</caption>
          <thead>
            <tr><th scope="col">Estado</th><th scope="col">Significado</th><th scope="col">Comportamiento</th></tr>
          </thead>
          <tbody>
            {STATES_INFO.map(([state, meaning, behaviour]) => (
              <tr key={state}><th scope="row">{state}</th><td>{meaning}</td><td>{behaviour}</td></tr>
            ))}
          </tbody>
        </table>
        <p className="field-hint">{STORAGE_NOTE}</p>
        <ExperimentalNotice variant="inline" />
      </div>
    </details>
  );
}
