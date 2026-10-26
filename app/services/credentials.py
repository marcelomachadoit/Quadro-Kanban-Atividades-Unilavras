"""Credenciais no Gerenciador de Credenciais do Windows (via keyring). Nunca em texto puro."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import keyring
from keyring.errors import KeyringError, PasswordDeleteError

log = logging.getLogger(__name__)

SERVICE = "UniKanban/novoportal.unilavras.edu.br"
_USER_SLOT = "__usuario__"   # guarda qual usuário está configurado


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
        except KeyringError as e:
            raise CredentialError(f"Não foi possível salvar no Gerenciador de Credenciais do Windows: {e}") from e
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
        except KeyringError as e:
            raise CredentialError(f"Falha ao ler o Gerenciador de Credenciais: {e}") from e
        return Credentials(u, p) if p else None

    def clear(self) -> None:
        u = self.username()
        for name in filter(None, (u, _USER_SLOT)):
            try:
                keyring.delete_password(self.service, name)
            except (PasswordDeleteError, KeyringError):
                pass
