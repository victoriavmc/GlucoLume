# Render - Previsualización de los correos de GlucoLume con datos ficticios
#
# Desde backend/:
#   python -m tests.email_preview.render              (todos los eventos)
#   python -m tests.email_preview.render CUENTA_CREADA (uno o varios eventos)
#   python -m tests.email_preview.render --con-detalle (mediciones con detalle autorizado)
#
# Genera tests/email_preview/output/<EVENTO>.html y .txt, más un index.html. No envía correos ni
# requiere base de datos. En la vista previa el banner se referencia como archivo local; en el
# correo real va embebido como cid:bannerCorreoGlucoLume.

import shutil
import sys
from pathlib import Path

from app.emails.eventTypes import EMAIL_EVENTS, EmailEventType
from app.emails.renderer import BANNER_CID
from app.services.email import loadBanner, renderEmailEvent
from tests.email_preview.sampleData import SAMPLE_RECIPIENT, sampleContexts

OUTPUT_DIR = Path(__file__).resolve().parent / "output"


def renderPreviews(events: list[EmailEventType], includeDetail: bool = False) -> list[Path]:
    OUTPUT_DIR.mkdir(exist_ok=True)
    banner = loadBanner()
    (OUTPUT_DIR / banner.filename).write_bytes(banner.content)
    contexts = sampleContexts()
    written = []
    for event in events:
        _, rendered = renderEmailEvent(event, SAMPLE_RECIPIENT, contexts[event], incluirDetalleMedicion=includeDetail)
        htmlPath = OUTPUT_DIR / f"{event}.html"
        htmlPath.write_text(rendered.html.replace(f"cid:{BANNER_CID}", banner.filename), encoding="utf-8")
        (OUTPUT_DIR / f"{event}.txt").write_text(f"Asunto: {rendered.subject}\n\n{rendered.text}", encoding="utf-8")
        written.append(htmlPath)
    links = "\n".join(
        f'<li><a href="{path.name}">{path.stem}</a> — {EMAIL_EVENTS[EmailEventType(path.stem)].subject}</li>'
        for path in written
    )
    (OUTPUT_DIR / "index.html").write_text(
        f"<!DOCTYPE html><meta charset='utf-8'><title>Correos GlucoLume</title><h1>Correos GlucoLume</h1><ul>{links}</ul>",
        encoding="utf-8",
    )
    return written


def main(args: list[str]) -> None:
    includeDetail = "--con-detalle" in args
    names = [arg for arg in args if not arg.startswith("--")]
    events = [EmailEventType(name) for name in names] or list(EmailEventType)
    written = renderPreviews(events, includeDetail)
    print(f"{len(written)} correos generados en {OUTPUT_DIR}")
    print(f"Abrir: {OUTPUT_DIR / 'index.html'}")


if __name__ == "__main__":
    if "--limpiar" in sys.argv:
        shutil.rmtree(OUTPUT_DIR, ignore_errors=True)
    main(sys.argv[1:])
