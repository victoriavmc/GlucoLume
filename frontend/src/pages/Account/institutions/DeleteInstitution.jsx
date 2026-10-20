// Eliminación lógica de la institución (solo propietario), en la «Zona de riesgo» de Datos institucionales. Nunca se ejecuta con un
// único clic: pide el nombre exacto y la reautenticación que corresponde a la cuenta: contraseña si tiene credencial local y el
// código MFA si lo tiene activado. Una cuenta solo Google no tiene contraseña: confirma con la verificación en dos pasos de GlucoLume.

import { KeyRound, Lock, Smartphone, Trash2, TriangleAlert } from 'lucide-react';
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import * as institutionsApi from '../../../api/institutionsApi.js';
import { useAuth } from '../../../auth/AuthContext.jsx';
import { Alert, TextField } from '../../../components/FormControls.jsx';
import './Administration.css';

export function DeleteInstitution({ institution, handleOperationError }) {
  const { account } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [needsPassword, setNeedsPassword] = useState(account.tieneCredencialLocal);
  const [needsMfa, setNeedsMfa] = useState(account.mfaHabilitado);
  const [useRecovery, setUseRecovery] = useState(false);
  const [form, setForm] = useState({ confirmacionNombre: '', password: '', codigo: '', codigoRecuperacion: '' });
  const [error, setError] = useState('');
  const [deleting, setDeleting] = useState(false);
  const nameMatches = form.confirmacionNombre.trim().toLocaleLowerCase('es') === institution.nombre.trim().toLocaleLowerCase('es');

  function update(field) {
    return (event) => {
      const value = field === 'codigo' ? event.target.value.replace(/\D/g, '') : event.target.value;
      setForm((current) => ({ ...current, [field]: value }));
    };
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (deleting || !nameMatches) return;
    setError('');
    setDeleting(true);
    try {
      await institutionsApi.deleteInstitution(institution.idInstitucion, {
        confirmacionNombre: form.confirmacionNombre.trim(),
        password: needsPassword ? form.password : undefined,
        codigo: needsMfa && !useRecovery ? form.codigo.trim() : undefined,
        codigoRecuperacion: needsMfa && useRecovery ? form.codigoRecuperacion.trim() : undefined,
      });
      navigate('/app/instituciones', {
        replace: true, state: { notice: `Eliminaste «${institution.nombre}». Sus integrantes ya no tienen acceso.` },
      });
    } catch (deleteError) {
      if (deleteError.codigo === 'PASSWORD_REQUERIDA') setNeedsPassword(true);
      if (deleteError.codigo === 'CODIGO_MFA_REQUERIDO') setNeedsMfa(true);
      setError(handleOperationError(deleteError));
      setForm((current) => ({ ...current, password: '', codigo: '', codigoRecuperacion: '' }));
      setDeleting(false);
    }
  }

  const cannotConfirm = !account.tieneCredencialLocal && !account.mfaHabilitado;

  return (
    <section className="panel is-danger risk-card" aria-labelledby="inst-eliminar">
      <div className="risk-card-head">
        <div className="panel-title">
          <span className="panel-icon">
            <TriangleAlert size={22} aria-hidden="true" />
          </span>
          <div>
            <h2 id="inst-eliminar">Eliminar institución</h2>
            <p>Solo el propietario puede hacerlo. No se puede deshacer desde GlucoLume.</p>
            <p className="risk-requirements">
              Para confirmarlo vas a tener que escribir el nombre exacto de la institución y verificar tu identidad (contraseña y,
              si lo tenés activado, el código de verificación en dos pasos).
            </p>
          </div>
        </div>
        {!cannotConfirm && !open && (
          <button type="button" className="btn btn-outline risk-button" onClick={() => setOpen(true)}>
            <Trash2 size={18} aria-hidden="true" /> Eliminar institución
          </button>
        )}
      </div>

      {cannotConfirm ? (
        <Alert kind="info">
          Tu cuenta usa Google y no tiene contraseña: para confirmar esta operación activá primero la verificación en
          dos pasos en <Link to="/app/seguridad">Seguridad</Link>.
        </Alert>
      ) : !open ? null : (
        <form onSubmit={handleSubmit} noValidate className="deletion-form" role="alertdialog" aria-labelledby="inst-eliminar-titulo"
          aria-describedby="inst-eliminar-consecuencias">
          <h3 id="inst-eliminar-titulo">¿Eliminar «{institution.nombre}»?</h3>
          <ul id="inst-eliminar-consecuencias" className="mfa-steps">
            <li>La institución deja de estar disponible y no aparece entre las instituciones activas.</li>
            <li>Moderadores y operadores pierden el acceso de inmediato, también en sesiones ya iniciadas.</li>
            <li>Se cancelan las invitaciones pendientes y no se pueden incorporar miembros ni registrar mediciones nuevas.</li>
            <li>
              Los datos de los pacientes se conservan protegidos durante 12 meses, sin acceso para el equipo, y luego
              se desidentifican de forma irreversible. Las mediciones se conservan anonimizadas.
            </li>
            <li>Las cuentas personales de los integrantes no se eliminan. El CUIT queda reservado.</li>
          </ul>
          {error && <Alert>{error}</Alert>}
          <TextField label={`Escribí «${institution.nombre}» para confirmar`} autoComplete="off" maxLength={150}
            value={form.confirmacionNombre} onChange={update('confirmacionNombre')} />
          {needsPassword && (
            <TextField label="Contraseña actual" icon={Lock} revealable autoComplete="current-password" maxLength={128}
              value={form.password} onChange={update('password')} />
          )}
          {needsMfa && (
            <>
              {useRecovery ? (
                <TextField key="recovery" label="Código de recuperación" icon={KeyRound} autoComplete="off" maxLength={32}
                  value={form.codigoRecuperacion} onChange={update('codigoRecuperacion')} />
              ) : (
                <TextField key="totp" label="Código de verificación" icon={Smartphone} inputMode="numeric"
                  autoComplete="one-time-code" maxLength={6} value={form.codigo} onChange={update('codigo')} />
              )}
              <button type="button" className="btn-text" onClick={() => setUseRecovery((value) => !value)}>
                {useRecovery ? 'Usar el código de la aplicación' : 'Usar un código de recuperación'}
              </button>
            </>
          )}
          <div className="form-actions">
            <button type="button" className="btn btn-ghost" disabled={deleting} onClick={() => { setOpen(false); setError(''); }}>
              Cancelar
            </button>
            <button type="submit" className="btn btn-primary" disabled={deleting || !nameMatches} aria-busy={deleting || undefined}>
              {deleting && <span className="spinner" aria-hidden="true" />} Eliminar definitivamente
            </button>
          </div>
        </form>
      )}
    </section>
  );
}
