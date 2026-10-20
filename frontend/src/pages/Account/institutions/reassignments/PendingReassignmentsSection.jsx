// Panel de la institución (propietario y moderador): pacientes pendientes de reasignación y avisos de bajas de operadores.
// Los números salen de FastAPI (/reassignments). Sin pendientes no muestra nada: no es una sección vacía permanente.

import { BellRing } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import * as institutionsApi from '../../../../api/institutionsApi.js';
import { formatDateTime } from '../institutionFormat.js';

export function PendingReassignmentsSection({ institution }) {
  const [overview, setOverview] = useState(null);

  useEffect(() => {
    let active = true;
    institutionsApi.getReassignments(institution.idInstitucion).then((value) => active && setOverview(value), () => {});
    return () => { active = false; };
  }, [institution.idInstitucion]);

  const unregistered = overview?.sinRegularizar ?? 0;
  if (!overview || (overview.pendientes === 0 && unregistered === 0)) return null;
  const waiting = overview.grupos.filter((group) => group.estado === 'PENDIENTE');
  return (
    <section className="panel is-warn" aria-labelledby="pendientes-reasignacion">
      <div className="panel-title">
        <span className="panel-icon"><BellRing size={22} aria-hidden="true" /></span>
        <div>
          <h2 id="pendientes-reasignacion">Pacientes pendientes de reasignación</h2>
          {overview.pendientes > 0 && (
            <p>
              {overview.pendientes === 1 ? '1 paciente espera' : `${overview.pendientes} pacientes esperan`} un nuevo operador responsable
              {' '}({waiting.length === 1 ? '1 transferencia pendiente' : `${waiting.length} transferencias pendientes`}).
            </p>
          )}
        </div>
      </div>
      {unregistered > 0 && (
        <p className="field-hint">
          Además, {unregistered === 1 ? '1 paciente figura' : `${unregistered} pacientes figuran`} a cargo de operadores ya desvinculados y {unregistered === 1 ? 'necesita' : 'necesitan'} regularizarse.
        </p>
      )}
      <ul className="member-list" aria-label="Bajas de operadores con pacientes a cargo">
        {waiting.map((group) => (
          <li key={group.idOperadorAnterior} className="member-row">
            <span>
              <b>{group.operadorAnterior ?? 'Operador no identificado'}</b> dejó la institución
              {group.fechaDesvinculacion ? ` el ${formatDateTime(group.fechaDesvinculacion)}` : ''}.
              <br />
              <small>{group.pendientes === 1 ? '1 paciente sin responsable' : `${group.pendientes} pacientes sin responsable`}</small>
            </span>
          </li>
        ))}
      </ul>
      <div className="form-actions">
        <Link to="pacientes/reasignaciones" className="btn btn-primary">Gestionar transferencia</Link>
      </div>
    </section>
  );
}
