"""Diálogos: atividades excluídas e resumo da atualização."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QListWidget, QListWidgetItem, QMessageBox, QVBoxLayout)

from app.models.activity import iso_to_dt
from app.ui.format import plural, relative_time, short_course
from app.ui.icons import icon
from app.ui.theme import COLORS
from app.ui.widgets import EmptyState, button, icon_label, label


class TrashDialog(QDialog):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle("Atividades excluídas")
        self.setMinimumSize(560, 440)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 18)
        lay.setSpacing(10)
        lay.addWidget(label("Atividades excluídas", "H2"))
        lay.addWidget(label("As que ainda existirem no portal voltam sozinhas na próxima atualização. "
                            "Você também pode restaurá-las agora.", "Muted", wrap=True))
        self.list = QListWidget()
        self.list.setSelectionMode(QListWidget.ExtendedSelection)
        self.list.itemDoubleClicked.connect(lambda *_: self._restore())
        self.empty = EmptyState("delete", "Nenhuma atividade excluída")
        lay.addWidget(self.list, 1)
        lay.addWidget(self.empty, 1)
        row = QHBoxLayout()
        self.purge_btn = button("Excluir definitivamente", "Danger", "delete", COLORS["danger"], on_click=self._purge)
        self.restore_all_btn = button("Restaurar todas", on_click=self._restore_all)
        self.restore_btn = button("Restaurar", "Primary", "restore", on_click=self._restore)
        row.addWidget(self.purge_btn)
        row.addStretch(1)
        row.addWidget(button("Fechar", "Ghost", on_click=self.accept))
        row.addWidget(self.restore_all_btn)
        row.addWidget(self.restore_btn)
        lay.addLayout(row)
        self._load()

    def _load(self) -> None:
        self.list.clear()
        items = self.ctx.db.list_activities(only_deleted=True)
        for a in items:
            it = QListWidgetItem(icon("dot", COLORS["subtle"], 14),
                                 f"{a.name}\n{short_course(a.course)} · excluída {relative_time(iso_to_dt(a.deleted_at))}")
            it.setData(Qt.UserRole, a.id)
            self.list.addItem(it)
        empty = not items
        self.list.setVisible(not empty)
        self.empty.setVisible(empty)
        for b in (self.restore_btn, self.restore_all_btn, self.purge_btn):
            b.setEnabled(not empty)
        if items:
            self.list.setCurrentRow(0)

    def _selected(self) -> list[int]:
        return [it.data(Qt.UserRole) for it in self.list.selectedItems()]

    def _restore(self) -> None:
        for aid in self._selected():
            self.ctx.db.restore(aid)
        self.ctx.data_changed.emit()
        self._load()

    def _restore_all(self) -> None:
        for a in self.ctx.db.list_activities(only_deleted=True):
            self.ctx.db.restore(a.id)
        self.ctx.data_changed.emit()
        self._load()

    def _purge(self) -> None:
        ids = self._selected()
        if ids and QMessageBox.question(
                self, "Excluir definitivamente",
                f"Apagar {plural(len(ids), 'atividade', 'atividades')} para sempre, junto com suas observações?\n\n"
                "Se ainda existirem no portal, serão adicionadas de novo na próxima atualização.") == QMessageBox.Yes:
            for aid in ids:
                self.ctx.db.purge(aid)
            self._load()


class ReportDialog(QDialog):
    """Resumo detalhado da última atualização (aberto a partir da notificação)."""

    def __init__(self, report, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Resumo da atualização")
        self.setMinimumWidth(560)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 18)
        lay.setSpacing(12)
        if report.errors:
            ic, color, title = "error", COLORS["danger"], "A atualização não foi concluída"
        elif report.cancelled:
            ic, color, title = "warning", COLORS["warn"], "Atualização interrompida"
        else:
            ic, color, title = "check_circle", COLORS["ok"], "Atualização concluída"
        h = QHBoxLayout()
        h.addWidget(icon_label(ic, color, 20))
        h.addWidget(label(title, "H2"), 1)
        lay.addLayout(h)
        stats = QHBoxLayout()
        stats.setSpacing(10)
        for n, txt in ((report.added + report.restored, "novas"), (report.updated, "alteradas"),
                       (report.unchanged, "sem mudança"), (len(report.courses_processed), "disciplinas")):
            box = QVBoxLayout()
            box.setSpacing(0)
            box.addWidget(label(str(n), "TileValue"))
            box.addWidget(label(txt, "Small"))
            stats.addLayout(box)
            stats.addSpacing(18)
        stats.addStretch(1)
        lay.addLayout(stats)
        details = self.details(report)
        if details:
            txt = label("<br>".join(details), wrap=True)
            txt.setTextInteractionFlags(Qt.TextSelectableByMouse)
            txt.setStyleSheet(f"background:white;border:1px solid {COLORS['border']};border-radius:10px;padding:12px;")
            lay.addWidget(txt)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(button("Fechar", "Primary", on_click=self.accept))
        lay.addLayout(row)

    @staticmethod
    def details(r) -> list[str]:
        out = []
        for e in r.errors:
            out.append(f"<b>Erro:</b> {e}".replace("\n", "<br>"))
        if r.added_names:
            out.append("<b>Novas:</b> " + ", ".join(r.added_names[:8]) + ("…" if len(r.added_names) > 8 else ""))
        if r.restored:
            out.append(f"<b>Voltaram ao quadro:</b> {r.restored} (tinham sido excluídas e continuam no portal)")
        for d, old, new in r.due_changes:
            out.append(f"<b>Prazo alterado</b> — {d}: {old} → {new}")
        for d, _f in r.conflicts:
            out.append(f"<b>Revisar</b> — {d}: o portal mudou um campo que você editou")
        if r.not_found:
            out.append(f"<b>Não encontradas no portal:</b> {r.not_found} (continuam no quadro)")
        if r.courses_skipped:
            out.append("<b>Ignoradas (≥ 95% concluídas):</b> " + ", ".join(short_course(c) for c in r.courses_skipped))
        for c in r.courses_unknown:
            out.append(f"<b>Sem percentual de conclusão:</b> {short_course(c)}")
        for c, why in r.courses_failed:
            out.append(f"<b>Não verificada:</b> {short_course(c)} — {why}")
        for rv in r.review:
            out.append(f"<b>Conferir data:</b> {rv}")
        if r.cancelled:
            out.append("Você interrompeu a atualização. O que já tinha sido coletado foi salvo.")
        return out
