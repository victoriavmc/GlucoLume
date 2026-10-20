// Pantallas del inventario de dispositivos:
//   - /app/dispositivos[/:id]                    inventario global (cuentas de plataforma);
//   - /app/instituciones/:id/dispositivos[/:id]  inventario de la institución (según el rol de cada integrante).
// Ocultar opciones no reemplaza la autorización: FastAPI responde 403/404 igualmente.

import { ArrowLeft } from 'lucide-react';
import { useMemo } from 'react';
import { Link, Navigate, useOutletContext, useParams } from 'react-router-dom';

import { devicesApi } from '../../../api/devicesApi.js';
import { useAuth } from '../../../auth/AuthContext.jsx';
import { friendlyError } from '../../../auth/errorMessages.js';
import { can } from '../institutions/institutionFormat.js';
import { DeviceDetail } from './DeviceDetail.jsx';
import { DevicesInventory } from './DevicesInventory.jsx';

const PLATFORM_ACCOUNTS = ['MODERADOR_PLATAFORMA', 'ADMINISTRADOR_PLATAFORMA'];

export function GlobalDevicesPage() {
  const { account } = useAuth();
  const api = useMemo(() => devicesApi(), []);
  if (!PLATFORM_ACCOUNTS.includes(account.usuario.tipoCuenta)) return <Navigate to="/app/inicio" replace />;
  return (
    <DevicesInventory title="Inventario de dispositivos" lead="Todos los dispositivos de GlucoLume: registro, estados y asignación a instituciones."
      api={api} institutional={false} canRegister canChangeState canAssign={account.usuario.tipoCuenta === 'ADMINISTRADOR_PLATAFORMA'}
      detailPath={(id) => id} handleOperationError={friendlyError} />
  );
}

export function GlobalDeviceDetailPage() {
  const { account } = useAuth();
  const { idDispositivo } = useParams();
  const api = useMemo(() => devicesApi(), []);
  if (!PLATFORM_ACCOUNTS.includes(account.usuario.tipoCuenta)) return <Navigate to="/app/inicio" replace />;
  return (
    <div className="page">
      <Link to=".." relative="path" className="back-link"><ArrowLeft size={16} aria-hidden="true" /> Inventario</Link>
      <DeviceDetail idDispositivo={idDispositivo} api={api} institutional={false} handleOperationError={friendlyError} />
    </div>
  );
}

export function InstitutionDevicesPage() {
  const { institution, handleOperationError } = useOutletContext();
  const api = useMemo(() => devicesApi(institution.idInstitucion), [institution.idInstitucion]);
  return (
    <DevicesInventory embedded title="Inventario de dispositivos"
      lead={institution.rolInstitucion === 'OPERADOR'
        ? 'Dispositivos operativos que podés usar para medir.'
        : 'Dispositivos de esta institución, que registran los operadores al conectarlos. Podés consultarlos, cambiar su nombre y su estado, o cargar uno que todavía no se conectó.'}
      api={api} institutional institutionName={institution.nombre} showOwner={institution.rolInstitucion !== 'OPERADOR'}
      canRegister={can(institution, 'GESTIONAR_DISPOSITIVOS')} canChangeState={can(institution, 'GESTIONAR_DISPOSITIVOS')} canAssign={false}
      detailPath={(id) => id} handleOperationError={handleOperationError} />
  );
}

export function InstitutionDeviceDetailPage() {
  const { institution, handleOperationError } = useOutletContext();
  const { idDispositivo } = useParams();
  const api = useMemo(() => devicesApi(institution.idInstitucion), [institution.idInstitucion]);
  return (
    <>
      <Link to=".." relative="path" className="back-link"><ArrowLeft size={16} aria-hidden="true" /> Inventario</Link>
      <DeviceDetail idDispositivo={idDispositivo} api={api} institutional handleOperationError={handleOperationError} />
    </>
  );
}
