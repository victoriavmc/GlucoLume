# Validación de S-07: tamaño MIME final, tipo de imagen adjunta, Content-ID y HTML de referencia.
# Uso: python banner_validate.py <raiz_backend> <salida_json> <salida_html>
import os, sys, json, datetime as dt
root, outJson, outHtml = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, root)
os.environ.update({"API_ENV": "development", "DB_HOST": "127.0.0.1", "DB_NAME": "lab", "DB_USER": "lab",
                   "DB_PASSWORD": "lab-no-real", "JWT_SECRET": "lab-jwt-secret-no-real-0123456789abcdef0123456789",
                   "FRONTEND_URL": "https://glucolume.example", "API_BASE_URL": "https://glucolume.example",
                   "SMTP_HOST": "127.0.0.1", "SMTP_PORT": "8025", "SMTP_USERNAME": "lab@glucolume.example",
                   "SMTP_PASSWORD": "lab-no-real", "SMTP_FROM": "lab@glucolume.example", "SMTP_FROM_NAME": "GlucoLume"})
from app.services import email as emailService
from app.emails.eventTypes import EmailEventType
ctx = {"nombre": "Prueba", "urlVerificacion": "https://glucolume.example/verificar-correo?token=prueba",
       "fechaExpiracion": dt.datetime(2026, 11, 5, 12, 0), "plazoHoras": 24}
msg = emailService.buildEmailMessage(EmailEventType.EMAIL_VERIFICACION, "destino@example.com", ctx)
raw = msg.as_bytes()
images = [p for p in msg.walk() if p.get_content_maintype() == "image"]
banner = emailService.loadBanner()
rendered = emailService.renderEmailEvent(EmailEventType.EMAIL_VERIFICACION, "destino@example.com", ctx)[1]
out = {"banner": banner.filename, "subtype": banner.subtype, "bannerBytes": len(banner.content),
       "mensajeMimeBytes": len(raw), "imagenes": [{"contentType": i.get_content_type(), "contentId": i["Content-ID"],
       "disposition": i.get_content_disposition(), "bytes": len(i.get_payload(decode=True))} for i in images],
       "cidEnHtml": f"cid:bannerCorreoGlucoLume" in rendered.html}
open(outJson, "w", encoding="utf8").write(json.dumps(out, ensure_ascii=False, indent=1))
open(outHtml, "w", encoding="utf8").write(rendered.html)
print(json.dumps(out, ensure_ascii=False))
