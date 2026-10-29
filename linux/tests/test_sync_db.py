"""Testes de persistência e atualização incremental (8–13)."""
from datetime import datetime

import pandas as pd

from app.config import TZ
from app.database.db import Database
from app.export import exporter
from app.models.activity import (SEEN_NOT_FOUND, STATUS_DOING, STATUS_DONE, ScrapedActivity)
from app.services.sync import SyncService, apply_user_edit, resolve_conflict


def act(name="Questionário 1", course="Banco de Dados", due=datetime(2026, 11, 5, 23, 59, tzinfo=TZ),
        points="10 pontos", url=None, sid=None):
    return ScrapedActivity(name=name, course=course, due_at=due, due_raw="05/11/2026 23:59" if due else "",
                           points=points, url=url, source_id=sid)


def test_insert_and_duplicates(db):
    r = SyncService(db).apply([act(), act(), act(name="Trabalho 2")], ["Banco de Dados"])
    assert (r.found, r.added) == (2, 2)
    r2 = SyncService(db).apply([act(), act(name="Trabalho 2")], ["Banco de Dados"])
    assert (r2.added, r2.unchanged, r2.updated) == (0, 2, 0)
    assert len(db.list_activities()) == 2


def test_duplicate_detected_by_source_id_even_if_renamed(db):
    SyncService(db).apply([act(sid="A1")], ["Banco de Dados"])
    r = SyncService(db).apply([act(name="Questionário 1 (revisado)", sid="A1")], ["Banco de Dados"])
    assert r.added == 0 and r.updated == 1
    assert db.list_activities()[0].name == "Questionário 1 (revisado)"


def test_legacy_record_without_id_is_not_duplicated(db):
    SyncService(db).apply([act()], ["Banco de Dados"])
    r = SyncService(db).apply([act(sid="NEW-ID-1")], ["Banco de Dados"])
    assert r.added == 0 and len(db.list_activities()) == 1


def test_incremental_update_preserves_status_and_notes(db):
    s = SyncService(db)
    s.apply([act()], ["Banco de Dados"])
    a = db.list_activities()[0]
    db.update_fields(a.id, status=STATUS_DOING, notes="Começar pelo exercício 3")
    r = s.apply([act(points="12 pontos"), act(name="Nova atividade")], ["Banco de Dados"])
    assert (r.added, r.updated) == (1, 1)
    a = db.get(a.id)
    assert a.status == STATUS_DOING
    assert a.notes == "Começar pelo exercício 3"
    assert a.points == "12 pontos"


def test_due_change_reported(db):
    s = SyncService(db)
    s.apply([act()], ["Banco de Dados"])
    r = s.apply([act(due=datetime(2026, 11, 8, 23, 59, tzinfo=TZ))], ["Banco de Dados"])
    assert r.due_changes == [("Questionário 1", "05/11/2026 23:59", "08/11/2026 23:59")]


def test_conflict_between_portal_and_manual_edit(db):
    s = SyncService(db)
    s.apply([act()], ["Banco de Dados"])
    a = db.list_activities()[0]
    apply_user_edit(db, a.id, a.name, a.course, datetime(2026, 11, 20, 12, 0, tzinfo=TZ), "15 pontos", a.status, "")
    r = s.apply([act(due=datetime(2026, 11, 8, 23, 59, tzinfo=TZ), points="10 pontos")], ["Banco de Dados"])
    a = db.get(a.id)
    assert a.due_at == datetime(2026, 11, 20, 12, 0, tzinfo=TZ)       # edição do usuário preservada
    assert a.points == "15 pontos"                                      # pontuação não mudou no portal
    assert [c["field"] for c in a.conflicts] == ["due_at"]
    assert ("Questionário 1", "due_at") in r.conflicts
    resolve_conflict(db, a.id, "due_at", accept_portal=True)
    a = db.get(a.id)
    assert a.conflicts == [] and a.due_at == datetime(2026, 11, 8, 23, 59, tzinfo=TZ)


def test_missing_activity_marked_not_deleted(db):
    s = SyncService(db)
    s.apply([act(), act(name="Outra", course="Redes")], ["Banco de Dados", "Redes"])
    # Redes falhou nesta coleta: suas atividades NÃO devem ser marcadas
    r = s.apply([], ["Banco de Dados"])
    assert r.not_found == 1
    by_name = {a.name: a for a in db.list_activities()}
    assert by_name["Questionário 1"].last_seen_status == SEEN_NOT_FOUND
    assert by_name["Outra"].last_seen_status != SEEN_NOT_FOUND
    assert len(by_name) == 2


def test_soft_delete_and_manual_restore(db):
    s = SyncService(db)
    s.apply([act()], ["Banco de Dados"])
    a = db.list_activities()[0]
    db.soft_delete(a.id)
    assert db.list_activities() == [] and len(db.list_activities(only_deleted=True)) == 1
    db.restore(a.id)
    assert len(db.list_activities()) == 1


def test_persistence_after_restart(db_path):
    d = Database(db_path)
    SyncService(d).apply([act()], ["Banco de Dados"])
    a = d.list_activities()[0]
    d.update_fields(a.id, status=STATUS_DONE, notes="ok")
    mid = d.create_manual("Estudar prova", "Redes", None, "", notes="manual")
    d.close()
    d2 = Database(db_path)          # "reinicia" o aplicativo
    items = {x.id: x for x in d2.list_activities()}
    assert items[a.id].status == STATUS_DONE and items[a.id].notes == "ok"
    assert items[mid].name == "Estudar prova" and items[mid].points == "-"
    d2.close()


def test_export_csv_excel_and_backup(db, tmp_path):
    SyncService(db).apply([act(), act(name="Sem prazo", due=None)], ["Banco de Dados"])
    acts = db.list_activities()
    csv = exporter.export_csv(acts, tmp_path / "a.csv")
    df = pd.read_csv(csv, sep=";", encoding="utf-8-sig")
    assert list(df.columns) == exporter.EXPORT_COLUMNS and len(df) == 2
    assert "-" in df["Prazo de entrega"].tolist()
    xlsx = exporter.export_excel(acts, tmp_path / "a.xlsx")
    assert pd.read_excel(xlsx).shape[0] == 2
    bk = exporter.backup_database(db.conn, tmp_path / "b.db")
    assert exporter.validate_backup(bk) == 2


def test_deleted_activities_come_back_on_update(db):
    s = SyncService(db)
    s.apply([act(), act(name="Trabalho 2")], ["Banco de Dados"])
    first = db.list_activities()[0]
    db.update_fields(first.id, status=STATUS_DOING, notes="anotação")
    for a in db.list_activities():
        db.soft_delete(a.id)
    r = s.apply([act(), act(name="Trabalho 2")], ["Banco de Dados"])
    assert r.restored == 2 and r.added == 0                       # reinseridas, sem duplicar
    assert len(db.list_activities()) == 2 and db.list_activities(only_deleted=True) == []
    assert db.get(first.id).notes == "anotação"                   # trabalho manual preservado
    assert "Reinseridas no quadro" in r.summary_text()


def test_deleted_activity_missing_from_portal_stays_deleted(db):
    s = SyncService(db)
    s.apply([act(), act(name="Trabalho 2")], ["Banco de Dados"])
    a = db.list_activities()[0]
    db.soft_delete(a.id)
    s.apply([act(name="Trabalho 2")], ["Banco de Dados"])
    assert db.get(a.id).deleted_at is not None


def test_deleted_manual_activity_stays_deleted(db):
    mid = db.create_manual("Minha tarefa", "BD", None, "")
    db.soft_delete(mid)
    SyncService(db).apply([act()], ["Banco de Dados"])
    assert db.get(mid).deleted_at is not None


# ------------------------------------------------------------------ atividades já entregues no portal

def _grades(*books):
    return {"name": "Banco de Dados", "gradeCategories": [{"name": "Atividades avaliativas", "gradeBooks": [
        {"name": n, "value": None, "isCompleted": done, "submittedAt": sub} for n, done, sub in books]}]}


def test_submitted_activity_moves_to_done_even_before_deadline(db):
    from app.services.sync import apply_submissions
    SyncService(db).apply([act(name="Atividade teórica - Ciclo 2"), act(name="Desafio - Ciclo 2")], ["Banco de Dados"])
    moved = apply_submissions(db, "Banco de Dados", _grades(("Atividade teórica - Ciclo 2", True, "2026-10-20 10:00:00"),
                                                            ("Desafio - Ciclo 2", False, None)))
    assert moved == ["Atividade teórica - Ciclo 2"]
    by = {a.name: a for a in db.list_activities()}
    done = by["Atividade teórica - Ciclo 2"]
    assert done.status == STATUS_DONE and done.portal_completed
    assert done.portal_submitted_at.startswith("2026-10-20T10:00")
    assert done.due_at > datetime(2026, 10, 26, tzinfo=TZ)            # prazo ainda não chegou
    assert by["Desafio - Ciclo 2"].status == "todo"


def test_submission_respects_manual_move_back(db):
    from app.services.sync import apply_submissions
    SyncService(db).apply([act(name="Atividade teórica - Ciclo 2")], ["Banco de Dados"])
    g = _grades(("Atividade teórica - Ciclo 2", True, None))
    apply_submissions(db, "Banco de Dados", g)
    a = db.list_activities()[0]
    db.update_fields(a.id, status="todo")                             # usuário devolveu para A fazer
    assert apply_submissions(db, "Banco de Dados", g) == []           # não força de novo
    assert db.get(a.id).status == "todo"


def test_submission_matches_only_same_course_and_survives_restart(db_path):
    from app.services.sync import apply_submissions
    d = Database(db_path)
    SyncService(d).apply([act(name="Lista 1"), act(name="Lista 1", course="Redes")], ["Banco de Dados", "Redes"])
    apply_submissions(d, "Banco de Dados", _grades(("Lista 1", True, None)))
    d.close()
    d2 = Database(db_path)
    st = {a.course: (a.status, a.portal_completed) for a in d2.list_activities()}
    assert st == {"Banco de Dados": ("done", True), "Redes": ("todo", False)}
    d2.close()


def test_old_database_is_migrated(tmp_path):
    import sqlite3
    p = tmp_path / "antigo.db"
    c = sqlite3.connect(p)
    c.executescript("CREATE TABLE activities (id INTEGER PRIMARY KEY AUTOINCREMENT, source_key TEXT NOT NULL UNIQUE,"
                    " source_id TEXT, origin TEXT NOT NULL DEFAULT 'portal', portal_name TEXT, portal_course TEXT,"
                    " portal_due_at TEXT, portal_due_raw TEXT, portal_points TEXT, url TEXT, user_name TEXT,"
                    " user_course TEXT, user_due_at TEXT, user_points TEXT, status TEXT NOT NULL DEFAULT 'todo',"
                    " notes TEXT NOT NULL DEFAULT '', position REAL NOT NULL DEFAULT 0, first_seen TEXT,"
                    " last_checked TEXT, last_seen_status TEXT NOT NULL DEFAULT 'encontrada', deleted_at TEXT,"
                    " conflicts TEXT NOT NULL DEFAULT '[]', due_ambiguous INTEGER NOT NULL DEFAULT 0, portal_hash TEXT,"
                    " updated_at TEXT);"
                    "INSERT INTO activities(source_key, portal_name, notes) VALUES('k', 'Antiga', 'minha nota');"
                    "PRAGMA user_version=1;")
    c.close()
    d = Database(p)
    a = d.list_activities()[0]
    assert (a.name, a.notes, a.portal_completed) == ("Antiga", "minha nota", False)   # dados preservados
    d.close()
