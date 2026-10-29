"""Aba Sobre: para que serve o aplicativo, o que ele faz e quem o criou."""
from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from app.config import APP_AUTHOR, APP_AUTHOR_EMAIL, APP_NAME, APP_VERSION, resource_path
from app.ui.settings_page import section
from app.ui.theme import COLORS
from app.ui.widgets import button, icon_label, label

FEATURES = (
    ("board", "Quadro de Atividades", "Atividades e avaliações da Sala de Aula Virtual organizadas em A fazer, "
                                      "Em andamento e Concluídas, com prazos e pontuação."),
    ("calendar", "Calendário", "Prazos e encontros virtuais das matérias em andamento, mês a mês."),
    ("education", "Notas", "Grade de Notas de cada disciplina e resultados do AVIN, questão por questão."),
    ("event", "Eventos", "Palestras, visitas técnicas e outros eventos da Unilavras com inscrições abertas."),
    ("agenda", "Agenda", "Seus compromissos, as provas e o AVIN (data do Planograma) junto com entregas, encontros "
                         "e eventos."),
)


class AboutPage(QWidget):
    def __init__(self, ctx=None, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        body.setObjectName("Page")
        body.setMaximumWidth(860)
        scroll.setWidget(body)
        outer.addWidget(scroll)
        lay = QVBoxLayout(body)
        lay.setContentsMargins(32, 26, 32, 28)
        lay.setSpacing(16)
        lay.addWidget(label("Sobre", "H1"))

        # ---- o aplicativo
        box, v = section(APP_NAME)
        head = QHBoxLayout()
        logo = QLabel()
        pm = QPixmap(str(resource_path("assets/icon.png")))
        if not pm.isNull():
            logo.setPixmap(pm.scaled(56, 56, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        head.addWidget(logo, 0, Qt.AlignTop)
        head.addSpacing(8)
        tv = QVBoxLayout()
        tv.setSpacing(6)
        tv.addWidget(label(
            f"O {APP_NAME} é o seu espaço de organização acadêmica na Unilavras. Ele reúne em um só lugar o que "
            "fica espalhado pelo portal do aluno: atividades e prazos da Sala de Aula Virtual, notas, encontros "
            "virtuais, eventos da instituição e a sua agenda pessoal.", wrap=True))
        tv.addWidget(label(
            "O aplicativo apenas lê o portal — nunca envia respostas, faz entregas ou altera algo por lá. "
            "Seus dados ficam somente neste computador, e a senha fica guardada no chaveiro do sistema "
            "(GNOME Keyring ou KWallet).", "Muted", wrap=True))
        head.addLayout(tv, 1)
        v.addLayout(head)
        v.addWidget(label(f"Versão {APP_VERSION}", "Small"))
        lay.addWidget(box)

        # ---- o que dá para fazer
        box, v = section("O que você encontra aqui")
        for ic, title, text in FEATURES:
            row = QHBoxLayout()
            row.setSpacing(12)
            row.addWidget(icon_label(ic, COLORS["primary"], 18), 0, Qt.AlignTop)
            tv = QVBoxLayout()
            tv.setSpacing(0)
            tv.addWidget(label(title, "H3"))
            tv.addWidget(label(text, "Muted", wrap=True))
            row.addLayout(tv, 1)
            v.addLayout(row)
        lay.addWidget(box)

        # ---- criador
        box, v = section("Criador", icon_name="user")
        v.addWidget(label(f"<b>{APP_AUTHOR}</b>"))
        mail = QHBoxLayout()
        mail.addWidget(label(f"E-mail: {APP_AUTHOR_EMAIL}", "Muted"))
        mail.addWidget(button("Enviar e-mail", "Link",
                              on_click=lambda: QDesktopServices.openUrl(QUrl(f"mailto:{APP_AUTHOR_EMAIL}"))))
        mail.addStretch(1)
        v.addLayout(mail)
        v.addWidget(label("Sugestões, dúvidas e relatos de problemas são bem-vindos por e-mail.", "Small", wrap=True))
        lay.addWidget(box)
        lay.addStretch(1)
