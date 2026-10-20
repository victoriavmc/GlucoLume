// Crear o reabrir una institución con el mismo formulario.
//
// Apenas el CUIT es válido se consulta su estado (POST /institutions/legal-id/status) y el formulario cambia de modo:
//   DISPONIBLE         -> modo CREACIÓN: «Crear institución» llama a POST /institutions.
//   ACTIVA             -> se informa el duplicado y el envío queda bloqueado.
//   CERRADA autorizada -> modo REAPERTURA: el CUIT queda fijo, nombre y tipo se pueden modificar y
//                         «Reabrir institución» llama a POST /institutions/reopen (una operación, sin solicitudes).
//   CERRADA sin autorización -> error explícito y envío bloqueado.
// Mientras se consulta el CUIT no se envía nada, y en modo creación nunca se reabre ni al revés: el modo lo decide el
// estado consultado, nunca una carrera entre la consulta y el clic. El éxito solo se muestra con la respuesta del
// backend (operacion REABIERTA y estado ACTIVA ya persistidos).

import { Building2, Hash, KeyRound, Lock, Pencil, RotateCcw, Smartphone } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';

import * as institutionsApi from '../../../api/institutionsApi.js';
import { ApiError } from '../../../api/client.js';
import { useAuth } from '../../../auth/AuthContext.jsx';
import { friendlyError } from '../../../auth/errorMessages.js';
import { Alert, SubmitButton, TextField } from '../../../components/FormControls.jsx';
import { isValidCuit, normalizeCuit } from '../../../utils/validation.js';
import {
  EMPTY_INSTITUTION, InstitutionFields, fieldErrorsFrom, institutionPayload, validateInstitution,
} from './InstitutionFields.jsx';

const CUIT_ERROR = 'Ingresá un CUIT válido: XX-XXXXXXXX-X u 11 dígitos, con su dígito verificador.';
export const REOPEN_MESSAGE = 'Esta institución se encuentra cerrada. Completá sus nuevos datos para reabrirla.';
const EMPTY_REAUTH = { password: '', codigo: '', codigoRecuperacion: '' };
const CHECK_DELAY_MS = 350;

export function CreateInstitutionForm({ onCreated, onCancel }) {
  const { account } = useAuth();
  const [form, setForm] = useState({ ...EMPTY_INSTITUTION, cuit: '' });
  const [reauth, setReauth] = useState(EMPTY_REAUTH);
  const [useRecovery, setUseRecovery] = useState(false);
  const [fieldErrors, setFieldErrors] = useState({});
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  // Resultado de la consulta del CUIT: { cuit, estado, puedeReabrir, mensaje, institucion } o null.
  const [status, setStatus] = useState(null);
  const [checking, setChecking] = useState(false);
  const requestId = useRef(0);

  const cuit = isValidCuit(form.cuit) ? normalizeCuit(form.cuit) : null;
  const current = status && status.cuit === cuit ? status : null;
  const mode = current?.estado === 'CERRADA' && current.puedeReabrir ? 'reopen' : 'create';
  const reopening = mode === 'reopen';
  const blockedReason = current && current.estado !== 'DISPONIBLE' && !reopening ? current.mensaje : null;
  const needsPassword = account.tieneCredencialLocal;
  const needsMfa = account.mfaHabilitado;
  const cannotConfirm = reopening && !needsPassword && !needsMfa;

  async function checkCuit(value) {
    const id = ++requestId.current;
    setChecking(true);
    try {
      const result = await institutionsApi.checkLegalId(value);
      if (id !== requestId.current) return null;
      const next = { ...result, cuit: value };
      setStatus(next);
      setError('');
      if (result.estado === 'CERRADA' && result.puedeReabrir) {
        // Modo reapertura: mismo formulario, precargado con los datos vigentes para actualizarlos.
        const { nombre, tipoInstitucion, descripcion } = result.institucion;
        setForm((currentForm) => ({ ...currentForm, nombre, tipoInstitucion, descripcion: descripcion ?? '' }));
      }
      return next;
    } catch (checkError) {
      if (id === requestId.current) {
        setStatus(null);
        setError(friendlyError(checkError));
      }
      return null;
    } finally {
      if (id === requestId.current) setChecking(false);
    }
  }

  // Se consulta apenas el CUIT es válido (no hace falta salir del campo).
  useEffect(() => {
    if (!cuit || (status && status.cuit === cuit)) return undefined;
    const timer = setTimeout(() => checkCuit(cuit), CHECK_DELAY_MS);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cuit]);

  function update(field) {
    return (event) => {
      const { value } = event.target;
      setForm((currentForm) => ({ ...currentForm, [field]: value }));
      if (fieldErrors[field]) setFieldErrors((currentErrors) => ({ ...currentErrors, [field]: undefined }));
    };
  }

  function updateReauth(field) {
    return (event) => {
      const value = field === 'codigo' ? event.target.value.replace(/\D/g, '') : event.target.value;
      setReauth((currentReauth) => ({ ...currentReauth, [field]: value }));
      if (fieldErrors[field === 'password' ? 'password' : 'codigo']) {
        setFieldErrors((currentErrors) => ({ ...currentErrors, password: undefined, codigo: undefined }));
      }
    };
  }

  function changeCuit() {
    // Volver a modo creación con otro CUIT.
    setStatus(null);
    setForm({ ...EMPTY_INSTITUTION, cuit: '' });
    setReauth(EMPTY_REAUTH);
    setFieldErrors({});
    setError('');
  }

  function payload() {
    return { ...institutionPayload(form), tipoIdentificadorLegal: 'CUIT', identificadorLegal: cuit };
  }

  async function reopen() {
    try {
      const result = await institutionsApi.reopenInstitution({
        ...payload(),
        password: needsPassword ? reauth.password : undefined,
        codigo: needsMfa && !useRecovery ? reauth.codigo.trim() : undefined,
        codigoRecuperacion: needsMfa && useRecovery ? reauth.codigoRecuperacion.trim() : undefined,
      });
      // Solo se informa éxito si el backend confirma la reapertura persistida.
      if (result?.operacion !== 'REABIERTA' || result.estado !== 'ACTIVA') {
        throw new ApiError(500, 'ERROR_SERVIDOR', 'No se pudo confirmar la reapertura. Intentá de nuevo.');
      }
      onCreated(result);
    } catch (reopenError) {
      setError(friendlyError(reopenError));
      setReauth(EMPTY_REAUTH);
      setSaving(false);
      // Si cambió el estado (ya reabierta, sin autorización), se vuelve a consultar y el modo se ajusta solo.
      if (['INSTITUCION_REGISTRADA', 'REPRESENTACION_NO_VERIFICADA', 'INSTITUCION_NO_ENCONTRADA', 'INSTITUCION_CERRADA_ADMINISTRATIVAMENTE'].includes(reopenError.codigo)) {
        const refreshed = await checkCuit(cuit);
        // Si el nuevo estado ya explica el rechazo (activa o sin autorización), se muestra una sola vez.
        const explained = refreshed && refreshed.estado !== 'DISPONIBLE' && !refreshed.puedeReabrir;
        setError(explained ? '' : friendlyError(reopenError));
      }
    }
  }

  async function create() {
    try {
      onCreated(await institutionsApi.createInstitution(payload()));
    } catch (createError) {
      setSaving(false);
      if (createError instanceof ApiError && ['INSTITUCION_REGISTRADA', 'INSTITUCION_CERRADA', 'INSTITUCION_CERRADA_ADMINISTRATIVAMENTE'].includes(createError.codigo)) {
        // El CUIT cambió de estado entre la consulta y el envío: se actualiza el modo sin enviar nada más.
        await checkCuit(cuit);
        return;
      }
      const byField = fieldErrorsFrom(createError);
      setFieldErrors(byField);
      if (!Object.keys(byField).length) setError(friendlyError(createError));
    }
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (saving || checking) return;
    const errors = validateInstitution(form);
    if (!cuit) {
      // Distingue un formato incorrecto de un dígito verificador que no coincide (el caso típico de un CUIT mal tipeado).
      const formatOk = /^(\d{2}-\d{8}-\d|\d{11})$/.test(form.cuit.trim());
      errors.cuit = formatOk
        ? 'Ingresá un CUIT válido: el dígito verificador no coincide, revisá que no haya un número mal tipeado.'
        : CUIT_ERROR;
    }
    if (reopening && needsPassword && !reauth.password) errors.password = 'Ingresá tu contraseña actual.';
    if (reopening && needsMfa && !(useRecovery ? reauth.codigoRecuperacion.trim() : reauth.codigo.trim())) {
      errors.codigo = 'Ingresá el código de verificación en dos pasos.';
    }
    setFieldErrors(errors);
    if (Object.keys(errors).length) return;
    // Sin estado consultado para este CUIT: se consulta y el usuario decide con el modo ya actualizado.
    if (!current) {
      const checked = await checkCuit(cuit);
      if (!checked || checked.estado !== 'DISPONIBLE') return;
    }
    if (blockedReason || cannotConfirm) return;
    setError('');
    setSaving(true);
    if (reopening) await reopen();
    else await create();
  }

  return (
    <form className="panel" onSubmit={handleSubmit} noValidate aria-labelledby="crear-institucion">
      <div className="panel-title">
        <span className="panel-icon">
          {reopening ? <RotateCcw size={22} aria-hidden="true" /> : <Building2 size={22} aria-hidden="true" />}
        </span>
        <div>
          <h2 id="crear-institucion">{reopening ? 'Reabrir institución' : 'Crear una institución'}</h2>
          <p>
            {reopening
              ? 'Se reactiva el mismo registro: conserva su identificador, su CUIT y su historial.'
              : 'Vas a quedar como propietario/a: podrás designar moderadores, que incorporan a los operadores.'}
          </p>
        </div>
      </div>

      {reopening && <Alert kind="info">{REOPEN_MESSAGE}</Alert>}
      {blockedReason && current.estado === 'CERRADA' && <Alert>{blockedReason}</Alert>}
      {error && <Alert>{error}</Alert>}

      <InstitutionFields form={form} update={update} errors={fieldErrors} extraGeneral={(
        <div>
          <TextField label="CUIT" icon={Hash} inputMode="numeric" placeholder="30-71234567-1" maxLength={13}
            value={form.cuit} onChange={update('cuit')} readOnly={reopening}
            error={fieldErrors.cuit || (current?.estado === 'ACTIVA' ? current.mensaje : undefined)}
            aria-describedby={checking ? 'cuit-estado' : undefined} />
          {checking && <p id="cuit-estado" className="field-hint" role="status">Verificando el CUIT…</p>}
          {reopening && (
            <button type="button" className="btn-text" onClick={changeCuit}>
              <Pencil size={14} aria-hidden="true" /> Usar otro CUIT
            </button>
          )}
        </div>
      )} />

      {reopening && (
        <fieldset className="form-section">
          <legend>Confirmá tu identidad</legend>
          <p className="field-hint">
            Vas a quedar como propietario/a (reapertura n.º {current.institucion.cantidadReaperturas + 1}). No se restauran
            moderadores, operadores, invitaciones ni el acceso a pacientes anteriores.
          </p>
          {cannotConfirm ? (
            <Alert kind="info">
              Tu cuenta usa Google y no tiene contraseña: para reabrir la institución activá primero la verificación en
              dos pasos en <Link to="/app/seguridad">Seguridad</Link>.
            </Alert>
          ) : (
            <>
              {needsPassword && (
                <TextField label="Contraseña actual" icon={Lock} revealable autoComplete="current-password" maxLength={128}
                  value={reauth.password} onChange={updateReauth('password')} error={fieldErrors.password} />
              )}
              {needsMfa && (
                <>
                  {useRecovery ? (
                    <TextField key="recovery" label="Código de recuperación" icon={KeyRound} autoComplete="off" maxLength={32}
                      value={reauth.codigoRecuperacion} onChange={updateReauth('codigoRecuperacion')} error={fieldErrors.codigo} />
                  ) : (
                    <TextField key="totp" label="Código de verificación" icon={Smartphone} inputMode="numeric"
                      autoComplete="one-time-code" maxLength={6} value={reauth.codigo} onChange={updateReauth('codigo')}
                      error={fieldErrors.codigo} />
                  )}
                  <button type="button" className="btn-text" onClick={() => setUseRecovery((value) => !value)}>
                    {useRecovery ? 'Usar el código de la aplicación' : 'Usar un código de recuperación'}
                  </button>
                </>
              )}
            </>
          )}
        </fieldset>
      )}

      {!reopening && (
        <p className="field-hint">
          El nombre puede repetirse entre instituciones; el CUIT identifica a la institución, es único y no se puede
          modificar después.
        </p>
      )}
      <p className="field-hint" id="institucion-privacidad">
        La institución es responsable de informar a sus pacientes y obtener su consentimiento antes de registrarlos y medirlos. Al darse
        de baja un paciente o cerrarse la institución, sus datos personales se conservan hasta 12 meses sin acceso y luego se
        desidentifican. Detalles en la <Link to="/privacidad">Política de privacidad</Link>.
      </p>
      <div className="form-actions">
        <button type="button" className="btn btn-ghost" onClick={onCancel} disabled={saving}>
          Cancelar
        </button>
        <SubmitButton loading={saving} loadingLabel={reopening ? 'Reabriendo…' : 'Creando…'} className="btn btn-primary"
          disabled={saving || checking || Boolean(blockedReason) || cannotConfirm}>
          {reopening ? 'Reabrir institución' : 'Crear institución'}
        </SubmitButton>
      </div>
    </form>
  );
}
