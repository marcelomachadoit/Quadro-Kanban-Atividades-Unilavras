"""Data do AVIN a partir do Planograma da disciplina (Sala de Aula Virtual).

Estrutura observada no portal real (out/2026):
* Em "Informações sobre a disciplina" há o tópico "Planograma" (``topicTypeId`` 3, arquivo); o campo
  ``modifiedAt`` muda quando o professor troca o documento.
* ``GET .../v2/plataforma/content/academics-main/{curso}/topics/{tópico}`` -> ``{"topics": {"content": {"html"}}}``,
  e o HTML traz ``<grupoabook file="https://static.../arquivo.pdf" filename="..._planograma.pdf">``.
* O PDF tem o quadro "Fique ligado!" com linhas "02/12/2026 AVIN" e "a definir AVIN - 2º chamada".
"""
from __future__ import annotations

import logging
import re
import tempfile
from datetime import date
from html import unescape
from pathlib import Path
from typing import Optional

from app.services import rules as R

log = logging.getLogger(__name__)

PDF_FILE_RE = re.compile(r"""\bfile\s*=\s*["'](https?://[^"']+?\.pdf)["']""", re.I)
# "02/12/2026 AVIN" — não confunde com "AVIN - 2º chamada", que costuma ficar "a definir"
AVIN_LINE_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})\s+AVIN\b(?!\s*[-–]\s*\d\s*[ºo°ª]?\s*chamada)", re.I)


def find_planograma_topic(contents: dict) -> Optional[dict]:
    """Tópico "Planograma" da árvore de conteúdo da disciplina (ou None se a disciplina não tiver)."""
    def visit(topics):
        for t in topics or []:
            if R.normalize(t.get("title")).startswith("planograma"):
                return t
            found = visit(t.get("children"))
            if found:
                return found
        return None
    return visit((contents or {}).get("topics"))


def topic_revision(topic: dict) -> str:
    """Identifica a versão do documento: muda quando o professor substitui o arquivo."""
    return f"{topic.get('id')}@{topic.get('modifiedAt') or ''}"


def pdf_url(topic_json: dict) -> Optional[str]:
    html = (((topic_json or {}).get("topics") or {}).get("content") or {}).get("html") or ""
    m = PDF_FILE_RE.search(unescape(html))
    return m[1] if m else None


def parse_avin_date(text: str) -> Optional[date]:
    """Primeira data válida "dd/mm/aaaa AVIN" do texto do Planograma."""
    for m in AVIN_LINE_RE.finditer(text or ""):
        try:
            return date(int(m[3]), int(m[2]), int(m[1]))
        except ValueError:
            continue
    return None


def pdf_text(data: bytes) -> str:
    """Texto de todas as páginas do PDF (QtPdf, que já acompanha o PySide6)."""
    import shiboken6
    from PySide6.QtPdf import QPdfDocument
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "planograma.pdf"
        path.write_bytes(data)
        doc = QPdfDocument()
        try:
            err = doc.load(str(path))
            if err != QPdfDocument.Error.None_:
                raise ValueError(f"PDF ilegível ({err.name})")
            return "\n".join(doc.getAllText(i).text() for i in range(doc.pageCount()))
        finally:
            shiboken6.delete(doc)          # libera o arquivo assim que o documento é destruído
