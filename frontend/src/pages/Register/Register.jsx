// /registro: registro con selección inicial del tipo de cuenta.
//
// La selección se guarda en el query param ?tipo=usuario|institucion: sobrevive a recargas y al botón
// "atrás", y se puede enlazar desde la Landing. Ambos tipos comparten el mismo formulario y el mismo
// endpoint (POST /auth/register); la institución agrega su propio bloque de datos.
//
//   usuario     -> tipoCuenta CONSUMIDOR_FINAL       (uso personal: mediciones propias, grupo)
//   institucion -> tipoCuenta USUARIO_INSTITUCIONAL  (solo la cuenta; ninguna institución se crea acá)
//
// El grupo no es un tipo de registro: se crea después, desde una cuenta individual.

import { ArrowLeft, ArrowRight, Building2, Check, Mail, User, Users } from 'lucide-react';
import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';

import { Alert } from '../../components/FormControls.jsx';
import { AuthShell } from '../Login/Login.jsx';
import { RegisterForm } from './RegisterForm.jsx';
import { RegisterSuccess } from './RegisterSuccess.jsx';
import './Register.css';

export const ACCOUNT_TYPES = {
  usuario: {
    tipoCuenta: 'CONSUMIDOR_FINAL',
    icon: User,
    label: 'Uso personal',
    text: 'Usá GlucoLume para administrar tus propias mediciones y, si querés, participar de un grupo.',
  },
  institucion: {
    tipoCuenta: 'USUARIO_INSTITUCIONAL',
    icon: Building2,
    label: 'Uso institucional',
    text: 'Creá una cuenta para trabajar con una o más instituciones en GlucoLume. Después podrás crear una institución o ser incorporado a una existente.',
  },
};

const STEPS = ['Tipo de cuenta', 'Tus datos', 'Verificá tu correo'];

function Stepper({ current }) {
  return (
    <ol className="stepper" aria-label="Pasos del registro">
      {STEPS.map((label, index) => {
        const state = index < current ? 'is-done' : index === current ? 'is-current' : '';
        return (
          <li key={label} className={state} aria-current={index === current ? 'step' : undefined}>
            <span className="stepper-dot">{index < current ? <Check size={14} aria-hidden="true" /> : index + 1}</span>
            {label}
          </li>
        );
      })}
    </ol>
  );
}

function TypeChooser({ onSelect }) {
  return (
    <div className="type-chooser">
      <p className="auth-subtitle">¿Qué tipo de cuenta necesitás?</p>
      <ul className="type-options">
        {Object.entries(ACCOUNT_TYPES).map(([key, { icon: Icon, label, text }]) => (
          <li key={key}>
            <button
              type="button"
              className={`type-option${key === 'institucion' ? ' is-institutional' : ''}`}
              onClick={() => onSelect(key)}
            >
              <span className="type-icon">
                <Icon size={26} aria-hidden="true" />
              </span>
              <span className="type-text">
                <b>{label}</b>
                <small>{text}</small>
              </span>
              <ArrowRight size={20} aria-hidden="true" className="type-arrow" />
            </button>
          </li>
        ))}
      </ul>
      <div className="auth-info">
        <span className="auth-info-icon">
          <Users size={24} aria-hidden="true" />
        </span>
        <div>
          <b>¿Y el grupo?</b>
          <p>No es otro tipo de cuenta: creá tu cuenta de usuario y después armá tu grupo o sumate a uno.</p>
        </div>
      </div>
      <p className="auth-footer">
        ¿Ya tenés una cuenta? <Link to="/login">Iniciar sesión <ArrowRight size={16} aria-hidden="true" /></Link>
      </p>
    </div>
  );
}

export default function Register() {
  const [params, setParams] = useSearchParams();
  const tipo = params.get('tipo');
  const type = ACCOUNT_TYPES[tipo] ? tipo : null;
  const [registeredEmail, setRegisteredEmail] = useState(null);

  const step = registeredEmail ? 2 : type ? 1 : 0;
  const SelectedIcon = type ? ACCOUNT_TYPES[type].icon : null;

  return (
    <AuthShell
      title={
        <>
          Empezá a usar
          <br />
          <span className="accent">GlucoLume</span>
        </>
      }
      lead="Creá tu cuenta en pocos pasos. Te vamos a enviar un correo para verificarla antes del primer ingreso."
    >
      <h2 className="auth-title">Crear una cuenta</h2>
      <Stepper current={step} />

      {registeredEmail && <RegisterSuccess email={registeredEmail} />}

      {!registeredEmail && !type && (
        <>
          {tipo && <Alert kind="info">Elegí un tipo de cuenta para continuar.</Alert>}
          <TypeChooser onSelect={(key) => setParams({ tipo: key })} />
        </>
      )}

      {!registeredEmail && type && (
        <>
          <div className={`selected-type${type === 'institucion' ? ' is-institutional' : ''}`}>
            <SelectedIcon size={20} aria-hidden="true" />
            <span>{ACCOUNT_TYPES[type].label}</span>
            <button type="button" className="btn-text" onClick={() => setParams({})}>
              <ArrowLeft size={16} aria-hidden="true" /> Cambiar
            </button>
          </div>
          <RegisterForm type={type} tipoCuenta={ACCOUNT_TYPES[type].tipoCuenta} onRegistered={setRegisteredEmail} />
        </>
      )}

      {!registeredEmail && (
        <p className="register-note">
          <Mail size={16} aria-hidden="true" /> La cuenta se activa al verificar tu correo electrónico.
        </p>
      )}
    </AuthShell>
  );
}
