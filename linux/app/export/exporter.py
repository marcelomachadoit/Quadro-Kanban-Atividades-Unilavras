"""Exportação (CSV/Excel), backup e restauração do banco local."""
from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd

from app.config import TZ
from app.models.activity import SEEN_LABELS, STATUS_LABELS, Activity, iso_to_dt

EXPORT_COLUMNS = ["Nome da atividade", "Disciplina", "Prazo de entrega", "Pontuação", "Status no quadro",
                  "URL de origem", "Última verificação", "Situação na última consulta", "Observações",
                  "Origem", "Divergências"]


def _fmt(iso) -> str:
    dt = iso_to_dt(iso)
    return dt.strftime("%d/%m/%Y %H:%M") if dt else "-"


def to_dataframe(activities: Iterable[Activity]) -> pd.DataFrame:
    rows = []
    for a in activities:
        rows.append({
            "Nome da atividade": a.name,
            "Disciplina": a.course,
            "Prazo de entrega": a.due_display,
            "Pontuação": a.points,
            "Status no quadro": STATUS_LABELS.get(a.status, a.status),
            "URL de origem": a.url or "-",
            "Última verificação": _fmt(a.last_checked),
            "Situação na última consulta": SEEN_LABELS.get(a.last_seen_status, a.last_seen_status),
            "Observações": a.notes or "",
            "Origem": "Portal" if a.origin == "portal" else "Manual",
            "Divergências": len(a.conflicts),
        })
    return pd.DataFrame(rows, columns=EXPORT_COLUMNS)


def export_csv(activities: Iterable[Activity], path: Path | str) -> Path:
    path = Path(path)
    # utf-8-sig + ';' abre corretamente no Excel em português
    to_dataframe(activities).to_csv(path, index=False, sep=";", encoding="utf-8-sig")
    return path


def export_excel(activities: Iterable[Activity], path: Path | str) -> Path:
    path = Path(path)
    df = to_dataframe(activities)
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        df.to_excel(xw, index=False, sheet_name="Atividades")
        ws = xw.sheets["Atividades"]
        widths = [44, 32, 18, 14, 16, 40, 18, 30, 40, 10, 12]
        for i, w in enumerate(widths):
            ws.column_dimensions[chr(65 + i)].width = w
        ws.freeze_panes = "A2"
    return path


def backup_database(conn: sqlite3.Connection, dest: Path | str) -> Path:
    """Cópia consistente (API de backup do SQLite) mesmo com o app aberto."""
    dest = Path(dest)
    target = sqlite3.connect(str(dest))
    try:
        conn.backup(target)
    finally:
        target.close()
    return dest


def validate_backup(path: Path | str) -> int:
    """Confere se o arquivo é um backup válido. Retorna a quantidade de atividades."""
    try:
        c = sqlite3.connect(f"file:{Path(path)}?mode=ro", uri=True)
        try:
            if c.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("arquivo corrompido")
            cols = {r[1] for r in c.execute("PRAGMA table_info(activities)")}
            if not {"source_key", "status", "portal_name", "user_name"} <= cols:
                raise ValueError("não é um backup do UniSpace")
            return c.execute("SELECT COUNT(*) FROM activities").fetchone()[0]
        finally:
            c.close()
    except sqlite3.DatabaseError as e:
        raise ValueError(f"arquivo inválido: {e}") from e


def restore_database(db_path: Path | str, backup_path: Path | str) -> Path:
    """Substitui o banco pelo backup. Antes guarda uma cópia de segurança do banco atual.
    O chamador deve fechar a conexão atual antes e reabrir depois."""
    db_path, backup_path = Path(db_path), Path(backup_path)
    validate_backup(backup_path)
    safety = db_path.with_name(f"antes-da-restauracao-{datetime.now(TZ):%Y%m%d-%H%M%S}.db")
    if db_path.exists():
        shutil.copy2(db_path, safety)
    for suffix in ("-wal", "-shm"):
        p = Path(str(db_path) + suffix)
        if p.exists():
            p.unlink()
    shutil.copy2(backup_path, db_path)
    return safety
