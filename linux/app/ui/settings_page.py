"""Configurações: conta do portal, atualização, dados e opções avançadas."""
from __future__ import annotations

import os
from datetime import datetime

from PySide6.QtCore import QStandardPaths, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QLineEdit, QMessageBox,
                               QScrollArea, QVBoxLayout, QWidget)

from app.config import DATA_DIR, DB_PATH, LOG_DIR, PORTAL_LOGIN_URL, TZ
from app.export import exporter
from app.models.activity import iso_to_dt
from app.services.credentials import CredentialError, Credentials
from app.ui.format import relative_time
from app.ui.icons import icon
from app.ui.theme import COLORS
from app.ui.widgets import button, icon_label, label
from app.ui.workers import TestConnectionWorker


def section(title: str, subtitle: str = "", icon_name: str = "") -> tuple[QFrame, QVBoxLayout]:
    f = QFrame()
    f.setObjectName("Panel")
    v = QVBoxLayout(f)
    v.setContentsMargins(24, 20, 24, 20)
    v.setSpacing(10)
    h = QHBoxLayout()
    if icon_name:
        h.addWidget(icon_label(icon_name, COLORS["primary"], 16))
    h.addWidget(label(title, "H2"))
    h.addStretch(1)
    v.addLayout(h)
    if subtitle:
        v.addWidget(label(subtitle, "Muted", wrap=True))
    return f, v


class SettingsPage(QWidget):
    notify = Signal(str, object)

    def __init__(self, ctx, main_window=None, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.main = main_window
        self.setObjectName("Page")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        body.setObjectName("Page")
        lay = QVBoxLayout(body)
        lay.setContentsMargins(32, 26, 32, 28)
        lay.setSpacing(16)
        scroll.setWidget(body)
        outer.addWidget(scroll)
        body.setMaximumWidth(860)

        lay.addWidget(label("Configurações", "H1"))

        # ---- conta
        box, v = section("Conta do portal", icon_name="user")
        self.account_status = label("", wrap=True)
        v.addWidget(self.account_status)
        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.user = QLineEdit()
        self.user.setPlaceholderText("Seu usuário do portal")
        self.pwd = QLineEdit()
        self.pwd.setEchoMode(QLineEdit.Password)
        self.pwd.setPlaceholderText("Sua senha do portal")
        self._eye = self.pwd.addAction(icon("eye", COLORS["muted"]), QLineEdit.TrailingPosition)
        self._eye.setToolTip("Mostrar senha")
        self._eye.triggered.connect(self._toggle_pwd)
        form.addRow(label("Usuário", "FieldLabel"), self.user)
        form.addRow(label("Senha", "FieldLabel"), self.pwd)
        v.addLayout(form)
        row = QHBoxLayout()
        self.save_btn = button("Salvar", "Primary", "save", on_click=self.save_creds)
        self.test_btn = button("Testar conexão", "", "sync", on_click=self.test_connection)
        self.open_portal_btn = button("Abrir portal no navegador", "Ghost", "globe",
                                      tip="Abre o portal no seu navegador habitual — use quando o portal pedir "
                                          "verificação de segurança",
                                      on_click=lambda: QDesktopServices.openUrl(QUrl(PORTAL_LOGIN_URL)))
        self.clear_btn = button("Remover", "Danger", "delete", COLORS["danger"], on_click=self.clear_creds,
                                tip="Apagar usuário e senha deste computador")
        row.addWidget(self.save_btn)
        row.addWidget(self.test_btn)
        row.addWidget(self.open_portal_btn)
        row.addStretch(1)
        row.addWidget(self.clear_btn)
        v.addLayout(row)
        self.test_result = label("", wrap=True)
        self.test_result.hide()
        v.addWidget(self.test_result)
        v.addWidget(label("🔒  Sua senha fica no chaveiro do sistema (GNOME Keyring ou KWallet). Ela nunca é gravada em "
                          "arquivos nem nos registros do aplicativo.", "Small", wrap=True))
        self.user.returnPressed.connect(lambda: self.pwd.setFocus())
        self.pwd.returnPressed.connect(self.save_creds)
        lay.addWidget(box)

        # ---- atualização
        box, v = section("Atualização", icon_name="sync")
        self.show_browser = QCheckBox("Mostrar a janela do navegador durante a atualização")
        self.show_browser.setChecked(self.ctx.show_browser)
        self.show_browser.toggled.connect(lambda c: setattr(self.ctx, "show_browser", c))
        v.addWidget(self.show_browser)
        v.addWidget(label("Normalmente a atualização roda em segundo plano. Ative só se a sua conta usar login "
                          "Microsoft 365 ou verificação em duas etapas, para concluí-las na janela do navegador.",
                          "Small", wrap=True))
        lay.addWidget(box)

        # ---- dados
        box, v = section("Seus dados", "Tudo fica salvo neste computador. Exporte uma planilha ou guarde uma cópia "
                                       "de segurança.", "folder")
        r3 = QHBoxLayout()
        r3.addWidget(button("Exportar para Excel", "", "download", on_click=self.export_xlsx))
        r3.addWidget(button("Exportar CSV", "", "download", on_click=self.export_csv))
        r3.addSpacing(12)
        r3.addWidget(button("Fazer backup", "", "save", on_click=self.backup))
        self.restore_btn = button("Restaurar backup", "", "restore", on_click=self.restore)
        r3.addWidget(self.restore_btn)
        r3.addStretch(1)
        v.addLayout(r3)
        lay.addWidget(box)

        # ---- avançado (recolhido)
        self.adv_toggle = button("Avançado", "Ghost", "chevron_right", on_click=self._toggle_advanced)
        lay.addWidget(self.adv_toggle, 0, Qt.AlignLeft)
        self.adv, v = section("Avançado", "Use somente se o portal mudar os nomes dos botões. A automação procura "
                                          "exatamente estes textos.")
        f2 = QFormLayout()
        labels = self.ctx.labels()
        self.lbl_class = QLineEdit(labels.classroom_tile)
        self.lbl_courses = QLineEdit(labels.courses_menu)
        f2.addRow(label("Botão da sala de aula", "FieldLabel"), self.lbl_class)
        f2.addRow(label("Menu de disciplinas", "FieldLabel"), self.lbl_courses)
        v.addLayout(f2)
        r2 = QHBoxLayout()
        r2.addWidget(button("Salvar nomes", on_click=self.save_labels))
        r2.addWidget(button("Restaurar padrão", "Ghost", on_click=self.reset_labels))
        r2.addStretch(1)
        v.addLayout(r2)
        v.addSpacing(8)
        v.addWidget(label(f"Banco de dados: {DB_PATH}", "Small", wrap=True))
        r4 = QHBoxLayout()
        r4.addWidget(button("Abrir pasta de dados", "Link",
                            on_click=lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(DATA_DIR)))))
        r4.addWidget(button("Abrir registros (logs)", "Link",
                            on_click=lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(LOG_DIR)))))
        r4.addStretch(1)
        v.addLayout(r4)
        self.adv.hide()
        lay.addWidget(self.adv)
        lay.addStretch(1)

        self._worker = None
        self.load()

    # ------------------------------------------------------------------ conta
    def load(self) -> None:
        try:
            c = self.ctx.creds.load()
        except CredentialError as e:
            c = None
            self._result(False, str(e))
        self.user.setText(c.username if c else (self.ctx.creds.username() or ""))
        self.pwd.setText(c.password if c else "")
        self._refresh_auth()

    def _refresh_auth(self) -> None:
        user = self.ctx.creds.username()
        last = iso_to_dt(self.ctx.db.get_meta("last_auth_success"))
        if not user:
            self.account_status.setText(f"<span style='color:{COLORS['muted']}'>Nenhuma conta conectada ainda.</span>")
        elif last:
            self.account_status.setText(f"<span style='color:{COLORS['ok']}'>●</span>  Conectado como <b>{user}</b> · "
                                        f"último acesso ao portal {relative_time(last)}")
        else:
            self.account_status.setText(f"<span style='color:{COLORS['warn']}'>●</span>  Conta <b>{user}</b> salva · "
                                        "ainda não testada")

    def _toggle_pwd(self) -> None:
        hidden = self.pwd.echoMode() == QLineEdit.Password
        self.pwd.setEchoMode(QLineEdit.Normal if hidden else QLineEdit.Password)
        self._eye.setIcon(icon("eye_off" if hidden else "eye", COLORS["muted"]))
        self._eye.setToolTip("Ocultar senha" if hidden else "Mostrar senha")

    def _result(self, ok: bool, msg: str) -> None:
        fg, bg = (COLORS["ok_text"], COLORS["ok_bg"]) if ok else (COLORS["danger_text"], COLORS["danger_bg"])
        self.test_result.setStyleSheet(f"color:{fg};background:{bg};border-radius:8px;padding:10px;")
        self.test_result.setText(msg)
        self.test_result.show()

    def save_creds(self) -> bool:
        try:
            self.ctx.creds.save(self.user.text(), self.pwd.text())
        except CredentialError as e:
            self._result(False, str(e))
            return False
        self.test_result.hide()
        self._refresh_auth()
        self.ctx.data_changed.emit()
        self.notify.emit("Conta salva com segurança", None)
        return True

    def clear_creds(self) -> None:
        if QMessageBox.question(self, "Remover conta",
                                "Remover o usuário e a senha salvos neste computador?\n"
                                "Suas atividades continuam no quadro.") == QMessageBox.Yes:
            self.ctx.creds.clear()
            self.user.clear()
            self.pwd.clear()
            self.test_result.hide()
            self._refresh_auth()
            self.ctx.data_changed.emit()
            self.notify.emit("Conta removida", None)

    def test_connection(self) -> None:
        if not self.user.text().strip() or not self.pwd.text():
            self._result(False, "Preencha usuário e senha.")
            return
        if self.main and self.main.update_running():
            self._result(False, "Aguarde a atualização em andamento terminar.")
            return
        self.test_btn.setEnabled(False)
        self.test_btn.setText("Testando…")
        self.test_result.hide()
        self._worker = TestConnectionWorker(self.ctx, Credentials(self.user.text().strip(), self.pwd.text()), self)
        self._worker.done.connect(self._tested)
        self._worker.start()

    def _tested(self, ok: bool, msg: str) -> None:
        self.test_btn.setEnabled(True)
        self.test_btn.setText("Testar conexão")
        self._result(ok, ("✓  " if ok else "") + msg)
        self._refresh_auth()

    # ------------------------------------------------------------------ avançado
    def _toggle_advanced(self) -> None:
        show = not self.adv.isVisible()
        self.adv.setVisible(show)
        self.adv_toggle.setIcon(icon("chevron_down" if show else "chevron_right", COLORS["text_2"]))

    def save_labels(self) -> None:
        self.ctx.db.set_meta("label_classroom", self.lbl_class.text().strip() or None)
        self.ctx.db.set_meta("label_courses", self.lbl_courses.text().strip() or None)
        self.notify.emit("Nomes salvos", None)

    def reset_labels(self) -> None:
        self.ctx.db.set_meta("label_classroom", None)
        self.ctx.db.set_meta("label_courses", None)
        labels = self.ctx.labels()
        self.lbl_class.setText(labels.classroom_tile)
        self.lbl_courses.setText(labels.courses_menu)

    # ------------------------------------------------------------------ dados
    def _stamp(self) -> str:
        return datetime.now(TZ).strftime("%Y-%m-%d_%H%M")

    def _ask_save(self, title: str, name: str, filt: str):
        docs = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)   # segue o xdg-user-dirs
        base = docs if docs and os.path.isdir(docs) else os.path.expanduser("~")
        path, _ = QFileDialog.getSaveFileName(self, title, os.path.join(base, name), filt)
        return path

    def export_xlsx(self) -> None:
        path = self._ask_save("Exportar para Excel", f"atividades_{self._stamp()}.xlsx", "Planilha Excel (*.xlsx)")
        if path:
            self._run(lambda: exporter.export_excel(self.ctx.db.list_activities(), path), "Planilha exportada", path)

    def export_csv(self) -> None:
        path = self._ask_save("Exportar para CSV", f"atividades_{self._stamp()}.csv", "CSV (*.csv)")
        if path:
            self._run(lambda: exporter.export_csv(self.ctx.db.list_activities(), path), "Arquivo CSV exportado", path)

    def backup(self) -> None:
        path = self._ask_save("Salvar backup", f"unispace_backup_{self._stamp()}.db", "Backup UniSpace (*.db)")
        if path:
            self._run(lambda: exporter.backup_database(self.ctx.db.conn, path), "Backup salvo", path)

    def restore(self) -> None:
        if self.main and self.main.update_running():
            QMessageBox.information(self, "Restaurar backup", "Aguarde a atualização em andamento terminar.")
            return
        path, _ = QFileDialog.getOpenFileName(self, "Restaurar backup", os.path.expanduser("~"),
                                              "Backup UniSpace (*.db)")
        if not path:
            return
        try:
            n = exporter.validate_backup(path)
        except ValueError as e:
            QMessageBox.critical(self, "Restaurar backup", f"Não foi possível usar este arquivo: {e}")
            return
        if QMessageBox.question(self, "Restaurar backup",
                                f"O backup tem {n} atividade(s) e vai substituir os dados atuais.\n"
                                "Antes disso, uma cópia dos dados atuais é guardada automaticamente. Continuar?") \
                != QMessageBox.Yes:
            return
        try:
            self.ctx.db.close()
            exporter.restore_database(DB_PATH, path)
            ok = True
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Restaurar backup", f"Falha ao restaurar: {e}")
            ok = False
        self.ctx.reopen_db()
        if ok:
            self.notify.emit("Backup restaurado", None)

    def _run(self, fn, ok_msg: str, path: str) -> None:
        try:
            fn()
        except PermissionError:
            QMessageBox.critical(self, "Não foi possível salvar",
                                 "Sem permissão para gravar o arquivo. Ele pode estar aberto em outro programa "
                                 "(como o Excel).")
            return
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Erro", str(e))
            return
        folder = os.path.dirname(path)
        self.notify.emit(ok_msg, ("Abrir pasta", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(folder))))
