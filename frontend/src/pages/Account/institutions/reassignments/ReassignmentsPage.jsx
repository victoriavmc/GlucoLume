// /app/instituciones/:id/pacientes/reasignaciones — Pacientes pendientes de reasignación (propietario y moderador).
// Cuando se desvincula a un operador con pacientes a cargo, sus pacientes activos quedan acá. La persona autorizada elige UN operador activo
// y reasigna uno o varios pacientes juntos. Nunca se elige un destinatario automáticamente. Todo sale de FastAPI, que vuelve a validar el
// destinatario (operador activo de la misma institución) y el permiso en cada llamada. Solo se muestran seudónimo y nombre del paciente.

import { ArrowRightLeft, CheckCircle2, TriangleAlert, Users } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { useOutletContext } from 'react-router-dom';

import * as institutionsApi from '../../../../api/institutionsApi.js';
import { friendlyError } from '../../../../auth/errorMessages.js';
import { Badge } from '../../../../components/Badge.jsx';
import { EmptyState } from '../../../../components/EmptyState.jsx';
import { Alert, CheckField, SelectField, TextAreaField } from '../../../../components/FormControls.jsx';
import { PatientIdentity } from '../../../../components/PatientIdentity.jsx';
import { formatDateTime } from '../institutionFormat.js';

const OUTCOME_LABELS = {
  REASIGNADO: 'reasignados', YA_RESUELTA: 'ya estaban resueltos', PACIENTE_DADO_DE_BAJA: 'dados de baja (no necesitan responsable)',
  NO_ENCONTRADA: 'no encontrados',
};
const fullName = (item) => [item.nombre, item.apellido].filter(Boolean).join(' ') || null;

function summarize(result) {
  const counts = {};
  result.resultados.forEach((item) => { counts[item.resultado] = (counts[item.resultado] ?? 0) + 1; });
  return Object.entries(counts).map(([key, count]) => `${count} ${OUTCOME_LABELS[key] ?? key}`).join(', ');
}

function ManagePanel({ institution, group, operators, onDone }) {
  const [items, setItems] = useState(null);
  const [selected, setSelected] = useState(new Set());
  const [target, setTarget] = useState('');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    institutionsApi.getReassignmentItems(institution.idInstitucion, { estado: 'PENDIENTE', idOperadorAnterior: group.idOperadorAnterior, tamanioPagina: 100 })
      .then((page) => { if (active) { setItems(page.items); setSelected(new Set(page.items.map((item) => item.idReasignacionPaciente))); } },
        (loadError) => { if (active) { setError(friendlyError(loadError)); setItems([]); } });
    return () => { active = false; };
  }, [institution.idInstitucion, group.idOperadorAnterior]);

  function toggle(id) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  async function confirm() {
    setBusy(true);
    setError('');
    try {
      const body = { idsReasignacion: [...selected], idOperadorNuevo: target, ...(note.trim() ? { observacion: note.trim() } : {}) };
      const result = await institutionsApi.assignReassignments(institution.idInstitucion, body);
      onDone(`Resultado de la transferencia: ${summarize(result)}.`);
    } catch (assignError) {
      setError(friendlyError(assignError));
      setBusy(false);
    }
  }

  const allSelected = items && items.length > 0 && selected.size === items.length;
  return (
    <div className="reassign-panel">
      {error && <Alert>{error}</Alert>}
      {items === null && <div className="auth-status" role="status"><span className="spinner" aria-hidden="true" /> Cargando pacientes…</div>}
      {items && items.length > 0 && (
        <>
          <CheckField label={`Seleccionar todos (${items.length})`} checked={allSelected}
            onChange={() => setSelected(allSelected ? new Set() : new Set(items.map((item) => item.idReasignacionPaciente)))} />
          <ul className="member-list" aria-label={`Pacientes de ${group.operadorAnterior ?? 'operador anterior'}`}>
            {items.map((item) => (
              <li key={item.idReasignacionPaciente} className="member-row">
                <CheckField checked={selected.has(item.idReasignacionPaciente)} onChange={() => toggle(item.idReasignacionPaciente)}
                  aria-label={`Seleccionar ${item.identificadorPseudonimo ?? 'paciente'}`}
                  label={<PatientIdentity name={fullName(item)} code={item.identificadorPseudonimo} available={fullName(item) ? true : false} />} />
              </li>
            ))}
          </ul>
          <SelectField label="Nuevo operador responsable" value={target} onChange={(event) => setTarget(event.target.value)}
            hint={operators.length === 0 ? 'No hay operadores activos disponibles. La tarea queda pendiente hasta que se incorpore uno.' : undefined}>
            <option value="">Elegí un operador activo…</option>
            {operators.map((operator) => (
              <option key={operator.idInstitucionUsuario} value={operator.idInstitucionUsuario}>
                {[operator.nombre, operator.apellido].filter(Boolean).join(' ')}
              </option>
            ))}
          </SelectField>
          <TextAreaField label="Motivo (opcional)" rows={2} maxLength={500} value={note} onChange={(event) => setNote(event.target.value)} />
          <div className="form-actions">
            <button type="button" className="btn btn-primary" disabled={busy || !target || selected.size === 0} onClick={confirm}>
              {busy && <span className="spinner" aria-hidden="true" />} Confirmar transferencia ({selected.size})
            </button>
          </div>
        </>
      )}
    </div>
  );
}

// Operadores ya desvinculados que figuran como responsables de pacientes sin que exista una tarea de reasignación (una baja anterior a la
// reasignación obligatoria). Regularizar solo CREA las tareas pendientes de ese operador, a pedido de quien gestiona: no reasigna a nadie.
function UnregisteredSection({ institution, groups, onDone }) {
  const [busyId, setBusyId] = useState('');
  const [error, setError] = useState('');

  async function regularize(group) {
    setBusyId(group.idOperadorAnterior);
    setError('');
    try {
      const result = await institutionsApi.regularizeReassignments(institution.idInstitucion, group.idOperadorAnterior);
      onDone(`Regularizamos a ${group.operadorAnterior ?? 'el operador anterior'}: ${result.pacientesPendientes === 1 ? '1 paciente quedó' : `${result.pacientesPendientes} pacientes quedaron`} pendiente${result.pacientesPendientes === 1 ? '' : 's'} de reasignación.`);
    } catch (regularizeError) {
      setError(friendlyError(regularizeError));
    } finally {
      setBusyId('');
    }
  }

  const total = groups.reduce((sum, group) => sum + group.pacientes, 0);
  return (
    <section className="reassign-orphans" aria-labelledby="sin-regularizar">
      <h3 id="sin-regularizar"><TriangleAlert size={18} aria-hidden="true" className="inline-icon" /> Asignaciones por regularizar</h3>
      <p className="field-hint">
        {total === 1 ? '1 paciente figura' : `${total} pacientes figuran`} a cargo de operadores que ya no pertenecen a la institución y todavía no
        tienen una reasignación pendiente. Al regularizar, esos pacientes pasan a la lista de pendientes para que elijas quién se hace cargo:
        no se reasigna nada automáticamente.
      </p>
      {error && <Alert>{error}</Alert>}
      <ul className="member-list" aria-label="Operadores desvinculados con pacientes sin regularizar">
        {groups.map((group) => (
          <li key={group.idOperadorAnterior} className="member-row">
            <span>
              <b>{group.operadorAnterior ?? 'Operador no identificado'}</b>
              <br />
              <small>
                {group.pacientes === 1 ? '1 paciente necesita responsable' : `${group.pacientes} pacientes necesitan responsable`}
                {group.fechaDesvinculacion ? ` · Desvinculado el ${formatDateTime(group.fechaDesvinculacion)}` : ''}
              </small>
            </span>
            <span className="member-actions">
              <button type="button" className="btn btn-outline" disabled={busyId !== ''} onClick={() => regularize(group)}
                aria-label={`Regularizar a ${group.operadorAnterior ?? 'operador anterior'}`}>
                {busyId === group.idOperadorAnterior && <span className="spinner" aria-hidden="true" />} Regularizar
              </button>
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

export default function ReassignmentsPage() {
  const { institution } = useOutletContext();
  const [overview, setOverview] = useState(null);
  const [operators, setOperators] = useState([]);
  const [opened, setOpened] = useState(null);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      const [summary, available] = await Promise.all([
        institutionsApi.getReassignments(institution.idInstitucion), institutionsApi.getAssignableOperators(institution.idInstitucion)]);
      setOverview(summary);
      setOperators(available);
      setError('');
    } catch (loadError) {
      setError(friendlyError(loadError));
      setOverview({ pendientes: 0, operadoresDisponibles: 0, grupos: [] });
    }
  }, [institution.idInstitucion]);

  useEffect(() => { load(); }, [load]);

  function handleDone(message) {
    setNotice(message);
    setOpened(null);
    load();
  }

  return (
    <section className="panel" aria-labelledby="reasignaciones-titulo">
      <div className="panel-title">
        <span className="panel-icon"><ArrowRightLeft size={22} aria-hidden="true" /></span>
        <div>
          <h2 id="reasignaciones-titulo">Pacientes pendientes de reasignación</h2>
          <p>
            Pacientes de operadores que dejaron la institución. Mientras estén pendientes nadie puede registrar mediciones para ellos y
            el operador anterior no tiene acceso. Elegí quién se hace cargo: no se asigna a nadie de forma automática.
          </p>
        </div>
      </div>

      {error && <Alert>{error}</Alert>}
      {notice && <Alert kind="success">{notice}</Alert>}
      {overview === null && <div className="auth-status" role="status"><span className="spinner" aria-hidden="true" /> Cargando…</div>}

      {overview && overview.sinRegularizar > 0 && (
        <UnregisteredSection institution={institution} groups={overview.gruposSinRegularizar} onDone={handleDone} />
      )}

      {overview && overview.grupos.length === 0 && overview.sinRegularizar === 0 && !error && (
        <EmptyState variant="framed" icon={CheckCircle2} headingLevel={0} title="No hay pacientes pendientes de reasignación." />
      )}

      {overview && overview.grupos.length > 0 && (
        <ul className="member-list" aria-label="Operadores desvinculados">
          {overview.grupos.map((group) => (
            <li key={group.idOperadorAnterior} className="member-row reassign-group">
              <span>
                <b><Users size={16} aria-hidden="true" className="inline-icon" /> {group.operadorAnterior ?? 'Operador no identificado'}</b>
                <br />
                <small>
                  Operador anterior · Desvinculado el {group.fechaDesvinculacion ? formatDateTime(group.fechaDesvinculacion) : 'sin fecha'}
                </small>
                <br />
                <small>
                  Pacientes pendientes: <b>{group.pendientes}</b>
                  {group.completadas > 0 && <> · Reasignados: {group.completadas}</>}
                </small>
                <br />
                <Badge tone={group.estado === 'PENDIENTE' ? 'warning' : 'success'}>
                  {group.estado === 'PENDIENTE' ? 'Pendiente de reasignación' : 'Reasignación resuelta'}
                </Badge>
              </span>
              {group.estado === 'PENDIENTE' && (
                <span className="member-actions">
                  <button type="button" className="btn btn-primary" aria-expanded={opened === group.idOperadorAnterior}
                    onClick={() => setOpened(opened === group.idOperadorAnterior ? null : group.idOperadorAnterior)}>
                    Gestionar transferencia
                  </button>
                </span>
              )}
              {opened === group.idOperadorAnterior && (
                <ManagePanel institution={institution} group={group} operators={operators} onDone={handleDone} />
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
