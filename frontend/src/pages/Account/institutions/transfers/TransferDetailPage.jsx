// /app/instituciones/:id/pacientes/transferencias/:idTransferencia — detalle de una transferencia en su propia página.
// Todo sale de GET /institutions/{id}/transfers/{idTransferencia}: el backend decide qué transferencias ve cada rol.
// Los UUID quedan en «Detalles técnicos»; la vista principal usa nombres, rol y descripciones funcionales.

import { ArrowLeft, ArrowRight } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link, useOutletContext, useParams } from 'react-router-dom';

import * as institutionsApi from '../../../../api/institutionsApi.js';
import { Badge } from '../../../../components/Badge.jsx';
import { Alert } from '../../../../components/FormControls.jsx';
import { PatientIdentity, fullName as personName } from '../../../../components/PatientIdentity.jsx';
import { formatInstant } from '../../../../utils/dateTime.js';
import { SEXO_LABELS, ROLE_LABELS } from '../institutionFormat.js';

const STATES = { PENDIENTE: 'Pendiente', ACEPTADA: 'Aceptada', RECHAZADA: 'Rechazada', CANCELADA: 'Cancelada' };
const RELATION_STATES = { ACTIVO: 'Vínculo activo', BAJA: 'Ya no está vinculado/a', PENDIENTE: 'Invitación pendiente' };

const fullName = (party) => (party ? [party.nombre, party.apellido].filter(Boolean).join(' ') || 'Operador no disponible' : 'No registrado');

function Operator({ title, party }) {
  return (
    <div className="transfer-party" aria-label={title}>
      <small>{title}</small>
      <b>{fullName(party)}</b>
      {party && (
        <span className="field-hint">
          {ROLE_LABELS[party.rolInstitucion] ?? 'Operador/a'} · {RELATION_STATES[party.estadoRelacion] ?? 'Vínculo registrado'}
        </span>
      )}
    </div>
  );
}

function Row({ label, value }) {
  return <div><dt>{label}</dt><dd className={value ? undefined : 'is-empty'}>{value || '—'}</dd></div>;
}

export function TransferDetailPage() {
  const { institution, handleOperationError } = useOutletContext();
  const { idTransferencia } = useParams();
  const [transfer, setTransfer] = useState(null);
  const [error, setError] = useState('');
  const backTo = `/app/instituciones/${institution.idInstitucion}/pacientes/transferencias`;

  useEffect(() => {
    let active = true;
    setTransfer(null);
    institutionsApi.getTransfer(institution.idInstitucion, idTransferencia).then(
      (result) => active && setTransfer(result),
      (loadError) => active && setError(handleOperationError(loadError)),
    );
    return () => { active = false; };
  }, [institution.idInstitucion, idTransferencia, handleOperationError]);

  const back = (
    <Link to={backTo} className="back-link"><ArrowLeft size={16} aria-hidden="true" /> Volver a transferencias</Link>
  );

  if (error) {
    return <><Alert>{error}</Alert>{back}</>;
  }
  if (!transfer) return <p className="field-hint" role="status">Cargando la transferencia…</p>;

  const { paciente } = transfer;
  const isTransfer = transfer.tipo === 'TRANSFERENCIA';

  return (
    <>
      {back}
      <section className="panel" aria-labelledby="transferencia-titulo">
        <div className="panel-head">
          <div>
            <h2 id="transferencia-titulo">{isTransfer ? 'Transferencia de paciente' : 'Reasignación de responsable'}</h2>
            <p>{transfer.institucion.nombre}</p>
          </div>
          <Badge tone={transfer.estado === 'ACEPTADA' ? 'success' : 'neutral'}>{STATES[transfer.estado]}</Badge>
        </div>
        <p className="transfer-summary">{transfer.descripcion}</p>
      </section>

      <section className="panel" aria-labelledby="transferencia-paciente">
        <h2 id="transferencia-paciente">Paciente transferido</h2>
        <PatientIdentity name={personName(paciente)} code={paciente.identificadorPseudonimo} available={paciente.datosIdentificativos} />
        <dl className="data-list">
          <Row label="Edad" value={paciente.edad !== null ? `${paciente.edad} años` : null} />
          <Row label="Sexo" value={SEXO_LABELS?.[paciente.sexoModelo] ?? paciente.sexoModelo} />
        </dl>
        {paciente.puedeVerPerfil && (
          <Link to={`/app/instituciones/${institution.idInstitucion}/pacientes/${paciente.idPerfilMedicion}`} className="btn btn-outline">
            Ver perfil del paciente
          </Link>
        )}
      </section>

      <section className="panel" aria-labelledby="transferencia-operadores">
        <h2 id="transferencia-operadores">Operadores involucrados</h2>
        <div className="transfer-flow">
          <Operator title="Operador de origen" party={transfer.origen} />
          <ArrowRight size={28} aria-label="cambia a" role="img" className="transfer-arrow" />
          <Operator title="Operador de destino" party={transfer.destino} />
        </div>
      </section>

      <section className="panel" aria-labelledby="transferencia-info">
        <h2 id="transferencia-info">Información de la transferencia</h2>
        <dl className="data-list">
          <Row label={isTransfer ? 'Solicitante' : 'Realizada por'} value={transfer.solicitante ? `${fullName(transfer.solicitante)}${transfer.solicitante.rolInstitucion ? ` (${ROLE_LABELS[transfer.solicitante.rolInstitucion]})` : ''}` : null} />
          <Row label="Fecha de solicitud" value={formatInstant(transfer.fechaPeticion)} />
          {isTransfer && transfer.estado !== 'PENDIENTE' && (
            <Row label={transfer.estado === 'ACEPTADA' ? 'Fecha de aceptación' : transfer.estado === 'RECHAZADA' ? 'Fecha de rechazo' : 'Fecha de cancelación'}
              value={formatInstant(transfer.fechaRespuesta)} />
          )}
          <Row label="Fecha efectiva del cambio de responsable" value={formatInstant(transfer.fechaTransferencia)} />
          <Row label="Estado" value={STATES[transfer.estado]} />
          <Row label="Institución" value={transfer.institucion.nombre} />
          <Row label="Observación" value={transfer.observacion} />
        </dl>
      </section>

      <section className="panel" aria-labelledby="transferencia-historial">
        <h2 id="transferencia-historial">Historial de estados</h2>
        <ol className="activity-list" aria-label="Historial de estados">
          {transfer.historial.map((step) => (
            <li key={step.clave}>
              <span><b>{step.etiqueta}</b>{step.usuario ? ` · ${step.usuario}` : ''}</span>
              <small>{formatInstant(step.fechaHora)}</small>
            </li>
          ))}
        </ol>
      </section>

      {/* Detalles técnicos: solo propietario y moderador; el backend no los envía al operador. */}
      {transfer.tecnico && (
        <details className="panel audit-technical">
          <summary>Detalles técnicos</summary>
          <dl className="data-list">
            <Row label="Identificador de la transferencia" value={transfer.tecnico.idTransferenciaPerfil} />
            <Row label="Identificador del perfil" value={transfer.tecnico.idPerfilMedicion} />
            <Row label="Vínculo del operador de origen" value={transfer.tecnico.idOperadorOrigen} />
            <Row label="Vínculo del operador de destino" value={transfer.tecnico.idOperadorDestino} />
            <Row label="Identificador de la institución" value={transfer.tecnico.idInstitucion} />
          </dl>
          {transfer.tecnico.eventos.length > 0 && (
            <pre className="audit-json" aria-label="Eventos originales">{JSON.stringify(transfer.tecnico.eventos, null, 2)}</pre>
          )}
        </details>
      )}
    </>
  );
}
