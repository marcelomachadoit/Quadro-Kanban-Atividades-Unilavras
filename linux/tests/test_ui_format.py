"""Textos voltados ao usuário: datas em linguagem natural, nomes curtos, urgência e agrupamento."""
from datetime import datetime

from app.config import TZ
from app.models.activity import Activity
from app.ui import format as F

NOW = datetime(2026, 10, 26, 14, 0, tzinfo=TZ)   # segunda-feira


def act(due=None, status="todo"):
    return Activity(portal_name="X", portal_course="BD", portal_due_at=due, status=status)


def test_friendly_due():
    assert F.friendly_due(None, NOW) == "Sem prazo"
    assert F.friendly_due(datetime(2026, 10, 26, 23, 59, tzinfo=TZ), NOW) == "Hoje, 23:59"
    assert F.friendly_due(datetime(2026, 10, 27, 23, 59, 59, tzinfo=TZ), NOW) == "Amanhã"   # só data
    assert F.friendly_due(datetime(2026, 10, 30, 23, 30, tzinfo=TZ), NOW) == "Sex, 30/10, 23:30"
    assert F.friendly_due(datetime(2026, 11, 12, 23, 59, 59, tzinfo=TZ), NOW) == "12/11"
    assert F.friendly_due(datetime(2027, 2, 1, 10, 0, tzinfo=TZ), NOW) == "01/02/2027, 10:00"


def test_urgency_levels_and_text_not_only_color():
    assert F.urgency(act("2026-10-25T10:00:00-03:00"), NOW) == F.URG_OVERDUE
    assert F.urgency(act("2026-10-27T10:00:00-03:00"), NOW) == F.URG_SOON
    assert F.urgency(act("2026-10-31T10:00:00-03:00"), NOW) == F.URG_WEEK
    assert F.urgency(act("2026-11-20T10:00:00-03:00"), NOW) == F.URG_LATER
    assert F.urgency(act(None), NOW) == F.URG_NONE
    assert F.urgency(act("2026-10-27T10:00:00-03:00", "done"), NOW) == F.URG_DONE
    assert "faltam 20 h" in F.due_pill_text(act("2026-10-27T10:00:00-03:00"), NOW)
    assert F.due_pill_text(act(None), NOW) == "Sem prazo"
    assert all(F.URGENCY_LABEL[u] for u in F.URGENCY_LABEL)


def test_short_course_and_color_stable():
    assert F.short_course("Estruturas de Dados (GRDESISL235)") == "Estruturas de Dados"
    assert F.short_course("Cálculo (Turma B)") == "Cálculo (Turma B)"     # parênteses comuns preservados
    assert F.course_color("Estruturas de Dados (GRDESISL235)") == F.course_color("Estruturas de Dados")


def test_points_and_groups():
    assert F.points_short("10 pontos") == "10 pts" and F.points_short("1 ponto") == "1 pt"
    assert F.points_short("-") == "" and F.points_short("2,5 pontos") == "2,5 pts"
    assert F.group_label(act("2026-10-26T23:00:00-03:00"), NOW) == "Hoje"
    assert F.group_label(act("2026-10-27T23:00:00-03:00"), NOW) == "Amanhã"
    assert F.group_label(act("2026-10-30T23:00:00-03:00"), NOW) == "Esta semana"
    assert F.group_label(act(None), NOW) == "Sem prazo"


def test_relative_time_and_greeting():
    assert F.relative_time(None, NOW) == "nunca"
    assert F.relative_time(datetime(2026, 10, 26, 13, 55, tzinfo=TZ), NOW) == "há 5 min"
    assert F.relative_time(datetime(2026, 10, 25, 9, 0, tzinfo=TZ), NOW) == "ontem às 09:00"
    assert F.greeting(NOW) == "Boa tarde"
