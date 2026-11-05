# Variables de prueba para importar la configuración (no son secretos reales; la base no se usa en estas mediciones).
import os
os.environ.update({
    "API_ENV": "development", "DB_HOST": "127.0.0.1", "DB_NAME": "lab", "DB_USER": "lab", "DB_PASSWORD": "lab-no-real",
    "JWT_SECRET": "lab-jwt-secret-no-real-0123456789abcdef0123456789", "MFA_ENCRYPTION_KEY": "",
    "FRONTEND_URL": "https://glucolume.example", "API_BASE_URL": "https://glucolume.example",
    "SMTP_HOST": "127.0.0.1", "SMTP_PORT": "8025", "SMTP_USERNAME": "lab@glucolume.example", "SMTP_PASSWORD": "lab-no-real",
    "SMTP_FROM": "lab@glucolume.example", "CONTACT_EMAIL": "contacto@glucolume.example",
})
import sys
sys.path.insert(0, "/home/user/GlucoLume/backend")
