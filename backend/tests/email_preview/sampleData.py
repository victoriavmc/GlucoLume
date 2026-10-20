# SampleData - Datos ficticios para previsualizar y probar cada correo
#
# Solo para pruebas y previsualización: ningún dato corresponde a personas reales.

from datetime import timedelta

from app.emails.eventTypes import EmailEventType as E
from app.services.email import frontendUrl
from app.utils.timeZone import nowForDb

SAMPLE_RECIPIENT = "persona.ejemplo@example.com"


def sampleContexts() -> dict[E, dict]:
    now = nowForDb()
    later = now + timedelta(hours=24)
    security = frontendUrl("seguridad")
    login = frontendUrl("ingreso")
    medicion = frontendUrl("/mediciones/ejemplo")
    base = {"nombre": "Ana"}
    detalle = {
        "valorGlucosa": "112.40",
        "unidad": "mg/dL",
        "spo2": "97.50",
        "frecuenciaCardiaca": 72,
        "condicionComida": "Ayuno",
        "fechaUltimaComida": now - timedelta(hours=9),
    }
    return {
        E.CONTACTO_RECIBIDO: {
            "fechaEvento": now, "nombreRemitente": "Ana Pérez", "correoRemitente": "ana.perez@example.com",
            "tipoConsulta": "Instituciones", "asuntoConsulta": "Uso en un consultorio",
            "mensaje": "Hola, queremos saber cómo usar GlucoLume en nuestro consultorio.",
        },
        E.CONTACTO_CONFIRMACION: {
            "nombre": "Ana", "tipoConsulta": "Instituciones", "asuntoConsulta": "Uso en un consultorio",
        },
        E.RECUPERACION_MFA_CODIGO: {**base, "codigoSeguridad": "482913", "minutosValidez": 10, "urlSeguridad": security},
        E.RECUPERACION_MFA_DESVINCULAR: {
            **base, "codigoSeguridad": "482913", "minutosValidez": 10, "urlSeguridad": security, "desvincular": True,
        },
        E.CUENTA_CREADA: {**base, "apellido": "Pérez", "fechaCreacion": now, "urlIngreso": login},
        E.EMAIL_VERIFICACION: {
            **base, "urlVerificacion": frontendUrl("/verificar-correo?token=TOKEN_DE_EJEMPLO"),
            "fechaExpiracion": later, "plazoHoras": 24,
        },
        E.EMAIL_CAMBIADO: {
            **base, "fechaEvento": now, "esCorreoAnterior": True,
            "correoNuevoEnmascarado": "an*****@example.org", "urlAccion": security,
        },
        E.ELIMINACION_SOLICITADA: {
            **base, "fechaEvento": now, "fechaExpiracion": later,
            "urlConfirmacion": frontendUrl("/cuenta/eliminar/confirmar?token=TOKEN_DE_EJEMPLO"),
            "urlProteccion": security,
        },
        E.CUENTA_ELIMINADA: {
            **base, "fechaEvento": now,
            "datosEliminados": ["Nombre y apellido", "Correo electrónico", "Nombre de usuario",
                                "Fecha de nacimiento", "Sexo"],
            "datosConservados": ["Edad al momento de la medición", "Sexo, cuando corresponda",
                                 "Valores y contexto de la medición"],
        },
        E.RECUPERACION_PASSWORD: {
            **base, "urlRestablecer": frontendUrl("/restablecer-contrasena?token=TOKEN_DE_EJEMPLO"),
            "fechaExpiracion": now + timedelta(hours=1),
        },
        E.PASSWORD_CAMBIADA: {**base, "fechaEvento": now, "urlSeguridad": security},
        E.NUEVO_INICIO_SESION: {
            **base, "fechaEvento": now, "metodo": "Correo o usuario y contraseña", "navegador": "Chrome",
            "sistemaOperativo": "Windows", "dispositivo": "Computadora",
            "urlSeguridad": security,
            "urlDesuscribir": frontendUrl("/cuenta/notificaciones/desuscribir?token=TOKEN_DE_EJEMPLO"),
        },
        E.INTENTO_ACCESO_INUSUAL: {
            **base, "fechaEvento": now, "cantidadIntentos": 3, "bloqueadoHasta": now + timedelta(minutes=15),
            "urlSeguridad": security,
        },
        E.MFA_ACTIVADO: {**base, "fechaEvento": now, "metodo": "TOTP", "urlSeguridad": security},
        E.MFA_DESACTIVADO: {**base, "fechaEvento": now, "urlSeguridad": security},
        E.CODIGO_MFA_EMAIL: {**base, "codigoMfa": "000000", "minutosValidez": 5},
        E.METODO_MFA_CAMBIADO: {
            **base, "metodoAnterior": "EMAIL", "metodoNuevo": "TOTP", "fechaEvento": now, "urlSeguridad": security,
        },
        E.GOOGLE_VINCULADO: {
            **base, "fechaEvento": now, "correoGoogle": "persona.ejemplo@gmail.com", "urlSeguridad": security,
        },
        E.GOOGLE_DESVINCULADO: {**base, "fechaEvento": now, "urlSeguridad": security, "tieneContrasenaLocal": False},
        E.GRUPO_CREADO: {
            **base, "nombreGrupo": "Grupo de ejemplo", "nombreCreador": "Laura Díaz", "rol": "PROPIETARIO",
            "fechaEvento": now, "urlGrupo": frontendUrl("/app/grupo/ID_DE_EJEMPLO"),
        },
        E.INVITACION_GRUPO: {
            **base, "nombreGrupo": "Grupo de ejemplo", "nombreInvitante": "Carlos Gómez", "fechaEvento": now,
            "fechaExpiracion": now + timedelta(days=7),
            "urlAceptar": frontendUrl("/grupos/invitacion/aceptar?token=TOKEN_DE_EJEMPLO"),
            "urlRechazar": frontendUrl("/grupos/invitacion/rechazar?token=TOKEN_DE_EJEMPLO"),
        },
        E.AGREGADO_GRUPO: {**base, "nombreGrupo": "Grupo de ejemplo", "fechaEvento": now, "rol": "MIEMBRO"},
        E.ELIMINADO_GRUPO: {**base, "nombreGrupo": "Grupo de ejemplo", "fechaEvento": now},
        E.MIEMBRO_ABANDONO_GRUPO: {
            **base, "nombreIntegrante": "Laura Díaz", "nombreGrupo": "Grupo de ejemplo", "fechaEvento": now,
        },
        E.MEDICION_MIEMBRO_GRUPO: {
            **base, "nombreIntegrante": "Juan Pérez", "nombreGrupo": "Grupo de ejemplo", "fechaMedicion": now,
            "urlGrupo": frontendUrl("/app/grupo/ID_DE_EJEMPLO"),
        },
        E.GRUPO_ELIMINADO_CONFIRMACION: {
            **base, "nombreGrupo": "Grupo de ejemplo", "cantidadIntegrantes": 3, "fechaEvento": now,
        },
        E.MIEMBRO_AGREGADO: {
            **base, "nombreIntegrante": "Laura Díaz", "nombreGrupo": "Grupo de ejemplo", "fechaEvento": now,
        },
        E.MIEMBRO_ELIMINADO: {
            **base, "nombreIntegrante": "Laura Díaz", "nombreGrupo": "Grupo de ejemplo", "fechaEvento": now,
        },
        E.ADMIN_GRUPO_ASIGNADO: {**base, "nombreGrupo": "Grupo de ejemplo", "fechaEvento": now},
        E.ADMIN_GRUPO_CAMBIADO: {
            **base, "nombreGrupo": "Grupo de ejemplo", "nombreNuevoAdministrador": "Carlos Gómez", "fechaEvento": now,
        },
        E.GRUPO_ELIMINADO: {**base, "nombreGrupo": "Grupo de ejemplo", "fechaEvento": now},
        E.INSTITUCION_CREADA: {
            **base, "nombreInstitucion": "Institución de ejemplo", "tipoInstitucion": "Clínica",
            "cuit": "30-71234567-1", "rol": "PROPIETARIO", "fechaEvento": now,
            "urlPanel": frontendUrl("/app/instituciones/ID_DE_EJEMPLO"),
        },
        E.INVITACION_INSTITUCION: {
            **base, "nombreInstitucion": "Institución de ejemplo", "rol": "OPERADOR", "nombreInvitante": "Carlos Gómez",
            "fechaExpiracion": now + timedelta(days=7),
            "urlAceptar": frontendUrl("/instituciones/invitacion/aceptar?token=TOKEN_DE_EJEMPLO"),
            "urlRechazar": frontendUrl("/instituciones/invitacion/rechazar?token=TOKEN_DE_EJEMPLO"),
        },
        E.INVITACION_INSTITUCION_NUEVA_CUENTA: {
            **base, "nombreInstitucion": "Institución de ejemplo", "rol": "MODERADOR", "nombreInvitante": "Carlos Gómez",
            "fechaExpiracion": now + timedelta(days=7),
            "urlActivar": frontendUrl("/activar-cuenta?token=TOKEN_DE_EJEMPLO"),
        },
        E.INVITACION_PLATAFORMA: {
            **base, "rolPlataforma": "Moderador del sistema", "fechaExpiracion": now + timedelta(days=7),
            "urlActivar": frontendUrl("/administracion/activar#codigo=CODIGO_DE_EJEMPLO"),
        },
        E.ACCESO_PLATAFORMA_REVOCADO: {**base, "fechaEvento": now},
        E.ALERTA_SEGURIDAD_PLATAFORMA: {
            **base, "descripcion": "25 respuestas 401/403 desde un mismo origen", "patron": "Rechazos de autorización", "cantidad": 25,
            "ventanaMinutos": 15, "fechaEvento": now, "urlAuditoria": frontendUrl("/plataforma/auditoria"),
        },
        E.TRANSFERENCIA_ADMIN_SOLICITADA: {
            **base, "nombreAdministrador": "Carlos Gómez", "fechaEvento": now,
            "urlTransferencia": frontendUrl("/plataforma/transferencia"),
        },
        E.TRANSFERENCIA_ADMIN_RESPONDIDA: {**base, "aceptada": True, "nombreDestinatario": "Laura Díaz", "fechaEvento": now},
        E.ADMINISTRACION_ASIGNADA: {**base, "fechaEvento": now, "urlAcceso": frontendUrl("/plataforma/login")},
        E.INSTITUCION_PAUSADA: {**base, "nombreInstitucion": "Institución de ejemplo", "motivo": "Revisión de seguridad", "fechaEvento": now},
        E.INSTITUCION_REACTIVADA: {**base, "nombreInstitucion": "Institución de ejemplo", "fechaEvento": now},
        E.INVITACION_RECHAZADA: {
            **base, "nombreInvitado": "Laura Díaz", "nombreInstitucion": "Institución de ejemplo", "rol": "OPERADOR",
            "fechaEvento": now,
        },
        E.INVITACION_ACEPTADA: {
            **base, "nombreInvitado": "Laura Díaz", "nombreInstitucion": "Institución de ejemplo", "rol": "OPERADOR",
            "fechaEvento": now,
        },
        **{
            event: {
                **base, "nombreInstitucion": "Institución de ejemplo", "identificadorPseudonimo": "PAC-0001",
                "nombreOperador": "Laura Díaz", "fechaEvento": now,
                "urlPaciente": frontendUrl("/app/instituciones/ID_DE_EJEMPLO/pacientes/ID_DE_EJEMPLO"),
            }
            for event in (E.PACIENTE_REGISTRADO, E.PACIENTE_ASIGNADO, E.PACIENTE_REASIGNADO, E.PACIENTE_BAJA)
        },
        **{
            event: {
                **base, "nombreInstitucion": "Institución de ejemplo", "identificadorPseudonimo": "PAC-0001",
                "nombreOperador": "Laura Díaz", "fechaEvento": now,
                "urlTransferencias": frontendUrl("/app/instituciones/ID_DE_EJEMPLO/transferencias"),
            }
            for event in (E.TRANSFERENCIA_SOLICITADA, E.TRANSFERENCIA_ACEPTADA, E.TRANSFERENCIA_RECHAZADA,
                          E.TRANSFERENCIA_CANCELADA)
        },
        E.AGREGADO_INSTITUCION: {
            **base, "nombreInstitucion": "Institución de ejemplo", "rol": "OPERADOR", "fechaEvento": now,
        },
        E.ELIMINADO_INSTITUCION: {**base, "nombreInstitucion": "Institución de ejemplo", "fechaEvento": now},
        E.PERIODO_GRACIA_INICIADO: {
            **base, "fechaEvento": now, "fechaVencimiento": now, "diasGracia": 30,
            "urlInvitaciones": frontendUrl("/app/instituciones"),
        },
        E.ASIGNACION_PACIENTE_GESTION: {
            **base, "nombreInstitucion": "Institución de ejemplo", "identificadorPseudonimo": "PAC-0001", "nombreOperador": "Laura Díaz",
            "nombreGestor": "Carlos Gómez", "propuesta": False, "invitadoPorGestor": True, "fechaEvento": now,
            "urlPaciente": frontendUrl("/app/instituciones/ID_DE_EJEMPLO/pacientes/ID_DE_EJEMPLO"),
        },
        E.PACIENTES_PENDIENTES_REASIGNACION: {
            **base, "nombreOperador": "Laura Díaz", "nombreInstitucion": "Institución de ejemplo", "cantidad": 3, "fechaEvento": now,
            "urlGestion": frontendUrl("/app/instituciones/ID_DE_EJEMPLO/pacientes/reasignaciones"),
        },
        E.OPERADOR_AGREGADO: {
            **base, "nombreOperador": "Laura Díaz", "nombreInstitucion": "Institución de ejemplo", "fechaEvento": now,
        },
        E.OPERADOR_ELIMINADO: {
            **base, "nombreOperador": "Laura Díaz", "nombreInstitucion": "Institución de ejemplo", "fechaEvento": now,
        },
        E.ROL_INSTITUCIONAL_CAMBIADO: {
            **base, "nombreInstitucion": "Institución de ejemplo", "rolAnterior": "OPERADOR", "rolNuevo": "MODERADOR",
            "fechaEvento": now,
        },
        E.INSTITUCION_ELIMINADA: {**base, "nombreInstitucion": "Institución de ejemplo", "fechaEvento": now},
        E.INSTITUCION_ELIMINADA_ADMINISTRATIVAMENTE: {**base, "nombreInstitucion": "Institución de ejemplo", "fechaEvento": now},
        E.MEDICION_REGISTRADA: {
            **base, "fechaMedicion": now, "dispositivo": "GL-DEMO-01", "estadoRegistro": "Completada",
            "urlMedicion": medicion, **detalle,
        },
        E.RESULTADO_MEDICION: {**base, "fechaMedicion": now, "dispositivo": "GL-DEMO-01", "urlMedicion": medicion, **detalle},
        E.CONFIRMAR_CORREO_RESULTADOS: {**base, "institucion": "Institución de ejemplo", "horas": 72, "guardaCorreo": True,
                                        "incluyeResultado": False, "urlConfirmacion": medicion},
        E.MEDICION_FUERA_UMBRAL: {
            **base, "fechaMedicion": now, "dispositivo": "GL-DEMO-01", "urlMedicion": medicion, **detalle,
        },
        E.ERROR_MEDICION: {**base, "fechaEvento": now, "dispositivo": "GL-DEMO-01"},
        E.INFORMACION_RETENCION_DATOS: {**base, "fechaEvento": now},
    }
