// Datos de la institución en tres secciones (información general, identificación legal, estado y registro). Todos los
// integrantes los consultan; solo el propietario los edita (PATCH /institutions/{id}). Al guardar, el detalle se recarga
// desde el backend: lo que se ve es lo persistido. El CUIT identifica a la institución y no se modifica. No se muestran
// identificadores internos de la base.

import { BadgeCheck, Building2, Fingerprint, Lock, Pencil, TriangleAlert } from 'lucide-react';
import { useState } from 'react';
import { useOutletContext } from 'react-router-dom';

import * as institutionsApi from '../../../api/institutionsApi.js';
import { Alert, SubmitButton } from '../../../components/FormControls.jsx';
import { DeleteInstitution } from './DeleteInstitution.jsx';
import { InstitutionFields, fieldErrorsFrom, institutionFormFrom, institutionPayload, validateInstitution } from './InstitutionFields.jsx';
import './Administration.css';
import { ROLE_LABELS, can, formatCuit, formatDateTime, personName, typeLabel } from './institutionFormat.js';

const ESTADO_LABELS = { ACTIVA: 'Activa', INACTIVA: 'Inactiva', CERRADA: 'Cerrada' };
const LEGAL_ID_LABELS = { CUIT: 'CUIT', OTRO: 'Otro identificador' };

function Section({ id, icon: Icon, title, hint, children }) {
  return (
    <section className="panel data-card" aria-labelledby={id}>
      <div className="panel-title">
        <span className="panel-icon"><Icon size={22} aria-hidden="true" /></span>
        <div><h2 id={id}>{title}</h2>{hint && <p>{hint}</p>}</div>
      </div>
      <dl className="data-list">{children}</dl>
    </section>
  );
}

function Row({ label, value, wide = false, note, dot = false }) {
  return (
    <div className={wide ? 'data-list-wide' : undefined}>
      <dt>{label}</dt>
      <dd className={value ? undefined : 'is-empty'}>{dot && value && <span className="status-dot" aria-hidden="true" />}{value || 'Sin informar'}</dd>
      {note && <small className="data-note">{note}</small>}
    </div>
  );
}

function InstitutionView({ institution }) {
  const reopened = institution.cantidadReaperturas ?? 0;
  return (
    <div className="data-layout">
      <Section id="datos-general" icon={Building2} title="Información general">
        <Row label="Nombre" value={institution.nombre} />
        <Row label="Tipo de institución" value={typeLabel(institution.tipoInstitucion)} />
        <Row label="Descripción" value={institution.descripcion} wide />
      </Section>
      <Section id="datos-legal" icon={Fingerprint} title="Identificación legal">
        <Row label="Tipo de identificador" value={LEGAL_ID_LABELS[institution.tipoIdentificadorLegal] ?? institution.tipoIdentificadorLegal} />
        <Row label={LEGAL_ID_LABELS[institution.tipoIdentificadorLegal] ?? 'Identificador'}
          value={institution.tipoIdentificadorLegal === 'CUIT' ? formatCuit(institution.identificadorLegal) : institution.identificadorLegal}
          note="No se puede modificar: identifica a la institución." />
      </Section>
      <Section id="datos-estado" icon={BadgeCheck} title="Estado y registro" hint="Tu rol en esta institución y su historial de registro.">
        <Row label="Estado actual" value={ESTADO_LABELS[institution.estado] ?? institution.estado} dot={institution.estado === 'ACTIVA'} />
        <Row label="Propietario/a" value={institution.propietario ? personName(institution.propietario) : null} />
        <Row label="Tu rol" value={ROLE_LABELS[institution.rolInstitucion]} />
        <Row label="Fecha de creación" value={formatDateTime(institution.fechaCreacion)} />
        <Row label="Última actualización" value={formatDateTime(institution.fechaActualizacion)} />
        <Row label="Cantidad de reaperturas" value={String(reopened)} />
        {institution.capacidadMaximaUsuarios != null && (
          <Row label="Capacidad máxima de cuentas activas" value={`${Number(institution.capacidadMaximaUsuarios).toLocaleString('es-AR')} (administrada por el sistema)`} />
        )}
        {reopened > 0 && (
          <Row label="Fecha de última reapertura" value={institution.fechaUltimaReapertura ? formatDateTime(institution.fechaUltimaReapertura) : null} />
        )}
      </Section>
    </div>
  );
}

function EditForm({ institution, reload, handleOperationError, onDone }) {
  const [form, setForm] = useState(() => institutionFormFrom(institution));
  const [fieldErrors, setFieldErrors] = useState({});
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  function update(field) {
    return (event) => {
      setForm((current) => ({ ...current, [field]: event.target.value }));
      if (fieldErrors[field]) setFieldErrors((current) => ({ ...current, [field]: undefined }));
    };
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (saving) return;
    const errors = validateInstitution(form);
    setFieldErrors(errors);
    if (Object.keys(errors).length) return;
    setError('');
    setSaving(true);
    try {
      await institutionsApi.updateInstitution(institution.idInstitucion, institutionPayload(form));
      await reload();
      onDone('Guardamos los cambios de la institución.');
    } catch (saveError) {
      const byField = fieldErrorsFrom(saveError);
      setFieldErrors(byField);
      if (!Object.keys(byField).length) setError(handleOperationError(saveError));
      setSaving(false);
    }
  }

  return (
    <form className="panel admin-form" onSubmit={handleSubmit} noValidate aria-labelledby="datos-editar">
      <div className="panel-title">
        <span className="panel-icon"><Pencil size={22} aria-hidden="true" /></span>
        <div><h2 id="datos-editar">Editar datos de la institución</h2><p>Los cambios quedan registrados en la auditoría.</p></div>
      </div>
      {error && <Alert>{error}</Alert>}
      <InstitutionFields form={form} update={update} errors={fieldErrors} />
      <p className="field-hint">
        <Lock size={14} aria-hidden="true" /> El CUIT ({formatCuit(institution.identificadorLegal)}) identifica a la institución y no se puede modificar.
      </p>
      <div className="form-actions">
        <button type="button" className="btn btn-ghost" onClick={() => onDone('')} disabled={saving}>
          Cancelar
        </button>
        <SubmitButton loading={saving} loadingLabel="Guardando…" className="btn btn-primary">
          Guardar cambios
        </SubmitButton>
      </div>
    </form>
  );
}

export function InstitutionDataPage() {
  const { institution, reload, handleOperationError } = useOutletContext();
  const [editing, setEditing] = useState(false);
  const [notice, setNotice] = useState('');
  const canEdit = can(institution, 'MODIFICAR_INSTITUCION');
  const canDelete = can(institution, 'ELIMINAR_INSTITUCION');

  return (
    <div className="admin-page">
      {notice && <Alert kind="success">{notice}</Alert>}
      <div className="admin-toolbar">
        <div className="admin-title">
          <h2>Datos institucionales</h2>
          <p>Datos de la institución. Última actualización: {formatDateTime(institution.fechaActualizacion)}</p>
        </div>
        {canEdit && !editing && (
          <button type="button" className="btn btn-outline" onClick={() => { setNotice(''); setEditing(true); }}>
            <Pencil size={16} aria-hidden="true" /> Editar datos
          </button>
        )}
      </div>
      {editing ? (
        <EditForm institution={institution} reload={reload} handleOperationError={handleOperationError}
          onDone={(message) => { setNotice(message); setEditing(false); }} />
      ) : (
        <InstitutionView institution={institution} />
      )}
      {!canEdit && <p className="field-hint">Solo el propietario de la institución puede modificar estos datos.</p>}
      {canDelete && !editing && (
        <div className="risk-zone">
          <h2 className="risk-zone-title"><TriangleAlert size={20} aria-hidden="true" /> Zona de riesgo</h2>
          <p>Operaciones que afectan a toda la institución y a sus datos. Leé las consecuencias antes de continuar.</p>
          <DeleteInstitution institution={institution} handleOperationError={handleOperationError} />
        </div>
      )}
    </div>
  );
}
