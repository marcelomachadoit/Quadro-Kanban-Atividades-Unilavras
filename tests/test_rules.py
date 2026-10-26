"""Testes das regras: conclusão (1, 2), prazos (3, 4, 7), pontuação (5), campos ausentes (6)."""
from datetime import datetime, timedelta

import pytest

from app.config import TZ
from app.models.activity import Activity
from app.services import rules as R


# 1 e 2 — seleção de disciplinas
@pytest.mark.parametrize("pct,expected", [(20, True), (70, True), (94, True), (94.9, True),
                                          (95, False), (95.0, False), (100, False)])
def test_course_eligibility(pct, expected):
    assert R.is_course_eligible(pct) is expected


@pytest.mark.parametrize("text,value", [("20%", 20.0), ("Concluído 94 %", 94.0), ("94,5%", 94.5),
                                        ("100% concluído", 100.0), (70, 70.0)])
def test_parse_percentage(text, value):
    assert R.parse_percentage(text) == value


@pytest.mark.parametrize("text", [None, "", "em andamento", "10% de 50%", "150%"])
def test_unknown_percentage_is_not_assumed(text):
    p = R.parse_percentage(text)
    assert p is None
    assert R.is_course_eligible(p) is None   # desconhecido: não presume < 95%


# 7 — datas no fuso de São Paulo
def test_parse_date_with_time(now):
    pd = R.parse_datetime_br("30/10/2026 23:59", now)
    assert pd.dt == datetime(2026, 10, 30, 23, 59, tzinfo=TZ)
    assert pd.has_time and not pd.ambiguous
    assert pd.dt.utcoffset() == timedelta(hours=-3)


def test_date_only_is_valid_until_end_of_day(now):
    pd = R.parse_datetime_br("26/10/2026", now)
    assert pd.dt == datetime(2026, 10, 26, 23, 59, 59, tzinfo=TZ)
    assert not pd.has_time
    assert R.due_state(pd.dt, now) != R.DUE_EXPIRED     # hoje, 14h: ainda vigente


@pytest.mark.parametrize("text,expected", [
    ("Prazo: 05/11/2026 às 18h30", datetime(2026, 11, 5, 18, 30, tzinfo=TZ)),
    ("Entrega até 5 de novembro de 2026, 18:30", datetime(2026, 11, 5, 18, 30, tzinfo=TZ)),
    ("Vencimento: 05.11.26", datetime(2026, 11, 5, 23, 59, 59, tzinfo=TZ)),
    ("2026-11-05T21:30:00Z", datetime(2026, 11, 5, 18, 30, tzinfo=TZ)),   # UTC -> São Paulo
    ("2026-11-05 18:30", datetime(2026, 11, 5, 18, 30, tzinfo=TZ)),
])
def test_date_formats(text, expected, now):
    assert R.parse_datetime_br(text, now).dt == expected


def test_date_without_year_is_flagged(now):
    pd = R.parse_datetime_br("Prazo: 10/11", now)
    assert pd.dt == datetime(2026, 11, 10, 23, 59, 59, tzinfo=TZ)
    assert pd.ambiguous


def test_invalid_date():
    pd = R.parse_datetime_br("31/02/2026")
    assert pd.dt is None and pd.ambiguous


def test_extract_due_prefers_label(now):
    t = "Publicado em 01/10/2026. Prazo de entrega: 10/11/2026 23:00. Vale 10 pontos"
    assert R.extract_due(t, now).dt == datetime(2026, 11, 10, 23, 0, tzinfo=TZ)


def test_extract_due_interval_uses_end(now):
    t = "Disponível de 01/10/2026 até 12/11/2026 às 23:59"
    assert R.extract_due(t, now).dt == datetime(2026, 11, 12, 23, 59, tzinfo=TZ)


# 3 e 4 — prazos futuros e expirados
def test_due_states(now):
    assert R.due_state(None, now) == R.DUE_NONE
    assert R.due_state(now - timedelta(minutes=1), now) == R.DUE_EXPIRED
    assert R.due_state(now + timedelta(hours=47), now) == R.DUE_SOON
    assert R.due_state(now + timedelta(hours=49), now) == R.DUE_FUTURE


def test_future_activity_included(now):
    d = R.decide_inclusion(True, R.parse_datetime_br("30/10/2026 23:59", now), None, now)
    assert d.include and not d.needs_review


def test_expired_activity_excluded(now):
    d = R.decide_inclusion(True, R.parse_datetime_br("20/10/2026 23:59", now), "10 pontos", now)
    assert not d.include and d.reason == "prazo expirado"


def test_ambiguous_date_not_silently_discarded(now):
    d = R.decide_inclusion(True, R.ParsedDate(None, ambiguous=True, raw="Prazo: em breve"), None, now)
    assert d.include and d.needs_review


# 5 — sem prazo, mas com pontuação
def test_no_due_but_points_included(now):
    d = R.decide_inclusion(True, R.ParsedDate(None), "10 pontos", now)
    assert d.include


def test_no_due_no_points_excluded(now):
    assert not R.decide_inclusion(True, R.ParsedDate(None), None, now).include


def test_material_not_assessment():
    assert not R.looks_like_assessment("Videoaula 3 - Normalização", "Duração 12 min")
    assert R.looks_like_assessment("Questionário do Módulo 3", "")
    assert R.looks_like_assessment("Leitura complementar", "Vale 2 pontos")   # material com pontuação real


@pytest.mark.parametrize("text,expected", [
    ("Vale: 10", "10 pontos"), ("Vale 2,5 pontos", "2,5 pontos"), ("Pontuação: 10,0 pts", "10 pontos"),
    ("Valor: 1 ponto", "1 ponto"), ("Atividade de 15 pontos", "15 pontos"),
    ("Sua nota: 8 pontos. Vale 10 pontos", "10 pontos"),       # total, não a nota obtida
    ("Nota: 7/10", "10 pontos"),
    ("Sem pontuação informada", None),
])
def test_extract_points(text, expected):
    assert R.extract_points(text) == expected


# 6 — campos ausentes com "-"
def test_missing_fields_are_dash():
    a = Activity(portal_name="Questionário do Módulo 3", portal_course="Banco de Dados", portal_points="10 pontos")
    assert a.name == "Questionário do Módulo 3"
    assert a.course == "Banco de Dados"
    assert a.due_display == "-"
    assert a.points == "10 pontos"
    assert Activity().name == "-" and Activity().course == "-" and Activity().points == "-"


# 8 — chave de duplicatas
def test_source_key_stable_and_normalized():
    k1 = R.make_source_key("Banco de Dados", "Questionário  do Módulo 3")
    k2 = R.make_source_key("banco de dados", "Questionario do modulo 3")
    assert k1 == k2
    assert R.make_source_key("BD", "X", source_id="123") == R.make_source_key("Outra", "Y", source_id="123")
    assert R.source_id_from_url("https://x/y/content?id=98765&course=1") == "id=98765"
    assert R.source_id_from_url("https://x/cursos/12/atividades/45678") == "45678"
