"""Persistência SQLite: criação do esquema, CRUD de atividades e metadados."""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from app.config import TZ
from app.models.activity import Activity, SEEN_MANUAL, STATUS_TODO, STATUSES, dt_to_iso

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS activities (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    source_key       TEXT NOT NULL UNIQUE,
    source_id        TEXT,
    origin           TEXT NOT NULL DEFAULT 'portal',
    portal_name      TEXT,
    portal_course    TEXT,
    portal_due_at    TEXT,
    portal_due_raw   TEXT,
    portal_points    TEXT,
    url              TEXT,
    user_name        TEXT,
    user_course      TEXT,
    user_due_at      TEXT,
    user_points      TEXT,
    status           TEXT NOT NULL DEFAULT 'todo',
    notes            TEXT NOT NULL DEFAULT '',
    position         REAL NOT NULL DEFAULT 0,
    first_seen       TEXT,
    last_checked     TEXT,
    last_seen_status TEXT NOT NULL DEFAULT 'encontrada',
    deleted_at       TEXT,
    conflicts        TEXT NOT NULL DEFAULT '[]',
    due_ambiguous    INTEGER NOT NULL DEFAULT 0,
    portal_hash      TEXT,
    updated_at       TEXT
);
CREATE INDEX IF NOT EXISTS ix_act_status ON activities(status);
CREATE INDEX IF NOT EXISTS ix_act_deleted ON activities(deleted_at);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS grade_snapshots (
    key        TEXT PRIMARY KEY,          -- "course:<id>" ou "avin:<id>"
    kind       TEXT NOT NULL,             -- "course" | "avin"
    payload    TEXT NOT NULL,             -- JSON
    sort_key   TEXT,                      -- data de início (ordem cronológica)
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS course_info (
    course_id  TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    start_date TEXT,
    progress   REAL,
    meetings   TEXT,                      -- JSON; NULL = ainda não lido
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS sync_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    outcome     TEXT,
    summary     TEXT
);
"""

COLUMNS = [
    "id", "source_key", "source_id", "origin", "portal_name", "portal_course", "portal_due_at",
    "portal_due_raw", "portal_points", "url", "user_name", "user_course", "user_due_at", "user_points",
    "status", "notes", "position", "first_seen", "last_checked", "last_seen_status", "deleted_at",
    "conflicts", "due_ambiguous", "updated_at",
]


class DatabaseError(RuntimeError):
    """Erro de leitura/escrita apresentável ao usuário."""


def now_iso() -> str:
    return dt_to_iso(datetime.now(TZ))


class Database:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self._lock = threading.RLock()
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(str(self.path), check_same_thread=False, isolation_level=None)
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA journal_mode=WAL")    # resiliente a fechamentos inesperados
            self.conn.execute("PRAGMA synchronous=NORMAL")
            self.conn.execute("PRAGMA foreign_keys=ON")
            self._init_schema()
        except sqlite3.Error as e:
            log.exception("Falha ao abrir banco")
            raise DatabaseError(f"Não foi possível abrir o banco de dados local: {e}") from e

    # ------------------------------------------------------------ infraestrutura
    def _init_schema(self) -> None:
        with self._lock:
            ver = self.conn.execute("PRAGMA user_version").fetchone()[0]
            self.conn.executescript(SCHEMA)
            if ver < SCHEMA_VERSION:
                # espaço para migrações futuras: if ver < 2: ALTER TABLE ...
                self.conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
            ok = self.conn.execute("PRAGMA quick_check").fetchone()[0]
            if ok != "ok":
                raise DatabaseError(f"O banco de dados parece corrompido ({ok}). Restaure um backup.")

    @contextmanager
    def transaction(self):
        with self._lock:
            try:
                self.conn.execute("BEGIN IMMEDIATE")
                yield self.conn
                self.conn.execute("COMMIT")
            except sqlite3.Error as e:
                self.conn.execute("ROLLBACK")
                log.exception("Erro de banco; transação desfeita")
                raise DatabaseError(f"Erro ao gravar no banco de dados: {e}") from e
            except BaseException:
                self.conn.execute("ROLLBACK")
                raise

    def close(self) -> None:
        with self._lock:
            try:
                self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except sqlite3.Error:
                pass
            self.conn.close()

    # ------------------------------------------------------------ meta
    def get_meta(self, key: str, default: Optional[str] = None) -> Optional[str]:
        with self._lock:
            r = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return r["value"] if r else default

    def set_meta(self, key: str, value: Optional[str]) -> None:
        with self.transaction() as c:
            c.execute("INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                      (key, value))

    # ------------------------------------------------------------ conversão
    @staticmethod
    def _row(r: sqlite3.Row) -> Activity:
        d = {k: r[k] for k in COLUMNS}
        d["conflicts"] = json.loads(d["conflicts"] or "[]")
        d["due_ambiguous"] = bool(d["due_ambiguous"])
        return Activity(**d)

    # ------------------------------------------------------------ consultas
    def list_activities(self, include_deleted: bool = False, only_deleted: bool = False) -> list[Activity]:
        q = "SELECT * FROM activities"
        if only_deleted:
            q += " WHERE deleted_at IS NOT NULL"
        elif not include_deleted:
            q += " WHERE deleted_at IS NULL"
        q += " ORDER BY position, id"
        with self._lock:
            return [self._row(r) for r in self.conn.execute(q)]

    def get(self, activity_id: int) -> Optional[Activity]:
        with self._lock:
            r = self.conn.execute("SELECT * FROM activities WHERE id=?", (activity_id,)).fetchone()
        return self._row(r) if r else None

    def get_by_key(self, key: str) -> Optional[Activity]:
        with self._lock:
            r = self.conn.execute("SELECT * FROM activities WHERE source_key=?", (key,)).fetchone()
        return self._row(r) if r else None

    def portal_hash(self, key: str) -> Optional[str]:
        with self._lock:
            r = self.conn.execute("SELECT portal_hash FROM activities WHERE source_key=?", (key,)).fetchone()
        return r["portal_hash"] if r else None

    # ------------------------------------------------------------ escrita
    def insert(self, a: Activity, conn: Optional[sqlite3.Connection] = None, portal_hash: Optional[str] = None) -> int:
        if a.status not in STATUSES:
            a.status = STATUS_TODO
        ts = now_iso()
        a.first_seen = a.first_seen or ts
        a.updated_at = ts
        cols = [c for c in COLUMNS if c != "id"]
        vals = [getattr(a, c) for c in cols]
        vals[cols.index("conflicts")] = a.conflicts_json()
        vals[cols.index("due_ambiguous")] = int(a.due_ambiguous)
        sql = f"INSERT INTO activities({','.join(cols)}, portal_hash) VALUES({','.join('?' * len(cols))}, ?)"
        if conn is not None:
            cur = conn.execute(sql, vals + [portal_hash])
        else:
            with self.transaction() as c:
                cur = c.execute(sql, vals + [portal_hash])
        a.id = cur.lastrowid
        return a.id

    def update_fields(self, activity_id: int, conn: Optional[sqlite3.Connection] = None, **fields) -> None:
        if not fields:
            return
        if "conflicts" in fields and not isinstance(fields["conflicts"], str):
            fields["conflicts"] = json.dumps(fields["conflicts"], ensure_ascii=False)
        if "due_ambiguous" in fields:
            fields["due_ambiguous"] = int(bool(fields["due_ambiguous"]))
        if "status" in fields and fields["status"] not in STATUSES:
            raise ValueError("status inválido")
        allowed = set(COLUMNS) | {"portal_hash"}
        bad = set(fields) - allowed
        if bad:
            raise ValueError(f"campos inválidos: {bad}")
        fields["updated_at"] = now_iso()
        sets = ",".join(f"{k}=?" for k in fields)
        args = list(fields.values()) + [activity_id]
        if conn is not None:
            conn.execute(f"UPDATE activities SET {sets} WHERE id=?", args)
        else:
            with self.transaction() as c:
                c.execute(f"UPDATE activities SET {sets} WHERE id=?", args)

    def create_manual(self, name: str, course: str, due_at: Optional[datetime], points: Optional[str],
                      status: str = STATUS_TODO, notes: str = "") -> int:
        import uuid
        a = Activity(source_key=f"manual-{uuid.uuid4().hex}", origin="manual",
                     user_name=name or None, user_course=course or None,
                     user_due_at=dt_to_iso(due_at), user_points=points or None,
                     status=status, notes=notes, last_seen_status=SEEN_MANUAL,
                     position=self.next_position(status))
        return self.insert(a)

    def next_position(self, status: str) -> float:
        with self._lock:
            r = self.conn.execute("SELECT MAX(position) FROM activities WHERE status=?", (status,)).fetchone()
        return (r[0] or 0) + 1

    def soft_delete(self, activity_id: int) -> None:
        self.update_fields(activity_id, deleted_at=now_iso())

    def restore(self, activity_id: int) -> None:
        self.update_fields(activity_id, deleted_at=None)

    def purge(self, activity_id: int) -> None:
        with self.transaction() as c:
            c.execute("DELETE FROM activities WHERE id=?", (activity_id,))

    def set_positions(self, ordered_ids: Iterable[int], status: str) -> None:
        with self.transaction() as c:
            for i, aid in enumerate(ordered_ids):
                c.execute("UPDATE activities SET position=?, status=?, updated_at=? WHERE id=?",
                          (float(i), status, now_iso(), aid))

    # ------------------------------------------------------------ notas
    def save_grade_snapshot(self, key: str, kind: str, payload: dict, sort_key: Optional[str]) -> None:
        """Grava (ou substitui) as notas mais recentes de uma disciplina ou de um AVIN."""
        with self.transaction() as c:
            c.execute("INSERT INTO grade_snapshots(key, kind, payload, sort_key, updated_at) VALUES(?,?,?,?,?) "
                      "ON CONFLICT(key) DO UPDATE SET kind=excluded.kind, payload=excluded.payload, "
                      "sort_key=excluded.sort_key, updated_at=excluded.updated_at",
                      (key, kind, json.dumps(payload, ensure_ascii=False), sort_key, now_iso()))

    def list_grade_snapshots(self) -> list[tuple[str, dict, Optional[str]]]:
        """[(kind, payload, updated_at)] em ordem cronológica de início."""
        with self._lock:
            rows = self.conn.execute("SELECT kind, payload, updated_at FROM grade_snapshots "
                                     "ORDER BY COALESCE(sort_key, '9999'), key").fetchall()
        out = []
        for r in rows:
            try:
                out.append((r["kind"], json.loads(r["payload"]), r["updated_at"]))
            except (TypeError, ValueError):
                log.warning("Registro de notas ilegível ignorado")
        return out

    # ------------------------------------------------------------ disciplinas e encontros virtuais
    def save_course_info(self, course_id: str, name: str, start_date: Optional[str], progress: Optional[float],
                         meetings: Optional[list] = None) -> None:
        """Atualiza nome/início/progresso; ``meetings=None`` mantém os encontros já conhecidos."""
        mj = json.dumps(meetings, ensure_ascii=False) if meetings is not None else None
        with self.transaction() as c:
            c.execute("INSERT INTO course_info(course_id, name, start_date, progress, meetings, updated_at) "
                      "VALUES(?,?,?,?,?,?) ON CONFLICT(course_id) DO UPDATE SET name=excluded.name, "
                      "start_date=excluded.start_date, progress=excluded.progress, "
                      "meetings=COALESCE(excluded.meetings, course_info.meetings), updated_at=excluded.updated_at",
                      (str(course_id), name, start_date, progress, mj, now_iso()))

    def list_course_info(self) -> list[dict]:
        with self._lock:
            rows = self.conn.execute("SELECT * FROM course_info ORDER BY COALESCE(start_date, '9999'), name").fetchall()
        out = []
        for r in rows:
            try:
                meetings = json.loads(r["meetings"]) if r["meetings"] else []
            except ValueError:
                meetings = []
            out.append({"course_id": r["course_id"], "name": r["name"], "start_date": r["start_date"],
                        "progress": r["progress"], "meetings": meetings})
        return out

    # ------------------------------------------------------------ histórico de sincronização
    def start_run(self) -> int:
        with self.transaction() as c:
            return c.execute("INSERT INTO sync_runs(started_at) VALUES(?)", (now_iso(),)).lastrowid

    def finish_run(self, run_id: int, outcome: str, summary: dict) -> None:
        with self.transaction() as c:
            c.execute("UPDATE sync_runs SET finished_at=?, outcome=?, summary=? WHERE id=?",
                      (now_iso(), outcome, json.dumps(summary, ensure_ascii=False), run_id))
