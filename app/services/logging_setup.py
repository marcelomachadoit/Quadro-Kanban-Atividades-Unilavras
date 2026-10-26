"""Logs rotativos com filtro que remove segredos (senhas, tokens, cookies)."""
from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler

from app.config import LOG_DIR

_PATTERNS = [
    (re.compile(r"(?i)(password|senha|passwd|pwd)(\"?\s*[:=]\s*\"?)[^\s\"&,;]+"), r"\1\2***"),
    (re.compile(r"(?i)(token|jwt|bearer|cookie|session(?:id)?|authorization|set-cookie)(\"?\s*[:=]?\s*\"?)[A-Za-z0-9._\-+/=]{8,}"), r"\1\2***"),
    (re.compile(r"(?i)([?&](?:token|code|ticket|sig|key|auth|session)[^=]*=)[^&\s]+"), r"\1***"),
    (re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{5,}"), "***JWT***"),
]
_secrets: set[str] = set()


def register_secret(value: str) -> None:
    """Valores registrados aqui (ex.: a senha em uso) nunca aparecem nos logs."""
    if value and len(value) >= 3:
        _secrets.add(value)


def redact(text: str) -> str:
    for s in _secrets:
        text = text.replace(s, "***")
    for pat, rep in _PATTERNS:
        text = pat.sub(rep, text)
    return text


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True
        record.msg = redact(msg)
        record.args = ()
        if record.exc_text:
            record.exc_text = redact(record.exc_text)
        return True


class _RedactingFormatter(logging.Formatter):
    def formatException(self, ei) -> str:
        return redact(super().formatException(ei))


def setup_logging(level: int = logging.INFO) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    if any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        return
    root.setLevel(level)
    fmt = _RedactingFormatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    fh = RotatingFileHandler(LOG_DIR / "unikanban.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    fh.setFormatter(fmt)
    fh.addFilter(RedactingFilter())
    root.addHandler(fh)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    sh.addFilter(RedactingFilter())
    root.addHandler(sh)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
