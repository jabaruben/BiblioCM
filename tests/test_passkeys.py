"""Passkeys WebAuthn (TODO-AUTH-003 / FR-AUTH-004) contra el servidor local.

Ninguna prueba usa hardware, credenciales reales ni el portal: el dispositivo
sintético de [webauthn_fake](webauthn_fake.py) construye la asertación y la
verificación la ejecuta la librería `webauthn` en el servidor, que es exactamente
la frontera que interesa probar (challenge de un solo uso, caducidad, origen/RP
ID, UV, firma, contador, reautenticación y rechazo en origen no confiable o no
listado, TODO-SEC-003).
"""
import http.client
import json
import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path

from cryptography.fernet import Fernet

from biblio import origins
from biblio.store import AppError, Store
from biblio.web import REAUTH_TTL, AppServer
from tests.test_web import FakeClient
from tests.webauthn_fake import FakeAuthenticator, b64u

APP_PASSWORD = "clave-de-prueba-123"


class PasskeyTestCase(unittest.TestCase):
    """Base: servidor temporal con OPAC falso y una cuenta ya registrada."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".biblio-test-", dir=Path(__file__).parents[1])
        self.path = Path(self.temp.name) / "biblio.sqlite3"
        self.store = Store(self.path, key=Fernet.generate_key())
        self.clients = []
        self.portal_state = {}

        def factory(card, password):
            client = FakeClient(card, password, state=self.portal_state)
            self.clients.append(client)
            return client

        self.server = AppServer(("127.0.0.1", 0), factory, store=self.store)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host = f"127.0.0.1:{self.server.server_port}"
        self.cookie, self.csrf = "", ""
        self.register("owner")

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.store.close()
        self.temp.cleanup()

    # -- utilidades HTTP -------------------------------------------------

    def request(self, path, body=None, extra=None, host=None, csrf=None):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        connection.putrequest("POST" if body is not None else "GET", path,
                              skip_host=True, skip_accept_encoding=True)
        connection.putheader("Host", host or self.host)
        connection.putheader("Connection", "close")
        if self.cookie:
            connection.putheader("Cookie", self.cookie)
        if body is not None:
            connection.putheader("Content-Type", "application/json")
            connection.putheader("X-CSRF-Token", self.csrf if csrf is None else csrf)
        for key, value in (extra or {}).items():
            connection.putheader(key, value)
        data = json.dumps(body).encode() if body is not None else None
        if data is not None:
            # `endheaders` no añade Content-Length: el servidor lo exige.
            connection.putheader("Content-Length", str(len(data)))
        connection.endheaders(data)
        response = connection.getresponse()
        payload = response.read()
        result = response.status, dict(response.getheaders()), payload
        connection.close()
        return result

    def data(self, path, body=None, status=200, **kwargs):
        code, _, raw = self.request(path, body, **kwargs)
        self.assertEqual(code, status, raw.decode())
        return json.loads(raw) if raw else {}

    def sql(self, statement, params=()):
        connection = sqlite3.connect(self.path)
        try:
            return connection.execute(statement, params).fetchall()
        finally:
            connection.close()

    def sql_exec(self, statement, params=()):
        connection = sqlite3.connect(self.path)
        try:
            connection.execute(statement, params)
            connection.commit()
        finally:
            connection.close()

    # -- flujos ----------------------------------------------------------

    def register(self, username="owner"):
        code, headers, raw = self.request("/api/register", {"username": username,
                                                            "name": username.title(),
                                                            "password": APP_PASSWORD})
        self.assertEqual(code, 200, raw)
        self.cookie = headers["Set-Cookie"].split(";")[0]
        self.csrf = json.loads(raw)["csrf"]
        return json.loads(raw)["user"]

    def reauth(self, password=APP_PASSWORD, status=200):
        return self.data("/api/auth/reauth", {"password": password}, status=status)

    def authenticator(self, **kwargs):
        return FakeAuthenticator("127.0.0.1", f"http://{self.host}", **kwargs)

    def registration_options(self, status=200):
        return self.data("/api/auth/passkeys/register/options", {}, status=status)["publicKey"]

    def add_passkey(self, authenticator, label="Llave de prueba", status=200):
        self.reauth()
        challenge = self.registration_options()["challenge"]
        credential = authenticator.registration(challenge)
        return self.data("/api/auth/passkeys/register",
                         {"credential": credential, "label": label}, status=status)

    def passkey_login(self, authenticator, status=200):
        challenge = self.data("/api/auth/passkeys/login/options", {})["publicKey"]["challenge"]
        code, headers, raw = self.request(
            "/api/auth/passkeys/login", {"credential": authenticator.authentication(challenge)})
        self.assertEqual(code, status, raw.decode())
        return code, headers, json.loads(raw)


class PasskeyFlowTests(PasskeyTestCase):
    """FR-AUTH-004: registro, login con passkey y CRUD con reautenticación."""

    def test_register_and_login_with_a_passkey(self):
        authenticator = self.authenticator()
        answer = self.add_passkey(authenticator)
        self.assertTrue(answer["ok"])
        self.assertEqual(answer["passkey"]["label"], "Llave de prueba")
        listed = self.data("/api/settings")["passkeys"]
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["label"], "Llave de prueba")
        self.assertEqual(listed[0]["id"], answer["passkey"]["id"])
        # La passkey se guarda con su clave pública y el contador inicial.
        stored = self.store.passkey(listed[0]["id"])
        self.assertGreater(len(stored["public_key"]), 0)
        self.assertEqual(stored["sign_count"], 0)
        # Login con la misma passkey: sesión nueva con los mismos permisos.
        previous_cookie = self.cookie
        _, headers, payload = self.passkey_login(authenticator)
        self.assertTrue(payload["authenticated"])
        self.assertEqual(payload["user"]["username"], "owner")
        self.cookie = headers["Set-Cookie"].split(";")[0]
        self.csrf = payload["csrf"]
        self.assertEqual(self.data("/api/settings")["user"]["username"], "owner")
        # El token rota: la cookie anterior ya no abre sesión.
        saved = self.cookie
        self.cookie = previous_cookie
        self.data("/api/settings", status=401)
        self.cookie = saved

    def test_password_login_still_works_after_adding_a_passkey(self):
        self.add_passkey(self.authenticator())
        code, headers, raw = self.request("/api/login", {"username": "owner", "password": APP_PASSWORD})
        self.assertEqual(code, 200, raw)
        self.cookie = headers["Set-Cookie"].split(";")[0]
        self.data("/api/settings")

    def test_management_requires_fresh_reauthentication(self):
        code, _, _ = self.request("/api/auth/passkeys/register/options", {})
        self.assertEqual(code, 403)
        code, _, raw = self.request("/api/auth/passkeys/register/options", {})
        self.assertEqual(json.loads(raw)["code"], "reauth_required")
        self.reauth(status=403, password="contraseña-mala-000")
        self.reauth()
        self.registration_options()

    def test_delete_requires_reauth_and_only_touches_own_passkeys(self):
        authenticator = self.authenticator()
        answer = self.add_passkey(authenticator)
        credential_id = answer["passkey"]["id"]
        other = self.register("otra")
        # Otro usuario no puede borrar la passkey ajena, ni con reauth.
        self.reauth()
        code, _, _ = self.request("/api/auth/passkeys/delete", {"id": credential_id})
        self.assertEqual(code, 403)
        self.assertIsNotNone(self.store.passkey(credential_id))
        # El dueño sí puede, con reautenticación fresca.
        self.login_owner()
        self.reauth()
        self.data("/api/auth/passkeys/delete", {"id": credential_id})
        self.assertIsNone(self.store.passkey(credential_id))
        # Borrar algo que no existe responde igual que si fuera ajeno.
        self.reauth()
        self.data("/api/auth/passkeys/delete", {"id": credential_id}, status=403)
        self.assertEqual(other["username"], "otra")

    def login_owner(self):
        code, headers, raw = self.request("/api/login", {"username": "owner", "password": APP_PASSWORD})
        self.assertEqual(code, 200, raw)
        self.cookie = headers["Set-Cookie"].split(";")[0]
        self.csrf = json.loads(raw)["csrf"]

    def test_second_registration_excludes_the_first_credential(self):
        authenticator = self.authenticator()
        self.add_passkey(authenticator)
        self.reauth()
        options = self.registration_options()
        excluded = [item["id"] for item in options.get("excludeCredentials", [])]
        self.assertEqual(excluded, [self.data("/api/settings")["passkeys"][0]["id"]])
        # Reenviar una credencial ya registrada choca con el ID único (409).
        challenge = options["challenge"]
        self.data("/api/auth/passkeys/register",
                  {"credential": authenticator.registration(challenge)}, status=409)

    def test_passkey_login_counts_as_reauthentication(self):
        authenticator = self.authenticator()
        self.add_passkey(authenticator)
        _, headers, payload = self.passkey_login(authenticator)
        self.cookie = headers["Set-Cookie"].split(";")[0]
        self.csrf = payload["csrf"]
        # La sesión abierta con passkey puede gestionar sin pedir la contraseña.
        self.registration_options()
        self.data("/api/auth/passkeys/delete", {"id": self.data("/api/settings")["passkeys"][0]["id"]})

    def test_reauth_window_expires(self):
        self.reauth()
        with self.server.lock:
            token = self.cookie.split("=", 1)[1]
            self.server.sessions[token]["reauth_at"] = time.monotonic() - REAUTH_TTL - 1
        code, _, _ = self.request("/api/auth/passkeys/register/options", {})
        self.assertEqual(code, 403)


class PasskeySecurityTests(PasskeyTestCase):
    """Pruebas negativas: origen, challenge, firma, UV, contador y autorización."""

    def test_registration_challenge_is_single_use(self):
        authenticator = self.authenticator()
        self.reauth()
        challenge = self.registration_options()["challenge"]
        credential = authenticator.registration(challenge)
        self.data("/api/auth/passkeys/register", {"credential": credential})
        self.data("/api/auth/passkeys/register", {"credential": credential}, status=400)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM passkeys")[0][0], 1)

    def test_expired_registration_challenge_is_rejected(self):
        authenticator = self.authenticator()
        self.reauth()
        challenge = self.registration_options()["challenge"]
        credential = authenticator.registration(challenge)
        self.sql_exec("UPDATE auth_challenges SET expires_at=1")
        self.data("/api/auth/passkeys/register", {"credential": credential}, status=400)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM passkeys")[0][0], 0)

    def test_foreign_origin_is_rejected_by_the_library(self):
        authenticator = FakeAuthenticator("127.0.0.1", "https://otro-origen.ejemplo.test")
        self.reauth()
        challenge = self.registration_options()["challenge"]
        credential = authenticator.registration(challenge)
        self.data("/api/auth/passkeys/register", {"credential": credential}, status=400)

    def test_server_rejects_webauthn_on_a_non_local_http_origin(self):
        # NFR-SVC-003: HTTP servido desde una IP de red no es un origen confiable.
        remote = "192.0.2.10:8000"
        origin = f"http://{remote}"
        for path, body in [("/api/auth/passkeys/login/options", {}),
                           ("/api/auth/passkeys/login", {"credential": {}}),
                           ("/api/auth/passkeys/register/options", {}),
                           ("/api/auth/passkeys/register", {"credential": {}})]:
            code, _, raw = self.request(path, body, extra={"Origin": origin}, host=remote)
            self.assertEqual(code, 403, f"{path}: {raw.decode()}")
        # El mismo Host sobre HTTPS sí sería de confianza (aquí no se simula TLS).

    def test_malformed_payloads_are_rejected_without_a_server_error(self):
        self.reauth()
        self.registration_options()
        for body in [{}, {"credential": "text"}, {"credential": {}},
                     {"credential": {"response": {}}},
                     {"credential": {"response": {"clientDataJSON": "@@@"}}},
                     {"credential": {"response": {"clientDataJSON": "e30", "attestationObject": "AA"}}}]:
            code, _, _ = self.request("/api/auth/passkeys/register", body)
            self.assertEqual(code, 400, body)

    def test_a_login_challenge_cannot_register_a_passkey(self):
        # El propósito ata el reto a su ceremonia: un reto de login vivo no
        # sirve para registrarse, ni siquiera del mismo usuario.
        authenticator = self.authenticator()
        challenge = self.data("/api/auth/passkeys/login/options", {})["publicKey"]["challenge"]
        credential = authenticator.registration(challenge)
        self.reauth()
        self.data("/api/auth/passkeys/register", {"credential": credential}, status=400)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM passkeys")[0][0], 0)

    def test_a_registration_challenge_cannot_log_in(self):
        # Recíproco: el reto emitido para registrarse no autentica a nadie.
        authenticator = self.authenticator()
        self.add_passkey(authenticator)
        self.reauth()
        challenge = self.registration_options()["challenge"]
        assertion = authenticator.authentication(challenge)
        self.data("/api/auth/passkeys/login", {"credential": assertion}, status=401)

    def test_registration_challenge_of_another_user_is_rejected(self):
        first = self.authenticator()
        self.reauth()
        challenge = self.registration_options()["challenge"]
        credential = first.registration(challenge)
        # Otro usuario intenta registrarse con el reto emitido a la primera sesión.
        self.register("otra")
        self.reauth()
        self.data("/api/auth/passkeys/register", {"credential": credential}, status=400)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM passkeys")[0][0], 0)

    def test_login_challenge_is_single_use_and_expires(self):
        authenticator = self.authenticator()
        self.add_passkey(authenticator)
        challenge = self.data("/api/auth/passkeys/login/options", {})["publicKey"]["challenge"]
        assertion = authenticator.authentication(challenge)
        self.data("/api/auth/passkeys/login", {"credential": assertion})
        self.data("/api/auth/passkeys/login", {"credential": assertion}, status=401)
        challenge = self.data("/api/auth/passkeys/login/options", {})["publicKey"]["challenge"]
        assertion = authenticator.authentication(challenge)
        self.sql_exec("UPDATE auth_challenges SET expires_at=1")
        self.data("/api/auth/passkeys/login", {"credential": assertion}, status=401)

    def test_login_rejects_unknown_credential_and_bad_signatures(self):
        authenticator = self.authenticator()
        other = self.authenticator()
        self.add_passkey(authenticator)
        # Una asertión firmada por otra clave no valida contra la credencial
        # registrada, aunque se presente con su ID.
        challenge = self.data("/api/auth/passkeys/login/options", {})["publicKey"]["challenge"]
        forged = other.authentication(challenge)
        forged["id"] = forged["rawId"] = b64u(authenticator.credential_id)
        self.data("/api/auth/passkeys/login", {"credential": forged}, status=400)
        # Una credencial nunca registrada tampoco abre sesión.
        challenge = self.data("/api/auth/passkeys/login/options", {})["publicKey"]["challenge"]
        self.data("/api/auth/passkeys/login", {"credential": other.authentication(challenge)}, status=401)

    def test_user_verification_is_required(self):
        authenticator = self.authenticator(uv=False)
        self.reauth()
        challenge = self.registration_options()["challenge"]
        self.data("/api/auth/passkeys/register", {"credential": authenticator.registration(challenge)},
                  status=400)
        trusted = self.authenticator()
        self.add_passkey(trusted)
        challenge = self.data("/api/auth/passkeys/login/options", {})["publicKey"]["challenge"]
        no_uv = FakeAuthenticator("127.0.0.1", f"http://{self.host}", uv=False)
        no_uv.credential_id = trusted.credential_id
        no_uv.private_key = trusted.private_key
        no_uv.sign_count = 0
        self.data("/api/auth/passkeys/login", {"credential": no_uv.authentication(challenge)}, status=400)

    def test_sign_count_must_only_advance(self):
        authenticator = self.authenticator()
        self.add_passkey(authenticator)
        credential_id = self.data("/api/settings")["passkeys"][0]["id"]
        # Un contador menor o igual que el guardado es señal de replay/clon.
        self.sql_exec("UPDATE passkeys SET sign_count=9 WHERE credential_id=?", (credential_id,))
        challenge = self.data("/api/auth/passkeys/login/options", {})["publicKey"]["challenge"]
        assertion = authenticator.authentication(challenge, increment=False)
        self.data("/api/auth/passkeys/login", {"credential": assertion}, status=400)

    def test_login_options_do_not_enumerate_users(self):
        first_status, _, first_raw = self.request("/api/auth/passkeys/login/options", {})
        first = json.loads(first_raw)
        self.register("otra")
        second_status, _, second_raw = self.request("/api/auth/passkeys/login/options", {})
        second = json.loads(second_raw)
        self.assertEqual((first_status, second_status), (200, 200))
        self.assertEqual(sorted(first["publicKey"]), sorted(second["publicKey"]))
        for payload in (first, second):
            # Sin `allowCredentials` no se lista ninguna passkey de nadie.
            self.assertFalse(payload["publicKey"].get("allowCredentials"))
        self.assertNotEqual(first["publicKey"]["challenge"], second["publicKey"]["challenge"])

    def test_concurrent_login_with_one_challenge_opens_one_session(self):
        authenticator = self.authenticator()
        self.add_passkey(authenticator)
        challenge = self.data("/api/auth/passkeys/login/options", {})["publicKey"]["challenge"]
        assertion = authenticator.authentication(challenge)
        results = []
        barrier = threading.Barrier(4)

        def attempt():
            barrier.wait()
            results.append(self.request("/api/auth/passkeys/login", {"credential": assertion})[0])

        threads = [threading.Thread(target=attempt) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sorted(results), [200, 401, 401, 401], results)


class TrustedOriginParsingTests(unittest.TestCase):
    """Origen canónico y lista de confianza (biblio/origins.py, TODO-SEC-003)."""

    def test_canonical_origins_normalise_case_and_default_ports(self):
        self.assertEqual(origins.parse_origin("https://Example.COM:443"), "https://example.com")
        self.assertEqual(origins.parse_origin("HTTPS://LocalHost"), "https://localhost")
        self.assertEqual(origins.parse_origin("http://localhost:0080"), "http://localhost")
        self.assertEqual(origins.parse_origin("http://localhost:8000"), "http://localhost:8000")
        self.assertEqual(origins.parse_origin("https://[::1]:8443"), "https://[::1]:8443")

    def test_non_canonical_origins_are_rejected(self):
        for value in ["https://user@ejemplo.test", "https://user:pass@ejemplo.test/x",
                      "http://a b", "http://evil.example/../x", "http://evil.example?x",
                      "http://evil.example#f", "http://evil.example:abc",
                      "http://evil.example:0", "http://evil.example:99999",
                      "http://evil.example:80:90", "ftp://evil.example",
                      "http://evil.example/\r\nX: y", ""]:
            self.assertIsNone(origins.parse_origin(value), value)

    def test_local_https_and_any_local_port_are_trusted_by_default(self):
        trusted = origins.TrustedOrigins()
        for value in ["http://localhost:5555", "http://127.0.0.1", "https://localhost",
                      "https://127.0.0.1:8443"]:
            self.assertTrue(trusted.trusted(origins.parse_origin(value)), value)
        for value in ["https://biblio.example.org", "http://192.0.2.10:8000",
                      "https://evil.example"]:
            self.assertFalse(trusted.trusted(origins.parse_origin(value)), value)
        self.assertFalse(trusted.trusted(None))

    def test_listed_origins_match_exactly_and_only_https_outside_loopback(self):
        trusted = origins.TrustedOrigins(origins.parse_trusted_origins(
            "https://biblio.example.org, https://biblio.example.org:8443"))
        self.assertTrue(trusted.trusted(origins.parse_origin("https://biblio.example.org")))
        self.assertTrue(trusted.trusted(origins.parse_origin("https://BIBLIO.example.org:8443")))
        # Ni sufijos ni prefijos del hostname listado cuentan como el mismo origen.
        self.assertFalse(trusted.trusted(origins.parse_origin("https://sub.biblio.example.org")))
        self.assertFalse(trusted.trusted(origins.parse_origin("https://evilbiblio.example.org")))
        self.assertFalse(trusted.trusted(origins.parse_origin("https://biblio.example.org:8444")))
        for raw in ["http://192.0.2.10", "https://", "biblio.example.org",
                    "https://user@biblio.example.org"]:
            with self.assertRaises(AppError, msg=raw):
                origins.parse_trusted_origins(raw)


class PasskeyTrustedOriginTests(unittest.TestCase):
    """Host hostil, TLS sin listar y origen HTTPS configurado (TODO-SEC-003)."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".biblio-test-", dir=Path(__file__).parents[1])
        self.addCleanup(self.temp.cleanup)
        self.servers = []

    def tearDown(self):
        for server, thread, store in self.servers:
            server.shutdown()
            server.server_close()
            thread.join()
            store.close()

    def start_server(self, secure=False, trusted=()):
        path = Path(self.temp.name) / f"biblio-{len(self.servers)}.sqlite3"
        store = Store(path, key=Fernet.generate_key())
        server = AppServer(("127.0.0.1", 0), lambda card, password: FakeClient(card, password),
                           store=store, secure=secure, trusted_origins=trusted)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.servers.append((server, thread, store))
        return server

    def request(self, server, method, path, host, body=None, cookie="", csrf="", origin=None):
        connection = http.client.HTTPConnection(*server.server_address, timeout=5)
        connection.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
        connection.putheader("Host", host)
        connection.putheader("Connection", "close")
        if cookie:
            connection.putheader("Cookie", cookie)
        if origin:
            connection.putheader("Origin", origin)
        data = json.dumps(body).encode() if body is not None else None
        if body is not None:
            connection.putheader("Content-Type", "application/json")
            connection.putheader("X-CSRF-Token", csrf)
            connection.putheader("Content-Length", str(len(data)))
        connection.endheaders(data)
        response = connection.getresponse()
        payload = response.read()
        result = response.status, dict(response.getheaders()), payload
        connection.close()
        return result

    def test_https_with_an_unlisted_host_is_rejected(self):
        # Antes de la corrección cualquier Host sobre TLS era de confianza.
        server = self.start_server(secure=True)
        for host in [f"evil.example:{server.server_port}", "evil.example", "192.0.2.10:8000"]:
            code, _, raw = self.request(server, "POST", "/api/auth/passkeys/login/options",
                                        host, body={})
            self.assertEqual(code, 403, f"{host}: {raw.decode()}")

    def test_https_with_a_local_host_still_works(self):
        server = self.start_server(secure=True)
        for host in [f"localhost:{server.server_port}", f"127.0.0.1:{server.server_port}"]:
            code, _, raw = self.request(server, "POST", "/api/auth/passkeys/login/options",
                                        host, body={})
            self.assertEqual(code, 200, f"{host}: {raw.decode()}")

    def test_only_the_exact_configured_https_origin_is_accepted(self):
        server = self.start_server(secure=True, trusted=["https://biblio.example.org"])
        code, _, raw = self.request(server, "POST", "/api/auth/passkeys/login/options",
                                    "biblio.example.org", body={})
        self.assertEqual(code, 200, raw.decode())
        for host in ["otro.example.org", "sub.biblio.example.org", "evil.example"]:
            code, _, raw = self.request(server, "POST", "/api/auth/passkeys/login/options",
                                        host, body={})
            self.assertEqual(code, 403, f"{host}: {raw.decode()}")

    def test_a_matching_origin_header_does_not_validate_a_hostile_host(self):
        # Un navegador en `https://evil.example` mandaría Origin==Host; el
        # Host hostil sigue fuera de la lista y WebAuthn responde 403.
        server = self.start_server(secure=True)
        code, _, raw = self.request(server, "POST", "/api/auth/passkeys/login/options",
                                    "evil.example", body={}, origin="https://evil.example")
        self.assertEqual(code, 403, raw.decode())

    def test_malformed_hosts_are_rejected_before_the_body(self):
        server = self.start_server()
        port = server.server_port
        for host in [f"evil.example:{port}/x", "evil@localhost", f"localhost:{port}abc",
                     f"localhost:{port}99", "evil example", "[::1]:8000"]:
            code, _, raw = self.request(server, "POST", "/api/auth/passkeys/login/options",
                                        host, body={})
            self.assertIn(code, (400, 403), f"{host}: {raw.decode()}")

    def test_full_flow_on_a_configured_https_origin(self):
        # El origen esperado y el RP ID salen del origen listado, no del bind.
        server = self.start_server(secure=True, trusted=["https://biblio.example.org"])
        host = "biblio.example.org"
        code, headers, raw = self.request(
            server, "POST", "/api/register", host,
            {"username": "owner", "name": "Owner", "password": APP_PASSWORD})
        self.assertEqual(code, 200, raw.decode())
        cookie = headers["Set-Cookie"].split(";")[0]
        csrf = json.loads(raw)["csrf"]
        authenticator = FakeAuthenticator("biblio.example.org", "https://biblio.example.org")
        code, _, raw = self.request(server, "POST", "/api/auth/reauth", host,
                                    {"password": APP_PASSWORD}, cookie=cookie, csrf=csrf)
        self.assertEqual(code, 200, raw.decode())
        code, _, raw = self.request(server, "POST", "/api/auth/passkeys/register/options",
                                    host, {}, cookie=cookie, csrf=csrf)
        self.assertEqual(code, 200, raw.decode())
        challenge = json.loads(raw)["publicKey"]["challenge"]
        code, _, raw = self.request(
            server, "POST", "/api/auth/passkeys/register", host,
            {"credential": authenticator.registration(challenge), "label": "Llave TLS"},
            cookie=cookie, csrf=csrf)
        self.assertEqual(code, 200, raw.decode())
        # Login con la misma passkey y el mismo Host de confianza.
        code, _, raw = self.request(server, "POST", "/api/auth/passkeys/login/options",
                                    host, {})
        self.assertEqual(code, 200, raw.decode())
        challenge = json.loads(raw)["publicKey"]["challenge"]
        code, _, raw = self.request(server, "POST", "/api/auth/passkeys/login", host,
                                    {"credential": authenticator.authentication(challenge)})
        self.assertEqual(code, 200, raw.decode())
        self.assertTrue(json.loads(raw)["authenticated"])
        # Un Host hostil no puede emitir retos ni derivar el origen esperado.
        code, _, raw = self.request(server, "POST", "/api/auth/passkeys/login/options",
                                    "evil.example", {})
        self.assertEqual(code, 403, raw.decode())


if __name__ == "__main__":
    unittest.main()
