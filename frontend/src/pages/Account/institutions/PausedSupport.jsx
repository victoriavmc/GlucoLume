// Institución pausada por la administración de GlucoLume: lo único que sigue abierto es escribir al soporte, y solo para el propietario.
// POST /institutions/{id}/support-request toma el nombre y el correo de la cuenta y agrega los datos de la institución; el backend vuelve a
// validar que sea el propietario y que la institución siga pausada.

import { LifeBuoy } from 'lucide-react';
import { useState } from 'react';

import * as institutionsApi from '../../../api/institutionsApi.js';
import { friendlyError } from '../../../auth/errorMessages.js';
import { Alert, TextAreaField, TextField } from '../../../components/FormControls.jsx';
import { Modal } from '../../../components/Modal.jsx';

const SUBJECT_MAX = 100;
const MESSAGE_MIN = 10;
const MESSAGE_MAX = 1500;

function SupportDialog({ institution, onClose, onSent }) {
  const [subject, setSubject] = useState('Solicitud de reactivación');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const cleanSubject = subject.trim().replace(/\s+/g, ' ');
  const cleanMessage = message.trim();
  const valid = cleanSubject.length >= 3 && cleanMessage.length >= MESSAGE_MIN;

  async function submit(event) {
    event.preventDefault();
    if (!valid || busy) return;
    setBusy(true);
    setError('');
    try {
      await institutionsApi.requestSupport(institution.idInstitucion, { asunto: cleanSubject, mensaje: cleanMessage });
      onSent();
    } catch (failure) {
      setError(friendlyError(failure));
      setBusy(false);
    }
  }

  return (
    <Modal role="dialog" title="Escribir al soporte de GlucoLume" onClose={busy ? undefined : onClose}
      actions={(
        <>
          <button type="button" className="btn btn-ghost" onClick={onClose} disabled={busy}>Cancelar</button>
          <button type="submit" form="paused-support-form" className="btn btn-primary" disabled={!valid || busy}>{busy ? 'Enviando…' : 'Enviar consulta'}</button>
        </>
      )}>
      <form id="paused-support-form" onSubmit={submit} noValidate>
        <p>Tu consulta sobre <b>{institution.nombre}</b> llega al soporte con los datos de la institución. Te respondemos al correo de tu cuenta.</p>
        <TextField label="Asunto" name="asunto" maxLength={SUBJECT_MAX} value={subject} onChange={(event) => setSubject(event.target.value)} />
        <TextAreaField label="Mensaje" name="mensaje" rows={5} maxLength={MESSAGE_MAX} value={message} onChange={(event) => setMessage(event.target.value)}
          hint={`Contanos qué pasó o qué necesitás (mínimo ${MESSAGE_MIN} caracteres). No incluyas contraseñas ni datos de pacientes.`} />
        {error && <Alert>{error}</Alert>}
      </form>
    </Modal>
  );
}

/** Contenido de la tarjeta de una institución pausada. `onSent` recibe el aviso de éxito para mostrarlo en la página. */
export function PausedInstitutionNotice({ institution, onSent }) {
  const [open, setOpen] = useState(false);
  const isOwner = institution.rolInstitucion === 'PROPIETARIO';
  return (
    <>
      <span className="field-hint">
        La administración de GlucoLume pausó esta institución. Tus datos se conservan y no podés operarla hasta que se reactive.
        {isOwner ? ' Podés escribirle al soporte para resolverlo.' : ' Pedile al propietario de la institución que se comunique con el soporte.'}
      </span>
      {isOwner && (
        <button type="button" className="btn btn-outline btn-sm" onClick={() => setOpen(true)} aria-label={`Escribir al soporte por ${institution.nombre}`}>
          <LifeBuoy size={16} aria-hidden="true" /> Escribir al soporte
        </button>
      )}
      {open && <SupportDialog institution={institution} onClose={() => setOpen(false)} onSent={() => { setOpen(false); onSent(); }} />}
    </>
  );
}
