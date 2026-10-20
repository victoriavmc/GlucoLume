// Configuración del grupo. Administrador: modificar datos, designar otro administrador y eliminar el grupo (baja
// lógica, con el nombre exacto como confirmación). Miembro: abandonar el grupo. Salir o eliminar no borra cuentas,
// perfiles ni mediciones.

import { DoorOpen, Pencil, TriangleAlert, UserCog } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useNavigate, useOutletContext } from 'react-router-dom';

import * as groupsApi from '../../../api/groupsApi.js';
import { Alert, SelectField, SubmitButton, TextField } from '../../../components/FormControls.jsx';
import { personName } from './groupFormat.js';

function EditGroup({ group, reload, handleOperationError }) {
  const [form, setForm] = useState({ nombre: group.nombre, descripcion: group.descripcion ?? '' });
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [saving, setSaving] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    if (form.nombre.trim().length < 2) {
      setError('Ingresá el nombre del grupo (al menos 2 caracteres).');
      return;
    }
    setSaving(true);
    setError('');
    try {
      await groupsApi.updateGroup(group.idGrupo, { nombre: form.nombre.trim(), descripcion: form.descripcion.trim() || null });
      await reload();
      setNotice('Guardamos los datos del grupo.');
    } catch (saveError) {
      setError(handleOperationError(saveError));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="panel" onSubmit={handleSubmit} noValidate aria-labelledby="grupo-editar">
      <div className="panel-title">
        <span className="panel-icon">
          <Pencil size={22} aria-hidden="true" />
        </span>
        <div>
          <h2 id="grupo-editar">Datos del grupo</h2>
        </div>
      </div>
      {error && <Alert>{error}</Alert>}
      {notice && <Alert kind="success">{notice}</Alert>}
      <TextField label="Nombre del grupo" maxLength={100} value={form.nombre}
        onChange={(event) => { setForm((current) => ({ ...current, nombre: event.target.value })); setNotice(''); }} />
      <TextField label="Descripción (opcional)" maxLength={500} value={form.descripcion}
        onChange={(event) => { setForm((current) => ({ ...current, descripcion: event.target.value })); setNotice(''); }} />
      <div className="form-actions">
        <SubmitButton loading={saving} loadingLabel="Guardando…" className="btn btn-primary">
          Guardar cambios
        </SubmitButton>
      </div>
    </form>
  );
}

function TransferAdmin({ group, reload, handleOperationError }) {
  const [members, setMembers] = useState(null);
  const [selected, setSelected] = useState('');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    groupsApi.listMembers(group.idGrupo).then((list) => setMembers(list.filter((member) => !member.esVos)))
      .catch((loadError) => setError(handleOperationError(loadError)));
  }, [group.idGrupo, handleOperationError]);

  async function transfer(event) {
    event.preventDefault();
    if (!selected) return;
    setSaving(true);
    setError('');
    try {
      await groupsApi.transferAdmin(group.idGrupo, selected);
      await reload();
    } catch (transferError) {
      setError(handleOperationError(transferError));
      setSaving(false);
    }
  }

  return (
    <form className="panel" onSubmit={transfer} aria-labelledby="grupo-transferir">
      <div className="panel-title">
        <span className="panel-icon">
          <UserCog size={22} aria-hidden="true" />
        </span>
        <div>
          <h2 id="grupo-transferir">Designar nuevo administrador</h2>
          <p>Pasás a ser miembro. Necesario antes de abandonar el grupo si hay otros integrantes.</p>
        </div>
      </div>
      {error && <Alert>{error}</Alert>}
      {members === null ? (
        <p className="field-hint" role="status">Cargando…</p>
      ) : members.length === 0 ? (
        <p className="field-hint">No hay otros integrantes a quienes designar.</p>
      ) : (
        <SelectField label="Nuevo administrador/a" value={selected} onChange={(event) => setSelected(event.target.value)}>
          <option value="">Elegí un integrante</option>
          {members.map((member) => (
            <option key={member.idGrupoUsuario} value={member.idGrupoUsuario}>{personName(member)}</option>
          ))}
        </SelectField>
      )}
      <div className="form-actions">
        <SubmitButton loading={saving} loadingLabel="Transfiriendo…" className="btn btn-outline" disabled={saving || !selected}>
          Transferir administración
        </SubmitButton>
      </div>
    </form>
  );
}

function DeleteGroup({ group, handleOperationError }) {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [error, setError] = useState('');
  const [deleting, setDeleting] = useState(false);
  const matches = name.trim().toLocaleLowerCase('es') === group.nombre.trim().toLocaleLowerCase('es');

  async function confirm(event) {
    event.preventDefault();
    if (!matches) return;
    setDeleting(true);
    setError('');
    try {
      await groupsApi.deleteGroup(group.idGrupo, name.trim());
      navigate('/app/grupo', { replace: true, state: { notice: `Eliminaste «${group.nombre}». Las mediciones de cada persona se conservan.` } });
    } catch (deleteError) {
      setError(handleOperationError(deleteError));
      setDeleting(false);
    }
  }

  return (
    <section className="panel is-danger" aria-labelledby="grupo-eliminar">
      <div className="panel-title">
        <span className="panel-icon">
          <TriangleAlert size={22} aria-hidden="true" />
        </span>
        <div>
          <h2 id="grupo-eliminar">Eliminar grupo</h2>
          <p>Todos dejan de pertenecer y de ver datos compartidos. Nadie pierde su cuenta ni sus mediciones.</p>
        </div>
      </div>
      {!open ? (
        <div className="form-actions">
          <button type="button" className="btn btn-outline" onClick={() => setOpen(true)}>Eliminar grupo</button>
        </div>
      ) : (
        <form className="deletion-form" onSubmit={confirm} role="alertdialog" aria-labelledby="grupo-eliminar-titulo">
          <h3 id="grupo-eliminar-titulo">¿Eliminar «{group.nombre}»?</h3>
          <ul className="mfa-steps">
            <li>Se dan de baja todos los integrantes y se cancelan las invitaciones pendientes.</li>
            <li>Se deja de compartir toda la información.</li>
            <li>Cada persona conserva su cuenta, su perfil y sus mediciones, y puede formar otro grupo.</li>
          </ul>
          {error && <Alert>{error}</Alert>}
          <TextField label={`Escribí «${group.nombre}» para confirmar`} autoComplete="off" maxLength={100} value={name}
            onChange={(event) => setName(event.target.value)} />
          <div className="form-actions">
            <button type="button" className="btn btn-ghost" disabled={deleting} onClick={() => setOpen(false)}>Cancelar</button>
            <button type="submit" className="btn btn-primary" disabled={deleting || !matches}>
              {deleting && <span className="spinner" aria-hidden="true" />} Eliminar definitivamente
            </button>
          </div>
        </form>
      )}
    </section>
  );
}

function LeaveGroup({ group, isAdmin, handleOperationError }) {
  const navigate = useNavigate();
  const [confirming, setConfirming] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const [error, setError] = useState('');
  const mustTransfer = isAdmin && group.cantidadIntegrantes > 1;
  const alone = isAdmin && group.cantidadIntegrantes === 1;

  async function leave() {
    setLeaving(true);
    setError('');
    try {
      await groupsApi.leaveGroup(group.idGrupo);
      navigate('/app/grupo', { replace: true, state: { notice: `Saliste de «${group.nombre}». Tus mediciones se conservan.` } });
    } catch (leaveError) {
      setError(handleOperationError(leaveError));
      setLeaving(false);
    }
  }

  return (
    <section className="panel" aria-labelledby="grupo-salir">
      <div className="panel-title">
        <span className="panel-icon">
          <DoorOpen size={22} aria-hidden="true" />
        </span>
        <div>
          <h2 id="grupo-salir">Abandonar el grupo</h2>
          <p>Dejás de ver los datos compartidos y el grupo deja de ver los tuyos. Conservás tus mediciones.</p>
        </div>
      </div>
      {error && <Alert>{error}</Alert>}
      {mustTransfer && <Alert kind="info">Para salir, primero designá a otro integrante como administrador.</Alert>}
      {alone && <Alert kind="info">Sos el único integrante: en lugar de abandonarlo, podés eliminar el grupo.</Alert>}
      {!isAdmin && (
        <div className="form-actions">
          {confirming ? (
            <>
              <span className="field-hint">¿Salir de «{group.nombre}»?</span>
              <button type="button" className="btn btn-ghost" disabled={leaving} onClick={() => setConfirming(false)}>Volver</button>
              <button type="button" className="btn btn-primary" disabled={leaving} onClick={leave}>
                {leaving && <span className="spinner" aria-hidden="true" />} Confirmar salida
              </button>
            </>
          ) : (
            <button type="button" className="btn btn-outline" onClick={() => setConfirming(true)}>Abandonar grupo</button>
          )}
        </div>
      )}
    </section>
  );
}

export function GroupSettings() {
  const { group, isAdmin, reload, handleOperationError } = useOutletContext();
  return (
    <>
      {isAdmin && <EditGroup key={group.nombre} group={group} reload={reload} handleOperationError={handleOperationError} />}
      {isAdmin && <TransferAdmin group={group} reload={reload} handleOperationError={handleOperationError} />}
      <LeaveGroup group={group} isAdmin={isAdmin} handleOperationError={handleOperationError} />
      {isAdmin && <DeleteGroup group={group} handleOperationError={handleOperationError} />}
    </>
  );
}
