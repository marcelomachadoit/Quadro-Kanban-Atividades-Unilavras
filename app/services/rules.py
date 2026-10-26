"""Regras de negócio puras (sem I/O): conclusão, datas, pontuação, inclusão e chaves únicas."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlsplit, parse_qsl

from app.config import COMPLETION_THRESHOLD, SOON_HOURS, TZ

# ---------------------------------------------------------------- texto

def normalize(text: Optional[str]) -> str:
    """Minúsculas, sem acentos e com espaços simples — para comparação e chaves."""
    if not text:
        return ""
    t = unicodedata.normalize("NFKD", str(text))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip().lower()


def clean_text(text: Optional[str]) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


# ---------------------------------------------------------------- conclusão

_PCT_RE = re.compile(r"(\d{1,3}(?:[.,]\d+)?)\s*%")


def parse_percentage(text) -> Optional[float]:
    """Extrai um percentual de conclusão. Retorna None se não puder interpretar com segurança."""
    if text is None:
        return None
    if isinstance(text, (int, float)):
        v = float(text)
        return v if 0 <= v <= 100 else None
    found = _PCT_RE.findall(str(text))
    if len(found) != 1:          # nenhum ou vários percentuais: ambíguo
        return None
    v = float(found[0].replace(",", "."))
    return v if 0 <= v <= 100 else None


def is_course_eligible(progress: Optional[float]) -> Optional[bool]:
    """True = processar (< 95%), False = ignorar (>= 95%), None = desconhecido (não presumir)."""
    if progress is None:
        return None
    return progress < COMPLETION_THRESHOLD


# ---------------------------------------------------------------- datas

MONTHS = {
    "janeiro": 1, "jan": 1, "fevereiro": 2, "fev": 2, "marco": 3, "mar": 3, "abril": 4, "abr": 4,
    "maio": 5, "mai": 5, "junho": 6, "jun": 6, "julho": 7, "jul": 7, "agosto": 8, "ago": 8,
    "setembro": 9, "set": 9, "outubro": 10, "out": 10, "novembro": 11, "nov": 11,
    "dezembro": 12, "dez": 12,
}

DUE_LABELS = [
    r"prazo(?:\s+de\s+entrega)?", r"data\s+(?:de\s+)?(?:entrega|limite|final|de\s+vencimento|de\s+t[eé]rmino|fim)",
    r"entrega\s+at[eé]", r"entregar\s+at[eé]", r"vencimento", r"vence(?:\s+em)?", r"dispon[ií]vel\s+at[eé]",
    r"encerra(?:-se)?(?:\s+em)?", r"t[eé]rmino", r"fecha(?:mento)?(?:\s+em)?", r"at[eé]", r"fim",
    r"due(?:\s+date)?",
]
DUE_LABEL_RE = re.compile(r"(?:%s)\s*[:\-–]?\s*" % "|".join(DUE_LABELS), re.I)

_TIME = r"(?:\s*(?:,|às|as|a\s+partir\s+das|-|–|at)?\s*(\d{1,2})\s*(?:[:hH])\s*(\d{2})?(?:\s*(?:min|m))?)?"
_NUM_DATE_RE = re.compile(r"\b(\d{1,2})[/.\-](\d{1,2})(?:[/.\-](\d{2,4}))?\b" + _TIME, re.I)
_TXT_DATE_RE = re.compile(
    r"\b(\d{1,2})\s*(?:de\s+)?([a-zçA-ZÇ]{3,9})\.?(?:\s*(?:de\s+)?(\d{4}))?\b" + _TIME, re.I)
_ISO_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})(?:[T\s](\d{2}):(\d{2})(?::(\d{2}))?(?:\.\d+)?(Z|[+\-]\d{2}:?\d{2})?)?")


@dataclass
class ParsedDate:
    dt: Optional[datetime]
    has_time: bool = False
    ambiguous: bool = False
    raw: str = ""


def _mk(y, mo, d, hh, mm, ss=0) -> Optional[datetime]:
    try:
        return datetime(y, mo, d, hh, mm, ss, tzinfo=TZ)
    except ValueError:
        return None


def parse_datetime_br(text: Optional[str], now: Optional[datetime] = None) -> ParsedDate:
    """Interpreta datas no formato brasileiro (e ISO) no fuso America/Sao_Paulo.

    * Data sem horário => válida até 23:59:59 do dia.
    * Data sem ano => ambígua (ano inferido, mas sinalizada para verificação).
    """
    raw = clean_text(text)
    if not raw:
        return ParsedDate(None, raw=raw)
    now = now or datetime.now(TZ)

    m = _ISO_RE.search(raw)
    if m:
        y, mo, d = int(m[1]), int(m[2]), int(m[3])
        if m[4]:
            tz = m[7]
            iso = m.group(0).replace(" ", "T")
            if tz:
                try:
                    dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(TZ)
                    return ParsedDate(dt, True, False, raw)
                except ValueError:
                    pass
            dt = _mk(y, mo, d, int(m[4]), int(m[5]), int(m[6] or 0))
            return ParsedDate(dt, True, dt is None, raw)
        dt = _mk(y, mo, d, 23, 59, 59)
        return ParsedDate(dt, False, dt is None, raw)

    m = _NUM_DATE_RE.search(raw)
    kind = "num"
    if not m:
        m = _TXT_DATE_RE.search(raw)
        kind = "txt"
        if m and normalize(m[2]).rstrip(".") not in MONTHS:
            m = None
    if not m:
        return ParsedDate(None, ambiguous=True, raw=raw)

    d = int(m[1])
    mo = int(m[2]) if kind == "num" else MONTHS[normalize(m[2]).rstrip(".")]
    year_txt = m[3]
    ambiguous = False
    if year_txt:
        y = int(year_txt)
        if y < 100:
            y += 2000
    else:
        # sem ano: assume o ano corrente; se já passou há muito tempo, provável ano seguinte
        y = now.year
        ambiguous = True
    hh_txt, mm_txt = m[4], m[5]
    if hh_txt is not None:
        hh, mm = int(hh_txt), int(mm_txt or 0)
        if hh > 23 or mm > 59:
            return ParsedDate(None, ambiguous=True, raw=raw)
        dt = _mk(y, mo, d, hh, mm)
        has_time = True
    else:
        dt = _mk(y, mo, d, 23, 59, 59)
        has_time = False
    if dt is None:
        return ParsedDate(None, ambiguous=True, raw=raw)
    return ParsedDate(dt, has_time, ambiguous, raw)


def extract_due(text: str, now: Optional[datetime] = None) -> ParsedDate:
    """Procura um prazo em um bloco de texto, preferindo datas após rótulos de prazo."""
    t = clean_text(text)
    if not t:
        return ParsedDate(None)
    best: Optional[ParsedDate] = None
    for lab in DUE_LABEL_RE.finditer(t):
        segment = t[lab.end(): lab.end() + 60]
        pd = parse_datetime_br(segment, now)
        if pd.dt is not None and _starts_near(segment):
            # quando há intervalo "de X até Y", o último rótulo (até/fim) prevalece
            best = pd
    if best is None:
        # rótulos com intervalo: "01/10/2026 a 30/10/2026" => fim do intervalo
        rng = re.search(r"(\d{1,2}/\d{1,2}(?:/\d{2,4})?[^/]{0,20}?)\s+(?:a|até|-|–)\s+(\d{1,2}/\d{1,2}(?:/\d{2,4})?(?:\s*(?:às|as|,)?\s*\d{1,2}[:h]\d{2})?)", t, re.I)
        if rng:
            pd = parse_datetime_br(rng.group(2), now)
            if pd.dt is not None:
                return pd
        return ParsedDate(None, raw="")
    return best


def _starts_near(segment: str) -> bool:
    m = re.search(r"\d", segment)
    return m is not None and m.start() <= 25


# ---------------------------------------------------------------- pontuação

_NUM = r"(\d{1,4}(?:[.,]\d{1,2})?)"
POINTS_LABELED_RE = re.compile(
    r"(?:vale(?:ndo)?|valor(?:\s+da\s+atividade)?|pontua[cç][aã]o(?:\s+m[aá]xima|\s+total)?|nota\s+m[aá]xima|"
    r"peso|pontos\s+poss[ií]veis|total\s+de\s+pontos|max(?:imum)?\s+points?)\s*[:\-–]?\s*" + _NUM +
    r"\s*(pontos?|pts?\.?|ponto\(s\))?", re.I)
POINTS_PLAIN_RE = re.compile(r"\b" + _NUM + r"\s*(pontos|ponto|pts\.?|pt)\b", re.I)
OBTAINED_RE = re.compile(r"(?:nota|obtid[ao]|sua\s+nota|voc[eê]\s+obteve|tirou|resultado)\s*[:\-–]?\s*" + _NUM +
                         r"\s*(?:/|de|em)\s*" + _NUM, re.I)
_OBTAINED_CTX = re.compile(r"(obtid|sua nota|voce obteve|voc[eê] obteve|tirou|nota do aluno|alcan[cç]ad)", re.I)


def _fmt_points(num: str) -> str:
    v = float(num.replace(",", "."))
    s = f"{v:g}".replace(".", ",")
    return f"{s} ponto" if v == 1 else f"{s} pontos"


def extract_points(text: str) -> Optional[str]:
    """Extrai a pontuação TOTAL de uma atividade (não a nota obtida pelo aluno)."""
    t = clean_text(text)
    if not t:
        return None
    m = POINTS_LABELED_RE.search(t)
    if m:
        return _fmt_points(m[1])
    for m in POINTS_PLAIN_RE.finditer(t):
        before = normalize(t[max(0, m.start() - 30): m.start()])
        if _OBTAINED_CTX.search(before):
            continue           # nota obtida, não o valor total
        return _fmt_points(m[1])
    m = OBTAINED_RE.search(t)  # "Nota: 8/10" -> total 10
    if m:
        return _fmt_points(m[2])
    return None


# ---------------------------------------------------------------- classificação

ASSESSMENT_WORDS = re.compile(
    r"\b(atividade|exerc[ií]cio|question[aá]rio|quiz|avalia[cç][aã]o|prova|trabalho|entrega|tarefa|"
    r"simulado|teste|f[oó]rum avaliativo|desafio|estudo de caso|projeto|portf[oó]lio|lista|"
    r"assignment|exam|semin[aá]rio|relat[oó]rio|resenha|checkpoint|case)\b", re.I)
MATERIAL_WORDS = re.compile(
    r"\b(v[ií]deo|videoaula|aula gravada|leitura|material|apostila|slides?|e-?book|livro|pdf|"
    r"podcast|texto|artigo|conte[uú]do|apresenta[cç][aã]o|biblioteca|link|arquivo|refer[eê]ncia)\b", re.I)


def looks_like_assessment(name: str, context: str = "", kind: str = "") -> bool:
    """Heurística: o item parece uma atividade avaliativa (e não material didático)?"""
    k = normalize(kind)
    if k and ASSESSMENT_WORDS.search(k):
        return True
    if k and MATERIAL_WORDS.search(k):
        # material só entra se tiver evidência de avaliação no contexto (prazo/pontuação)
        return bool(extract_points(context))
    n = clean_text(name)
    if ASSESSMENT_WORDS.search(n):
        return True
    if MATERIAL_WORDS.search(n):
        return bool(extract_points(context))
    return bool(extract_points(context))


DUE_NONE, DUE_EXPIRED, DUE_SOON, DUE_FUTURE = "sem_prazo", "expirado", "proximo", "futuro"


def due_state(due_at: Optional[datetime], now: Optional[datetime] = None) -> str:
    if due_at is None:
        return DUE_NONE
    now = now or datetime.now(TZ)
    if due_at < now:
        return DUE_EXPIRED
    if due_at - now <= timedelta(hours=SOON_HOURS):
        return DUE_SOON
    return DUE_FUTURE


@dataclass
class InclusionDecision:
    include: bool
    reason: str
    needs_review: bool = False


def decide_inclusion(is_assessment: bool, due: ParsedDate, points: Optional[str],
                     now: Optional[datetime] = None) -> InclusionDecision:
    """Aplica o critério de inclusão do projeto."""
    if not is_assessment:
        return InclusionDecision(False, "não é atividade avaliativa")
    has_due_text = bool(due.raw)
    if due.dt is None and not points and not has_due_text:
        return InclusionDecision(False, "sem prazo nem pontuação identificáveis")
    if due.dt is None and has_due_text:
        # existe texto de prazo, mas não interpretável: não descartar silenciosamente
        return InclusionDecision(True, "prazo não interpretável — verificar", needs_review=True)
    if due.dt is not None and due_state(due.dt, now) == DUE_EXPIRED:
        if due.ambiguous:
            return InclusionDecision(True, "prazo ambíguo (possivelmente expirado) — verificar", needs_review=True)
        return InclusionDecision(False, "prazo expirado")
    if due.dt is not None and due.ambiguous:
        return InclusionDecision(True, "prazo sem ano explícito — verificar", needs_review=True)
    return InclusionDecision(True, "ok")


# ---------------------------------------------------------------- chave única

_ID_PARAMS = ("id", "itemid", "activityid", "atividadeid", "contentid", "content_id", "cmid", "assignmentid", "taskid")


def source_id_from_url(url: Optional[str]) -> Optional[str]:
    """Tenta obter um identificador estável a partir da URL da atividade."""
    if not url:
        return None
    s = urlsplit(url)
    for k, v in parse_qsl(s.query):
        if k.lower() in _ID_PARAMS and v:
            return f"{k.lower()}={v}"
    parts = [p for p in s.path.split("/") if p]
    for p in reversed(parts):
        if re.fullmatch(r"[0-9]{3,}|[0-9a-f]{8}-[0-9a-f-]{27,}|[A-Za-z0-9_-]{16,}", p):
            return p
    return None


def make_source_key(course: Optional[str], name: Optional[str], source_id: Optional[str] = None,
                    url: Optional[str] = None) -> str:
    """Chave estável: id da origem > id extraído da URL > disciplina+nome normalizados."""
    sid = source_id or source_id_from_url(url)
    if sid:
        basis = f"id|{sid}"
    else:
        basis = f"nm|{normalize(course)}|{normalize(name)}"
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()
