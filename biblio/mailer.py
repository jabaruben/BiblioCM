"""Correo saliente configurable (TODO-AUTH-002 / ADR-017).

Sin configuración no hay envío: la aplicación no asume ningún proveedor. La
configuración llega por entorno (`BIBLIO_SMTP_*`), nunca por fichero del
repositorio, y las pruebas usan un servidor SMTP falso local. Este módulo no
imprime ni registra tokens ni contraseñas: el código de verificación solo viaja
dentro del cuerpo del correo enviado a la persona.
"""
from __future__ import annotations

import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage

DEFAULT_FROM = "BiblioCM <no-responder@localhost>"


@dataclass(frozen=True)
class MailConfig:
    host: str
    port: int = 587
    username: str = ""
    password: str = ""
    use_ssl: bool = False
    starttls: bool = True
    from_addr: str = DEFAULT_FROM
    timeout: float = 10.0


def _flag(env, name, default):
    return (env.get(name, default) or "").strip() == "1"


def config_from_env(env=None):
    """Configuración desde el entorno, o `None` si no hay host (correo off)."""
    env = os.environ if env is None else env
    host = (env.get("BIBLIO_SMTP_HOST") or "").strip()
    if not host:
        return None
    return MailConfig(
        host=host,
        port=int(env.get("BIBLIO_SMTP_PORT", "587")),
        username=(env.get("BIBLIO_SMTP_USER") or "").strip(),
        password=env.get("BIBLIO_SMTP_PASSWORD") or "",
        use_ssl=_flag(env, "BIBLIO_SMTP_SSL", "0"),
        starttls=_flag(env, "BIBLIO_SMTP_STARTTLS", "1"),
        from_addr=(env.get("BIBLIO_SMTP_FROM") or "").strip() or DEFAULT_FROM,
        timeout=float(env.get("BIBLIO_SMTP_TIMEOUT", "10")),
    )


class Mailer:
    def __init__(self, config):
        self.config = config

    def send(self, to, subject, body):
        message = EmailMessage()
        message["From"] = self.config.from_addr
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)
        context = ssl.create_default_context()
        if self.config.use_ssl:
            with smtplib.SMTP_SSL(self.config.host, self.config.port,
                                  timeout=self.config.timeout, context=context) as client:
                if self.config.username:
                    client.login(self.config.username, self.config.password)
                client.send_message(message)
            return
        with smtplib.SMTP(self.config.host, self.config.port,
                          timeout=self.config.timeout) as client:
            client.ehlo()
            if self.config.starttls:
                client.starttls(context=context)
                client.ehlo()
            if self.config.username:
                client.login(self.config.username, self.config.password)
            client.send_message(message)

    def send_verification(self, to, token, hours):
        body = (
            "Alguien (esperemos que tú) pidió verificar este email en BiblioCM.\n"
            "\n"
            f"Código: {token}\n"
            "\n"
            f"Introduce el código en Configuración → Tu email dentro de {hours} horas.\n"
            "Si no pediste esto, ignora el mensaje: no ha pasado nada en tu cuenta.\n"
            "No reenvíes ni compartas este mensaje: quien tenga el código puede\n"
            "verificar el email en tu lugar.\n"
        )
        self.send(to, "Código de verificación de BiblioCM", body)

    def send_recovery(self, to, token, minutes):
        body = (
            "Se pidió restablecer la contraseña de BiblioCM para este email.\n"
            "\n"
            f"Código: {token}\n"
            "\n"
            f"Introduce el código en «¿Olvidaste tu contraseña?» dentro de {minutes} minutos.\n"
            "Si no pediste esto, ignora el mensaje: tu contraseña no ha cambiado.\n"
            "No reenvíes ni compartas este mensaje: quien tenga el código puede\n"
            "cambiar la contraseña de tu cuenta.\n"
        )
        self.send(to, "Recuperación de contraseña de BiblioCM", body)
