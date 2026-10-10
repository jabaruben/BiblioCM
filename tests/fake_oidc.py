"""Proveedor OIDC falso local para pruebas (FR-AUTH-005 / ADR-018).

Sirve descubrimiento, JWKS, endpoint de token y una página de autorización que
redirige al callback con el `code`. Los token ID se firman con RS256 usando una
clave RSA generada en la propia prueba; **nunca** se habla con Google ni con
ningún proveedor real, y no hay credenciales que versionar.
"""
from __future__ import annotations

import base64
import hashlib
import json
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from joserfc import jwt
from joserfc.jwk import generate_key

CLIENT_ID = "cliente-ficticio"
CLIENT_SECRET = "secreto-ficticio"


class FakeOidcHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, status, body=b"", content_type="application/json", headers=()):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for key, value in headers:
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        provider = self.server.provider
        query = urllib.parse.urlsplit(self.path)
        if query.path == "/.well-known/openid-configuration":
            base = provider.base_url
            self._send(200, json.dumps({
                "issuer": base,
                "authorization_endpoint": base + "/authorize",
                "token_endpoint": base + "/token",
                "jwks_uri": base + "/jwks.json",
                "response_types_supported": ["code"],
                "subject_types_supported": ["public"],
                "id_token_signing_alg_values_supported": ["RS256"],
            }).encode())
            return
        if query.path == "/jwks.json":
            self._send(200, json.dumps({"keys": [provider.jwk.as_dict(private=False)]}).encode())
            return
        if query.path == "/authorize":
            parameters = urllib.parse.parse_qs(query.query)
            try:
                code = provider.authorize(parameters)
            except ValueError as exc:
                self._send(400, json.dumps({"error": str(exc)}).encode())
                return
            redirect = urllib.parse.urlsplit(parameters["redirect_uri"][0])
            separator = "&" if redirect.query else "?"
            location = (parameters["redirect_uri"][0] + separator +
                        urllib.parse.urlencode({"code": code,
                                                "state": parameters.get("state", [""])[0]}))
            self._send(303, b"", headers=[("Location", location)])
            return
        self._send(404, b"{}")

    def do_POST(self):
        provider = self.server.provider
        length = int(self.headers.get("Content-Length", "0"))
        form = {key: value[0] for key, value in
                urllib.parse.parse_qs(self.rfile.read(length).decode()).items()}
        if urllib.parse.urlsplit(self.path).path != "/token":
            self._send(404, b"{}")
            return
        try:
            body = provider.token(form)
        except ValueError as exc:
            self._send(400, json.dumps({"error": str(exc)}).encode())
            return
        self._send(200, json.dumps(body).encode())


class FakeOidcServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


class FakeOidcProvider:
    """Proveedor controlable: lo que el token contiene lo decide la prueba."""

    def __init__(self):
        self.jwk = generate_key("RSA", parameters={"kid": "ficticio-1", "use": "sig", "alg": "RS256"})
        self.codes = {}
        self.scenario = {}
        self.seen = []
        self.server = FakeOidcServer(("127.0.0.1", 0), FakeOidcHandler)
        self.server.provider = self
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def base_url(self):
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    @property
    def client_id(self):
        return CLIENT_ID

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def authorize(self, parameters):
        """Valida la petición de autorización y emite un `code` de un solo uso."""
        if parameters.get("client_id", [None])[0] != self.client_id:
            raise ValueError("client_id")
        for required in ("redirect_uri", "state", "nonce", "code_challenge"):
            if not parameters.get(required, [None])[0]:
                raise ValueError(required)
        if parameters.get("code_challenge_method", [None])[0] != "S256":
            raise ValueError("code_challenge_method")
        if parameters.get("response_type", [None])[0] != "code":
            raise ValueError("response_type")
        if "openid" not in parameters.get("scope", [""])[0].split():
            raise ValueError("scope")
        code = f"codigo-{len(self.codes) + 1}-{int(time.time() * 1000)}"
        self.codes[code] = {"nonce": parameters["nonce"][0],
                            "redirect_uri": parameters["redirect_uri"][0],
                            "code_challenge": parameters["code_challenge"][0]}
        return code

    def token(self, form):
        """Intercambia el `code`: valida PKCE y firma el token ID según el guion."""
        self.seen.append(dict(form))
        if form.get("client_id") != self.client_id or form.get("client_secret") != CLIENT_SECRET:
            raise ValueError("client_auth_failed")
        if self.scenario.get("token_error"):
            raise ValueError(self.scenario["token_error"])
        record = self.codes.pop(form.get("code", ""), None)
        if record is None:
            raise ValueError("invalid_grant")
        if form.get("redirect_uri") != record["redirect_uri"]:
            raise ValueError("redirect_uri")
        verifier = form.get("code_verifier", "")
        digest = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        if digest != record["code_challenge"]:
            raise ValueError("code_verifier")
        nonce = record["nonce"]
        now = int(time.time())
        claims = {"iss": self.base_url, "sub": "sub-ficticio-1", "aud": self.client_id,
                  "iat": now, "exp": now + 300, "nonce": nonce,
                  "email": "ana.tester@ejemplo.test", "email_verified": True,
                  "name": "Ana Tester"}
        claims.update(self.scenario.get("claims", {}))
        header = {"alg": "RS256", "kid": "ficticio-1"}
        key = generate_key("RSA", parameters={"kid": "otra-clave"}) if self.scenario.get("wrong_key") else self.jwk
        header.update(self.scenario.get("header", {}))
        id_token = jwt.encode(header, claims, key)
        if self.scenario.get("drop_id_token"):
            return {"access_token": "acceso-ficticio"}
        return {"access_token": "acceso-ficticio", "id_token": id_token, "token_type": "Bearer"}

    def mint(self, **claims):
        """Token ID firmado fuera del flujo, para probar la verificación directa."""
        now = int(time.time())
        payload = {"iss": self.base_url, "sub": "sub-ficticio-1", "aud": self.client_id,
                   "iat": now, "exp": now + 300, "nonce": "nonce-ficticio"}
        payload.update(claims)
        key = generate_key("RSA", parameters={"kid": "otra-clave"}) if self.scenario.get("wrong_key") else self.jwk
        return jwt.encode({"alg": "RS256", "kid": "ficticio-1"}, payload, key)
