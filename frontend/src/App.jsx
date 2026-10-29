import { lazy, Suspense } from 'react';
import { Navigate, Route, Routes, useLocation } from 'react-router-dom';

import { AuthProvider } from './auth/AuthContext.jsx';
import { FullPageLoader } from './components/FullPageLoader.jsx';
import { AuthenticatedLayout } from './layouts/AuthenticatedLayout.jsx';
import { SectionGuard } from './pages/Account/institutions/SectionGuard.jsx';
import { PlatformLayout, RequireMfa, RequirePermission } from './layouts/PlatformLayout.jsx';
import Landing from './pages/Landing/Landing.jsx';
import PrivacyPolicy from './pages/Privacy/PrivacyPolicy.jsx';
import CaracteristicasPage from './pages/Landing/CaracteristicasPage.jsx';
import ActivateAccount from './pages/Register/ActivateAccount.jsx';
import GoogleCallback from './pages/Login/GoogleCallback.jsx';
import Login from './pages/Login/Login.jsx';
import Register from './pages/Register/Register.jsx';
import VerifyEmail from './pages/Register/VerifyEmail.jsx';
import { ForgotPasswordPage, ResetPasswordPage } from './pages/Login/PasswordRecovery.jsx';
import { GuestOnlyRoute, ProtectedRoute } from './routes/ProtectedRoute.jsx';

// Carga diferida por pantalla: cada módulo se pide una sola vez aunque exporte varias páginas (`name` elige la exportación; sin él, la de por defecto).
// Si el módulo ya se descargó (precarga desde main.jsx o ruta ya visitada) el componente se dibuja SIN suspender: un Suspense que muestra su
// fallback mantiene el contenido oculto un mínimo de ~300 ms (la regla de React 19 contra parpadeos) aunque el módulo llegue al instante, y eso
// sumaba ~250 ms al LCP de cada pantalla en red rápida (medido el 23/10/2026, docs/RENDIMIENTO.md §5).
function lazyNamed(loader, name = 'default') {
  let Loaded = null;
  const pick = (module) => { Loaded = module[name]; return { default: Loaded }; };
  const Lazy = lazy(() => loader().then(pick));
  function Page(props) {
    return Loaded ? <Loaded {...props} /> : <Lazy {...props} />;
  }
  Page.preload = () => loader().then((module) => { Loaded = module[name]; });
  return Page;
}

// Páginas por ruta (carga diferida: el JavaScript inicial trae el shell, la portada, las pantallas de acceso y las guardas; el resto se descarga al
// visitar su ruta; 23/10/2026, docs/RENDIMIENTO.md). Las de acceso (login, registro, recuperación, verificación) quedan en el inicial a propósito:
// son la primera pantalla de quien llega a la portada y una descarga extra por 4 KB no vale la espera.
const ConfirmDeletionPage = lazyNamed(() => import('./pages/Account/ConfirmDeletionPage.jsx'));
const ConfirmResultEmailPage = lazyNamed(() => import('./pages/ResultEmail/ConfirmResultEmailPage.jsx'));
const loadGroupDashboard = () => import('./pages/Account/groups/GroupDashboard.jsx');
const GroupMemberPage = lazyNamed(loadGroupDashboard, 'GroupMemberPage');
const loadSharedData = () => import('./pages/Account/groups/SharedData.jsx');
const SharedData = lazyNamed(loadSharedData, 'SharedData');
const loadDiabetesTips = () => import('./pages/Account/DiabetesTipsPage.jsx');
const DiabetesTipsPage = lazyNamed(loadDiabetesTips);
const PublicTipsPage = lazyNamed(loadDiabetesTips, 'PublicTipsPage');
const loadHomePage = () => import('./pages/Account/HomePage.jsx');
const HomePage = lazyNamed(loadHomePage);
const loadInstitutionDataPage = () => import('./pages/Account/institutions/InstitutionDataPage.jsx');
const InstitutionDataPage = lazyNamed(loadInstitutionDataPage, 'InstitutionDataPage');
const loadInstitutionSubnav = () => import('./pages/Account/institutions/InstitutionSubnav.jsx');
const PatientsTabs = lazyNamed(loadInstitutionSubnav, 'PatientsTabs');
const PersonnelLayout = lazyNamed(loadInstitutionSubnav, 'PersonnelLayout');
const loadInstitutionDashboards = () => import('./pages/Account/institutions/dashboard/InstitutionDashboards.jsx');
const OperatorDashboardPage = lazyNamed(loadInstitutionDashboards, 'OperatorDashboardPage');
const loadInstitutionOverview = () => import('./pages/Account/institutions/InstitutionOverview.jsx');
const InstitutionOverview = lazyNamed(loadInstitutionOverview, 'InstitutionOverview');
const loadInstitutionLayout = () => import('./pages/Account/institutions/InstitutionLayout.jsx');
const InstitutionLayout = lazyNamed(loadInstitutionLayout);
const loadInstitutionsPage = () => import('./pages/Account/institutions/InstitutionsPage.jsx');
const InstitutionsPage = lazyNamed(loadInstitutionsPage);
const loadPersonnelInvitationsPage = () => import('./pages/Account/institutions/PersonnelInvitationsPage.jsx');
const PersonnelInvitationsPage = lazyNamed(loadPersonnelInvitationsPage, 'PersonnelInvitationsPage');
const loadPersonnelPage = () => import('./pages/Account/institutions/PersonnelPage.jsx');
const PersonnelPage = lazyNamed(loadPersonnelPage, 'PersonnelPage');
const loadPatientCreatePage = () => import('./pages/Account/institutions/patients/PatientCreatePage.jsx');
const PatientCreatePage = lazyNamed(loadPatientCreatePage, 'PatientCreatePage');
const loadPatientDetailPage = () => import('./pages/Account/institutions/patients/PatientDetailPage.jsx');
const PatientDetailPage = lazyNamed(loadPatientDetailPage, 'PatientDetailPage');
const loadPatientsPage = () => import('./pages/Account/institutions/patients/PatientsPage.jsx');
const PatientsPage = lazyNamed(loadPatientsPage, 'PatientsPage');
const loadOwnMeasurementScreens = () => import('./pages/Account/measurements/OwnMeasurementScreens.jsx');
const MeasurementHistoryPage = lazyNamed(loadOwnMeasurementScreens, 'MeasurementHistoryPage');
const MeasurementProfilePage = lazyNamed(loadOwnMeasurementScreens, 'MeasurementProfilePage');
const NewMeasurementPage = lazyNamed(loadOwnMeasurementScreens, 'NewMeasurementPage');
const loadMeasurementsPage = () => import('./pages/Account/measurements/MeasurementsPage.jsx');
const InstitutionMeasurementDetail = lazyNamed(loadMeasurementsPage, 'InstitutionMeasurementDetail');
const MeasurementDetailPage = lazyNamed(loadMeasurementsPage, 'MeasurementDetailPage');
const MeasurementsPage = lazyNamed(loadMeasurementsPage, 'MeasurementsPage');
const loadPatientMeasurePage = () => import('./pages/Account/institutions/patients/PatientMeasurePage.jsx');
const PatientMeasurePage = lazyNamed(loadPatientMeasurePage, 'PatientMeasurePage');
const loadConnectDevicePage = () => import('./pages/Account/acquisition/ConnectDevicePage.jsx');
const ConnectDevicePage = lazyNamed(loadConnectDevicePage, 'ConnectDevicePage');
const InstitutionConnectDevicePage = lazyNamed(loadConnectDevicePage, 'InstitutionConnectDevicePage');
const ProfilePage = lazyNamed(() => import('./pages/Account/ProfilePage.jsx'));
const loadPlatformAuth = () => import('./pages/Platform/PlatformAuth.jsx');
const PlatformActivateWithCode = lazyNamed(loadPlatformAuth, 'PlatformActivateWithCode');
const PlatformForgot = lazyNamed(loadPlatformAuth, 'PlatformForgot');
const PlatformLogin = lazyNamed(loadPlatformAuth, 'PlatformLogin');
const PlatformReset = lazyNamed(loadPlatformAuth, 'PlatformReset');
const SecurityPage = lazyNamed(() => import('./pages/Account/SecurityPage.jsx'));
const NotificationsPage = lazyNamed(() => import('./pages/Account/notifications/NotificationsPage.jsx'));
const NotificationPreferencesPage = lazyNamed(() => import('./pages/Account/notifications/NotificationPreferencesPage.jsx'));

const loadAnalytics = () => import('./pages/Account/institutions/analytics/PatientAnalyticsPage.jsx');
const PatientAnalyticsPage = lazyNamed(loadAnalytics, 'PatientAnalyticsPage');
const loadMatrices = () => import('./pages/Account/matrices/MatrixPages.jsx');
const GlobalMatricesPage = lazyNamed(loadMatrices, 'GlobalMatricesPage');
const GlobalMatrixDetailPage = lazyNamed(loadMatrices, 'GlobalMatrixDetailPage');
const InstitutionMatricesPage = lazyNamed(loadMatrices, 'InstitutionMatricesPage');
const InstitutionMatrixDetailPage = lazyNamed(loadMatrices, 'InstitutionMatrixDetailPage');
const loadAudit = () => import('./pages/Account/audit/AuditPages.jsx');
const AuditRedirect = lazyNamed(loadAudit, 'AuditRedirect');
const GlobalAuditDetailPage = lazyNamed(loadAudit, 'GlobalAuditDetailPage');
const GlobalAuditPage = lazyNamed(loadAudit, 'GlobalAuditPage');
const InstitutionAuditDetailPage = lazyNamed(loadAudit, 'InstitutionAuditDetailPage');
const InstitutionAuditPage = lazyNamed(loadAudit, 'InstitutionAuditPage');
const loadDevices = () => import('./pages/Account/devices/DevicePages.jsx');
const GlobalDeviceDetailPage = lazyNamed(loadDevices, 'GlobalDeviceDetailPage');
const GlobalDevicesPage = lazyNamed(loadDevices, 'GlobalDevicesPage');
const InstitutionDeviceDetailPage = lazyNamed(loadDevices, 'InstitutionDeviceDetailPage');
const InstitutionDevicesPage = lazyNamed(loadDevices, 'InstitutionDevicesPage');
const loadPlatformPages = () => import('./pages/Platform/PlatformPages.jsx');
const ModeratorDetailPage = lazyNamed(loadPlatformPages, 'ModeratorDetailPage');
const ModeratorsPage = lazyNamed(loadPlatformPages, 'ModeratorsPage');
const PlatformPasswordPage = lazyNamed(loadPlatformPages, 'PlatformPasswordPage');
const PlatformProfilePage = lazyNamed(loadPlatformPages, 'PlatformProfilePage');
const PlatformSecurityPage = lazyNamed(loadPlatformPages, 'PlatformSecurityPage');
const SubscriptionsPage = lazyNamed(loadPlatformPages, 'SubscriptionsPage');
const TransferPage = lazyNamed(loadPlatformPages, 'TransferPage');
const loadPlatformDashboard = () => import('./pages/Platform/PlatformDashboard.jsx');
const PlatformDashboardPage = lazyNamed(loadPlatformDashboard, 'PlatformDashboardPage');
const loadPlatformInstitutions = () => import('./pages/Platform/PlatformInstitutions.jsx');
const PlatformInstitutionDetailPage = lazyNamed(loadPlatformInstitutions, 'PlatformInstitutionDetailPage');
const PlatformInstitutionsPage = lazyNamed(loadPlatformInstitutions, 'PlatformInstitutionsPage');

const loadGroupOverview = () => import('./pages/Account/groups/GroupOverview.jsx');
const GroupLayout = lazyNamed(() => import('./pages/Account/groups/GroupLayout.jsx'));
const GroupMembers = lazyNamed(loadGroupOverview, 'GroupMembers');
const GroupOverview = lazyNamed(loadGroupOverview, 'GroupOverview');
const GroupsHome = lazyNamed(() => import('./pages/Account/groups/GroupsHome.jsx'));
const GroupSettings = lazyNamed(() => import('./pages/Account/groups/GroupSettings.jsx'), 'GroupSettings');
const MyPrivacy = lazyNamed(() => import('./pages/Account/groups/MyPrivacy.jsx'), 'MyPrivacy');
const SharedMeasurementDetail = lazyNamed(() => import('./pages/Account/groups/SharedMeasurementDetail.jsx'), 'SharedMeasurementDetail');
const InstitutionActivityPage = lazyNamed(() => import('./pages/Account/institutions/InstitutionActivityPage.jsx'), 'InstitutionActivityPage');
const PersonnelProfilePage = lazyNamed(() => import('./pages/Account/institutions/PersonnelProfilePage.jsx'), 'PersonnelProfilePage');
const ReassignmentsPage = lazyNamed(() => import('./pages/Account/institutions/reassignments/ReassignmentsPage.jsx'));
const TransferDetailPage = lazyNamed(() => import('./pages/Account/institutions/transfers/TransferDetailPage.jsx'), 'TransferDetailPage');
const TransfersPage = lazyNamed(() => import('./pages/Account/institutions/transfers/TransfersPage.jsx'), 'TransfersPage');

// Precarga de la pantalla pedida. Sin esto, el navegador recién descarga el JavaScript de una pantalla cuando React la dibuja, y eso ocurre DESPUÉS de
// recuperar la sesión (/auth/refresh y /auth/me): descarga y datos quedaban en serie (LCP de /app/inicio en red rápida: 198 ms con todo en un solo
// archivo, 442 ms con carga diferida sin precarga; medido el 23/10/2026, docs/RENDIMIENTO.md §5). Se llama desde main.jsx con la ruta con la que se abrió la
// página: descarga y sesión corren en paralelo. Los errores se ignoran (el Suspense volverá a pedir el módulo si hace falta).
const PRELOADS = [
  [/^\/app\/?$|^\/app\/inicio\/?$/, [HomePage]],
  [/^\/app\/mediciones\/historial\/?$/, [MeasurementHistoryPage]],
  [/^\/app\/mediciones\/?$/, [MeasurementsPage]],
  [/^\/app\/instituciones\/?$/, [InstitutionsPage]],
  [/^\/app\/instituciones\/[^/]+\/?$/, [InstitutionLayout, InstitutionOverview]],
  [/^\/app\/instituciones\/[^/]+\/pacientes\/?$/, [InstitutionLayout, PatientsTabs, PatientsPage]],
  [/^\/app\/instituciones\/[^/]+\/personal\/operadores\/[^/]+\/?$/, [InstitutionLayout, PersonnelLayout, OperatorDashboardPage]],
];

export function preloadForPath(pathname) {
  const match = PRELOADS.find(([pattern]) => pattern.test(pathname));
  if (match) match[1].forEach((page) => page.preload().catch(() => {}));
}

/** En el login, con el navegador ocioso y sin «ahorro de datos», trae el inicio del espacio privado: es adonde se va al ingresar (no en la portada: quien solo la lee no gasta datos). */
export function warmPrivateHome() {
  if (navigator.connection?.saveData) return;
  const warm = () => HomePage.preload().catch(() => {});
  if (typeof window.requestIdleCallback === 'function') window.requestIdleCallback(warm, { timeout: 4000 });
  else setTimeout(warm, 1500);
}

/** Enlaces de activación anteriores (/plataforma/activar?token=…): llevan a la ruta principal sin duplicar la activación; el código pasa al fragmento. */
function LegacyActivationLink() {
  const token = new URLSearchParams(useLocation().search).get('token');
  return <Navigate to={{ pathname: '/administracion/activar', hash: token ? `#codigo=${token}` : '' }} replace />;
}

export function AppRoutes() {
  return (
    <Suspense fallback={<FullPageLoader />}>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route
          path="/login"
          element={
            <GuestOnlyRoute>
              <Login />
            </GuestOnlyRoute>
          }
        />
        <Route path="/auth/google/callback" element={<GoogleCallback />} />
        <Route path="/privacidad" element={<PrivacyPolicy />} />
        {/* Consejos para diabéticos sin iniciar sesión (mismo contenido que /app/consejos). */}
        <Route path="/consejos" element={<PublicTipsPage />} />
        <Route path="/consejos/:idConsejo" element={<PublicTipsPage />} />
        <Route path="/caracteristicas" element={<CaracteristicasPage />} />
        <Route path="/recuperar-contrasena" element={<ForgotPasswordPage />} />
        <Route path="/restablecer-contrasena" element={<ResetPasswordPage />} />
        <Route
          path="/registro"
          element={
            <GuestOnlyRoute>
              <Register />
            </GuestOnlyRoute>
          }
        />
        <Route path="/verificar-correo" element={<VerifyEmail />} />
        <Route path="/activar-cuenta" element={<ActivateAccount />} />
        <Route path="/cuenta/eliminar/confirmar" element={<ConfirmDeletionPage />} />
        <Route path="/confirmar-correo-resultados" element={<ConfirmResultEmailPage />} />
        {/* Administración de la plataforma: accesos propios y panel con su layout. */}
        <Route path="/administracion/activar" element={<PlatformActivateWithCode />} />
        <Route path="/administracion/login" element={<Navigate to="/plataforma/login" replace />} />{/* dirección alternativa del acceso administrativo: no concede nada, solo lleva al acceso real */}
        <Route path="/plataforma/login" element={<PlatformLogin />} />
        <Route path="/plataforma/activar" element={<LegacyActivationLink />} />
        <Route path="/plataforma/recuperar" element={<PlatformForgot />} />
        <Route path="/plataforma/restablecer" element={<PlatformReset />} />
        <Route path="/plataforma" element={<PlatformLayout />}>
          <Route index element={<Navigate to="dashboard" replace />} />
          <Route path="dashboard" element={<PlatformDashboardPage />} />
          <Route path="instituciones" element={<RequirePermission permission="SUPERVISAR_INSTITUCIONES"><PlatformInstitutionsPage /></RequirePermission>} />
          <Route path="instituciones/:idInstitucion" element={<RequirePermission permission="SUPERVISAR_INSTITUCIONES"><PlatformInstitutionDetailPage /></RequirePermission>} />
          <Route path="moderadores" element={<RequirePermission permission="GESTIONAR_MODERADORES"><ModeratorsPage /></RequirePermission>} />
          <Route path="moderadores/:idUsuario" element={<RequirePermission permission="GESTIONAR_MODERADORES"><ModeratorDetailPage /></RequirePermission>} />
          <Route path="transferencia" element={<RequireMfa><TransferPage /></RequireMfa>} />
          <Route path="dispositivos" element={<RequirePermission permission="CONSULTAR_DISPOSITIVOS_GLOBALES"><GlobalDevicesPage /></RequirePermission>} />
          <Route path="dispositivos/:idDispositivo" element={<RequirePermission permission="CONSULTAR_DISPOSITIVOS_GLOBALES"><GlobalDeviceDetailPage /></RequirePermission>} />
          <Route path="matrices" element={<RequirePermission permission="GESTIONAR_MATRICES_GLOBALES"><GlobalMatricesPage /></RequirePermission>} />
          <Route path="matrices/:idMatriz" element={<RequirePermission permission="GESTIONAR_MATRICES_GLOBALES"><GlobalMatrixDetailPage /></RequirePermission>} />
          <Route path="auditoria" element={<RequirePermission permission="CONSULTAR_AUDITORIA_GLOBAL"><GlobalAuditPage /></RequirePermission>} />
          <Route path="auditoria/:idAuditoria" element={<RequirePermission permission="CONSULTAR_AUDITORIA_GLOBAL"><GlobalAuditDetailPage basePath="/plataforma/auditoria" /></RequirePermission>} />
          <Route path="suscripciones" element={<RequirePermission permission="SUSCRIPCIONES_Y_PAGOS"><SubscriptionsPage /></RequirePermission>} />
          <Route path="perfil" element={<PlatformProfilePage />} />
          <Route path="seguridad" element={<PlatformSecurityPage />} />
          <Route path="cambiar-contrasena" element={<PlatformPasswordPage />} />
          <Route path="*" element={<Navigate to="dashboard" replace />} />
        </Route>
        {/* Espacio privado: un único layout para todas las páginas internas. */}
        <Route
          path="/app"
          element={
            <ProtectedRoute>
              <AuthenticatedLayout />
            </ProtectedRoute>
          }
        >
          <Route index element={<Navigate to="inicio" replace />} />
          <Route path="inicio" element={<HomePage />} />
          <Route path="consejos" element={<DiabetesTipsPage />} />
          <Route path="consejos/:idConsejo" element={<DiabetesTipsPage />} />
          <Route path="perfil" element={<ProfilePage />} />
          <Route path="conectar-dispositivo" element={<ConnectDevicePage />} />
          <Route path="seguridad" element={<SecurityPage />} />
          <Route path="notificaciones" element={<NotificationsPage />} />
          <Route path="notificaciones/preferencias" element={<NotificationPreferencesPage />} />
          <Route path="dispositivos" element={<GlobalDevicesPage />} />
          <Route path="dispositivos/:idDispositivo" element={<GlobalDeviceDetailPage />} />
          <Route path="auditoria" element={<GlobalAuditPage />} />
          <Route path="auditoria/:idAuditoria" element={<GlobalAuditDetailPage />} />
          <Route path="matrices" element={<GlobalMatricesPage />} />
          <Route path="matrices/:idMatriz" element={<GlobalMatrixDetailPage />} />
          <Route path="mediciones" element={<MeasurementsPage />} />
          <Route path="mediciones/nueva" element={<NewMeasurementPage />} />
          <Route path="mediciones/perfil" element={<MeasurementProfilePage />} />
          <Route path="mediciones/historial" element={<MeasurementHistoryPage />} />
          <Route path="mediciones/:idMedicion" element={<MeasurementDetailPage />} />
          <Route path="grupo" element={<GroupsHome />} />
          <Route path="grupo/:idGrupo" element={<GroupLayout />}>
            <Route index element={<GroupOverview />} />
            <Route path="integrantes" element={<GroupMembers />} />
            <Route path="integrantes/:idGrupoUsuario" element={<GroupMemberPage />} />
            <Route path="invitaciones" element={<Navigate to="../integrantes" relative="path" replace />} />
            <Route path="privacidad" element={<MyPrivacy />} />
            <Route path="compartidos" element={<SharedData />} />
            <Route path="compartidos/:idGrupoUsuario/mediciones/:idMedicion" element={<SharedMeasurementDetail />} />
            <Route path="configuracion" element={<GroupSettings />} />
          </Route>
          <Route path="instituciones" element={<InstitutionsPage />} />
          <Route path="instituciones/:idInstitucion" element={<InstitutionLayout />}>
            <Route index element={<InstitutionOverview />} />
            <Route path="panel" element={<Navigate to=".." replace />} />
            <Route path="personal" element={<PersonnelLayout />}>
              <Route index element={<PersonnelPage key="TODOS" />} />
              <Route path="moderadores" element={<PersonnelPage key="MODERADOR" rol="MODERADOR" />} />
              <Route path="operadores" element={<PersonnelPage key="OPERADOR" rol="OPERADOR" />} />
              <Route path="invitaciones" element={<PersonnelInvitationsPage />} />
              <Route path="perfil/:idPersona" element={<PersonnelProfilePage />} />
              <Route path="operadores/:idOperador" element={<OperatorDashboardPage />} />
            </Route>
            <Route path="administracion" element={<SectionGuard permission="CONSULTAR_EQUIPO" />}>
              <Route index element={<Navigate to="datos" replace />} />
              <Route path="datos" element={<InstitutionDataPage />} />
              <Route path="auditoria" element={<AuditRedirect />} />
              <Route path="auditoria/:idAuditoria" element={<AuditRedirect />} />
              <Route path="configuracion" element={<Navigate to="../datos" replace />} />
            </Route>
            {/* Auditoría y Actividad: módulos propios del menú institucional (la auditoría es solo del propietario). */}
            <Route path="auditoria" element={<InstitutionAuditPage />} />
            <Route path="auditoria/:idAuditoria" element={<InstitutionAuditDetailPage />} />
            <Route path="actividad" element={<InstitutionActivityPage />} />
            {/* Rutas anteriores: se conservan como redirecciones. */}
            <Route path="datos" element={<Navigate to="../administracion/datos" replace />} />
            <Route path="moderadores" element={<Navigate to="../personal/moderadores" replace />} />
            <Route path="operadores" element={<Navigate to="../personal/operadores" replace />} />
            <Route path="transferencias" element={<Navigate to="../pacientes/transferencias" replace />} />
            <Route path="configuracion" element={<Navigate to="../administracion/datos" replace />} />
            <Route path="pacientes" element={<><PatientsTabs /><PatientsPage /></>} />
            <Route path="pacientes/nuevo" element={<PatientCreatePage />} />
            <Route path="pacientes/analisis" element={<><PatientsTabs /><PatientAnalyticsPage /></>} />
            <Route path="pacientes/:idPerfilMedicion" element={<PatientDetailPage />} />
            {/* El dashboard del paciente se quitó: la ficha tiene todo. Los enlaces viejos llevan a la ficha. */}
            <Route path="pacientes/:idPerfilMedicion/dashboard" element={<Navigate to=".." relative="path" replace />} />
            <Route path="pacientes/:idPerfilMedicion/medir" element={<PatientMeasurePage />} />
            <Route path="pacientes/:idPerfilMedicion/mediciones/:idMedicion" element={<InstitutionMeasurementDetail />} />
            <Route path="pacientes/reasignaciones" element={<SectionGuard permission="CONSULTAR_EQUIPO"><PatientsTabs /><ReassignmentsPage /></SectionGuard>} />
            <Route path="pacientes/transferencias" element={<><PatientsTabs /><TransfersPage /></>} />
            <Route path="pacientes/transferencias/:idTransferencia" element={<><PatientsTabs /><TransferDetailPage /></>} />
            <Route path="conectar-dispositivo" element={<InstitutionConnectDevicePage />} />
            <Route path="dispositivos" element={<SectionGuard permission="GESTIONAR_DISPOSITIVOS"><InstitutionDevicesPage /></SectionGuard>} />
            <Route path="dispositivos/:idDispositivo" element={<SectionGuard permission="GESTIONAR_DISPOSITIVOS"><InstitutionDeviceDetailPage /></SectionGuard>} />
            <Route path="matrices" element={<InstitutionMatricesPage />} />
            <Route path="matrices/:idMatriz" element={<InstitutionMatrixDetailPage />} />
          </Route>
          <Route path="*" element={<Navigate to="inicio" replace />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <AppRoutes />
    </AuthProvider>
  );
}
