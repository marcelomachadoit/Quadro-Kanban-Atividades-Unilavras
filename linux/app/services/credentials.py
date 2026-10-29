"""Credenciais no chaveiro do sistema (Secret Service: GNOME Keyring ou KWallet, via keyring). Nunca em texto puro."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import keyring
from keyring.errors import KeyringError, NoKeyringError, PasswordDeleteError

log = logging.getLogger(__name__)

SERVICE = "UniSpace/novoportal.unilavras.edu.br"
LEGACY_SERVICE = "UniKanban/novoportal.unilavras.edu.br"   # nome antigo do aplicativo
_USER_SLOT = "__usuario__"   # guarda qual usuário está configurado
NO_VAULT = ("Nenhum chaveiro do sistema está disponível. Instale e desbloqueie o GNOME Keyring (pacote "
            "gnome-keyring) ou o KWallet e abra o aplicativo de novo.")


class CredentialError(RuntimeError):
    pass


@dataclass
class Credentials:
    username: str
    password: str


class CredentialStore:
    def __init__(self, service: str = SERVICE):
        self.service = service

    def save(self, username: str, password: str) -> None:
        username = (username or "").strip()
        if not username or not password:
            raise CredentialError("Informe o usuário e a senha.")
        try:
            old = self.username()
            keyring.set_password(self.service, _USER_SLOT, username)
            keyring.set_password(self.service, username, password)
            if old and old != username:
                try:
                    keyring.delete_password(self.service, old)
                except PasswordDeleteError:
                    pass
        except NoKeyringError as e:
            raise CredentialError(NO_VAULT) from e
        except KeyringError as e:
            raise CredentialError(f"Não foi possível salvar no chaveiro do sistema: {e}") from e
        log.info("Credenciais salvas no cofre do sistema (usuário configurado).")

    def username(self) -> Optional[str]:
        try:
            return keyring.get_password(self.service, _USER_SLOT)
        except KeyringError:
            return None

    def load(self) -> Optional[Credentials]:
        try:
            u = keyring.get_password(self.service, _USER_SLOT)
            if not u:
                return None
            p = keyring.get_password(self.service, u)
        except NoKeyringError as e:
            raise CredentialError(NO_VAULT) from e
        except KeyringError as e:
            raise CredentialError(f"Falha ao ler o chaveiro do sistema: {e}") from e
        return Credentials(u, p) if p else None

    def migrate_from(self, legacy_service: str = LEGACY_SERVICE) -> bool:
        """Copia a conta salva pelo UniKanban (nome antigo) para o cofre do UniSpace e apaga a cópia antiga."""
        try:
            if self.username():
                return False
            old = CredentialStore(legacy_service)
            creds = old.load()
            if not creds:
                return False
            self.save(creds.username, creds.password)
            old.clear()
        except (KeyringError, CredentialError):
            log.warning("Não foi possível migrar a conta salva pelo UniKanban.")
            return False
        log.info("Conta do portal migrada do UniKanban para o UniSpace.")
        return True

    def clear(self) -> None:
        u = self.username()
        for name in filter(None, (u, _USER_SLOT)):
            try:
                keyring.delete_password(self.service, name)
            except (PasswordDeleteError, KeyringError):
                pass
