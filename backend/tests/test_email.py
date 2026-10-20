import os
import smtplib
from email.message import EmailMessage
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
TEST_EMAIL_TO = os.getenv("TEST_EMAIL_TO", "correo@gmail.com")

message = EmailMessage()
message["Subject"] = "Prueba de correo - GlucoLume"
message["From"] = SMTP_USERNAME
message["To"] = TEST_EMAIL_TO
message.set_content(
    "Este es un correo de prueba enviado correctamente desde GlucoLume."
)

try:
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()

        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.send_message(message)

    print("✅ Correo enviado correctamente")
    print(f"✅ Destinatario: {TEST_EMAIL_TO}")

except Exception as error:
    print("❌ Error al enviar correo")
    print(error)