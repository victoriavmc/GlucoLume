// /privacidad — Política de Privacidad (pública, sin iniciar sesión).
//
// El texto describe el comportamiento REAL del sistema (ver docs/PRIVACIDAD_Y_RETENCION.md, que lista qué código respalda cada
// afirmación). Si cambia el texto de forma sustancial hay que subir POLICY_VERSION en backend/app/services/consent.py.
// Prototipo académico (Trabajo Integrador Final): toma como referencia la Ley 25.326; no afirma cumplimiento certificado.

import { Link } from 'react-router-dom';

import { ExperimentalNotice } from '../../components/ExperimentalNotice.jsx';
import { Navbar } from '../../components/Navbar.jsx';
import { SiteFooter } from '../../components/SiteFooter.jsx';
import { SkipLink } from '../../components/SkipLink.jsx';
import './PrivacyPolicy.css';

export const POLICY_VERSION = '1.1';
export const POLICY_DATE = '19 de octubre de 2026';

const CONTENTS = [
  { id: 'p-alcance', label: '1. Qué es GlucoLume y alcance de esta política' },
  { id: 'p-datos', label: '2. Qué datos personales recopila' },
  { id: 'p-experimentales', label: '3. Qué datos experimentales se almacenan' },
  { id: 'p-finalidad', label: '4. Para qué se usan' },
  { id: 'p-consentimiento', label: '5. Consentimiento' },
  { id: 'p-acceso', label: '6. Quién puede acceder y cómo se protegen' },
  { id: 'p-externos', label: '7. Servicios externos que intervienen' },
  { id: 'p-derechos', label: '8. Cómo consultar, rectificar o eliminar tu información' },
  { id: 'p-conservacion', label: '9. Cuánto tiempo se conservan los datos' },
  { id: 'p-cambios', label: '10. Cambios y validación' },
];

export default function PrivacyPolicy() {
  return (
    <div className="landing">
      <SkipLink />
      <Navbar />
      <main className="section legal-page" id="contenido" tabIndex={-1}>
        <div className="container legal-layout">
          <nav className="legal-toc" aria-label="Índice de contenidos">
            <b>Contenido</b>
            <ul>
              {CONTENTS.map(({ id, label }) => (
                <li key={id}>
                  <a href={`#${id}`}>{label}</a>
                </li>
              ))}
            </ul>
          </nav>

          <article className="legal-container">
          <header className="legal-head">
            <h1>Política de Privacidad</h1>
            <p className="legal-meta">
              <span>Versión {POLICY_VERSION}</span>
              <span>Vigente desde el {POLICY_DATE}</span>
            </p>
          </header>

          <ExperimentalNotice />

          <section aria-labelledby="p-alcance">
            <h2 id="p-alcance">1. Qué es GlucoLume y alcance de esta política</h2>
            <p>
              GlucoLume es un prototipo académico de investigación y desarrollo tecnológico, realizado como Trabajo Integrador
              Final de la Licenciatura en Sistemas de Información, para explorar la estimación no invasiva de glucosa con
              sensores ópticos. No es un producto comercial, no es un dispositivo médico certificado, no presta servicios
              clínicos, no realiza diagnósticos ni recomienda tratamientos y no es ni reemplaza una historia clínica.
            </p>
            <p>
              Para el tratamiento de datos personales toma como <strong>referencia</strong> la Ley argentina 25.326 de
              Protección de los Datos Personales. Es una referencia de diseño: GlucoLume no es una institución sanitaria y
              este documento no certifica el cumplimiento de ninguna norma.
            </p>
          </section>

          <section aria-labelledby="p-datos">
            <h2 id="p-datos">2. Qué datos personales recopila</h2>
            <ul>
              <li>
                <strong>Cuenta:</strong> nombre, apellido, nombre de usuario, correo electrónico y tipo de cuenta. La contraseña
                no se guarda: solo un resumen irreversible (hash).
              </li>
              <li>
                <strong>Perfil de medición:</strong> fecha de nacimiento (o edad) y sexo, opcionales (se recomiendan: el modelo experimental los usa para
                estimar, pero no hacen falta para medir). Para pacientes registrados por una institución, el personal autorizado puede cargar nombre, apellido,
                documento (opcional), fecha de nacimiento o edad y sexo.
              </li>
              <li>
                <strong>Acceso con Google (opcional):</strong> identificador de tu cuenta de Google, correo y nombre.
              </li>
              <li>
                <strong>Seguridad y sesiones:</strong> tus sesiones abiertas y un registro de auditoría de acciones relevantes
                (qué se hizo, cuándo y quién). Para proteger las cuentas, cada evento de ese registro guarda también la dirección
                IP y un resumen del navegador y del sistema operativo: solo los consulta la administración de GlucoLume y se
                borran a los 90 días. Al iniciar sesión, esos datos se usan además para el aviso de «nuevo inicio de sesión» que
                te enviamos por correo.
              </li>
              <li>
                <strong>Formulario de contacto:</strong> nombre, correo, asunto y mensaje. Se envían por correo al equipo del
                proyecto y <strong>no se guardan en la base de datos</strong>.
              </li>
              <li>
                <strong>Consentimientos:</strong> qué aceptaste o revocaste, cuándo y con qué versión del texto.
              </li>
            </ul>
          </section>

          <section aria-labelledby="p-experimentales">
            <h2 id="p-experimentales">3. Qué datos experimentales se almacenan</h2>
            <p>
              Cuando medís (o cuando una institución mide a un paciente) se guardan: las muestras de la señal óptica del sensor
              (canales rojo e infrarrojo), la oximetría (SpO₂), la frecuencia cardíaca, la estimación experimental de glucosa si
              el modelo está disponible, el valor de un glucómetro capilar si decidís cargarlo como referencia, la fecha y hora,
              la condición de comida y la hora de la última ingesta, tu edad y sexo al momento de la medición, y datos técnicos
              del dispositivo (sensor, firmware y versión del algoritmo).
            </p>
            <p>
              Pueden existir <strong>datos simulados</strong> (modo DEMO) para probar el sistema: se identifican claramente como
              «DEMO» y no son mediciones de una persona. Los datos experimentales no forman parte de una historia clínica.
            </p>
          </section>

          <section aria-labelledby="p-finalidad">
            <h2 id="p-finalidad">4. Para qué se usan</h2>
            <ul>
              <li>Crear y proteger tu cuenta, verificar tu correo y avisarte de eventos de seguridad.</li>
              <li>Realizar mediciones, mostrarte tu historial y calcular gráficos y estadísticas con tus propios datos.</li>
              <li>Evaluar y mejorar el prototipo con fines académicos y de investigación, en forma experimental.</li>
              <li>
                Compartir información con las personas que vos elegís (grupo) o con la institución que te atiende, según los
                permisos descriptos más abajo.
              </li>
            </ul>
            <p>No se usan para publicidad, no se venden y no se utilizan para tomar decisiones médicas sobre vos.</p>
          </section>

          <section aria-labelledby="p-consentimiento">
            <h2 id="p-consentimiento">5. Consentimiento</h2>
            <ul>
              <li>
                <strong>Al registrarte</strong> (con correo y contraseña, con Google o al activar una cuenta a la que te invitaron)
                confirmás que leíste esta política. No podés registrarte sin hacerlo.
              </li>
              <li>
                <strong>Antes de medir</strong> te pedimos una autorización expresa y separada para almacenar tus mediciones
                experimentales, con su finalidad académica. Podés rechazarla: en ese caso no se recolectan mediciones tuyas.
              </li>
              <li>
                Podés <strong>revocar</strong> esa autorización cuando quieras desde «Mis mediciones». Desde ese momento no se
                inician ni se reciben nuevas mediciones. Lo ya medido no se borra al revocar: para eliminarlo, eliminá tu cuenta
                (sección 8).
              </li>
              <li>Registramos qué aceptaste o revocaste, cuándo y con qué versión de estos textos.</li>
            </ul>
            <p>
              Las mediciones de pacientes de una institución las realiza el personal de esa institución, que es responsable de
              informar al paciente y obtener su consentimiento; la autorización de esta sección no las cubre.
            </p>
          </section>

          <section aria-labelledby="p-acceso">
            <h2 id="p-acceso">6. Quién puede acceder y cómo se protegen</h2>
            <ul>
              <li>
                <strong>Vos</strong>, a los datos de tu cuenta y tus mediciones.
              </li>
              <li>
                <strong>Integrantes de tu grupo</strong>, únicamente lo que vos habilites en «Mi privacidad»: datos básicos del
                perfil, última medición, historial (con sus gráficos y estadísticas), y un aviso de que te mediste (con día y
                hora, nunca el valor). Todo está desactivado por defecto y podés cambiarlo cuando quieras.
              </li>
              <li>
                <strong>Personal de una institución</strong>, solo respecto de los pacientes de esa institución y según su rol.
              </li>
              <li>
                <strong>Administración de la plataforma</strong>, para operar el sistema: gestiona cuentas de plataforma,
                dispositivos y matrices, y consulta registros de auditoría y estadísticas agregadas, no tus mediciones
                individuales.
              </li>
            </ul>
            <p>
              Medidas: contraseñas protegidas con hash, verificación en dos pasos opcional, sesiones con vencimiento, control
              de acceso por roles y permisos en el servidor y registro de auditoría. Como prototipo académico, no se ofrecen las
              garantías de seguridad ni de disponibilidad de un servicio comercial.
            </p>
          </section>

          <section aria-labelledby="p-externos">
            <h2 id="p-externos">7. Servicios externos que intervienen</h2>
            <ul>
              <li>
                <strong>Google (inicio de sesión con Google):</strong> solo si elegís ese método. Google recibe tu pedido de
                autenticación y nos entrega tu identificador, correo y nombre. GlucoLume no recibe tu contraseña de Google.
              </li>
              <li>
                <strong>Proveedor de correo (SMTP):</strong> envía los correos del sistema (verificación, recuperación de
                contraseña, avisos de seguridad y de grupos, resultados que pidas enviar). Recibe tu dirección y el contenido de
                cada mensaje.
              </li>
            </ul>
            <p>
              GlucoLume no usa herramientas de analítica, publicidad ni píxeles de seguimiento, y no comparte tus datos con
              otros terceros. Usa una cookie técnica temporal solo durante el inicio de sesión con Google y almacena tu sesión
              en tu navegador para mantenerte conectado.
            </p>
          </section>

          <section aria-labelledby="p-derechos">
            <h2 id="p-derechos">8. Cómo consultar, rectificar o eliminar tu información</h2>
            <ul>
              <li><strong>Consultar:</strong> tus datos están en «Perfil», «Mis mediciones» y «Seguridad».</li>
              <li><strong>Rectificar:</strong> editá tus datos desde «Perfil».</li>
              <li>
                <strong>Eliminar:</strong> podés eliminar tu cuenta desde «Seguridad». Te pedimos confirmación por correo y tu
                contraseña (y el segundo factor, si lo tenés). No se puede eliminar mientras seas propietario de un grupo o
                de una institución activa, o tengas un vínculo institucional activo: primero hay que transferirlo, cerrarlo o
                salir.
              </li>
              <li>
                <strong>Consultas o pedidos:</strong> escribinos desde el{' '}
                <Link to="/#contacto">formulario de contacto</Link> eligiendo «Privacidad y datos». Si sos paciente de una
                institución, dirigite también a esa institución.
              </li>
            </ul>
            <p>
              La Ley 25.326 prevé que podés reclamar ante la Agencia de Acceso a la Información Pública (AAIP), órgano de
              control en Argentina.
            </p>
          </section>

          <section aria-labelledby="p-conservacion">
            <h2 id="p-conservacion">9. Cuánto tiempo se conservan los datos</h2>
            <ul>
              <li>
                <strong>Cuenta activa:</strong> mientras la mantengas. Una cuenta nueva que no verifica su correo se elimina al
                vencer el plazo de verificación (24 horas).
              </li>
              <li>
                <strong>Al eliminar tu cuenta:</strong> se borran o anonimizan de inmediato tu nombre, apellido, correo, usuario,
                fecha de nacimiento, sexo, contraseña, acceso con Google y verificación en dos pasos. Tus mediciones se conservan
                <em> sin datos que te identifiquen</em> (edad y sexo al momento de medir, valores, fecha y contexto) con fines
                académicos y estadísticos. En esta versión del prototipo ese conjunto desidentificado no tiene un plazo de
                borrado automático.
              </li>
              <li>
                <strong>Pacientes de una institución:</strong> al cerrarse la institución o darse de baja el paciente, sus datos
                personales se conservan hasta 12 meses sin acceso operativo y luego se desidentifican de forma irreversible
                (nombre, apellido, documento, fecha de nacimiento y edad).
              </li>
              <li>
                <strong>Registros de consentimiento y de auditoría:</strong> se conservan como constancia de las acciones
                realizadas; no incluyen contraseñas ni resultados de mediciones. La dirección IP y el navegador asociados a
                cada evento se borran a los 90 días.
              </li>
            </ul>
            <p>
              El plazo de 12 meses es una decisión de diseño de este proyecto académico; no es un plazo impuesto por la Ley
              25.326. Si pedís la eliminación de tu cuenta, se atiende sin esperar ese plazo.
            </p>
          </section>

          <section aria-labelledby="p-cambios">
            <h2 id="p-cambios">10. Cambios y validación</h2>
            <p>
              Si esta política cambia de manera sustancial, se actualiza su versión y se te vuelve a pedir la autorización que
              corresponda. Este documento fue elaborado con fines académicos y no constituye asesoramiento legal.
            </p>
          </section>
          </article>
        </div>
      </main>
      <SiteFooter />
    </div>
  );
}
