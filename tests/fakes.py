"""Cliente simulado do portal, com a mesma interface de PortalClient (dados no formato real observado)."""
from app.automation.portal import Cancelled, LoginFailed, SessionExpired, StructureChanged


def topic(tid, title, ttype=8, cat=5, deadline=None, grade=None, children=None, blocked=False):
    return {"id": tid, "title": title, "topicTypeId": ttype, "categoryTypeId": cat,
            "hasDeadline": deadline is not None, "deadlineAt": deadline, "hasGrade": grade is not None,
            "grade": {"value": grade}, "isBlockedContentByConditional": blocked, "children": children or []}


def contents(cid, name, topics, start="2026-10-05"):
    return {"context": {"academicMainId": cid, "academicMainName": name, "academicMainStartAt": start,
                        "progress": "40"}, "topics": topics}


COURSES = {"courses": [
    {"id": 1, "name": "Banco de Dados", "progress": "40", "startDate": "2026-10-05"},
    {"id": 2, "name": "Redes", "progress": "94", "startDate": "2026-10-05"},
    {"id": 3, "name": "Algoritmos", "progress": "95", "startDate": "2026-06-11"},
    {"id": 4, "name": "Cálculo", "progress": "100", "startDate": "2026-06-11"},
    {"id": 5, "name": "Ética", "progress": None, "startDate": "2026-06-11"},
], "nextPage": False}

CONTENTS = {
    "1": contents(1, "Banco de Dados", [
        topic(10, "Ciclo I", 1, 1, children=[
            topic(11, "Slides da aula", 3, 2),
            topic(12, "Questionário do Módulo 3", 15, 8, grade=10),                    # sem prazo, com pontos
            topic(13, "Lista de exercícios 1", 8, 5, deadline="2026-10-20 23:59:00", grade=4),  # expirada
            topic(14, "Trabalho prático", 8, 5, deadline="2026-11-10 23:59:00", grade=15),
        ]),
        topic(20, "Prova I: 12/11", 1, 1, blocked=True),
    ]),
    "2": contents(2, "Redes", [topic(30, "Desafio", 8, 5, deadline="2026-10-27 12:00:00", grade=3)]),
}


class FakeClient:
    def __init__(self, *, profile_dir=None, headless=True, labels=None, cancel=None, on_step=None, on_manual=None,
                 behaviour=None):
        self.cancel = cancel
        self.on_step = on_step or (lambda s: None)
        self.b = behaviour or {}
        self.lxp_base = "https://unilavrasedu.grupoa.education"
        self.logins = 0
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def check_cancel(self):
        if self.cancel is not None and self.cancel.is_set():
            raise Cancelled("cancelado")

    def login(self, creds):
        self.logins += 1
        if self.b.get("login_fail"):
            raise LoginFailed("O portal recusou o login: Usuário ou senha inválidos")
        self.on_step("Efetuando login")

    def open_classroom(self):
        if self.b.get("structure"):
            raise StructureChanged("Não encontrei a opção \"Sala de Aula Virtual\" no portal.")

    def list_courses(self):
        return [self.b.get("courses", COURSES)]

    def course_cards_text(self):
        return []

    def course_contents(self, course):
        self.check_cancel()
        self.calls.append(course.source_id)
        exp = self.b.get("expire_once")
        if exp == course.source_id and self.logins < 2:
            raise SessionExpired("expirou")
        if self.b.get("fail") == course.source_id:
            from app.automation.portal import AutomationError
            raise AutomationError("Abrir a disciplina: o portal não respondeu após 3 tentativas.")
        if self.b.get("cancel_after") == course.source_id:
            self.cancel.set()
        return CONTENTS[course.source_id]

    def save_diagnostic(self, *a):
        return None


def factory(**behaviour):
    holder = {}

    def make(**kw):
        holder["client"] = FakeClient(behaviour=behaviour, **kw)
        return holder["client"]
    make.holder = holder
    return make
