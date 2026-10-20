import { AtSign, Pencil, UserRound } from 'lucide-react';

import { ACCOUNT_TYPES, ageFrom, formatDate, sexoLabel } from './accountFormat.js';

function Value({ children }) {
  return children ? <dd>{children}</dd> : <dd className="is-empty">Sin completar</dd>;
}

export function ProfileSummary({ account, onEdit }) {
  const user = account.usuario;
  const age = ageFrom(user.fechaNacimiento);

  return (
    <>
      <section className="panel" aria-labelledby="perfil-cuenta">
        <div className="panel-head">
          <div className="panel-title">
            <span className="panel-icon">
              <AtSign size={22} aria-hidden="true" />
            </span>
            <div>
              <h2 id="perfil-cuenta">Datos de la cuenta</h2>
              <p>Con estos datos iniciás sesión.</p>
            </div>
          </div>
        </div>
        <dl className="data-list">
          <div>
            <dt>Nombre de usuario</dt>
            <Value>{user.usuario}</Value>
          </div>
          <div>
            <dt>Correo electrónico</dt>
            <Value>{user.correoElectronico}</Value>
          </div>
          <div>
            <dt>Tipo de cuenta</dt>
            <Value>{ACCOUNT_TYPES[user.tipoCuenta] ?? user.tipoCuenta}</Value>
          </div>
          <div>
            <dt>Acceso</dt>
            <Value>
              {[account.tieneCredencialLocal && 'Contraseña', account.tieneGoogle && 'Google'].filter(Boolean).join(' y ')}
            </Value>
          </div>
        </dl>
      </section>

      <section className="panel" aria-labelledby="perfil-personal">
        <div className="panel-head">
          <div className="panel-title">
            <span className="panel-icon">
              <UserRound size={22} aria-hidden="true" />
            </span>
            <div>
              <h2 id="perfil-personal">Datos personales</h2>
              <p>Se usan para identificarte y asociar tus mediciones.</p>
            </div>
          </div>
          <button type="button" className="btn btn-primary" onClick={onEdit}>
            <Pencil size={18} aria-hidden="true" /> Editar perfil
          </button>
        </div>
        <dl className="data-list">
          <div>
            <dt>Nombre</dt>
            <Value>{user.nombre}</Value>
          </div>
          <div>
            <dt>Apellido</dt>
            <Value>{user.apellido}</Value>
          </div>
          <div>
            <dt>Fecha de nacimiento</dt>
            <Value>{user.fechaNacimiento && `${formatDate(user.fechaNacimiento)} (${age} años)`}</Value>
          </div>
          <div>
            <dt>Sexo</dt>
            <Value>{sexoLabel(user.sexo)}</Value>
          </div>
        </dl>
      </section>
    </>
  );
}
