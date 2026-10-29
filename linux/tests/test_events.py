"""Eventos da Unilavras: leitura da lista pública, detalhes do even3, banco e aba Eventos."""
from datetime import date, datetime, timedelta

from app.automation.events_parser import is_truncated, parse_event_details, parse_events_list
from app.config import EVENTS_URL, TZ
from app.services.events import EventsUpdater

LIST_HTML = """
<div class="grid lg:grid-cols-3 gap-4 xl:gap-x-12">
  <div class="mb-6 lg:mb-4"><div class="relative block bg-white rounded-lg shadow-lg"><div class="p-2">
    <h5 class="font-bold text-2sm mb-1 pt-4">Palestra - Entre a pesquisa e a pr&aacute;tica: as experi&ecirc;ncias de...</h5>
    <p class="text-gray-500 mb-4 text-2sm">Data: <b><u>29/10/2026</u></b></p>
    <a href="https://even3.com.br/palestra2026" target="_blank" class="inline-block">Saiba mais</a>
  </div></div></div>
  <div class="mb-6 lg:mb-4"><div class="relative block bg-white rounded-lg shadow-lg"><div class="p-2">
    <h5 class="font-bold text-2sm mb-1 pt-4">Visita Técnica Unilavras - Congonhas e Ouro Preto</h5>
    <p class="text-gray-500 mb-4 text-2sm">Data: <b><u>06/11/2026</u></b></p>
    <a href="https://even3.com.br/visita2026" target="_blank" class="inline-block">Saiba mais</a>
  </div></div></div>
</div>
"""

DETAIL_HTML = """<html><head><title>Palestra completa</title>
<meta property="og:title" content="Palestra - Entre a pesquisa e a pr&#225;tica: as experi&#234;ncias de um mestrado" />
<script type="application/ld+json">{"@context":"https://schema.org","@type":"Event",
"name":"Palestra - Entre a pesquisa e a prática: as experiências de um mestrado profissional",
"startDate":"2026-10-29T19:00:00.000-03:00","endDate":"2026-10-29T00:0021:00:00.000-03:00",
"location":{"@type":"Place","name":"Auditório","address":{"@type":"PostalAddress","addressLocality":"Lavras"}},
"description":"Palestra on-line com convidada."}</script></head><body></body></html>"""


def fake_fetch(pages: dict):
    calls = []

    def fetch(url):
        calls.append(url)
        if url not in pages:
            raise OSError("404")
        return pages[url]
    fetch.calls = calls
    return fetch


def test_parse_events_list_reads_cards():
    evs = parse_events_list(LIST_HTML)
    assert [e.date for e in evs] == ["2026-10-29", "2026-11-06"]
    assert evs[0].title.startswith("Palestra - Entre a pesquisa e a prática") and is_truncated(evs[0].title)
    assert evs[0].url == "https://even3.com.br/palestra2026" and evs[0].key == evs[0].url
    assert parse_events_list("<html>sem eventos</html>") == []


def test_parse_event_details_structured_data():
    info = parse_event_details(DETAIL_HTML)
    assert info["title"].endswith("mestrado profissional")
    assert info["start_at"].startswith("2026-10-29T19:00")
    assert "end_at" not in info                           # data de término malformada é ignorada
    assert info["location"] == "Auditório · Lavras" and info["description"] == "Palestra on-line com convidada."
    assert parse_event_details("<title>Só título</title>") == {"title": "Só título"}


def test_updater_saves_and_reuses_details(db):
    fetch = fake_fetch({EVENTS_URL: LIST_HTML, "https://even3.com.br/palestra2026": DETAIL_HTML})
    r = EventsUpdater(db, fetch=fetch, delay_s=0).run()
    assert (r.found, r.new, r.details_failed, r.errors) == (2, 2, 1, [])
    evs = db.list_portal_events()
    assert evs[0].title.endswith("mestrado profissional") and evs[0].time == "19:00"
    assert evs[1].location is None and evs[1].time is None
    fetch.calls.clear()
    r2 = EventsUpdater(db, fetch=fetch, delay_s=0).run()
    assert r2.new == 0
    assert "https://even3.com.br/palestra2026" not in fetch.calls          # já detalhado: não abre de novo
    assert db.list_portal_events()[0].first_seen == evs[0].first_seen


def test_updater_removes_events_no_longer_listed_and_keeps_data_on_error(db):
    EventsUpdater(db, fetch=fake_fetch({EVENTS_URL: LIST_HTML}), delay_s=0).run()
    one = LIST_HTML.split('<div class="mb-6 lg:mb-4">')
    EventsUpdater(db, fetch=fake_fetch({EVENTS_URL: one[0] + '<div class="mb-6 lg:mb-4">' + one[2]}), delay_s=0).run()
    assert [e.date for e in db.list_portal_events()] == ["2026-11-06"]
    r = EventsUpdater(db, fetch=fake_fetch({}), delay_s=0).run()          # site fora do ar
    assert r.errors and len(db.list_portal_events()) == 1


def test_network_is_blocked_in_tests(db):
    r = EventsUpdater(db, delay_s=0).run()
    assert r.errors and "conexão" in r.errors[0]


# ------------------------------------------------------------------ interface

def _seed(db, days_ahead=(1, 20)):
    from app.models.events import PortalEvent
    today = datetime.now(TZ).date()
    db.replace_portal_events([
        PortalEvent(key=f"https://even3.com.br/e{i}", title=f"Evento {i}", date=(today + timedelta(days=d)).isoformat(),
                    url=f"https://even3.com.br/e{i}", start_at=datetime.combine(today + timedelta(days=d),
                                                                                 datetime.min.time().replace(hour=19),
                                                                                 TZ).isoformat(),
                    location="Lavras")
        for i, d in enumerate(days_ahead)] + [
        PortalEvent(key="passado", title="Evento passado", date=(today - timedelta(days=2)).isoformat())])
    return today


def test_events_page_lists_future_and_adds_to_agenda(qapp, db):
    from app.ui.context import AppContext
    from app.ui.events_page import EventCard, EventsPage
    ctx = AppContext(db)
    _seed(db)
    page = EventsPage(ctx)
    cards = page.findChildren(EventCard)
    assert sorted(c.ev.title for c in cards) == ["Evento 0", "Evento 1"]   # evento passado não aparece
    page._set_filter("week")
    assert [e.title for e in page.visible_events(datetime.now(TZ))] == ["Evento 0"]
    page.add_to_agenda(page.visible_events(datetime.now(TZ))[0])
    items = db.list_agenda_items()
    assert len(items) == 1 and items[0].category == "Evento" and items[0].start_time == "19:00"
    page.add_to_agenda(page.visible_events(datetime.now(TZ))[0])          # não duplica
    assert len(db.list_agenda_items()) == 1
    card = next(c for c in page.findChildren(EventCard) if c.ev.title == "Evento 0")
    assert card.agenda_btn.text() == "Na agenda" and not card.agenda_btn.isEnabled()


def test_event_date_helpers():
    from app.models.events import PortalEvent
    ev = PortalEvent(key="k", title="t", date="2026-11-14", start_at="2026-11-14T03:30:00-03:00")
    assert ev.day == date(2026, 11, 14) and ev.time == "03:30"
    assert PortalEvent(key="k", title="t", date="2026-11-14", start_at="2026-10-01T10:00:00-03:00").time is None
    assert ev.is_upcoming(date(2026, 11, 14)) and not ev.is_upcoming(date(2026, 11, 15))
