// Formulario de registro, el mismo para uso personal e institucional (POST /auth/register).
//
// El tipo elegido solo define Usuario.tipoCuenta (CONSUMIDOR_FINAL | USUARIO_INSTITUCIONAL). Una cuenta
// institucional NO registra una institución acá: después crea una o la incorpora una existente.
// "Continuar con Google" usa el mismo OAuth para ambos tipos; el tipo viaja en el flujo OAuth del backend.

import { ArrowRight, AtSign, Check, Circle, Lock, Mail, User } from 'lucide-react';
import { useId, useState } from 'react';
import { Link } from 'react-router-dom';

import * as authApi from '../../api/authApi.js';
import { ApiError } from '../../api/client.js';
import { friendlyError } from '../../auth/errorMessages.js';
import { startGoogleLogin } from '../../auth/googleLogin.js';
import { Alert, SubmitButton, TextField } from '../../components/FormControls.jsx';
import { Modal } from '../../components/Modal.jsx';
import { POLICY_REQUIRED_MESSAGE, PolicyConsent } from '../../components/PolicyConsent.jsx';
import { EMAIL_PATTERN, PASSWORD_RULES, passwordMeetsPolicy, usernameError } from '../../utils/validation.js';
import { GoogleIcon } from '../Login/GoogleIcon.jsx';

const EMPTY = { nombre: '', apellido: '', usuario: '', correoElectronico: '', password: '', confirmPassword: '' };

// Códigos del backend que corresponden a un campo puntual.
const FIELD_BY_CODE = {
  CORREO_REGISTRADO: 'correoElectronico',
  USUARIO_REGISTRADO: 'usuario',
  PASSWORD_DEBIL: 'password',
};

const FIELDS = ['nombre', 'apellido', 'usuario', 'correoElectronico', 'password'];

function validate(form) {
  const errors = {};
  if (!form.nombre.trim()) errors.nombre = 'Ingresá tu nombre.';
  if (!form.apellido.trim()) errors.apellido = 'Ingresá tu apellido.';
  const username = usernameError(form.usuario);
  if (username) errors.usuario = username;
  if (!EMAIL_PATTERN.test(form.correoElectronico.trim())) errors.correoElectronico = 'Ingresá un correo electrónico válido.';
  if (!passwordMeetsPolicy(form.password)) errors.password = 'La contraseña no cumple todos los requisitos.';
  if (form.confirmPassword !== form.password) errors.confirmPassword = 'Las contraseñas no coinciden.';
  return errors;
}

function serverFieldErrors(error) {
  if (!(error instanceof ApiError)) return {};
  if (FIELD_BY_CODE[error.codigo]) return { [FIELD_BY_CODE[error.codigo]]: friendlyError(error) };
  const errors = {};
  for (const field of error.fields ?? []) {
    if (FIELDS.includes(field.ruta) && !errors[field.ruta]) errors[field.ruta] = field.mensaje;
  }
  return errors;
}

export function PasswordRules({ value, id }) {
  return (
    <ul className="password-rules" id={id} aria-label="Requisitos de la contraseña">
      {PASSWORD_RULES.map((rule) => {
        const ok = rule.test(value);
        return (
          <li key={rule.id} className={ok ? 'is-ok' : undefined}>
            {ok ? <Check size={14} aria-hidden="true" /> : <Circle size={14} aria-hidden="true" />}
            {rule.label}
            <span className="visually-hidden">{ok ? ' (cumplido)' : ' (pendiente)'}</span>
          </li>
        );
      })}
    </ul>
  );
}

export function RegisterForm({ type, tipoCuenta, onRegistered }) {
  const isInstitutional = type === 'institucion';
  const rulesId = useId();
  const [form, setForm] = useState(EMPTY);
  const [fieldErrors, setFieldErrors] = useState({});
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [redirecting, setRedirecting] = useState(false);
  const [emailTaken, setEmailTaken] = useState(false);
  const [policyRead, setPolicyRead] = useState(false);
  const [policyError, setPolicyError] = useState('');

  function confirmPolicy(checked) {
    setPolicyRead(checked);
    if (checked) setPolicyError('');
  }

  function update(field) {
    return (event) => {
      setForm((current) => ({ ...current, [field]: event.target.value }));
      if (fieldErrors[field]) setFieldErrors((current) => ({ ...current, [field]: undefined }));
    };
  }

  function handleGoogle() {
    if (!policyRead) {
      setPolicyError(POLICY_REQUIRED_MESSAGE);
      return;
    }
    // Mismo OAuth que el inicio de sesión; con `type` el backend crea la cuenta nueva de ese tipo. La confirmación de la
    // política viaja al backend, que la exige y la registra al crear la cuenta.
    setRedirecting(true);
    startGoogleLogin(false, type, true);
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (loading) return;
    const errors = validate(form);
    setFieldErrors(errors);
    if (!policyRead) setPolicyError(POLICY_REQUIRED_MESSAGE);
    if (Object.keys(errors).length || !policyRead) return;
    setError('');
    setLoading(true);
    try {
      await authApi.register({
        nombre: form.nombre.trim(),
        apellido: form.apellido.trim(),
        usuario: form.usuario.trim(),
        correoElectronico: form.correoElectronico.trim(),
        password: form.password,
        tipoCuenta,
        aceptaPoliticaPrivacidad: true,
      });
      onRegistered(form.correoElectronico.trim());
    } catch (registerError) {
      const byField = serverFieldErrors(registerError);
      setFieldErrors(byField);
      // Un correo, una cuenta: si ya existe (con cualquier tipo de cuenta) se explica en un aviso que no se puede registrar.
      if (registerError instanceof ApiError && registerError.codigo === 'CORREO_REGISTRADO') setEmailTaken(true);
      if (!Object.keys(byField).length) setError(friendlyError(registerError));
      setLoading(false);
    }
  }

  return (
    <form className="auth-form register-form" onSubmit={handleSubmit} noValidate>
      {emailTaken && (
        <Modal
          title="Este correo ya está registrado"
          onClose={() => setEmailTaken(false)}
          actions={
            <>
              <button type="button" className="btn btn-outline" onClick={() => setEmailTaken(false)}>
                Usar otro correo
              </button>
              <Link to="/login" className="btn btn-primary">Iniciar sesión</Link>
            </>
          }
        >
          <p>
            No podés registrarte porque ese correo ya tiene una cuenta, aunque la hayas creado con otro tipo (personal o
            institucional). Un mismo correo solo puede tener una cuenta.
          </p>
          <p>Iniciá sesión con tu cuenta existente o registrate con otro correo.</p>
        </Modal>
      )}
      {error && <Alert>{error}</Alert>}

      <fieldset className="form-section">
        <legend>
          <User size={18} aria-hidden="true" /> Tus datos
        </legend>
        <div className="form-row">
          <TextField label="Nombre" name="nombre" icon={User} autoComplete="given-name" maxLength={100}
            value={form.nombre} onChange={update('nombre')} error={fieldErrors.nombre} />
          <TextField label="Apellido" name="apellido" icon={User} autoComplete="family-name" maxLength={100}
            value={form.apellido} onChange={update('apellido')} error={fieldErrors.apellido} />
        </div>
      </fieldset>

      <fieldset className="form-section">
        <legend>
          <Lock size={18} aria-hidden="true" /> Cuenta y acceso
        </legend>
        <TextField label="Correo electrónico" name="correoElectronico" icon={Mail} type="email" autoComplete="email"
          maxLength={254} placeholder="tucorreo@ejemplo.com" value={form.correoElectronico}
          onChange={update('correoElectronico')} error={fieldErrors.correoElectronico} />
        <TextField label="Nombre de usuario" name="usuario" icon={AtSign} autoComplete="username" maxLength={50}
          value={form.usuario} onChange={update('usuario')} error={fieldErrors.usuario} />
        <TextField label="Contraseña" name="password" icon={Lock} revealable autoComplete="new-password" maxLength={128}
          value={form.password} onChange={update('password')} error={fieldErrors.password} aria-describedby={rulesId} />
        <PasswordRules value={form.password} id={rulesId} />
        <p className="field-hint">No uses tu nombre, apellido, usuario ni correo dentro de la contraseña.</p>
        <TextField label="Repetir contraseña" name="confirmPassword" icon={Lock} revealable autoComplete="new-password"
          maxLength={128} value={form.confirmPassword} onChange={update('confirmPassword')}
          error={fieldErrors.confirmPassword} />
      </fieldset>

      <PolicyConsent checked={policyRead} onChange={confirmPolicy} error={policyError} disabled={loading || redirecting} />

      <SubmitButton loading={loading} loadingLabel="Creando la cuenta…" disabled={loading || redirecting}>
        {isInstitutional ? 'Crear cuenta institucional' : 'Crear cuenta'} <ArrowRight size={18} aria-hidden="true" />
      </SubmitButton>

      <div className="divider">
        <span>o registrate con</span>
      </div>
      <button type="button" className="btn btn-ghost btn-block btn-lg" onClick={handleGoogle} disabled={loading || redirecting}>
        {redirecting ? <span className="spinner" aria-hidden="true" /> : <GoogleIcon />}
        {redirecting ? 'Redirigiendo a Google…' : 'Continuar con Google'}
      </button>
      {isInstitutional && (
        <p className="field-hint">
          Solo se crea tu cuenta. Después vas a poder crear una institución o esperar a que una institución existente
          te incorpore.
        </p>
      )}
    </form>
  );
}
