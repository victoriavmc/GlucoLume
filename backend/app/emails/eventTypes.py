# EmailEventTypes - Catálogo de correos de GlucoLume
#
# Cada evento define su plantilla (relativa a app/emails), asunto, categoría visible, variables
# requeridas y avisos del footer. Los asuntos son genéricos: nunca incluyen datos de salud.

from dataclasses import dataclass
from enum import StrEnum


class EmailEventType(StrEnum):
    # Cuenta
    CUENTA_CREADA = "CUENTA_CREADA"
    EMAIL_VERIFICACION = "EMAIL_VERIFICACION"
    EMAIL_CAMBIADO = "EMAIL_CAMBIADO"
    ELIMINACION_SOLICITADA = "ELIMINACION_SOLICITADA"
    CUENTA_ELIMINADA = "CUENTA_ELIMINADA"
    # La cuenta institucional quedó sin ninguna institución: comienza el período de gracia de 30 días.
    PERIODO_GRACIA_INICIADO = "PERIODO_GRACIA_INICIADO"
    # Contraseña (nombres de evento, no secretos: falsos positivos de bandit B105)
    RECUPERACION_PASSWORD = "RECUPERACION_PASSWORD"  # nosec B105
    PASSWORD_CAMBIADA = "PASSWORD_CAMBIADA"  # nosec B105
    # Seguridad
    NUEVO_INICIO_SESION = "NUEVO_INICIO_SESION"
    INTENTO_ACCESO_INUSUAL = "INTENTO_ACCESO_INUSUAL"
    # MFA
    MFA_ACTIVADO = "MFA_ACTIVADO"
    MFA_DESACTIVADO = "MFA_DESACTIVADO"
    CODIGO_MFA_EMAIL = "CODIGO_MFA_EMAIL"
    # Código para recuperar el acceso cuando se perdió la aplicación autenticadora
    RECUPERACION_MFA_CODIGO = "RECUPERACION_MFA_CODIGO"
    # Mismo código, pedido desde Seguridad: perdió la aplicación y también los códigos de recuperación
    RECUPERACION_MFA_DESVINCULAR = "RECUPERACION_MFA_DESVINCULAR"
    METODO_MFA_CAMBIADO = "METODO_MFA_CAMBIADO"
    # Google
    GOOGLE_VINCULADO = "GOOGLE_VINCULADO"
    GOOGLE_DESVINCULADO = "GOOGLE_DESVINCULADO"
    # Grupo familiar
    # Confirmación al creador de un grupo familiar.
    GRUPO_CREADO = "GRUPO_CREADO"
    INVITACION_GRUPO = "INVITACION_GRUPO"
    AGREGADO_GRUPO = "AGREGADO_GRUPO"
    ELIMINADO_GRUPO = "ELIMINADO_GRUPO"
    MIEMBRO_ABANDONO_GRUPO = "MIEMBRO_ABANDONO_GRUPO"
    MIEMBRO_AGREGADO = "MIEMBRO_AGREGADO"
    # Un integrante completó una medición y autorizó avisar al grupo (quién y cuándo; nunca el valor).
    MEDICION_MIEMBRO_GRUPO = "MEDICION_MIEMBRO_GRUPO"
    # Novedad para los demás integrantes cuando alguien se suma o abandona el grupo (descripcion no incluye datos de salud).
    NOVEDAD_GRUPO = "NOVEDAD_GRUPO"
    MIEMBRO_ELIMINADO = "MIEMBRO_ELIMINADO"
    ADMIN_GRUPO_ASIGNADO = "ADMIN_GRUPO_ASIGNADO"
    ADMIN_GRUPO_CAMBIADO = "ADMIN_GRUPO_CAMBIADO"
    GRUPO_ELIMINADO = "GRUPO_ELIMINADO"
    # Confirmación a quien eliminó el grupo (los demás integrantes reciben GRUPO_ELIMINADO).
    GRUPO_ELIMINADO_CONFIRMACION = "GRUPO_ELIMINADO_CONFIRMACION"
    # Institución
    # Confirmación al propietario de una institución registrada.
    INSTITUCION_CREADA = "INSTITUCION_CREADA"
    INVITACION_INSTITUCION = "INVITACION_INSTITUCION"
    # Invitación a una persona sin cuenta: activar la cuenta institucional creada para ella.
    INVITACION_INSTITUCION_NUEVA_CUENTA = "INVITACION_INSTITUCION_NUEVA_CUENTA"
    INVITACION_ACEPTADA = "INVITACION_ACEPTADA"
    INVITACION_RECHAZADA = "INVITACION_RECHAZADA"
    AGREGADO_INSTITUCION = "AGREGADO_INSTITUCION"
    ELIMINADO_INSTITUCION = "ELIMINADO_INSTITUCION"
    # Pacientes institucionales: alta, asignación de responsable y baja.
    PACIENTE_REGISTRADO = "PACIENTE_REGISTRADO"
    PACIENTE_ASIGNADO = "PACIENTE_ASIGNADO"
    PACIENTE_REASIGNADO = "PACIENTE_REASIGNADO"
    PACIENTE_BAJA = "PACIENTE_BAJA"
    # A los propietarios: un moderador cambió (o propuso cambiar) el responsable de un paciente.
    ASIGNACION_PACIENTE_GESTION = "ASIGNACION_PACIENTE_GESTION"
    # Transferencia de pacientes entre operadores (TransferenciaPerfil).
    TRANSFERENCIA_SOLICITADA = "TRANSFERENCIA_SOLICITADA"
    TRANSFERENCIA_ACEPTADA = "TRANSFERENCIA_ACEPTADA"
    TRANSFERENCIA_RECHAZADA = "TRANSFERENCIA_RECHAZADA"
    TRANSFERENCIA_CANCELADA = "TRANSFERENCIA_CANCELADA"
    OPERADOR_AGREGADO = "OPERADOR_AGREGADO"
    OPERADOR_ELIMINADO = "OPERADOR_ELIMINADO"
    # Un operador con pacientes a cargo fue desvinculado: hay pacientes pendientes de reasignación (a moderadores / propietario).
    PACIENTES_PENDIENTES_REASIGNACION = "PACIENTES_PENDIENTES_REASIGNACION"
    ROL_INSTITUCIONAL_CAMBIADO = "ROL_INSTITUCIONAL_CAMBIADO"
    INSTITUCION_ELIMINADA = "INSTITUCION_ELIMINADA"
    INSTITUCION_ELIMINADA_ADMINISTRATIVAMENTE = "INSTITUCION_ELIMINADA_ADMINISTRATIVAMENTE"
    # Mediciones
    MEDICION_REGISTRADA = "MEDICION_REGISTRADA"
    RESULTADO_MEDICION = "RESULTADO_MEDICION"
    CONFIRMAR_CORREO_RESULTADOS = "CONFIRMAR_CORREO_RESULTADOS"
    MEDICION_FUERA_UMBRAL = "MEDICION_FUERA_UMBRAL"
    ERROR_MEDICION = "ERROR_MEDICION"
    # Recordatorio del horario de medición que eligió la cuenta (services/userNotifications.py); no incluye datos de medición.
    RECORDATORIO_MEDICION = "RECORDATORIO_MEDICION"
    # Privacidad
    INFORMACION_RETENCION_DATOS = "INFORMACION_RETENCION_DATOS"
    # Contacto (formulario público de la landing; lo recibe la casilla CONTACT_EMAIL)
    CONTACTO_RECIBIDO = "CONTACTO_RECIBIDO"
    # Confirmación automática a quien envió la consulta
    CONTACTO_CONFIRMACION = "CONTACTO_CONFIRMACION"
    # Administración de la plataforma
    INVITACION_PLATAFORMA = "INVITACION_PLATAFORMA"
    # Confirmación a quien invitó: la invitación ya salió hacia el correo del moderador.
    INVITACION_PLATAFORMA_ENVIADA = "INVITACION_PLATAFORMA_ENVIADA"
    ACCESO_PLATAFORMA_REVOCADO = "ACCESO_PLATAFORMA_REVOCADO"
    ALERTA_SEGURIDAD_PLATAFORMA = "ALERTA_SEGURIDAD_PLATAFORMA"
    TRANSFERENCIA_ADMIN_SOLICITADA = "TRANSFERENCIA_ADMIN_SOLICITADA"
    TRANSFERENCIA_ADMIN_RESPONDIDA = "TRANSFERENCIA_ADMIN_RESPONDIDA"
    ADMINISTRACION_ASIGNADA = "ADMINISTRACION_ASIGNADA"
    INSTITUCION_PAUSADA = "INSTITUCION_PAUSADA"
    INSTITUCION_REACTIVADA = "INSTITUCION_REACTIVADA"


CATEGORIA_CUENTA = "Cuenta"
CATEGORIA_SEGURIDAD = "Seguridad"
CATEGORIA_MFA = "Verificación en dos pasos"
CATEGORIA_GOOGLE = "Cuenta de Google"
CATEGORIA_GRUPO = "Grupo familiar"
CATEGORIA_INSTITUCION = "Institución"
CATEGORIA_MEDICIONES = "Mediciones"
CATEGORIA_PRIVACIDAD = "Privacidad"
CATEGORIA_CONTACTO = "Contacto"
CATEGORIA_PLATAFORMA = "Administración de GlucoLume"


@dataclass(frozen=True)
class EmailEventSpec:
    template: str
    subject: str
    category: str
    # Variables que el llamador debe enviar (además de las comunes que agrega el servicio).
    requiredContext: tuple[str, ...] = ()
    # Variables que deben ser URLs de acción (correos con acción crítica).
    actionUrls: tuple[str, ...] = ()
    # Footer: "Si no reconocés esta actividad, revisá la seguridad de tu cuenta."
    securityNotice: bool = False
    # Footer: aclaración de prototipo experimental (mediciones).
    clinicalDisclaimer: bool = False
    highPriority: bool = False


# Datos de una medición que solo se muestran con autorización explícita (ver services/email.py).
MEASUREMENT_DETAIL_KEYS = (
    "valorGlucosa",
    "unidad",
    "spo2",
    "frecuenciaCardiaca",
    "condicionComida",
    "fechaUltimaComida",
    "contexto",
    "modo",
    "esDemo",
    "indiceOptico",
)

_E = EmailEventType

EMAIL_EVENTS: dict[EmailEventType, EmailEventSpec] = {
    # --- Cuenta ---------------------------------------------------------------------------
    _E.CUENTA_CREADA: EmailEventSpec(
        "cuenta/cuentaCreada.html", "Bienvenido/a a GlucoLume", CATEGORIA_CUENTA,
        ("fechaCreacion", "urlIngreso"), ("urlIngreso",),
    ),
    _E.EMAIL_VERIFICACION: EmailEventSpec(
        "cuenta/emailVerificacion.html", "Verificá tu correo electrónico", CATEGORIA_CUENTA,
        ("urlVerificacion", "fechaExpiracion", "plazoHoras"), ("urlVerificacion",),
    ),
    _E.EMAIL_CAMBIADO: EmailEventSpec(
        "cuenta/emailCambiado.html", "Tu correo electrónico fue modificado", CATEGORIA_CUENTA,
        ("fechaEvento", "esCorreoAnterior", "urlAccion"), ("urlAccion",), securityNotice=True, highPriority=True,
    ),
    _E.ELIMINACION_SOLICITADA: EmailEventSpec(
        "cuenta/eliminacionSolicitada.html", "Solicitud de eliminación de cuenta", CATEGORIA_CUENTA,
        ("fechaEvento", "fechaExpiracion", "urlConfirmacion", "urlProteccion"),
        ("urlConfirmacion", "urlProteccion"), securityNotice=True, highPriority=True,
    ),
    _E.CUENTA_ELIMINADA: EmailEventSpec(
        "cuenta/cuentaEliminada.html", "Tu cuenta de GlucoLume fue eliminada", CATEGORIA_CUENTA,
        ("fechaEvento", "datosEliminados"),
    ),
    _E.PERIODO_GRACIA_INICIADO: EmailEventSpec(
        "cuenta/periodoGraciaIniciado.html", "Tu cuenta no tiene instituciones: tenés 30 días", CATEGORIA_CUENTA,
        ("fechaEvento", "fechaVencimiento", "diasGracia", "urlInvitaciones"), ("urlInvitaciones",),
    ),
    # --- Contraseña -----------------------------------------------------------------------
    _E.RECUPERACION_PASSWORD: EmailEventSpec(
        "seguridad/recuperacionPassword.html", "Restablecé tu contraseña", CATEGORIA_SEGURIDAD,
        ("urlRestablecer", "fechaExpiracion"), ("urlRestablecer",),
    ),
    _E.PASSWORD_CAMBIADA: EmailEventSpec(
        "seguridad/passwordCambiada.html", "Cambiaste tu contraseña con éxito", CATEGORIA_SEGURIDAD,
        ("fechaEvento", "urlSeguridad"), ("urlSeguridad",), securityNotice=True, highPriority=True,
    ),
    # --- Seguridad ------------------------------------------------------------------------
    _E.NUEVO_INICIO_SESION: EmailEventSpec(
        "seguridad/nuevoInicioSesion.html", "Nuevo inicio de sesión en GlucoLume", CATEGORIA_SEGURIDAD,
        ("fechaEvento", "urlSeguridad", "urlDesuscribir"), ("urlSeguridad", "urlDesuscribir"), securityNotice=True,
    ),
    _E.INTENTO_ACCESO_INUSUAL: EmailEventSpec(
        "seguridad/intentoAccesoInusual.html", "Revisá una actividad de seguridad", CATEGORIA_SEGURIDAD,
        ("fechaEvento", "urlSeguridad"), ("urlSeguridad",), securityNotice=True, highPriority=True,
    ),
    # --- MFA ------------------------------------------------------------------------------
    _E.MFA_ACTIVADO: EmailEventSpec(
        "mfa/mfaActivado.html", "La verificación en dos pasos fue activada", CATEGORIA_MFA,
        ("fechaEvento", "metodo", "urlSeguridad"), ("urlSeguridad",), securityNotice=True,
    ),
    _E.MFA_DESACTIVADO: EmailEventSpec(
        "mfa/mfaDesactivado.html", "La verificación en dos pasos fue desactivada", CATEGORIA_MFA,
        ("fechaEvento", "urlSeguridad"), ("urlSeguridad",), securityNotice=True, highPriority=True,
    ),
    _E.RECUPERACION_MFA_CODIGO: EmailEventSpec(
        "mfa/recuperacionMfa.html", "Código para recuperar tu acceso - GlucoLume", CATEGORIA_MFA,
        ("codigoSeguridad", "minutosValidez", "urlSeguridad"), ("urlSeguridad",), securityNotice=True, highPriority=True,
    ),
    _E.RECUPERACION_MFA_DESVINCULAR: EmailEventSpec(
        "mfa/recuperacionMfa.html", "Código para recuperar la verificación en dos pasos - GlucoLume", CATEGORIA_MFA,
        ("codigoSeguridad", "minutosValidez", "urlSeguridad"), ("urlSeguridad",), securityNotice=True, highPriority=True,
    ),
    _E.CODIGO_MFA_EMAIL: EmailEventSpec(
        "mfa/codigoMfaEmail.html", "Tu código de verificación de GlucoLume", CATEGORIA_MFA,
        ("codigoMfa", "minutosValidez"), securityNotice=True,
    ),
    _E.METODO_MFA_CAMBIADO: EmailEventSpec(
        "mfa/metodoMfaCambiado.html", "Se modificó tu método de verificación", CATEGORIA_MFA,
        ("metodoAnterior", "metodoNuevo", "fechaEvento", "urlSeguridad"), ("urlSeguridad",),
        securityNotice=True, highPriority=True,
    ),
    # --- Google ---------------------------------------------------------------------------
    _E.GOOGLE_VINCULADO: EmailEventSpec(
        "google/googleVinculado.html", "Tu cuenta de Google fue vinculada", CATEGORIA_GOOGLE,
        ("fechaEvento", "urlSeguridad"), ("urlSeguridad",), securityNotice=True,
    ),
    _E.GOOGLE_DESVINCULADO: EmailEventSpec(
        "google/googleDesvinculado.html", "Tu cuenta de Google fue desvinculada", CATEGORIA_GOOGLE,
        ("fechaEvento", "urlSeguridad", "tieneContrasenaLocal"), ("urlSeguridad",), securityNotice=True,
    ),
    # --- Grupo familiar -------------------------------------------------------------------
    _E.GRUPO_CREADO: EmailEventSpec(
        "grupos/grupoCreado.html", "GlucoLume — Tu grupo fue creado correctamente", CATEGORIA_GRUPO,
        ("nombreGrupo", "nombreCreador", "rol", "fechaEvento", "urlGrupo"), ("urlGrupo",),
    ),
    _E.INVITACION_GRUPO: EmailEventSpec(
        "grupos/invitacionGrupo.html", "Te invitaron a un grupo de GlucoLume", CATEGORIA_GRUPO,
        ("nombreGrupo", "nombreInvitante", "fechaEvento", "fechaExpiracion", "urlAceptar", "urlRechazar"),
        ("urlAceptar", "urlRechazar"),
    ),
    _E.AGREGADO_GRUPO: EmailEventSpec(
        "grupos/agregadoGrupo.html", "Ahora formás parte de un grupo", CATEGORIA_GRUPO,
        ("nombreGrupo", "fechaEvento"),
    ),
    _E.ELIMINADO_GRUPO: EmailEventSpec(
        "grupos/eliminadoGrupo.html", "Ya no pertenecés al grupo", CATEGORIA_GRUPO, ("nombreGrupo", "fechaEvento"),
    ),
    _E.MIEMBRO_ABANDONO_GRUPO: EmailEventSpec(
        "grupos/miembroAbandonoGrupo.html", "Un integrante abandonó el grupo", CATEGORIA_GRUPO,
        ("nombreIntegrante", "nombreGrupo", "fechaEvento"),
    ),
    _E.MEDICION_MIEMBRO_GRUPO: EmailEventSpec(
        "grupos/medicionMiembro.html", "Un integrante de tu grupo se midió", CATEGORIA_GRUPO,
        ("nombreIntegrante", "nombreGrupo", "fechaMedicion", "urlGrupo"), ("urlGrupo",),
    ),
    _E.NOVEDAD_GRUPO: EmailEventSpec(
        "grupos/novedadGrupo.html", "Hubo novedades en tu grupo", CATEGORIA_GRUPO,
        ("descripcion", "nombreGrupo", "fechaEvento", "urlGrupo"), ("urlGrupo",),
    ),
    _E.MIEMBRO_AGREGADO: EmailEventSpec(
        "grupos/miembroAgregado.html", "Se agregó un integrante al grupo", CATEGORIA_GRUPO,
        ("nombreIntegrante", "nombreGrupo", "fechaEvento"),
    ),
    _E.MIEMBRO_ELIMINADO: EmailEventSpec(
        "grupos/miembroEliminado.html", "Se eliminó un integrante del grupo", CATEGORIA_GRUPO,
        ("nombreIntegrante", "nombreGrupo", "fechaEvento"),
    ),
    _E.ADMIN_GRUPO_ASIGNADO: EmailEventSpec(
        "grupos/adminGrupoAsignado.html", "Ahora administrás el grupo", CATEGORIA_GRUPO,
        ("nombreGrupo", "fechaEvento"),
    ),
    _E.ADMIN_GRUPO_CAMBIADO: EmailEventSpec(
        "grupos/adminGrupoCambiado.html", "Cambió el administrador del grupo", CATEGORIA_GRUPO,
        ("nombreGrupo", "nombreNuevoAdministrador", "fechaEvento"),
    ),
    _E.GRUPO_ELIMINADO: EmailEventSpec(
        "grupos/grupoEliminado.html", "El grupo fue eliminado", CATEGORIA_GRUPO, ("nombreGrupo", "fechaEvento"),
    ),
    _E.GRUPO_ELIMINADO_CONFIRMACION: EmailEventSpec(
        "grupos/grupoEliminadoConfirmacion.html", "Eliminaste el grupo con éxito", CATEGORIA_GRUPO,
        ("nombreGrupo", "cantidadIntegrantes", "fechaEvento"),
    ),
    # --- Institución ----------------------------------------------------------------------
    _E.INSTITUCION_CREADA: EmailEventSpec(
        "instituciones/institucionCreada.html", "GlucoLume — Institución registrada correctamente",
        CATEGORIA_INSTITUCION, ("nombreInstitucion", "tipoInstitucion", "cuit", "rol", "fechaEvento", "urlPanel"),
        ("urlPanel",),
    ),
    _E.INVITACION_INSTITUCION: EmailEventSpec(
        "instituciones/invitacionInstitucion.html", "Una institución te invitó a GlucoLume", CATEGORIA_INSTITUCION,
        ("nombreInstitucion", "rol", "fechaExpiracion", "urlAceptar", "urlRechazar"), ("urlAceptar", "urlRechazar"),
    ),
    _E.INVITACION_INSTITUCION_NUEVA_CUENTA: EmailEventSpec(
        "instituciones/invitacionNuevaCuenta.html", "Activá tu cuenta para sumarte a una institución",
        CATEGORIA_INSTITUCION, ("nombreInstitucion", "rol", "fechaExpiracion", "urlActivar"), ("urlActivar",),
    ),
    _E.INVITACION_ACEPTADA: EmailEventSpec(
        "instituciones/invitacionAceptada.html", "Tu invitación institucional fue aceptada", CATEGORIA_INSTITUCION,
        ("nombreInvitado", "nombreInstitucion", "rol", "fechaEvento"),
    ),
    _E.PACIENTE_REGISTRADO: EmailEventSpec(
        "instituciones/pacienteRegistrado.html", "Registraste un paciente", CATEGORIA_INSTITUCION,
        ("nombreInstitucion", "identificadorPseudonimo", "nombreOperador", "fechaEvento", "urlPaciente"),
        ("urlPaciente",),
    ),
    _E.PACIENTE_ASIGNADO: EmailEventSpec(
        "instituciones/pacienteAsignado.html", "Tenés un paciente nuevo a tu cargo", CATEGORIA_INSTITUCION,
        ("nombreInstitucion", "identificadorPseudonimo", "nombreOperador", "fechaEvento", "urlPaciente"),
        ("urlPaciente",),
    ),
    _E.PACIENTE_REASIGNADO: EmailEventSpec(
        "instituciones/pacienteReasignado.html", "Un paciente pasó a otro operador", CATEGORIA_INSTITUCION,
        ("nombreInstitucion", "identificadorPseudonimo", "nombreOperador", "fechaEvento", "urlPaciente"),
        ("urlPaciente",),
    ),
    _E.ASIGNACION_PACIENTE_GESTION: EmailEventSpec(
        "instituciones/asignacionPacienteGestion.html", "Un moderador cambió el responsable de un paciente", CATEGORIA_INSTITUCION,
        ("nombreInstitucion", "identificadorPseudonimo", "nombreOperador", "nombreGestor", "propuesta", "invitadoPorGestor",
         "fechaEvento", "urlPaciente"),
        ("urlPaciente",),
    ),
    _E.PACIENTE_BAJA: EmailEventSpec(
        "instituciones/pacienteBaja.html", "Un paciente a tu cargo fue dado de baja", CATEGORIA_INSTITUCION,
        ("nombreInstitucion", "identificadorPseudonimo", "nombreOperador", "fechaEvento", "urlPaciente"),
        ("urlPaciente",),
    ),
    _E.TRANSFERENCIA_SOLICITADA: EmailEventSpec(
        "instituciones/transferenciaSolicitada.html", "Tenés una transferencia de paciente pendiente", CATEGORIA_INSTITUCION,
        ("nombreInstitucion", "identificadorPseudonimo", "nombreOperador", "fechaEvento", "urlTransferencias"),
        ("urlTransferencias",),
    ),
    _E.TRANSFERENCIA_ACEPTADA: EmailEventSpec(
        "instituciones/transferenciaAceptada.html", "Aceptaron la transferencia de tu paciente", CATEGORIA_INSTITUCION,
        ("nombreInstitucion", "identificadorPseudonimo", "nombreOperador", "fechaEvento", "urlTransferencias"),
        ("urlTransferencias",),
    ),
    _E.TRANSFERENCIA_RECHAZADA: EmailEventSpec(
        "instituciones/transferenciaRechazada.html", "Rechazaron la transferencia de tu paciente", CATEGORIA_INSTITUCION,
        ("nombreInstitucion", "identificadorPseudonimo", "nombreOperador", "fechaEvento", "urlTransferencias"),
        ("urlTransferencias",),
    ),
    _E.TRANSFERENCIA_CANCELADA: EmailEventSpec(
        "instituciones/transferenciaCancelada.html", "Se canceló una transferencia de paciente", CATEGORIA_INSTITUCION,
        ("nombreInstitucion", "identificadorPseudonimo", "nombreOperador", "fechaEvento", "urlTransferencias"),
        ("urlTransferencias",),
    ),
    _E.INVITACION_RECHAZADA: EmailEventSpec(
        "instituciones/invitacionRechazada.html", "Tu invitación institucional fue rechazada", CATEGORIA_INSTITUCION,
        ("nombreInvitado", "nombreInstitucion", "rol", "fechaEvento"),
    ),
    _E.AGREGADO_INSTITUCION: EmailEventSpec(
        "instituciones/agregadoInstitucion.html", "Tu cuenta fue vinculada a una institución", CATEGORIA_INSTITUCION,
        ("nombreInstitucion", "rol", "fechaEvento"),
    ),
    _E.ELIMINADO_INSTITUCION: EmailEventSpec(
        "instituciones/eliminadoInstitucion.html", "Ya no pertenecés a la institución", CATEGORIA_INSTITUCION,
        ("nombreInstitucion", "fechaEvento"),
    ),
    _E.OPERADOR_AGREGADO: EmailEventSpec(
        "instituciones/operadorAgregado.html", "Se agregó un nuevo operador", CATEGORIA_INSTITUCION,
        ("nombreOperador", "nombreInstitucion", "fechaEvento"),
    ),
    _E.OPERADOR_ELIMINADO: EmailEventSpec(
        "instituciones/operadorEliminado.html", "Se eliminó un operador", CATEGORIA_INSTITUCION,
        ("nombreOperador", "nombreInstitucion", "fechaEvento"),
    ),
    _E.PACIENTES_PENDIENTES_REASIGNACION: EmailEventSpec(
        "instituciones/pacientesPendientesReasignacion.html", "Hay pacientes pendientes de reasignación", CATEGORIA_INSTITUCION,
        ("nombreOperador", "nombreInstitucion", "cantidad", "urlGestion", "fechaEvento"), ("urlGestion",),
    ),
    _E.ROL_INSTITUCIONAL_CAMBIADO: EmailEventSpec(
        "instituciones/rolInstitucionalCambiado.html", "Cambió tu rol en la institución", CATEGORIA_INSTITUCION,
        ("nombreInstitucion", "rolAnterior", "rolNuevo", "fechaEvento"),
    ),
    _E.INSTITUCION_ELIMINADA: EmailEventSpec(
        "instituciones/institucionEliminada.html", "La institución fue eliminada", CATEGORIA_INSTITUCION,
        ("nombreInstitucion", "fechaEvento"),
    ),
    _E.INSTITUCION_ELIMINADA_ADMINISTRATIVAMENTE: EmailEventSpec(
        "instituciones/institucionEliminadaAdministrativamente.html", "La institución fue cerrada por la administración de GlucoLume",
        CATEGORIA_INSTITUCION, ("nombreInstitucion", "fechaEvento"), securityNotice=True, highPriority=True,
    ),
    # --- Mediciones -----------------------------------------------------------------------
    _E.MEDICION_REGISTRADA: EmailEventSpec(
        "mediciones/medicionRegistrada.html", "Nueva medición registrada", CATEGORIA_MEDICIONES,
        ("fechaMedicion", "estadoRegistro", "urlMedicion"), ("urlMedicion",), clinicalDisclaimer=True,
    ),
    _E.RESULTADO_MEDICION: EmailEventSpec(
        "mediciones/resultadoMedicion.html", "Tu medición está disponible", CATEGORIA_MEDICIONES,
        ("fechaMedicion",), ("urlMedicion",),  # urlMedicion opcional: un paciente sin cuenta recibe el resultado sin enlace clinicalDisclaimer=True,
    ),
    _E.CONFIRMAR_CORREO_RESULTADOS: EmailEventSpec(
        "mediciones/confirmarCorreoResultados.html", "Confirmá tu correo para recibir tus resultados", CATEGORIA_MEDICIONES,
        ("institucion", "horas", "urlConfirmacion"), ("urlConfirmacion",), clinicalDisclaimer=True,
    ),
    _E.MEDICION_FUERA_UMBRAL: EmailEventSpec(
        "mediciones/medicionFueraUmbral.html", "Revisá una medición registrada", CATEGORIA_MEDICIONES,
        ("fechaMedicion", "urlMedicion"), ("urlMedicion",), clinicalDisclaimer=True,
    ),
    _E.ERROR_MEDICION: EmailEventSpec(
        "mediciones/errorMedicion.html", "No se pudo completar una medición", CATEGORIA_MEDICIONES,
        ("fechaEvento",), clinicalDisclaimer=True,
    ),
    _E.RECORDATORIO_MEDICION: EmailEventSpec(
        "mediciones/recordatorioMedicion.html", "Es hora de medirte en GlucoLume", CATEGORIA_CUENTA,
        ("urlMediciones",), ("urlMediciones",),
    ),
    # --- Privacidad -----------------------------------------------------------------------
    _E.INFORMACION_RETENCION_DATOS: EmailEventSpec(
        "privacidad/informacionRetencionDatos.html", "Información sobre tus datos en GlucoLume", CATEGORIA_PRIVACIDAD,
        ("fechaEvento",),
    ),
    # --- Contacto -------------------------------------------------------------------------
    _E.CONTACTO_RECIBIDO: EmailEventSpec(
        "contacto/contactoRecibido.html", "Nueva consulta desde GlucoLume", CATEGORIA_CONTACTO,
        ("fechaEvento", "nombreRemitente", "correoRemitente", "tipoConsulta", "asuntoConsulta", "mensaje"),
    ),
    _E.CONTACTO_CONFIRMACION: EmailEventSpec(
        "contacto/contactoConfirmacion.html", "Recibimos tu consulta - GlucoLume", CATEGORIA_CONTACTO,
        ("nombre", "tipoConsulta", "asuntoConsulta"),
    ),
    # --- Administración de la plataforma ----------------------------------------------------
    _E.INVITACION_PLATAFORMA: EmailEventSpec(
        "plataforma/invitacionPlataforma.html", "Te invitaron a administrar GlucoLume", CATEGORIA_PLATAFORMA,
        ("rolPlataforma", "fechaExpiracion", "urlActivar"), ("urlActivar",), securityNotice=True, highPriority=True,
    ),
    _E.INVITACION_PLATAFORMA_ENVIADA: EmailEventSpec(
        "plataforma/invitacionPlataformaEnviada.html", "Enviaste una invitación para moderar GlucoLume", CATEGORIA_PLATAFORMA,
        ("nombreInvitado", "correoInvitado", "rolPlataforma", "fechaExpiracion"), securityNotice=True,
    ),
    _E.ACCESO_PLATAFORMA_REVOCADO: EmailEventSpec(
        "plataforma/accesoRevocado.html", "Tu acceso a la administración de GlucoLume fue revocado", CATEGORIA_PLATAFORMA,
        ("fechaEvento",), securityNotice=True, highPriority=True,
    ),
    _E.ALERTA_SEGURIDAD_PLATAFORMA: EmailEventSpec(
        "plataforma/alertaSeguridad.html", "Actividad sospechosa en GlucoLume", CATEGORIA_PLATAFORMA,
        ("descripcion", "patron", "cantidad", "ventanaMinutos", "fechaEvento", "urlAuditoria"), ("urlAuditoria",),
        securityNotice=True, highPriority=True,
    ),
    _E.TRANSFERENCIA_ADMIN_SOLICITADA: EmailEventSpec(
        "plataforma/transferenciaSolicitada.html", "Te ofrecen la administración de GlucoLume", CATEGORIA_PLATAFORMA,
        ("nombreAdministrador", "fechaEvento", "urlTransferencia"), ("urlTransferencia",), securityNotice=True,
        highPriority=True,
    ),
    _E.TRANSFERENCIA_ADMIN_RESPONDIDA: EmailEventSpec(
        "plataforma/transferenciaRespondida.html", "Respuesta a la transferencia de administración", CATEGORIA_PLATAFORMA,
        ("aceptada", "nombreDestinatario", "fechaEvento"), securityNotice=True, highPriority=True,
    ),
    _E.INSTITUCION_PAUSADA: EmailEventSpec(
        "instituciones/institucionPausada.html", "Tu institución fue pausada en GlucoLume", CATEGORIA_INSTITUCION,
        ("nombreInstitucion", "motivo", "fechaEvento"), securityNotice=True, highPriority=True,
    ),
    _E.INSTITUCION_REACTIVADA: EmailEventSpec(
        "instituciones/institucionReactivada.html", "Tu institución fue reactivada en GlucoLume", CATEGORIA_INSTITUCION,
        ("nombreInstitucion", "fechaEvento"), securityNotice=True,
    ),
    _E.ADMINISTRACION_ASIGNADA: EmailEventSpec(
        "plataforma/administracionAsignada.html", "Ahora sos el administrador de GlucoLume", CATEGORIA_PLATAFORMA,
        ("fechaEvento", "urlAcceso"), ("urlAcceso",), securityNotice=True, highPriority=True,
    ),
}

MEASUREMENT_EVENTS = frozenset(
    event for event, spec in EMAIL_EVENTS.items() if spec.category == CATEGORIA_MEDICIONES
)
