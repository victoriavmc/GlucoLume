// /app/instituciones/:id/transferencias — Transferencias recibidas, enviadas e historial (RF32).
// Un operador ve las suyas y responde las que recibe; propietario y moderador ven el historial de la institución.
// Todo sale de FastAPI; las acciones disponibles las informa el backend en cada transferencia (puedeAceptar, etc.).
// Solo se muestran el identificador seudónimo, la edad y el sexo del paciente: nunca su nombre ni documento.

import { ArrowRightLeft, Check, ChevronLeft, ChevronRight, X } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { Link, useOutletContext, useSearchParams } from 'react-router-dom';

import * as institutionsApi from '../../../../api/institutionsApi.js';
import { Alert } from '../../../../components/FormControls.jsx';
import { Badge } from '../../../../components/Badge.jsx';
import { EmptyState } from '../../../../components/EmptyState.jsx';
import { TabPanel, Tabs } from '../../../../components/Tabs.jsx';
import { PatientIdentity, fullName as personName } from '../../../../components/PatientIdentity.jsx';
import { useLatestRequest } from '../../../../utils/useLatestRequest.js';
import { SEXO_LABELS, formatDateTime } from '../institutionFormat.js';

const PAGE_SIZE = 10;
const STATES = { PENDIENTE: 'Pendiente', ACEPTADA: 'Aceptada', RECHAZADA: 'Rechazada', CANCELADA: 'Cancelada' };
const TABS = {
  recibidas: { label: 'Recibidas', title: 'Transferencias recibidas', operatorOnly: true },
  enviadas: { label: 'Enviadas', title: 'Transferencias enviadas', operatorOnly: true },
  todas: { label: 'Historial', title: 'Historial de transferencias', operatorOnly: false },
};

const fullName = (party) => (party ? [party.nombre, party.apellido].filter(Boolean).join(' ') || 'Operador' : 'No registrado');

function TransferRow({ transfer, busyId, confirming, onAsk, onAct, onBack }) {
  const { paciente } = transfer;
  const busy = busyId === transfer.idTransferenciaPerfil;
  const asking = confirming?.id === transfer.idTransferenciaPerfil ? confirming.action : null;
  const messages = {
    accept: '¿Aceptar? El paciente y sus mediciones pasan a tu cargo.',
    reject: '¿Rechazar la transferencia? El paciente sigue con quien lo transfería.',
    cancel: '¿Cancelar la solicitud?',
  };
  return (
    <li className="member-row">
      <span>
        <PatientIdentity name={personName(paciente)} code={paciente.identificadorPseudonimo} available={paciente.datosIdentificativos} />
        <small> · {paciente.edad !== null ? `${paciente.edad} años` : 'Edad sin informar'} · {SEXO_LABELS?.[paciente.sexoModelo] ?? paciente.sexoModelo}</small>
        <br />
        <small>Operador de origen: {fullName(transfer.origen)} → Operador destinatario: {fullName(transfer.destino)}</small>
        <br />
        <small>
          Solicitada: {formatDateTime(transfer.fechaPeticion)}
          {transfer.fechaTransferencia && ` · Efectiva: ${formatDateTime(transfer.fechaTransferencia)}`}
        </small>
        {transfer.observacion && (<><br /><small>Observación: {transfer.observacion}</small></>)}
        <br />
        <Badge tone={transfer.estado === 'ACEPTADA' ? 'success' : 'neutral'}>{STATES[transfer.estado]}</Badge>
        {transfer.tipo === 'REASIGNACION' && <> <Badge tone="neutral">Reasignación directa</Badge></>}
        {' '}
        <Link to={transfer.idTransferenciaPerfil} className="btn btn-ghost"
          aria-label={`Ver detalle de la transferencia de ${paciente.identificadorPseudonimo}`}>Ver detalle</Link>
      </span>
      {(transfer.puedeAceptar || transfer.puedeCancelar) && (
        <span className="member-actions">
          {asking ? (
            <>
              <span className="field-hint">{messages[asking]}</span>
              <button type="button" className="btn btn-primary" disabled={busy} onClick={() => onAct(transfer, asking)}>
                {busy && <span className="spinner" aria-hidden="true" />} Confirmar
              </button>
              <button type="button" className="btn btn-ghost" disabled={busy} onClick={onBack}>Volver</button>
            </>
          ) : (
            <>
              {transfer.puedeAceptar && (
                <>
                  <button type="button" className="btn btn-primary" onClick={() => onAsk(transfer, 'accept')}
                    aria-label={`Aceptar transferencia de ${paciente.identificadorPseudonimo}`}>
                    <Check size={16} aria-hidden="true" /> Aceptar
                  </button>
                  <button type="button" className="btn btn-outline" onClick={() => onAsk(transfer, 'reject')}
                    aria-label={`Rechazar transferencia de ${paciente.identificadorPseudonimo}`}>
                    <X size={16} aria-hidden="true" /> Rechazar
                  </button>
                </>
              )}
              {transfer.puedeCancelar && (
                <button type="button" className="btn btn-outline" onClick={() => onAsk(transfer, 'cancel')}
                  aria-label={`Cancelar transferencia de ${paciente.identificadorPseudonimo}`}>
                  <X size={16} aria-hidden="true" /> Cancelar solicitud
                </button>
              )}
            </>
          )}
        </span>
      )}
    </li>
  );
}

export function TransfersPage() {
  const { institution, handleOperationError } = useOutletContext();
  const isOperator = institution.rolInstitucion === 'OPERADOR';
  const tabs = Object.entries(TABS).filter(([, tab]) => isOperator || !tab.operatorOnly);
  const [searchParams] = useSearchParams();
  const requested = searchParams.get('direccion');
  const [direccion, setDireccion] = useState(
    tabs.some(([key]) => key === requested) ? requested : isOperator ? 'recibidas' : 'todas',
  );
  const [pagina, setPagina] = useState(1);
  const [page, setPage] = useState(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [confirming, setConfirming] = useState(null);
  const [busyId, setBusyId] = useState(null);

  const beginRequest = useLatestRequest(); // una respuesta lenta de un filtro anterior no pisa a la del filtro actual

  const load = useCallback(async () => {
    const isCurrent = beginRequest();
    try {
      const result = await institutionsApi.listTransfers(institution.idInstitucion, { direccion, pagina, tamanioPagina: PAGE_SIZE });
      if (isCurrent()) setPage(result);
    } catch (loadError) {
      if (!isCurrent()) return;
      setError(handleOperationError(loadError));
      setPage({ items: [], total: 0, pagina: 1, tamanioPagina: PAGE_SIZE });
    }
  }, [institution.idInstitucion, direccion, pagina, handleOperationError, beginRequest]);

  useEffect(() => {
    load();
  }, [load]);

  async function act(transfer, action) {
    setBusyId(transfer.idTransferenciaPerfil);
    setError('');
    setNotice('');
    const calls = { accept: institutionsApi.acceptTransfer, reject: institutionsApi.rejectTransfer, cancel: institutionsApi.cancelTransfer };
    const done = {
      accept: 'Aceptaste la transferencia: el paciente ya está a tu cargo.',
      reject: 'Rechazaste la transferencia. El paciente sigue con quien lo transfería.',
      cancel: 'Cancelaste la solicitud de transferencia.',
    };
    try {
      await calls[action](institution.idInstitucion, transfer.idTransferenciaPerfil);
      setNotice(done[action]);
      setConfirming(null);
    } catch (actionError) {
      setError(handleOperationError(actionError));
      setConfirming(null);
    } finally {
      setBusyId(null);
      await load();
    }
  }

  const totalPages = page ? Math.max(1, Math.ceil(page.total / PAGE_SIZE)) : 1;
  const pending = page ? page.items.filter((item) => item.estado === 'PENDIENTE') : [];
  const answered = page ? page.items.filter((item) => item.estado !== 'PENDIENTE') : [];
  const rowProps = {
    busyId, confirming, onAsk: (transfer, action) => { setNotice(''); setConfirming({ id: transfer.idTransferenciaPerfil, action }); },
    onAct: act, onBack: () => setConfirming(null),
  };

  return (
    <section className="panel" aria-labelledby="transferencias-titulo">
      <div className="panel-title">
        <span className="panel-icon"><ArrowRightLeft size={22} aria-hidden="true" /></span>
        <div>
          <h2 id="transferencias-titulo">{TABS[direccion].title}</h2>
          <p>El responsable de un paciente cambia solo cuando el operador destinatario acepta.</p>
        </div>
      </div>
      {tabs.length > 1 && (
        <Tabs label="Tipo de transferencias" idBase="transfers" variant="pill" value={direccion}
          items={tabs.map(([key, tab]) => ({ key, label: tab.label }))}
          onChange={(key) => { setDireccion(key); setPagina(1); setPage(null); setConfirming(null); setNotice(''); }} />
      )}
      {notice && <Alert kind="success">{notice}</Alert>}
      {error && <Alert>{error}</Alert>}
      <TabPanel idBase="transfers" value={direccion} className="ui-stack">
      {page === null ? (
        <p className="field-hint" role="status">Cargando transferencias…</p>
      ) : page.items.length === 0 ? (
        <EmptyState variant="framed" headingLevel={0} title="No hay transferencias en esta sección." />
      ) : direccion === 'todas' ? (
        <ul className="member-list-items" aria-label="Historial de transferencias">
          {page.items.map((item) => <TransferRow key={item.idTransferenciaPerfil} transfer={item} {...rowProps} />)}
        </ul>
      ) : (
        <>
          {pending.length > 0 && (
            <>
              <h3 className="member-list-title">Pendientes</h3>
              <ul className="member-list-items" aria-label="Transferencias pendientes">
                {pending.map((item) => <TransferRow key={item.idTransferenciaPerfil} transfer={item} {...rowProps} />)}
              </ul>
            </>
          )}
          {answered.length > 0 && (
            <>
              <h3 className="member-list-title">{direccion === 'recibidas' ? 'Historial de respuestas' : 'Respondidas y canceladas'}</h3>
              <ul className="member-list-items" aria-label="Transferencias respondidas">
                {answered.map((item) => <TransferRow key={item.idTransferenciaPerfil} transfer={item} {...rowProps} />)}
              </ul>
            </>
          )}
        </>
      )}
      </TabPanel>
      {page && page.total > PAGE_SIZE && (
        <nav className="pagination" aria-label="Páginas de transferencias">
          <button type="button" className="btn btn-ghost" disabled={pagina <= 1} onClick={() => setPagina((p) => p - 1)}>
            <ChevronLeft size={16} aria-hidden="true" /> Anterior
          </button>
          <span>Página {page.pagina} de {totalPages} · {page.total} transferencias</span>
          <button type="button" className="btn btn-ghost" disabled={pagina >= totalPages} onClick={() => setPagina((p) => p + 1)}>
            Siguiente <ChevronRight size={16} aria-hidden="true" />
          </button>
        </nav>
      )}
    </section>
  );
}
