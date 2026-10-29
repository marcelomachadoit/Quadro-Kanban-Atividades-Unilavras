"""Leitura da página pública de eventos (eventos.unilavras.edu.br) e da página de cada evento (even3)."""
from __future__ import annotations

import html
import json
import re
from datetime import date, datetime
from typing import Optional

from app.models.activity import dt_to_iso
from app.models.events import PortalEvent

_CARD_TITLE = re.compile(r"<h5\b[^>]*>(.*?)</h5>", re.S | re.I)
_DATE = re.compile(r"(\d{2})/(\d{2})/(\d{4})")
_HREF = re.compile(r"<a\b[^>]*\bhref=\"([^\"]+)\"", re.I)
_TAGS = re.compile(r"<[^>]+>")
_LD_JSON = re.compile(r"<script[^>]*application/ld\+json[^>]*>(.*?)</script>", re.S | re.I)
_OG = re.compile(r"<meta\s+(?:property|name)=\"(og:title|og:description|description)\"\s+content=\"([^\"]*)\"", re.I)
_TITLE = re.compile(r"<title>(.*?)</title>", re.S | re.I)


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(_TAGS.sub(" ", fragment))).strip()


def is_truncated(title: str) -> bool:
    return title.rstrip().endswith(("...", "…"))


def parse_events_list(page: str) -> list[PortalEvent]:
    """Cada cartão da lista tem título (h5), "Data: dd/mm/aaaa" e o botão "Saiba mais" com o link de inscrição."""
    out: list[PortalEvent] = []
    seen: set[str] = set()
    titles = list(_CARD_TITLE.finditer(page))
    for i, m in enumerate(titles):
        end = titles[i + 1].start() if i + 1 < len(titles) else len(page)
        block = page[m.end():end]
        title = _text(m.group(1))
        d = _DATE.search(block)
        if not title or not d:
            continue
        try:
            day = date(int(d.group(3)), int(d.group(2)), int(d.group(1)))
        except ValueError:
            continue
        h = _HREF.search(block)
        url = html.unescape(h.group(1)).strip() if h else None
        if url and not url.lower().startswith(("http://", "https://")):
            url = None
        key = url or f"{title}|{day.isoformat()}"
        if key in seen:
            continue
        seen.add(key)
        out.append(PortalEvent(key=key, title=title, date=day.isoformat(), url=url))
    return out


def _parse_dt(value) -> Optional[datetime]:
    """Datas do even3 às vezes vêm malformadas ("2026-10-30T00:0022:00:00"); nesses casos são ignoradas."""
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _location(loc) -> Optional[str]:
    if isinstance(loc, list):
        loc = loc[0] if loc else None
    if isinstance(loc, str):
        return loc.strip() or None
    if not isinstance(loc, dict):
        return None
    if loc.get("@type") == "VirtualLocation":
        return "Online"
    addr = loc.get("address") if isinstance(loc.get("address"), dict) else {}
    parts = [loc.get("name"), addr.get("addressLocality")]
    parts = [str(p).strip() for p in parts if p and str(p).strip()]
    return " · ".join(dict.fromkeys(parts)) or None


def parse_event_details(page: str) -> dict:
    """Título completo, início/fim, local e descrição (dados estruturados schema.org; meta tags como alternativa)."""
    info: dict = {}
    for m in _LD_JSON.finditer(page):
        try:
            data = json.loads(m.group(1))
        except ValueError:
            continue
        for d in (data if isinstance(data, list) else [data]):
            if not isinstance(d, dict) or "Event" not in str(d.get("@type", "")):
                continue
            if d.get("name"):
                info["title"] = html.unescape(str(d["name"])).strip()
            start, end = _parse_dt(d.get("startDate")), _parse_dt(d.get("endDate"))
            if start:
                info["start_at"] = dt_to_iso(start)
            if end and (not start or end >= start):
                info["end_at"] = dt_to_iso(end)
            loc = _location(d.get("location"))
            if loc:
                info["location"] = loc
            if d.get("description"):
                info["description"] = html.unescape(str(d["description"])).strip()
            break
        if info:
            break
    meta = {k.lower(): html.unescape(v).strip() for k, v in _OG.findall(page)}
    if "title" not in info:
        t = meta.get("og:title") or (_text(_TITLE.search(page).group(1)) if _TITLE.search(page) else "")
        if t:
            info["title"] = t
    if "description" not in info:
        desc = meta.get("og:description") or meta.get("description")
        if desc:
            info["description"] = desc
    return info


def merge_details(ev: PortalEvent, info: dict) -> PortalEvent:
    title = info.get("title")
    if title and (is_truncated(ev.title) or len(title) >= len(ev.title)):
        ev.title = title
    for k in ("start_at", "end_at", "location", "description"):
        if info.get(k):
            setattr(ev, k, info[k])
    return ev
