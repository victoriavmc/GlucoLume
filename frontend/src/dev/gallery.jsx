// Galería de los componentes compartidos, solo para desarrollo: http://localhost:5173/gallery.html
// No forma parte de la aplicación (no está en las rutas ni en el build: Vite compila solo index.html). Sirve para revisar
// la apariencia y el teclado de cada componente en sus variantes antes de migrar las pantallas. `#modal` abre la ventana.

import { Activity, Cpu, Inbox, Layers, Users } from 'lucide-react';
import { StrictMode, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';

import { Badge } from '../components/Badge.jsx';
import { EmptyState } from '../components/EmptyState.jsx';
import { CheckField, SelectField, TextAreaField, TextField } from '../components/FormControls.jsx';
import { Modal } from '../components/Modal.jsx';
import { PageHeader } from '../components/PageHeader.jsx';
import { NavTabs, TabPanel, Tabs } from '../components/Tabs.jsx';
import '../layouts/AuthenticatedLayout.css';
import '../styles/global.css';
import '../styles/components.css';

const VARIABLES = [
  { key: 'glucosa', label: 'Glucosa experimental', icon: Activity },
  { key: 'frecuencia', label: 'Frecuencia cardíaca', icon: Activity },
  { key: 'spo2', label: 'SpO₂', icon: Activity },
  { key: 'indice', label: 'Índice óptico', icon: Activity },
];

function TabsSection() {
  const [pill, setPill] = useState('glucosa');
  const [soft, setSoft] = useState('frecuencia');
  const [underline, setUnderline] = useState('spo2');
  return (
    <section className="panel" aria-labelledby="g-tabs">
      <h2 id="g-tabs">Tabs y NavTabs</h2>
      <Tabs label="Variable a graficar (pill)" idBase="g-pill" items={VARIABLES} value={pill} onChange={setPill} variant="pill" />
      <TabPanel idBase="g-pill" value={pill}><p className="field-hint">Panel de «{pill}». Flechas, Inicio y Fin cambian de pestaña.</p></TabPanel>
      <Tabs label="Secciones (soft)" idBase="g-soft" items={VARIABLES.slice(0, 3)} value={soft} onChange={setSoft} variant="soft" activation="manual" />
      <TabPanel idBase="g-soft" value={soft}><p className="field-hint">Activación manual: las flechas mueven el foco y Enter selecciona.</p></TabPanel>
      <Tabs label="Pestañas con subrayado" idBase="g-underline" items={[...VARIABLES.slice(0, 3), { key: 'x', label: 'Deshabilitada', disabled: true }]} value={underline} onChange={setUnderline} variant="underline" />
      <TabPanel idBase="g-underline" value={underline}><p className="field-hint">Variante con subrayado.</p></TabPanel>
      <NavTabs label="Secciones del personal" items={[{ to: '/', label: 'Todos' }, { to: '/moderadores', label: 'Moderadores' }, { to: '/operadores', label: 'Operadores' }]} />
    </section>
  );
}

function BadgeSection() {
  return (
    <section className="panel" aria-labelledby="g-badges">
      <h2 id="g-badges">Badge</h2>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
        <Badge tone="success" dot>Activa</Badge>
        <Badge tone="warning" dot>Pendiente</Badge>
        <Badge tone="danger" dot>Rechazada</Badge>
        <Badge tone="info" icon={Cpu}>Experimental</Badge>
        <Badge tone="brand" icon={Users}>Propietario/a</Badge>
        <Badge tone="neutral">Sin asignar</Badge>
        <Badge tone="success" size="sm">Vigente</Badge>
        <Badge tone="danger" size="sm">Vencida</Badge>
      </div>
    </section>
  );
}

function EmptySection() {
  return (
    <section className="panel" aria-labelledby="g-empty">
      <h2 id="g-empty">EmptyState</h2>
      <EmptyState icon={Inbox} title="Todavía no hay pacientes" description="Cuando registres al primero, vas a verlo en este listado." action={<button type="button" className="btn btn-primary">Registrar paciente</button>} />
      <EmptyState variant="framed" icon={Layers} title="Sin datos disponibles" description="No hay mediciones completadas en este período." />
      <EmptyState variant="inline" icon={Inbox} title="No tenés invitaciones pendientes" />
    </section>
  );
}

function FormSection() {
  const [text, setText] = useState('Observación de ejemplo');
  const [checked, setChecked] = useState(false);
  return (
    <section className="panel" aria-labelledby="g-forms">
      <h2 id="g-forms">Campos de formulario</h2>
      <form className="form-grid" onSubmit={(event) => event.preventDefault()}>
        <TextField label="Correo electrónico" type="email" hint="Usá el correo de tu trabajo." placeholder="nombre@ejemplo.com" />
        <TextField label="Contraseña" revealable error="Ingresá una contraseña de al menos 10 caracteres." defaultValue="corta" />
        <SelectField label="Estado" hint="Filtra el listado." options={[{ value: 'ACTIVO', label: 'Activos' }, { value: 'BAJA', label: 'Dados de baja' }]} />
        <SelectField label="Operador responsable" error="Elegí un operador." defaultValue="">
          <option value="">Seleccioná…</option><option value="1">Tomás Simulado</option>
        </SelectField>
        <TextAreaField label="Observaciones (opcional)" hint="Se guarda con la medición." maxLength={120} value={text} onChange={(event) => setText(event.target.value)} />
        <CheckField label="Recordarme en este equipo" hint="No lo uses en equipos compartidos." checked={checked} onChange={(event) => setChecked(event.target.checked)} />
        <CheckField label="Acepto la política de privacidad" error="Tenés que aceptarla para continuar." />
        <TextField label="Campo deshabilitado" disabled defaultValue="No editable" />
      </form>
    </section>
  );
}

function ModalSection() {
  const [open, setOpen] = useState(window.location.hash === '#modal');
  return (
    <section className="panel" aria-labelledby="g-modal">
      <h2 id="g-modal">Modal</h2>
      <p className="field-hint">Foco atrapado, fondo inerte y Escape para cerrar.</p>
      <div><button type="button" className="btn btn-outline" onClick={() => setOpen(true)}>Abrir ventana de confirmación</button></div>
      {open && (
        <Modal title="¿Eliminar a esta persona?" onClose={() => setOpen(false)}
          actions={<><button type="button" className="btn btn-ghost" onClick={() => setOpen(false)}>Cancelar</button><button type="button" className="btn btn-primary" onClick={() => setOpen(false)}>Eliminar</button></>}>
          <p>Se eliminarán sus datos personales. Esta acción no se puede deshacer.</p>
        </Modal>
      )}
    </section>
  );
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <MemoryRouter>
      <main className="app-content" style={{ marginLeft: 0 }} id="contenido">
        <div className="page is-form">
          <PageHeader title="Galería de componentes" description="Componentes compartidos de GlucoLume en todas sus variantes (solo desarrollo)."
            back={{ to: '/', label: 'Volver' }} actions={<button type="button" className="btn btn-primary">Acción principal</button>} />
          <PageHeader as="h2" title="Encabezado con h2 (pantalla que ya tiene h1)" description="Mismo aspecto, sin un segundo h1." />
          <TabsSection />
          <BadgeSection />
          <EmptySection />
          <FormSection />
          <ModalSection />
        </div>
      </main>
    </MemoryRouter>
  </StrictMode>,
);
