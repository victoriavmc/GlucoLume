// Aviso no bloqueante de la versión vigente de la Política de Privacidad (backend/app/services/consent.py). Sin aceptarlo el acceso sigue
// igual; la aceptación solo habilita la extensión de 90 días desde la baja para los eventos de seguridad. «Ahora no» oculta el aviso
// hasta recargar la página.
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import { acceptPolicy, getConsents } from '../api/authApi.js';
import './PolicyUpdateNotice.css';

export function PolicyUpdateNotice() {
  const [pendiente, setPendiente] = useState(false);
  const [ocultado, setOcultado] = useState(false);
  const [ocupado, setOcupado] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let vigente = true;
    getConsents()
      .then((estado) => {
        if (vigente) setPendiente(estado?.POLITICA_PRIVACIDAD?.aceptado === false);
      })
      .catch(() => {});  // el aviso es opcional: si falla la consulta, no se muestra
    return () => {
      vigente = false;
    };
  }, []);

  if (!pendiente || ocultado) return null;

  async function aceptar() {
    setOcupado(true);
    setError('');
    try {
      await acceptPolicy();
      setPendiente(false);
    } catch {
      setError('No pudimos registrar tu aceptación. Probá de nuevo más tarde.');
    } finally {
      setOcupado(false);
    }
  }

  return (
    <section className="policy-notice" aria-labelledby="policy-notice-titulo">
      <h2 id="policy-notice-titulo" className="policy-notice-titulo">Actualizamos la Política de Privacidad</h2>
      <p>
        La versión 1.2 cambia los plazos de la dirección IP y del navegador asociados a tus eventos de seguridad. Tu acceso no cambia.
        Si la aceptás, los eventos de seguridad de una cuenta eliminada conservan esa información hasta 90 días después de la baja.
      </p>
      <p>
        <Link to="/privacidad">Leer la política</Link>
      </p>
      {error && <p className="field-error" role="alert">{error}</p>}
      <div className="policy-notice-acciones">
        <button type="button" className="btn btn-primary" onClick={aceptar} disabled={ocupado}>
          Acepto la versión 1.2
        </button>
        <button type="button" className="btn btn-ghost" onClick={() => setOcultado(true)}>
          Ahora no
        </button>
      </div>
    </section>
  );
}
