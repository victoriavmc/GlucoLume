// Aviso emergente para cuentas individuales que aún no informaron edad ni sexo. Es informativo: nunca bloquea nada ni
// se muestra como error. Aparece al entrar a la cuenta; «Más tarde» (o cerrarlo) lo oculta 7 días en este navegador,
// y «Completar datos» lleva a la configuración de perfil. Cuando la cuenta ya tiene ambos datos, no vuelve a aparecer.
import { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';

import { useAuth } from '../auth/AuthContext.jsx';
import { Modal } from './Modal.jsx';
import { postponeKey } from './recommendedDataStorage.js';

export const PROFILE_NOTICE = 'Podés realizar mediciones sin completar tu edad o sexo. Sin embargo, se recomienda informar estos datos para '
  + 'mejorar la contextualización de los resultados.';

const POSTPONE_DAYS = 7;
const PROFILE_PATH = '/app/perfil';

// Sin almacenamiento disponible (modo privado, datos bloqueados) el aviso simplemente vuelve en la próxima carga.
function isPostponed(key) {
  try {
    const until = Number(window.localStorage.getItem(key));
    return Number.isFinite(until) && Date.now() < until;
  } catch {
    return false;
  }
}

function postpone(key) {
  try {
    window.localStorage.setItem(key, String(Date.now() + POSTPONE_DAYS * 24 * 60 * 60 * 1000));
  } catch {
    // Sin almacenamiento no se puede recordar la postergación.
  }
}

export function RecommendedDataModal() {
  const { account } = useAuth();
  const { pathname } = useLocation();
  const [cerrado, setCerrado] = useState(false);
  const usuario = account?.usuario;
  const faltan = usuario?.tipoCuenta === 'CONSUMIDOR_FINAL' && (!usuario.fechaNacimiento || !usuario.sexo);
  const key = usuario ? postponeKey(usuario.idUsuario) : null;
  // En la propia pantalla de perfil la persona ya está completando los datos: no se interrumpe.
  if (!faltan || cerrado || pathname.replace(/\/+$/, '') === PROFILE_PATH || isPostponed(key)) return null;

  function maybeLater() {
    postpone(key);
    setCerrado(true);
  }

  return (
    <Modal
      title="Completá tu edad y sexo"
      onClose={maybeLater}
      actions={(
        <>
          <button type="button" className="btn btn-ghost" onClick={maybeLater}>Más tarde</button>
          <Link to={`${PROFILE_PATH}?editar=1`} className="btn btn-primary" onClick={() => setCerrado(true)}>Completar datos</Link>
        </>
      )}
    >
      <p>{PROFILE_NOTICE}</p>
    </Modal>
  );
}
