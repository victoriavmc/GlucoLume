import { ArrowRight, Building2, Mail, MessageSquareText, Send, User } from 'lucide-react';
import { useId, useState } from 'react';
import { Link } from 'react-router-dom';

import { sendContact } from '../../api/contactApi.js';
import { friendlyError } from '../../auth/errorMessages.js';
import { Alert, SelectField, SubmitButton, TextAreaField, TextField } from '../../components/FormControls.jsx';
import { EMAIL_PATTERN } from '../../utils/validation.js';

// Mismos valores que TipoConsulta (backend/app/schemas/contact.py).
const TIPOS_CONSULTA = [
  { value: 'INFORMACION_GENERAL', label: 'Información general' },
  { value: 'SUSCRIPCIONES', label: 'Suscripciones' },
  { value: 'SOPORTE', label: 'Ayuda / Soporte' },
  { value: 'INSTITUCIONES', label: 'Instituciones' },
  { value: 'PRIVACIDAD', label: 'Privacidad y datos' },
  { value: 'OTRO', label: 'Otro' },
];

// Mismos nombres de campo que ContactRequest en el backend.
const EMPTY = { nombre: '', email: '', tipoConsulta: 'INFORMACION_GENERAL', asunto: '', mensaje: '', sitioWeb: '' };
const ASUNTO_MIN = 3;
const ASUNTO_MAX = 150;
const MESSAGE_MIN = 10;
const MESSAGE_MAX = 2000;

// Ruta del error 422 del backend -> campo del formulario.
const CONTACT_FIELDS = ['nombre', 'email', 'tipoConsulta', 'asunto', 'mensaje'];

function validate(form) {
  const errors = {};
  if (form.nombre.trim().length < 2) errors.nombre = 'Ingresá tu nombre.';
  if (!EMAIL_PATTERN.test(form.email.trim())) errors.email = 'Ingresá un correo electrónico válido.';
  if (form.asunto.trim().length < ASUNTO_MIN) errors.asunto = 'Ingresá el asunto de tu consulta.';
  if (form.mensaje.trim().length < MESSAGE_MIN) errors.mensaje = `Contanos un poco más (al menos ${MESSAGE_MIN} caracteres).`;
  return errors;
}

export function ContactSection() {
  const trapId = useId();
  const [form, setForm] = useState(EMPTY);
  const [fieldErrors, setFieldErrors] = useState({});
  const [error, setError] = useState('');
  // null: sin envío; { confirmacionEnviada }: la consulta llegó (respuesta exitosa del backend).
  const [sent, setSent] = useState(null);
  const [loading, setLoading] = useState(false);

  function update(field) {
    return (event) => {
      setForm((current) => ({ ...current, [field]: event.target.value }));
      if (fieldErrors[field]) setFieldErrors((current) => ({ ...current, [field]: undefined }));
    };
  }

  async function handleSubmit(event) {
    event.preventDefault();
    // Sin doble envío: mientras la solicitud está en curso el botón queda deshabilitado y se ignora el submit.
    if (loading) return;
    setSent(null);
    const errors = validate(form);
    setFieldErrors(errors);
    if (Object.keys(errors).length) return;
    setError('');
    setLoading(true);
    try {
      const response = await sendContact({
        ...form,
        nombre: form.nombre.trim(),
        email: form.email.trim(),
        asunto: form.asunto.trim(),
        mensaje: form.mensaje.trim(),
      });
      setSent({ confirmacionEnviada: Boolean(response?.confirmacionEnviada) });
      setForm(EMPTY);
    } catch (sendError) {
      const byField = {};
      for (const field of sendError.fields ?? []) {
        if (CONTACT_FIELDS.includes(field.ruta) && !byField[field.ruta]) byField[field.ruta] = field.mensaje;
      }
      setFieldErrors(byField);
      // 503 (contacto o SMTP no disponibles): mensaje del backend, sin detalles técnicos.
      if (!Object.keys(byField).length) setError(friendlyError(sendError));
    } finally {
      setLoading(false);
    }
  }

  return (
    <section id="contacto" className="section" aria-labelledby="contacto-title">
      <div className="container contact-grid">
        <div className="contact-intro">
          <span className="pill">
            <Mail size={16} aria-hidden="true" /> Contacto
          </span>
          <h2 id="contacto-title">¿Querés saber más?</h2>
          <p className="section-lead">
            Escribinos tu consulta sobre GlucoLume, el uso institucional o el tratamiento de tus datos. Te respondemos
            al correo que nos indiques.
          </p>
          <div className="contact-cta">
            <Building2 size={22} aria-hidden="true" />
            <p>
              <b>¿Representás una institución?</b> Podés registrarla directamente y empezar a sumar a tu equipo.
            </p>
          </div>
          <div className="cta-actions">
            <Link to="/registro" className="btn btn-primary btn-lg">
              Registrarse <ArrowRight size={18} aria-hidden="true" />
            </Link>
            <Link to="/login" className="btn btn-outline btn-lg">
              Iniciar sesión
            </Link>
          </div>
        </div>

        <form className="card contact-form" onSubmit={handleSubmit} noValidate aria-labelledby="contacto-title">
          {sent && (
            <Alert kind="success">
              {sent.confirmacionEnviada ? (
                <>
                  <b>¡Consulta enviada!</b> Recibimos tu mensaje correctamente. También enviamos una confirmación a
                  tu correo electrónico.
                </>
              ) : (
                'Recibimos tu consulta correctamente.'
              )}
            </Alert>
          )}
          {error && <Alert>{error}</Alert>}
          <TextField
            label="Nombre"
            icon={User}
            name="nombre"
            autoComplete="name"
            maxLength={100}
            value={form.nombre}
            onChange={update('nombre')}
            error={fieldErrors.nombre}
          />
          <TextField
            label="Correo electrónico"
            icon={Mail}
            name="email"
            type="email"
            autoComplete="email"
            maxLength={254}
            value={form.email}
            onChange={update('email')}
            error={fieldErrors.email}
          />
          <SelectField
            label="Tipo de consulta"
            options={TIPOS_CONSULTA}
            value={form.tipoConsulta}
            onChange={update('tipoConsulta')}
            error={fieldErrors.tipoConsulta}
          />
          <TextField
            label="Asunto"
            icon={MessageSquareText}
            name="asunto"
            maxLength={ASUNTO_MAX}
            value={form.asunto}
            onChange={update('asunto')}
            error={fieldErrors.asunto}
          />
          <TextAreaField
            label="Mensaje"
            rows={5}
            maxLength={MESSAGE_MAX}
            value={form.mensaje}
            onChange={update('mensaje')}
            error={fieldErrors.mensaje}
          />
          {/* Campo trampa para envíos automatizados: invisible y fuera del orden de tabulación. */}
          <div className="visually-hidden" aria-hidden="true">
            <label htmlFor={trapId}>No completar</label>
            <input id={trapId} tabIndex={-1} autoComplete="off" value={form.sitioWeb} onChange={update('sitioWeb')} />
          </div>
          <SubmitButton loading={loading} loadingLabel="Enviando…">
            Enviar consulta <Send size={18} aria-hidden="true" />
          </SubmitButton>
          <p className="contact-privacy">
            Usamos tus datos solo para responder esta consulta. No los guardamos en GlucoLume.
          </p>
        </form>
      </div>
    </section>
  );
}
