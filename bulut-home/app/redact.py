"""Gizli değer maskeleme. Loglara, aktivite akışına, hata kayıtlarına ve bildirimlere giden metinler buradan geçer."""
from __future__ import annotations

import logging
import re
import threading

_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"),                 # Anthropic
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_\-]{16,}"),        # OpenAI/DeepSeek benzeri
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-~+/=]{8,}"),
    re.compile(r"(?i)((?:x-api-key|x-subscription-token|api[_-]?key|token|authorization)[\"']?\s*[:=]\s*[\"']?)[^\s\"',}]{6,}"),
    re.compile(r"\b\d{6,12}:[A-Za-z0-9_\-]{30,}\b"),           # Telegram bot token
    re.compile(r"\btk_[A-Za-z0-9]{20,}\b"),                    # ntfy erişim token'ı
]
_known: set[str] = set()
_lock = threading.Lock()
MASK = "***"


def register(*values: str | None) -> None:
    """Yapılandırmadaki gerçek gizli değerleri kaydet; birebir geçtikleri her yerde maskelenir."""
    with _lock:
        for v in values:
            if v and len(v) >= 6:
                _known.add(v)


def redact(text: object) -> str | None:
    if text is None:
        return None
    s = str(text)
    with _lock:
        known = sorted(_known, key=len, reverse=True)
    for v in known:
        if v in s:
            s = s.replace(v, MASK)
    for p in _PATTERNS:
        s = p.sub(lambda m: (m.group(1) if m.groups() and m.group(1) else "") + MASK, s)
    return s


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:  # noqa: BLE001
            return True
        clean = redact(msg)
        if clean != msg:
            record.msg, record.args = clean, ()
        return True


def install_logging_filter() -> None:
    f = RedactingFilter()
    for name in ("", "uvicorn", "uvicorn.error", "uvicorn.access", "httpx", "httpx2", "anthropic"):
        lg = logging.getLogger(name)
        if not any(isinstance(x, RedactingFilter) for x in lg.filters):
            lg.addFilter(f)
        for h in lg.handlers:
            if not any(isinstance(x, RedactingFilter) for x in h.filters):
                h.addFilter(f)
