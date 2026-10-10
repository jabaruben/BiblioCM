"""Multicuenta.

El registro guarda **solo** números de carné y etiquetas. Las contraseñas no se
escriben en disco: se leen del entorno o se piden de forma interactiva. En la
app Android esto se sustituye por el Android Keystore, que es justo el hueco que
dejará el motor al portarlo a Kotlin.
"""

from __future__ import annotations

import getpass
import json
import os
import pathlib
from dataclasses import dataclass, field

ENV_PREFIX = "BIBLIO_PWD_"
DEFAULT_REGISTRY = pathlib.Path.home() / ".config" / "biblio" / "accounts.json"


@dataclass
class Account:
    id: str
    card: str
    label: str = ""
    password: str = field(default="", repr=False)

    def password_from_env(self) -> str:
        return os.environ.get(f"{ENV_PREFIX}{self.id.upper().replace('-', '_')}", "")

    def resolve_password(self, interactive: bool = True) -> str:
        if self.password:
            return self.password
        from_env = self.password_from_env()
        if from_env:
            return from_env
        if interactive:
            entered = getpass.getpass(f"Contraseña de {self.label or self.card}: ")
            if entered:
                return entered
        raise KeyError(
            f"no hay contraseña para la cuenta '{self.id}'. "
            f"Define {ENV_PREFIX}{self.id.upper().replace('-', '_')} o usa --password-stdin."
        )


class Registry:
    def __init__(self, accounts: list[Account], path: pathlib.Path | None = None):
        self.accounts = accounts
        self.path = path

    @classmethod
    def load(cls, path: pathlib.Path | None = None) -> "Registry":
        path = path or DEFAULT_REGISTRY
        if not path.exists():
            return cls([], path)
        raw = json.loads(path.read_text(encoding="utf-8"))
        accounts = [
            Account(id=item["id"], card=item["card"], label=item.get("label", ""))
            for item in raw.get("accounts", [])
        ]
        return cls(accounts, path)

    def save(self) -> None:
        assert self.path is not None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "accounts": [
                {"id": a.id, "card": a.card, "label": a.label} for a in self.accounts
            ]
        }
        self.path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def add(self, account: Account) -> None:
        self.accounts = [a for a in self.accounts if a.id != account.id]
        self.accounts.append(account)

    def get(self, account_id: str) -> Account:
        for account in self.accounts:
            if account.id == account_id or account.card == account_id:
                return account
        known = ", ".join(a.id for a in self.accounts) or "(ninguna)"
        raise KeyError(f"cuenta desconocida '{account_id}'. Disponibles: {known}")

    def select(self, wanted: list[str] | None) -> list[Account]:
        if not wanted:
            return list(self.accounts)
        return [self.get(item) for item in wanted]