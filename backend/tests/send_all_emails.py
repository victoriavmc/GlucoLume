import os
import smtplib
import ssl
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import getSessionFactory
from app.emails.eventTypes import EmailEventType
from app.services import email as emailService
from tests.email_preview.realData import buildContext, findUser, loadRealData
from tests.email_preview.sampleData import sampleContexts


# ============================================================
# CONFIGURACIÓN
# ============================================================

# backend/tests/send_all_emails.py
# parents[0] = tests
# parents[1] = backend
# parents[2] = Glucolume-web
ROOT_DIR = Path(__file__).resolve().parents[2]

load_dotenv(ROOT_DIR / ".env")

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
TEST_EMAIL_TO = os.getenv("TEST_EMAIL_TO", "correo@gmail.com")
CONTEXTS = sampleContexts()


def validar_configuracion():
    faltantes = []

    if not SMTP_HOST:
        faltantes.append("SMTP_HOST")

    if not SMTP_USERNAME:
        faltantes.append("SMTP_USERNAME")

    if not SMTP_PASSWORD:
        faltantes.append("SMTP_PASSWORD")

    if not TEST_EMAIL_TO:
        faltantes.append("TEST_EMAIL_TO")

    if faltantes:
        raise RuntimeError(
            "Faltan variables en .env: " + ", ".join(faltantes)
        )


def cargar_datos_reales():
    """Datos reales del usuario cuyo correo es TEST_EMAIL_TO (solo lectura).

    Si el usuario no existe o la base no está disponible, se devuelve None y se usan
    solamente los datos de muestra.
    """
    try:
        with getSessionFactory()() as db:
            usuario = findUser(db, TEST_EMAIL_TO)
            if usuario is None:
                print("Usuario no encontrado en la base: se usan datos de muestra.")
                return None
            datos = loadRealData(db, usuario)
    except SQLAlchemyError as exc:
        print(f"Base de datos no disponible ({type(exc).__name__}): se usan datos de muestra.")
        return None

    print("Usuario encontrado en la base: se usan sus datos reales y muestra para lo que falte.")
    if datos.unavailable:
        print(f"Sin datos reales de: {', '.join(datos.unavailable)}.")
    return datos


def preparar_mensaje(event, datos=None):
    if event not in CONTEXTS:
        raise RuntimeError(
            f"No existe contexto de prueba para {event.value}"
        )

    context, campos_reales, campos_muestra = buildContext(event, CONTEXTS[event], datos)

    message = emailService.buildEmailMessage(
        event,
        TEST_EMAIL_TO,
        context,
        incluirDetalleMedicion=True,
    )

    # Por seguridad, aseguramos el destinatario real del test.
    if message["To"]:
        del message["To"]

    message["To"] = TEST_EMAIL_TO

    # Si el servicio no hubiera establecido From.
    if not message["From"]:
        message["From"] = SMTP_USERNAME

    return message, campos_reales, campos_muestra


def enviar_todos():
    validar_configuracion()

    eventos = list(EmailEventType)

    print("=" * 70)
    print("PRUEBA REAL DE CORREOS - GLUCOLUME")
    print("=" * 70)
    print(f"Servidor SMTP : {SMTP_HOST}:{SMTP_PORT}")
    print(f"Destinatario  : {TEST_EMAIL_TO}")
    print(f"Total correos : {len(eventos)}")
    print("=" * 70)

    datos = cargar_datos_reales()

    enviados = 0
    errores = []

    contexto_ssl = ssl.create_default_context()

    # Gmail normalmente utiliza 587 + STARTTLS.
    if SMTP_PORT == 465:
        servidor = smtplib.SMTP_SSL(
            SMTP_HOST,
            SMTP_PORT,
            context=contexto_ssl,
            timeout=30,
        )
    else:
        servidor = smtplib.SMTP(
            SMTP_HOST,
            SMTP_PORT,
            timeout=30,
        )

    try:
        servidor.ehlo()

        if SMTP_PORT != 465:
            servidor.starttls(context=contexto_ssl)
            servidor.ehlo()

        servidor.login(
            SMTP_USERNAME,
            SMTP_PASSWORD,
        )

        print("\nConexión SMTP correcta.\n")

        for numero, event in enumerate(eventos, start=1):
            try:
                message, campos_reales, campos_muestra = preparar_mensaje(event, datos)

                servidor.send_message(message)

                enviados += 1

                print(
                    f"[{numero:02}/{len(eventos):02}] "
                    f"ENVIADO  -> {event.value}"
                )
                print(
                    f"         reales: {', '.join(campos_reales) or '—'}"
                    f" | muestra: {', '.join(campos_muestra) or '—'}"
                )

            except Exception as exc:
                errores.append(
                    (event.value, str(exc))
                )

                print(
                    f"[{numero:02}/{len(eventos):02}] "
                    f"ERROR    -> {event.value}: {exc}"
                )

    finally:
        try:
            servidor.quit()
        except Exception:
            pass

    print("\n" + "=" * 70)
    print("RESULTADO")
    print("=" * 70)
    print(f"Enviados correctamente: {enviados}")
    print(f"Fallidos:              {len(errores)}")
    print(f"Total:                 {len(eventos)}")

    if errores:
        print("\nERRORES:")

        for event, error in errores:
            print(f"- {event}: {error}")

    print("=" * 70)

    if enviados != len(eventos):
        raise SystemExit(1)


if __name__ == "__main__":
    enviar_todos()