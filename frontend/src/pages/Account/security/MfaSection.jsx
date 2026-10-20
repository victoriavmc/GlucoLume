// Verificación en dos pasos (TOTP), según el backend:
//   activar:    POST /auth/mfa/setup -> { secreto, otpauthUri }  (todavía NO activa)
//               POST /auth/mfa/enable { codigo } -> { codigosRecuperacion }  (activa tras un código válido)
//   desactivar: POST /auth/mfa/disable { codigo | codigoRecuperacion }  (exige uno de los dos)
// El secreto y los códigos de recuperación solo se muestran durante la configuración.

import { Copy, Download, KeyRound, ShieldCheck, ShieldOff, Smartphone } from 'lucide-react';
import { QRCodeSVG } from 'qrcode.react';
import { useState } from 'react';

import * as authApi from '../../../api/authApi.js';
import { useAuth } from '../../../auth/AuthContext.jsx';
import { friendlyError } from '../../../auth/errorMessages.js';
import { Badge } from '../../../components/Badge.jsx';
import { Alert, SubmitButton, TextField } from '../../../components/FormControls.jsx';
import { copyText } from '../../../utils/clipboard.js';
import { MfaAccountRecovery } from './MfaAccountRecovery.jsx';

const TOTP_PATTERN = /^\d{6}$/;

function CodeField({ value, onChange, error, label = 'Código de verificación' }) {
  return (
    <TextField label={label} icon={Smartphone} name="codigo" inputMode="numeric" autoComplete="one-time-code"
      maxLength={6} placeholder="123456" value={value} error={error}
      onChange={(event) => onChange(event.target.value.replace(/\D/g, ''))} />
  );
}

function RecoveryCodes({ codes, onDone }) {
  const [copied, setCopied] = useState(false);
  const text = codes.join('\n');

  async function copy() {
    setCopied(await copyText(text));
  }

  function download() {
    const url = URL.createObjectURL(new Blob([`Códigos de recuperación de GlucoLume\n\n${text}\n`], { type: 'text/plain' }));
    const link = Object.assign(document.createElement('a'), { href: url, download: 'glucolume-codigos-recuperacion.txt' });
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="auth-form">
      <Alert kind="success">La verificación en dos pasos quedó activada.</Alert>
      <p className="mfa-text">
        Guardá estos <b>códigos de recuperación</b> en un lugar seguro. Cada uno sirve <b>una sola vez</b> si no tenés tu
        teléfono. No vamos a volver a mostrarlos.
      </p>
      <ol className="recovery-codes" aria-label="Códigos de recuperación">
        {codes.map((code) => (
          <li key={code}>
            <code>{code}</code>
          </li>
        ))}
      </ol>
      <div className="form-actions">
        <button type="button" className="btn btn-ghost" onClick={copy}>
          <Copy size={18} aria-hidden="true" /> {copied ? 'Copiados' : 'Copiar'}
        </button>
        <button type="button" className="btn btn-ghost" onClick={download}>
          <Download size={18} aria-hidden="true" /> Descargar
        </button>
        <button type="button" className="btn btn-primary" onClick={onDone}>
          Ya los guardé
        </button>
      </div>
    </div>
  );
}

function EnableFlow({ onCancel, onEnabled }) {
  const [setup, setSetup] = useState(null);
  const [starting, setStarting] = useState(false);
  const [code, setCode] = useState('');
  const [fieldError, setFieldError] = useState('');
  const [error, setError] = useState('');
  const [verifying, setVerifying] = useState(false);
  const [showSecret, setShowSecret] = useState(false);

  async function start() {
    setStarting(true);
    setError('');
    try {
      setSetup(await authApi.startMfaSetup());
    } catch (startError) {
      setError(friendlyError(startError));
    } finally {
      setStarting(false);
    }
  }

  async function verify(event) {
    event.preventDefault();
    if (verifying) return;
    if (!TOTP_PATTERN.test(code)) {
      setFieldError('Ingresá el código de 6 dígitos que muestra la aplicación.');
      return;
    }
    setFieldError('');
    setError('');
    setVerifying(true);
    try {
      const { codigosRecuperacion } = await authApi.enableMfa(code);
      onEnabled(codigosRecuperacion);
    } catch (verifyError) {
      setError(friendlyError(verifyError));
      setCode('');
      setVerifying(false);
    }
  }

  if (!setup) {
    return (
      <div className="auth-form">
        {error && <Alert>{error}</Alert>}
        <p className="mfa-text">
          Vas a necesitar una aplicación autenticadora en tu teléfono, como Google Authenticator, Microsoft
          Authenticator u otra compatible con TOTP.
        </p>
        <div className="form-actions">
          <button type="button" className="btn btn-ghost" onClick={onCancel} disabled={starting}>
            Cancelar
          </button>
          <button type="button" className="btn btn-primary" onClick={start} disabled={starting}>
            {starting && <span className="spinner" aria-hidden="true" />} Continuar
          </button>
        </div>
      </div>
    );
  }

  return (
    <form className="auth-form" onSubmit={verify} noValidate>
      {error && <Alert>{error}</Alert>}
      <ol className="mfa-steps">
        <li>Abrí tu aplicación autenticadora y escaneá este código QR.</li>
        <li>Ingresá el código de 6 dígitos que te muestra la aplicación.</li>
      </ol>
      <div className="mfa-qr">
        <QRCodeSVG value={setup.otpauthUri} size={184} level="M" title="Código QR para la aplicación autenticadora" />
      </div>
      <button type="button" className="link-button" onClick={() => setShowSecret((value) => !value)}
        aria-expanded={showSecret}>
        {showSecret ? 'Ocultar la clave' : '¿No podés escanear? Ingresá la clave manualmente'}
      </button>
      {showSecret && (
        <p className="mfa-secret">
          Clave: <code>{setup.secreto.replace(/(.{4})/g, '$1 ').trim()}</code>
        </p>
      )}
      <CodeField value={code} onChange={setCode} error={fieldError} />
      <div className="form-actions">
        <button type="button" className="btn btn-ghost" onClick={onCancel} disabled={verifying}>
          Cancelar
        </button>
        <SubmitButton loading={verifying} loadingLabel="Verificando…" className="btn btn-primary">
          Verificar y activar
        </SubmitButton>
      </div>
    </form>
  );
}

function DisableFlow({ onCancel, onDisabled, onLostEverything }) {
  const [useRecovery, setUseRecovery] = useState(false);
  const [value, setValue] = useState('');
  const [fieldError, setFieldError] = useState('');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    if (saving) return;
    const text = value.trim();
    if (useRecovery ? !text : !TOTP_PATTERN.test(text)) {
      setFieldError(useRecovery ? 'Ingresá un código de recuperación.' : 'Ingresá el código de 6 dígitos.');
      return;
    }
    setFieldError('');
    setError('');
    setSaving(true);
    try {
      await authApi.disableMfa(useRecovery ? { codigoRecuperacion: text } : { codigo: text });
      onDisabled();
    } catch (disableError) {
      setError(friendlyError(disableError));
      setValue('');
      setSaving(false);
    }
  }

  return (
    <form className="auth-form" onSubmit={handleSubmit} noValidate>
      <p className="mfa-text">Para desactivarla, confirmá con un código de tu aplicación o un código de recuperación.</p>
      {error && <Alert>{error}</Alert>}
      {useRecovery ? (
        <TextField key="recovery" label="Código de recuperación" icon={KeyRound} autoComplete="off" maxLength={32}
          placeholder="XXXX-XXXX" value={value} onChange={(event) => setValue(event.target.value)} error={fieldError} />
      ) : (
        <CodeField key="totp" value={value} onChange={setValue} error={fieldError} />
      )}
      <button type="button" className="link-button" onClick={() => { setUseRecovery((v) => !v); setValue(''); setFieldError(''); }}>
        {useRecovery ? 'Usar el código de la aplicación' : 'Usar un código de recuperación'}
      </button>
      <div className="form-actions">
        <button type="button" className="btn btn-ghost" onClick={onCancel} disabled={saving}>
          Cancelar
        </button>
        <SubmitButton loading={saving} loadingLabel="Desactivando…" className="btn btn-outline">
          Desactivar verificación
        </SubmitButton>
      </div>

      {/* Alternativa separada del campo de código: no desactiva nada, inicia una recuperación verificada. */}
      <div className="mfa-lost">
        <p>
          <b>¿Perdiste acceso a tu aplicación autenticadora y a tus códigos de recuperación?</b>
        </p>
        <button type="button" className="btn btn-ghost" onClick={onLostEverything} disabled={saving}>
          Recuperar acceso de otra manera
        </button>
      </div>
    </form>
  );
}

export function MfaSection({ account }) {
  const { refreshAccount } = useAuth();
  // idle | enabling | codes | disabling | recovering
  const [mode, setMode] = useState('idle');
  const [codes, setCodes] = useState([]);
  const [notice, setNotice] = useState('');
  const enabled = account.mfaHabilitado;

  async function handleEnabled(recoveryCodes) {
    setCodes(recoveryCodes);
    setMode('codes');
    await refreshAccount();
  }

  function handleRecovered() {
    setMode('idle');
    setNotice(
      'Verificación en dos pasos desactivada. El método de autenticación anterior fue desvinculado de tu cuenta. ' +
        'Podés configurar nuevamente la verificación en dos pasos desde acá.',
    );
  }

  async function handleDisabled() {
    setMode('idle');
    setNotice('La verificación en dos pasos quedó desactivada.');
    await refreshAccount();
  }

  return (
    <section className="panel" aria-labelledby="seguridad-mfa">
      <div className="panel-head">
        <div className="panel-title">
          <span className="panel-icon">
            {enabled ? <ShieldCheck size={22} aria-hidden="true" /> : <ShieldOff size={22} aria-hidden="true" />}
          </span>
          <div>
            <h2 id="seguridad-mfa">Verificación en dos pasos</h2>
            <p>
              {enabled
                ? 'Tu cuenta pide un código adicional al iniciar sesión, también si ingresás con Google.'
                : 'Agregá una capa adicional de seguridad a tu cuenta.'}
            </p>
          </div>
        </div>
        <Badge tone={enabled ? 'success' : 'neutral'}>Estado: {enabled ? 'Activada' : 'Desactivada'}</Badge>
      </div>

      {notice && mode === 'idle' && <Alert kind="success">{notice}</Alert>}

      {mode === 'idle' && (
        <div className="form-actions">
          {enabled ? (
            <button type="button" className="btn btn-outline" onClick={() => { setNotice(''); setMode('disabling'); }}>
              Desactivar verificación
            </button>
          ) : (
            <button type="button" className="btn btn-primary" onClick={() => { setNotice(''); setMode('enabling'); }}>
              Activar verificación en dos pasos
            </button>
          )}
        </div>
      )}
      {mode === 'enabling' && <EnableFlow onCancel={() => setMode('idle')} onEnabled={handleEnabled} />}
      {mode === 'codes' && <RecoveryCodes codes={codes} onDone={() => { setCodes([]); setMode('idle'); }} />}
      {mode === 'disabling' && (
        <DisableFlow
          onCancel={() => setMode('idle')}
          onDisabled={handleDisabled}
          onLostEverything={() => setMode('recovering')}
        />
      )}
      {mode === 'recovering' && (
        <MfaAccountRecovery account={account} onCancel={() => setMode('disabling')} onRecovered={handleRecovered} />
      )}
    </section>
  );
}
