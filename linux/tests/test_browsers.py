"""Escolha do navegador no Linux: Chrome > Chromium > Firefox > Edge, pulando os que não abrem."""
from pathlib import Path

import pytest
from playwright.sync_api import Error as PWError

from app.automation import browsers as B
from app.automation.portal import BrowserUnavailable, PortalClient


@pytest.fixture(autouse=True)
def _no_snap_no_chromium(monkeypatch, tmp_path):
    monkeypatch.setattr(B, "SNAP_BIN", tmp_path / "snap-bin")      # sem snaps instalados
    monkeypatch.setattr(B.shutil, "which", lambda name: None)       # sem Chromium no PATH


def test_order_on_linux():
    assert [b.key for b in B.candidates("linux")] == ["chrome", "chromium", "firefox", "edge"]
    assert B.candidates("win32") == [] and B.candidates("darwin") == []      # versão só para Linux


def test_profiles_are_separate_and_chrome_keeps_the_original():
    base = Path("dados") / "chrome-profile"
    by = {b.key: B.profile_dir(base, b) for b in B.BROWSERS}
    assert by["chrome"] == base
    assert by["edge"] == Path("dados") / "browser-profile-edge" and len(set(by.values())) == 4


def test_snap_browsers_keep_the_profile_where_the_snap_can_read(monkeypatch, tmp_path):
    (tmp_path / "snap-bin").mkdir()
    (tmp_path / "snap-bin" / "firefox").touch()
    monkeypatch.setattr(B.Path, "home", lambda: tmp_path / "casa")
    base = Path("dados") / "chrome-profile"
    by = {b.key: B.profile_dir(base, b) for b in B.BROWSERS}
    assert by["firefox"] == tmp_path / "casa" / "snap" / "firefox" / "common" / "unispace-profile"
    assert by["chromium"] == Path("dados") / "browser-profile-chromium"      # Chromium não está em snap
    assert by["chrome"] == base


def test_launch_args_only_chromium_gets_chrome_flags():
    by = {b.key: b.launch_args for b in B.BROWSERS}
    assert by["chrome"]["channel"] == "chrome" and "args" in by["chrome"]
    assert by["edge"]["channel"] == "msedge"
    assert by["firefox"] == {"channel": "moz-firefox"}
    assert "channel" not in by["chromium"] and "args" in by["chromium"]


def test_chromium_uses_the_executable_found_in_path(monkeypatch):
    found = {"/snap/bin/chromium": "/snap/bin/chromium"}
    monkeypatch.setattr(B.shutil, "which", found.get)
    chromium = next(b for b in B.BROWSERS if b.key == "chromium")
    assert chromium.launch_args["executable_path"] == "/snap/bin/chromium"


def test_first_available_skips_missing_browsers():
    tried = []

    def open_with(choice):
        tried.append(choice.key)
        if choice.key != "edge":
            raise PWError(f"Chromium distribution '{choice.channel}' is not found")
        return "contexto"
    result, choice = B.first_available(open_with, platform="linux")
    assert (result, choice.key) == ("contexto", "edge")
    assert tried == ["chrome", "chromium", "firefox", "edge"]


def test_first_available_reports_every_failure():
    def open_with(choice):
        raise PWError(f"{choice.label} ausente\ndetalhes longos")
    with pytest.raises(LookupError) as e:
        B.first_available(open_with, platform="linux")
    assert str(e.value) == ("Google Chrome: Google Chrome ausente; Chromium: Chromium ausente; "
                            "Mozilla Firefox: Mozilla Firefox ausente; Microsoft Edge: Microsoft Edge ausente")


class _Engine:
    def __init__(self, log, name, ok_channels):
        self.log, self.name, self.ok = log, name, ok_channels

    def launch_persistent_context(self, profile, **kw):
        self.log.append((self.name, kw.get("channel"), Path(profile).name))
        if kw.get("channel") not in self.ok:
            raise PWError("Executable doesn't exist")
        return _Ctx()


class _Ctx:
    pages = []

    def set_default_timeout(self, ms):
        pass

    def set_default_navigation_timeout(self, ms):
        pass

    def new_page(self):
        return "página"

    def close(self):
        pass


class _PW:
    def __init__(self, ok_channels):
        self.log = []
        self.chromium = _Engine(self.log, "chromium", ok_channels)
        self.firefox = _Engine(self.log, "firefox", ok_channels)
        self.webkit = _Engine(self.log, "webkit", ok_channels)
        self.stopped = False

    def stop(self):
        self.stopped = True


def _client(monkeypatch, tmp_path, pw):
    from app.automation import portal
    monkeypatch.setattr(portal, "sync_playwright", lambda: type("S", (), {"start": lambda self: pw})())
    monkeypatch.setattr(B.sys, "platform", "linux")
    return PortalClient(tmp_path / "chrome-profile", headless=True)


def test_portal_falls_back_to_edge_without_other_browsers(monkeypatch, tmp_path):
    pw = _PW(ok_channels={"msedge"})
    c = _client(monkeypatch, tmp_path, pw)
    c.start()
    assert c.browser.key == "edge" and c.portal == "página"
    assert pw.log == [("chromium", "chrome", "chrome-profile"), ("chromium", None, "browser-profile-chromium"),
                      ("firefox", "moz-firefox", "browser-profile-firefox"),
                      ("chromium", "msedge", "browser-profile-edge")]
    assert (tmp_path / "browser-profile-edge").is_dir()


def test_portal_prefers_chrome(monkeypatch, tmp_path):
    pw = _PW(ok_channels={"chrome", "msedge"})
    c = _client(monkeypatch, tmp_path, pw)
    c.start()
    assert c.browser.key == "chrome" and len(pw.log) == 1


def test_portal_without_any_browser(monkeypatch, tmp_path):
    pw = _PW(ok_channels=set())
    c = _client(monkeypatch, tmp_path, pw)
    with pytest.raises(BrowserUnavailable, match="Nenhum navegador compatível"):
        c.start()
    assert pw.stopped
