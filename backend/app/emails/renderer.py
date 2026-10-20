# EmailRenderer - Renderizado de las plantillas de correo (Jinja2)
#
# - Autoescape HTML: los datos del usuario nunca se interpretan como HTML.
# - StrictUndefined: una variable faltante falla al renderizar en lugar de quedar vacía.
# - El texto plano alternativo se genera a partir del mismo HTML.

import re
from dataclasses import dataclass
from functools import lru_cache
from html.parser import HTMLParser
from pathlib import Path
from typing import ClassVar

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from app.emails import formatting
from app.emails.eventTypes import EMAIL_EVENTS, EmailEventType

# Plantillas, banner y estilos viven en app/emails (base.html, macros.html y una carpeta por categoría).
EMAILS_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = EMAILS_DIR
BANNER_CID = "bannerCorreoGlucoLume"


@dataclass(frozen=True)
class RenderedEmail:
    subject: str
    html: str
    text: str


@lru_cache
def _environment() -> Environment:
    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=select_autoescape(["html"]),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters.update(
        fechaHora=formatting.formatDateTime,
        fecha=formatting.formatDate,
        enmascararCorreo=formatting.maskEmail,
        rol=formatting.roleLabel,
        metodoMfa=formatting.mfaMethodLabel,
    )
    return env


def renderEmail(eventType: EmailEventType, context: dict) -> RenderedEmail:
    spec = EMAIL_EVENTS[eventType]
    html = _environment().get_template(spec.template).render(
        **context,
        categoria=spec.category,
        asunto=spec.subject,
        avisoSeguridad=spec.securityNotice,
        avisoClinico=spec.clinicalDisclaimer,
        prioridadAlta=spec.highPriority,
        bannerSrc=f"cid:{BANNER_CID}",
    )
    return RenderedEmail(subject=spec.subject, html=html, text=htmlToText(html))


class _TextExtractor(HTMLParser):
    _BLOCK_TAGS: ClassVar[frozenset[str]] = frozenset({"p", "div", "tr", "table", "h1", "h2", "h3", "li", "br", "td"})
    _SKIP_TAGS: ClassVar[frozenset[str]] = frozenset({"style", "head", "title"})

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0
        self._href: str | None = None

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP_TAGS:
            self._skip += 1
        elif tag == "a":
            self._href = dict(attrs).get("href")
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag in self._BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self._SKIP_TAGS:
            self._skip -= 1
        elif tag == "a":
            if self._href and not self._href.startswith("cid:"):
                self.parts.append(f" ({self._href})")
            self._href = None
        elif tag in self._BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def htmlToText(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    text = "".join(parser.parts)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"
