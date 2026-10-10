"""Orígenes de confianza para passkeys, Google y la validación de `Origin`.

NFR-SVC-003 / FR-AUTH-004 / FR-AUTH-005: el `Host` de un pedido no es por sí
solo una autoridad de confianza, ni siquiera sobre TLS. El servidor deriva el
origen canónico del pedido (esquema de `--secure` + Host parseado de forma
estricta) y solo lo acepta como origen WebAuthn o como base del callback OIDC
de Google cuando es **local** (`localhost`/`127.0.0.1`, con cualquier puerto
válido) o está declarado en la lista explícita `BIBLIO_TRUSTED_ORIGINS`.

Un origen canónico es `http(s)://host[:puerto]` sin userinfo, ruta, query,
fragmento, espacios ni caracteres de control; el host va en minúsculas (IPv6
entre corchetes se conserva para no romper la validación de `Origin` del API)
y el puerto debe ser un entero estricto en 1–65535, con los puertos por
defecto (80/443) normalizados fuera. Los orígenes no locales solo se admiten
sobre HTTPS: la passkey sobre HTTP de red sigue prohibida por NFR-SVC-003.
"""
from __future__ import annotations

import re

from .store import AppError

# Hostnames aceptados como origen local (NFR-SVC-003).
LOCAL_HOSTNAMES = frozenset({"localhost", "127.0.0.1"})
HOSTNAME_RE = re.compile(r"[A-Za-z0-9.\-]+")
DEFAULT_PORTS = {"http": 80, "https": 443}


def _split_authority(authority):
    """`(host_lower, puerto_str|None)` o `(None, None)` si la autoridad no es válida.

    Rechaza userinfo (`@`), IPv6 sin corchetes, host vacío y puertos no
    numéricos o fuera de 1–65535; «0080» se normaliza a «80».
    """
    if not isinstance(authority, str) or not authority or "@" in authority:
        return None, None
    if authority.startswith("["):
        end = authority.find("]")
        if end < 0:
            return None, None
        inner, rest = authority[1:end].lower(), authority[end + 1:]
        if not re.fullmatch(r"[0-9a-f:.]+", inner):
            return None, None
        host = f"[{inner}]"  # la forma canónica conserva los corchetes del literal IPv6.
        if rest and not rest.startswith(":"):
            return None, None
        port = rest[1:] if rest else ""
    else:
        if authority.count(":") > 1:  # IPv6 sin corchetes no es una autoridad válida.
            return None, None
        host, _, port = authority.partition(":")
        host = host.lower()
        if not HOSTNAME_RE.fullmatch(host):
            return None, None
    if not port:
        return host, None
    if not port.isascii() or not port.isdigit():
        return None, None
    value = int(port)
    if not 0 < value < 65536:
        return None, None
    return host, str(value)


def parse_origin(value):
    """Origen canónico `scheme://host[:puerto]` o `None` si el valor no lo es.

    Acepta solo `http`/`https` con autoridad exacta (ver `_split_authority`);
    el puerto por defecto del esquema se omite en el resultado para que
    `https://host:443` y `https://host` sean el mismo origen, igual que en la
    cabecera `Origin` del navegador.
    """
    if not isinstance(value, str) or not value:
        return None
    if any(not 0x21 <= ord(ch) <= 0x7e for ch in value):  # control, espacios, no-ASCII
        return None
    match = re.fullmatch(r"(?i)(http|https)://(.+)", value)
    if not match:
        return None
    scheme = match.group(1).lower()
    host, port = _split_authority(match.group(2))
    if host is None:
        return None
    if port is None or int(port) == DEFAULT_PORTS[scheme]:
        return f"{scheme}://{host}"
    return f"{scheme}://{host}:{port}"


def canonical_origin(scheme, host_header):
    """Origen canónico del pedido, o `None` si el `Host` no es una autoridad válida."""
    if scheme not in DEFAULT_PORTS or not host_header:
        return None
    return parse_origin(f"{scheme}://{host_header}")


def host_of(origin):
    """Hostname en minúsculas de un origen canónico (sin puerto)."""
    authority = origin.split("://", 1)[1]
    if authority.startswith("["):
        return authority[1:authority.find("]")]
    return authority.split(":")[0]


class TrustedOrigins:
    """Orígenes aceptados: locales por defecto + una lista explícita exacta.

    Cualquier puerto local vale (desarrollo con puertos efímeros y proxy local
    tipo mkcert); los orígenes no locales solo entran por la lista y siempre
    como coincidencia exacta de origen canónico, nunca por sufijo de hostname.
    """

    def __init__(self, extra=()):
        self.extra = frozenset(extra)

    def trusted(self, origin):
        """¿Es este origen canónico de confianza para WebAuthn/callback OIDC?"""
        if origin is None:
            return False
        scheme = origin.split("://", 1)[0]
        if host_of(origin) in LOCAL_HOSTNAMES and scheme in DEFAULT_PORTS:
            return True
        return origin in self.extra


def parse_trusted_origins(raw):
    """Orígenes extra desde `BIBLIO_TRUSTED_ORIGINS` (separados por coma).

    Cada entrada debe ser un origen canónico; los no locales solo sobre HTTPS
    (NFR-SVC-003). Una configuración inválida es un error del servidor, no un
    default silencioso: quien la escribió espera que se cumpla.
    """
    values = [item.strip() for item in (raw or "").split(",") if item.strip()]
    parsed = []
    for value in values:
        origin = parse_origin(value)
        if origin is None or (
                origin.split("://", 1)[0] == "http" and host_of(origin) not in LOCAL_HOSTNAMES):
            raise AppError(
                503, "BIBLIO_TRUSTED_ORIGINS solo admite orígenes canónicos; los no "
                      "locales deben ser https, p. ej. https://biblio.example.org.")
        parsed.append(origin)
    return parsed
