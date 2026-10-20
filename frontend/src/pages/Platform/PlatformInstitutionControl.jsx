// Control de una institución desde la Administración de GlucoLume: aviso de pausa vigente, acciones (pausar, reactivar, modificar el límite de
// cuentas) y auditoría administrativa de la institución. Lo ven el administrador y el moderador del sistema; los permisos (GESTIONAR_ESTADO_INSTITUCIONES,
// GESTIONAR_CUPOS_INSTITUCIONES, AUDITAR_INSTITUCIONES) los decide FastAPI en cada llamada: ocultar un botón acá es solo presentación.

import { ClipboardList, Gauge, Pause, Play, Trash2, TriangleAlert } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';

import * as platformApi from '../../api/platformApi.js';
import { friendlyError } from '../../auth/errorMessages.js';
import { Badge } from '../../components/Badge.jsx';
import { Alert, TextAreaField, TextField } from '../../components/FormControls.jsx';
import { Modal } from '../../components/Modal.jsx';
import { ReauthFields, useReauth } from '../../components/Reauth.jsx';
import { formatDateTime, formatNumber } from '../Account/groups/groupFormat.js';

const n = (value) => formatNumber(value ?? 0);
const MIN_REASON = 10;
const MAX_CAPACITY = 100000;
const CATEGORY_LABEL = {
  REGISTRO: 'Registro', PAUSA: 'Pausa y reactivación', CIERRE: 'Cierre', CUPOS: 'Cupos', CUENTAS: 'Cuentas', EXPORTACIONES: 'Exportaciones',
  AUTENTICACION: 'Accesos fallidos', SEGURIDAD: 'Seguridad',
};

/** Pausa vigente: motivo, fecha y rol de quien la aplicó. Sin evidencia en la auditoría se avisa, porque el estado es la fuente de verdad. */
export function SuspensionNotice({ detail }) {
  if (detail.fila.estado !== 'INACTIVA') return null;
  const { suspension } = detail;
  return (
    <Alert kind="info">
      <b>Institución pausada.</b> Nadie de su equipo puede operarla: sin ingreso al contexto institucional, cuentas, pacientes, mediciones ni dispositivos. No se eliminó ningún dato.
      {suspension ? (
        <> Pausada el {formatDateTime(suspension.fecha)}{suspension.rolActor ? ` por ${suspension.rolActor === 'ADMINISTRADOR_PLATAFORMA' ? 'el administrador' : 'un moderador'} del sistema` : ''}.
          {suspension.motivo && <> Motivo: «{suspension.motivo}».</>}</>
      ) : <> No hay un registro de pausa en la auditoría (el estado se cambió por fuera de la aplicación).</>}
    </Alert>
  );
}

/** Institución eliminada por la administración (no por su propietario): no se puede reabrir desde la cuenta. */
export function AdministrativeClosureNotice({ detail }) {
  const closure = detail.cierreAdministrativo;
  if (!closure) return null;
  return (
    <Alert kind="info">
      <b>Eliminada por la administración de GlucoLume</b> el {formatDateTime(closure.fecha)}. Motivo: «{closure.motivo}». Su propietario no puede reabrirla desde su cuenta;
      los datos de pacientes se conservan durante el plazo de retención y luego se desidentifican.
    </Alert>
  );
}

/** Exceso sobre el límite: las cuentas se conservan, pero no se admiten nuevas hasta regularizar. */
export function ExcessNotice({ detail }) {
  if (!detail.excedente) return null;
  return (
    <Alert kind="info">
      <TriangleAlert size={16} aria-hidden="true" /> <b>Institución excedida:</b> tiene {n(detail.cupoUtilizado)} cuentas activas y su límite es {n(detail.fila.limiteCuentas)}{' '}
      ({n(detail.excedente)} de más). Las cuentas existentes se conservan, pero no se pueden incorporar cuentas nuevas hasta ampliar el límite o liberar cupos.
    </Alert>
  );
}

function ReasonDialog({ title, intro, confirmLabel, extra, extraValid = true, onConfirm, onClose }) {
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const clean = reason.trim();
  const valid = clean.length >= MIN_REASON && extraValid;

  async function submit(event) {
    event.preventDefault();
    if (!valid || busy) return;
    setBusy(true);
    setError('');
    try {
      await onConfirm(clean);
    } catch (failure) {
      setError(friendlyError(failure));
      setBusy(false);
    }
  }

  return (
    <Modal role="dialog" title={title} onClose={busy ? undefined : onClose}
      actions={(
        <>
          <button type="button" className="btn btn-ghost" onClick={onClose} disabled={busy}>Cancelar</button>
          <button type="submit" form="pd-reason-form" className="btn btn-primary" disabled={!valid || busy}>
            {busy ? 'Guardando…' : confirmLabel}
          </button>
        </>
      )}>
      <form id="pd-reason-form" onSubmit={submit} noValidate>
        <p>{intro}</p>
        {extra}
        <TextAreaField label="Motivo" name="motivo" rows={3} maxLength={300} value={reason} onChange={(event) => setReason(event.target.value)}
          hint={`Obligatorio (mínimo ${MIN_REASON} caracteres). Queda en la auditoría junto con tu usuario, tu rol y la fecha.`} />
        {error && <Alert>{error}</Alert>}
      </form>
    </Modal>
  );
}

/** Eliminación administrativa: nombre exacto, motivo y reautenticación reforzada (contraseña y código MFA). El backend vuelve a validar todo. */
function DeleteDialog({ detail, hasPassword, onConfirm, onClose }) {
  const [name, setName] = useState('');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const reauth = useReauth(hasPassword);
  const row = detail.fila;
  const cleanReason = reason.trim();
  const valid = name.trim().toLowerCase() === row.nombre.trim().toLowerCase() && cleanReason.length >= MIN_REASON && !reauth.missing;

  async function submit(event) {
    event.preventDefault();
    if (!valid || busy) return;
    setBusy(true);
    setError('');
    try {
      await onConfirm({ motivo: cleanReason, confirmacionNombre: name.trim(), reautenticacion: reauth.body() });
    } catch (failure) {
      setError(friendlyError(failure));
      setBusy(false);
      reauth.reset();
    }
  }

  return (
    <Modal role="dialog" title="Eliminar institución" onClose={busy ? undefined : onClose}
      actions={(
        <>
          <button type="button" className="btn btn-ghost" onClick={onClose} disabled={busy}>Cancelar</button>
          <button type="submit" form="pd-delete-form" className="btn btn-primary" disabled={!valid || busy}>{busy ? 'Eliminando…' : 'Eliminar institución'}</button>
        </>
      )}>
      <form id="pd-delete-form" onSubmit={submit} noValidate>
        <Alert kind="info">
          <TriangleAlert size={16} aria-hidden="true" /> Es un cierre administrativo: se dan de baja todos los vínculos, se revocan los accesos y <b>su propietario no podrá reabrirla</b>.
          No se borran datos clínicos: se conservan durante el plazo de retención y luego se desidentifican. Se avisa por correo a su equipo.
        </Alert>
        <TextField label={`Escribí el nombre exacto: ${row.nombre}`} name="confirmacionNombre" maxLength={150} autoComplete="off" value={name}
          onChange={(event) => setName(event.target.value)} />
        <TextAreaField label="Motivo" name="motivo" rows={3} maxLength={300} value={reason} onChange={(event) => setReason(event.target.value)}
          hint={`Obligatorio (mínimo ${MIN_REASON} caracteres). Queda en la auditoría junto con tu usuario, tu rol y la fecha.`} />
        <ReauthFields reauth={reauth} hasPassword={hasPassword} idPrefix="delete-inst" />
        {error && <Alert>{error}</Alert>}
      </form>
    </Modal>
  );
}

/** Botones de acción según el estado y los permisos. `onChanged` recibe el detalle actualizado que devuelve el backend. */
export function InstitutionActions({ detail, permissions, hasPassword = false, onChanged }) {
  const [dialog, setDialog] = useState(null);
  const { fila } = detail;
  const canState = permissions.includes('GESTIONAR_ESTADO_INSTITUCIONES');
  const canQuota = permissions.includes('GESTIONAR_CUPOS_INSTITUCIONES');
  const canDelete = permissions.includes('ELIMINAR_INSTITUCIONES') && fila.estado !== 'CERRADA';
  const [capacity, setCapacity] = useState('');
  const parsed = /^\d+$/.test(capacity.trim()) ? Number(capacity.trim()) : NaN;
  const capacityValid = Number.isInteger(parsed) && parsed >= 1 && parsed <= MAX_CAPACITY;
  const closed = fila.estado === 'CERRADA';
  if (!canState && !canQuota && !canDelete) return null;
  const close = () => setDialog(null);
  const done = (updated) => { close(); onChanged(updated); };

  return (
    <>
      <div className="pd-actions" role="group" aria-label="Acciones sobre la institución">
        {canState && fila.estado === 'ACTIVA' && (
          <button type="button" className="btn btn-outline" onClick={() => setDialog('pause')}><Pause size={16} aria-hidden="true" /> Pausar institución</button>
        )}
        {canState && fila.estado === 'INACTIVA' && (
          <button type="button" className="btn btn-primary" onClick={() => setDialog('reactivate')}><Play size={16} aria-hidden="true" /> Reactivar institución</button>
        )}
        {canQuota && !closed && (
          <button type="button" className="btn btn-outline" onClick={() => { setCapacity(String(fila.limiteCuentas ?? '')); setDialog('capacity'); }}>
            <Gauge size={16} aria-hidden="true" /> Modificar límite de cuentas
          </button>
        )}
        {canDelete && (
          <button type="button" className="btn btn-outline" disabled={detail.eliminacionDisponible === false} onClick={() => setDialog('delete')}
            title={detail.eliminacionDisponible === false ? 'La base de datos instalada no tiene el cierre administrativo.' : undefined}>
            <Trash2 size={16} aria-hidden="true" /> Eliminar institución
          </button>
        )}
      </div>
      {canDelete && detail.eliminacionDisponible === false && (
        <p className="field-hint">La eliminación administrativa no está disponible: la base de datos instalada no tiene el cierre administrativo del esquema vigente.</p>
      )}
      {dialog === 'delete' && (
        <DeleteDialog detail={detail} hasPassword={hasPassword} onClose={close}
          onConfirm={async (body) => done(await platformApi.deleteInstitution(fila.idInstitucion, body))} />
      )}
      {dialog === 'pause' && (
        <ReasonDialog title="Pausar institución" confirmLabel="Pausar institución" onClose={close}
          intro={`«${fila.nombre}» queda pausada de inmediato: nadie de su equipo podrá operarla (ingreso, cuentas, pacientes, mediciones, dispositivos, exportaciones). No se elimina ningún dato y se avisa al propietario por correo.`}
          onConfirm={async (motivo) => done(await platformApi.pauseInstitution(fila.idInstitucion, motivo))} />
      )}
      {dialog === 'reactivate' && (
        <ReasonDialog title="Reactivar institución" confirmLabel="Reactivar institución" onClose={close}
          intro={`«${fila.nombre}» vuelve a operar. No se levantan bloqueos de cuentas individuales ni se restablecen sesiones cerradas. Se avisa al propietario por correo.`}
          onConfirm={async (motivo) => done(await platformApi.reactivateInstitution(fila.idInstitucion, motivo))} />
      )}
      {dialog === 'capacity' && (
        <ReasonDialog title="Modificar límite de cuentas" confirmLabel="Guardar límite" onClose={close} extraValid={capacityValid}
          intro={`Máximo de cuentas internas (propietario, moderadores y operadores). Hoy hay ${n(detail.cupoUtilizado)} activas. No cuenta pacientes ni grupos.`}
          extra={(
            <>
              <TextField label="Nuevo límite de cuentas" name="capacidad" inputMode="numeric" maxLength={6} value={capacity}
                onChange={(event) => setCapacity(event.target.value.replace(/\D/g, ''))}
                error={capacity && !capacityValid ? `Ingresá un entero entre 1 y ${n(MAX_CAPACITY)}.` : undefined} />
              {capacityValid && parsed < detail.cupoUtilizado && (
                <Alert kind="info">
                  El nuevo límite es menor que las cuentas activas ({n(detail.cupoUtilizado)}): se conservan todas, no se suspende ninguna, pero la institución
                  queda <b>excedida</b> y no podrá incorporar cuentas nuevas hasta regularizarse.
                </Alert>
              )}
            </>
          )}
          onConfirm={async (motivo) => done(await platformApi.changeInstitutionCapacity(fila.idInstitucion, parsed, motivo))} />
      )}
    </>
  );
}

/** Auditoría administrativa y de seguridad de la institución (sin datos clínicos, contraseñas, tokens ni códigos). */
export function InstitutionAuditSection({ idInstitucion, reloadKey }) {
  const [category, setCategory] = useState('');
  const [result, setResult] = useState('');
  const [page, setPage] = useState(1);
  const [state, setState] = useState({ data: null, error: '' });

  const load = useCallback(() => {
    let active = true;
    setState((current) => ({ ...current, error: '' }));
    platformApi.getInstitutionAudit(idInstitucion, { categoria: category || undefined, resultado: result || undefined, pagina: page, tamanio: 10 }).then(
      (data) => active && setState({ data, error: '' }), (error) => active && setState({ data: null, error: friendlyError(error) }));
    return () => { active = false; };
  }, [idInstitucion, category, result, page, reloadKey]);
  useEffect(() => load(), [load]);

  const { data, error } = state;
  const pages = data ? Math.max(1, Math.ceil(data.total / data.tamanioPagina)) : 1;
  const categories = data?.categorias ?? CATEGORY_LABEL;
  return (
    <section className="pd-card" aria-labelledby="det-auditoria">
      <header className="pd-card-head">
        <span className="pd-card-icon" aria-hidden="true"><ClipboardList size={20} /></span>
        <div><h2 id="det-auditoria">Auditoría de la institución</h2><p>Registro, pausas, cupos, cuentas, exportaciones y accesos fallidos. Sin datos clínicos ni credenciales.</p></div>
      </header>
      <form className="pd-filters" aria-label="Filtros de auditoría" onSubmit={(event) => event.preventDefault()}>
        <label className="pd-status">
          <span className="sr-only">Categoría</span>
          <select className="field-input field-select" value={category} onChange={(event) => { setCategory(event.target.value); setPage(1); }}>
            <option value="">Todas las categorías</option>
            {Object.entries(categories).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <label className="pd-status">
          <span className="sr-only">Resultado</span>
          <select className="field-input field-select" value={result} onChange={(event) => { setResult(event.target.value); setPage(1); }}>
            <option value="">Todos los resultados</option>
            <option value="EXITO">Exitosos</option>
            <option value="FALLO">Fallidos</option>
          </select>
        </label>
      </form>
      {error && <Alert>{error}</Alert>}
      {!data && !error && <p className="field-hint" role="status">Cargando auditoría…</p>}
      {data && data.items.length === 0 && <p className="field-hint">No hay eventos con esos filtros.</p>}
      {data && data.items.length > 0 && (
        <div className="an-table-wrap">
          <table className="an-table pd-table">
            <caption className="sr-only">Eventos de auditoría de la institución</caption>
            <thead><tr><th scope="col">Fecha</th><th scope="col">Evento</th><th scope="col">Actor</th><th scope="col">Resultado</th><th scope="col">Detalle</th></tr></thead>
            <tbody>
              {data.items.map((item) => (
                <tr key={item.idAuditoria}>
                  <td>{formatDateTime(item.fechaHora)}</td>
                  <th scope="row"><b>{item.etiqueta}</b><small>{categories[item.categoria] ?? item.categoria}</small></th>
                  <td>{item.actor}</td>
                  <td><Badge tone={item.resultado === 'EXITO' ? 'success' : 'danger'}>{item.resultado === 'EXITO' ? 'Exitoso' : 'Fallido'}</Badge></td>
                  <td>
                    {item.estadoAnterior && item.estadoNuevo && <span>{item.estadoAnterior} → {item.estadoNuevo}. </span>}
                    {item.limiteNuevo != null && <span>Límite {n(item.limiteAnterior)} → {n(item.limiteNuevo)}{item.cuentasActivas != null ? ` (${n(item.cuentasActivas)} activas${item.excedente ? `, ${n(item.excedente)} de más` : ''})` : ''}. </span>}
                    {item.motivo && <span>Motivo: {item.motivo}</span>}
                    {!item.motivo && !item.estadoNuevo && item.limiteNuevo == null && <span className="pd-muted">—</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data && pages > 1 && (
        <nav className="pd-pager" aria-label="Paginación de la auditoría">
          <button type="button" className="btn btn-ghost btn-sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>Anterior</button>
          <span>Página {page} de {pages}</span>
          <button type="button" className="btn btn-ghost btn-sm" disabled={page >= pages} onClick={() => setPage(page + 1)}>Siguiente</button>
        </nav>
      )}
    </section>
  );
}
