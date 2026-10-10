"""Acceso opcional con Google vía OIDC (FR-AUTH-005).

Flujo de código con `state` y `nonce` de un solo uso, caducidad y PKCE, con
verificación del token ID firmado por una librería mantenida (`joserfc`): firma,
`iss`, `aud`, `exp`/`iat` y `nonce` se comprueban contra el JWKS del proveedor.
La identidad de la cuenta es `sub` dentro del `iss` configurado: el email del
token **nunca** crea ni encuentra cuentas de forma implícita.

La configuración es opt-in por entorno (`BIBLIO_GOOGLE_*`): sin client id/secret
no hay botón, no hay callback y este módulo no se usa. Ninguna petición sale de
la máquina salvo hacia los endpoints OIDC configurados (y las pruebas usan un
proveedor falso local, nunca Google).

`joserfc` es el motor JOSE que `authlib` delega desde su 1.8 (que deprecó su
propio módulo `authlib.jose`); se fija como dependencia en `pyproject.toml`
(ADR-018).
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Optional

from joserfc import jwt
from joserfc.errors import JoseError
from joserfc.jwk import KeySet
from joserfc.jwt import JWTClaimsRegistry

from .origins import LOCAL_HOSTNAMES
from .store import AppError

# Solo se aceptan endpoints HTTPS; en bucle se admite HTTP para el proveedor
# falso de pruebas (127.0.0.1/localhost), nunca para un host de red.
TIMEOUT = 10
JWKS_TTL = 3600
DISCOVERY_TTL = 3600
LEEWAY = 60
ALGORITHMS = ("RS256",)
SCOPE = "openid email profile"
STATE_TTL = 600


def _check_url(url, _what="endpoint"):
    """Endpoint OIDC utilizable: HTTPS, o HTTP solo en bucle (proveedor de pruebas).

    También descarta authority con userinfo: una URL de configuración con
    credenciales incrustadas no es una forma aceptada de autenticar aquí.
    """
    match = re.match(r"^(https?)://([^/?#]+)", url or "")
    if not match or "@" in match.group(2):
        raise AppError(503, "La configuración de acceso con Google no es válida en este servidor.")
    scheme, authority = match.group(1), match.group(2)
    host = authority.split(":")[0].lower()
    if scheme != "https" and not (scheme == "http" and host in LOCAL_HOSTNAMES):
        raise AppError(503, "La configuración de acceso con Google no es válida en este servidor.")


@dataclass(frozen=True)
class GoogleConfig:
    client_id: str
    client_secret: str
    issuer: str
    auth_endpoint: Optional[str] = None
    token_endpoint: Optional[str] = None
    jwks_uri: Optional[str] = None
    # Override del callback (proxy/reverse): debe ser canónico y su origen de
    # confianza. Sin él, `web.google_redirect_uri` lo deriva del origen de
    # confianza del pedido, nunca del Host crudo (NFR-SVC-003).
    redirect_uri: Optional[str] = None


def config_from_env(env=None):
    """Configuración por entorno; `None` cuando no está activada (opt-in)."""
    env = os.environ if env is None else env
    client_id = (env.get("BIBLIO_GOOGLE_CLIENT_ID") or "").strip()
    client_secret = (env.get("BIBLIO_GOOGLE_CLIENT_SECRET") or "").strip()
    if not client_id or not client_secret:
        return None
    return GoogleConfig(
        client_id=client_id,
        client_secret=client_secret,
        issuer=(env.get("BIBLIO_GOOGLE_ISSUER") or "https://accounts.google.com").rstrip("/"),
        auth_endpoint=(env.get("BIBLIO_GOOGLE_AUTH_ENDPOINT") or "").rstrip("/") or None,
        token_endpoint=(env.get("BIBLIO_GOOGLE_TOKEN_ENDPOINT") or "").rstrip("/") or None,
        jwks_uri=(env.get("BIBLIO_GOOGLE_JWKS_URI") or "").rstrip("/") or None,
        redirect_uri=(env.get("BIBLIO_GOOGLE_REDIRECT_URI") or "").strip() or None,
    )


def _get(url, accept="application/json"):
    request = urllib.request.Request(url, headers={"Accept": accept})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return response.read()


def code_challenge(verifier):
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


class GoogleProvider:
    """Endpoints OIDC (con descubrimiento perezoso) y verificación del token ID.

    La caché vive en la instancia del servidor: cada proceso (y cada prueba)
    resuelve sus propios endpoints, sin estado de módulo compartido.
    """

    def __init__(self, config, fetch=_get):
        self.config = config
        self.fetch = fetch
        self._endpoints = None
        self._endpoints_at = 0.0
        self._keys = None
        self._keys_at = 0.0

    @property
    def enabled(self):
        return True

    def endpoints(self):
        now = time.monotonic()
        if self._endpoints and now - self._endpoints_at < DISCOVERY_TTL:
            return self._endpoints
        document = {
            "authorization_endpoint": self.config.auth_endpoint,
            "token_endpoint": self.config.token_endpoint,
            "jwks_uri": self.config.jwks_uri,
        }
        if not all(document.values()):
            url = self.config.issuer + "/.well-known/openid-configuration"
            _check_url(url, "discovery")
            try:
                found = json.loads(self.fetch(url))
            except (urllib.error.URLError, ValueError, OSError) as exc:
                raise AppError(503, "No se pudo consultar al proveedor de acceso con Google.") from exc
            # El documento debe declarar el mismo issuer configurado: un punto de
            # terminación que no pertenece a ese issuer no vale como fuente de claves.
            if found.get("issuer") not in (self.config.issuer, self.config.issuer + "/"):
                raise AppError(503, "El proveedor de acceso con Google no coincide con la configuración.")
            document = {
                "authorization_endpoint": found.get("authorization_endpoint") or self.config.auth_endpoint,
                "token_endpoint": found.get("token_endpoint") or self.config.token_endpoint,
                "jwks_uri": found.get("jwks_uri") or self.config.jwks_uri,
            }
        for value in document.values():
            if not value:
                raise AppError(503, "La configuración de acceso con Google no es válida en este servidor.")
            _check_url(value, "endpoint")
        self._endpoints = document
        self._endpoints_at = now
        return document

    def keys(self):
        now = time.monotonic()
        if self._keys and now - self._keys_at < JWKS_TTL:
            return self._keys
        uri = self.endpoints()["jwks_uri"]
        try:
            payload = json.loads(self.fetch(uri))
            key_set = KeySet.import_key_set(payload)
        except (JoseError, ValueError, OSError, KeyError) as exc:
            raise AppError(503, "No se pudieron consultar las claves del proveedor de acceso con Google.") from exc
        self._keys, self._keys_at = key_set, now
        return key_set

    def authorization_url(self, redirect_uri, state, nonce, verifier):
        endpoints = self.endpoints()
        params = {
            "client_id": self.config.client_id,
            "response_type": "code",
            "scope": SCOPE,
            "redirect_uri": redirect_uri,
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge(verifier),
            "code_challenge_method": "S256",
        }
        return endpoints["authorization_endpoint"] + "?" + urllib.parse.urlencode(params)

    def exchange_code(self, redirect_uri, code, verifier):
        endpoints = self.endpoints()
        body = urllib.parse.urlencode({
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
            "code_verifier": verifier,
        }).encode()
        request = urllib.request.Request(
            endpoints["token_endpoint"], data=body, method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                payload = json.loads(response.read())
        except (urllib.error.URLError, ValueError, OSError) as exc:
            raise AppError(502, "El proveedor de acceso con Google no respondió.") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("id_token"), str):
            raise AppError(400, "El proveedor de acceso con Google no devolvió un token válido.")
        return payload

    def verify_id_token(self, id_token, nonce):
        """Verifica firma, issuer, audiencia, expiración y nonce del token ID."""
        try:
            token = jwt.decode(id_token, self.keys(), algorithms=list(ALGORITHMS))
        except JoseError:
            raise AppError(401, "El token de Google no es válido.") from None
        claims = token.claims
        registry = JWTClaimsRegistry(
            leeway=LEEWAY,
            iss={"essential": True, "value": self.config.issuer},
            aud={"essential": True, "value": self.config.client_id},
            sub={"essential": True},
            exp={"essential": True},
            iat={"essential": True},
            nonce={"essential": True, "value": nonce},
        )
        try:
            registry.validate(claims)
        except JoseError as exc:
            raise AppError(401, "El token de Google no es válido.") from None
        audience = claims.get("aud")
        if isinstance(audience, list) and len(audience) > 1 and claims.get("azp") != self.config.client_id:
            raise AppError(401, "El token de Google no es válido.")
        if not isinstance(claims.get("sub"), str) or not claims["sub"]:
            raise AppError(401, "El token de Google no es válido.")
        return claims
