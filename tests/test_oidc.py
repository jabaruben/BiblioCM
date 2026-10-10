"""Acceso opcional con Google vía OIDC (TODO-AUTH-004 / FR-AUTH-005).

Pruebas contra el servidor local con el proveedor falso de
[fake_oidc](fake_oidc.py): descubrimiento, JWKS y token firmado con RS256, sin
hablar con Google ni usar credenciales reales. Cubren el opt-in, `state`/`nonce`
y PKCE de un solo uso, verificación del token (firma, issuer, audiencia,
expiración y nonce), identidad por `sub`, alta explícita con alias
determinista, ausencia de merge por email y vinculación/desvinculación con
reautenticación.
"""
import contextlib
import http.client
import io
import json
import sqlite3
import tempfile
import threading
import time
import unittest
import unittest.mock
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from cryptography.fernet import Fernet

from biblio import mailer as mailer_module
from biblio.oidc import GoogleConfig, GoogleProvider, config_from_env, STATE_TTL as OIDC_STATE_TTL
from biblio.store import AppError, Store
from biblio.web import REAUTH_TTL, AppServer, Handler
from tests.fake_oidc import CLIENT_ID, CLIENT_SECRET, FakeOidcProvider
from tests.test_identity import FakeSmtpServer, smtp_config
from tests.test_web import FakeClient

APP_PASSWORD = "clave-de-prueba-123"


class OidcTestCase(unittest.TestCase):
    """Base: servidor con OPAC/SMTP falso y el proveedor OIDC local."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".biblio-test-", dir=Path(__file__).parents[1])
        self.path = Path(self.temp.name) / "biblio.sqlite3"
        self.store = Store(self.path, key=Fernet.generate_key())
        self.provider = FakeOidcProvider()
        self.smtp = FakeSmtpServer()
        self.smtp_thread = threading.Thread(target=self.smtp.serve_forever, daemon=True)
        self.smtp_thread.start()
        mailer = mailer_module.Mailer(smtp_config(self.smtp.port))
        config = GoogleConfig(client_id=CLIENT_ID, client_secret=CLIENT_SECRET,
                              issuer=self.provider.base_url)
        self.server = AppServer(("127.0.0.1", 0), lambda card, password: FakeClient(card, password),
                                store=self.store, mailer=mailer, google=config)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host = f"127.0.0.1:{self.server.server_port}"
        self.cookie, self.csrf = "", ""
        # Cookie de enlace del flujo Google en **este** navegador y todas las
        # `Set-Cookie` de la última respuesta (el navegador tiene un jar propio).
        self.binding, self.last_cookies = "", []
        self.register("owner")

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.smtp.shutdown()
        self.smtp.server_close()
        self.smtp_thread.join()
        self.provider.stop()
        self.store.close()
        self.temp.cleanup()

    def request(self, path, body=None, extra=None):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=10)
        headers = {"Cookie": self.cookie, "Host": self.host}
        if body is not None:
            headers.update({"Content-Type": "application/json", "X-CSRF-Token": self.csrf})
        headers.update(extra or {})
        connection.request("POST" if body is not None else "GET",
                           path, json.dumps(body) if body is not None else None, headers)
        response = connection.getresponse()
        data = response.read()
        pairs = response.getheaders()
        # El jar del navegador: todas las `Set-Cookie`, no solo la última.
        self.last_cookies = [value for key, value in pairs if key.lower() == "set-cookie"]
        result = response.status, dict(pairs), data
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

    def verify_email(self, email="owner@ejemplo.test"):
        self.data("/api/auth/email/request", {"email": email})
        self.data("/api/auth/email/verify", {"token": self.smtp.last_token()})
        return email

    # -- flujo OIDC ------------------------------------------------------

    def start(self, mode, status=200):
        """Pide el `authorize_url`. Login/signup son públicos: sin sesión.

        El navegador que inicia el flujo guarda la cookie de enlace que emite
        el servidor (`self.binding`) y la envía al volver del proveedor.
        """
        saved = self.cookie, self.csrf
        if mode in ("login", "signup"):
            self.cookie, self.csrf = "", ""
        try:
            code, _, raw = self.request("/api/auth/google/start", {"mode": mode})
        finally:
            self.cookie, self.csrf = saved
        self.assertEqual(code, status, raw.decode())
        self.binding = next((value.split(";")[0] for value in self.last_cookies
                             if value.startswith("biblio_oidc=")), "")
        return json.loads(raw)["authorize_url"] if status == 200 else None

    def authorize(self, authorize_url):
        """El proveedor autoriza y devuelve el `code` con su `state`."""
        parts = urlsplit(authorize_url)
        connection = http.client.HTTPConnection(parts.hostname, parts.port, timeout=10)
        connection.request("GET", parts.path + "?" + parts.query)
        response = connection.getresponse()
        location = response.getheader("Location")
        connection.close()
        self.assertEqual(response.status, 303, location)
        return parse_qs(urlsplit(location).query)

    def callback(self, parameters, status=303, binding=None):
        """Callback del proveedor contra la app; devuelve cabeceras y destino.

        El navegador envía al volver **solo** la cookie de enlace: la de sesión
        es `SameSite=Strict` y no viaja en una navegación cruzada. `binding`
        permite simular otro navegador (cookie ajena, ausente o caducada).
        """
        query = "&".join(f"{key}={value[0] if isinstance(value, (list, tuple)) else value}"
                         for key, value in parameters.items())
        cookie = self.binding if binding is None else binding
        code, headers, raw = self.request("/api/auth/google/callback?" + query, None,
                                          {"Cookie": cookie})
        self.assertEqual(code, status, raw.decode())
        location = headers.get("Location", "")
        for value in self.last_cookies:
            if value.startswith("biblio_session=") and value != "biblio_session=;":
                self.cookie = value.split(";")[0]
            if value.startswith("biblio_session=;"):
                self.cookie = ""
            if value.startswith("biblio_oidc=;"):
                self.binding = ""
        return headers, location

    def assert_no_session(self, headers):
        """El flujo no abrió sesión y retiró siempre su cookie de enlace."""
        self.assertTrue(any(value.startswith("biblio_oidc=;") for value in self.last_cookies),
                        self.last_cookies)
        self.assertFalse(any(value.startswith("biblio_session=") for value in self.last_cookies),
                         self.last_cookies)
        self.assertNotIn("biblio_session=", headers.get("Set-Cookie", ""))

    def complete(self, mode, callback_status=303):
        return self.callback(self.authorize(self.start(mode)), status=callback_status)


class GoogleDisabledTests(unittest.TestCase):
    """Sin configuración no hay botón, no hay start y no hay callback."""

    def test_everything_is_disabled_without_configuration(self):
        temp = tempfile.TemporaryDirectory(prefix=".biblio-test-", dir=Path(__file__).parents[1])
        self.addCleanup(temp.cleanup)
        store = Store(Path(temp.name) / "biblio.sqlite3")
        self.addCleanup(store.close)
        self.assertIsNone(config_from_env({}))
        server = AppServer(("127.0.0.1", 0), lambda card, password: FakeClient(card, password), store=store)
        self.addCleanup(server.server_close)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (server.shutdown(), thread.join()))
        connection = http.client.HTTPConnection(*server.server_address, timeout=5)
        connection.request("GET", "/api/session")
        response = connection.getresponse()
        session = json.loads(response.read())
        connection.close()
        self.assertEqual(session["google"], {"enabled": False})
        for path, body, expected in [("/api/auth/google/start", {"mode": "login"}, 503),
                                     ("/api/auth/google/start", {"mode": "signup"}, 503),
                                     ("/api/auth/google/start", {"mode": "link"}, 503),
                                     ("/api/auth/google/unlink", {}, 401)]:
            connection = http.client.HTTPConnection(*server.server_address, timeout=5)
            connection.request("POST", path, json.dumps(body),
                               {"Content-Type": "application/json", "Host": f"127.0.0.1:{server.server_port}"})
            reply = connection.getresponse()
            payload = reply.read()
            self.assertEqual(reply.status, expected, f"{path}: {payload}")
            connection.close()
        connection = http.client.HTTPConnection(*server.server_address, timeout=5)
        connection.request("GET", "/api/auth/google/callback?code=1&state=2")
        reply = connection.getresponse()
        self.assertEqual(reply.status, 503)
        connection.close()


class GoogleConfigurationTests(unittest.TestCase):
    """Configuración por entorno y validación de endpoints."""

    def test_environment_builds_configuration(self):
        config = config_from_env({"BIBLIO_GOOGLE_CLIENT_ID": "id-ficticio",
                                  "BIBLIO_GOOGLE_CLIENT_SECRET": "secreto-ficticio",
                                  "BIBLIO_GOOGLE_ISSUER": "https://ejemplo.test/"})
        self.assertEqual(config.client_id, "id-ficticio")
        self.assertEqual(config.issuer, "https://ejemplo.test")

    def test_partial_configuration_disables_the_feature(self):
        self.assertIsNone(config_from_env({"BIBLIO_GOOGLE_CLIENT_ID": "solo-id"}))
        self.assertIsNone(config_from_env({"BIBLIO_GOOGLE_CLIENT_SECRET": "solo-secreto"}))

    def test_http_endpoints_outside_loopback_are_rejected(self):
        config = GoogleConfig(client_id="id", client_secret="secreto",
                              issuer="https://ejemplo.test",
                              auth_endpoint="https://ejemplo.test/authorize",
                              token_endpoint="http://192.0.2.10/token",
                              jwks_uri="https://ejemplo.test/jwks")
        provider = GoogleProvider(config, fetch=lambda url: b"{}")
        with self.assertRaises(AppError) as caught:
            provider.endpoints()
        self.assertEqual(caught.exception.status, 503)

    def test_discovery_must_match_the_configured_issuer(self):
        config = GoogleConfig(client_id="id", client_secret="secreto",
                              issuer="https://ejemplo.test")
        provider = GoogleProvider(config, fetch=lambda url: json.dumps(
            {"issuer": "https://otro.test", "authorization_endpoint": "https://otro.test/a",
             "token_endpoint": "https://otro.test/t", "jwks_uri": "https://otro.test/j"}).encode())
        with self.assertRaises(AppError) as caught:
            provider.endpoints()
        self.assertEqual(caught.exception.status, 503)


class GoogleFlowTests(OidcTestCase):
    """Flujos completos: vincular, entrar, crear cuenta y desvincular."""

    def test_authorization_request_carries_state_nonce_and_pkce(self):
        authorize_url = self.start("login")
        parameters = parse_qs(urlsplit(authorize_url).query)
        self.assertEqual(parameters["client_id"], [CLIENT_ID])
        self.assertEqual(parameters["response_type"], ["code"])
        self.assertEqual(parameters["code_challenge_method"], ["S256"])
        self.assertIn("openid", parameters["scope"][0].split())
        self.assertTrue(parameters["state"][0])
        self.assertTrue(parameters["nonce"][0])
        self.assertTrue(parameters["code_challenge"][0])
        self.assertTrue(parameters["redirect_uri"][0].endswith("/api/auth/google/callback"))
        # El estado y el nonce viven en la base solo como hash + detalle cifrado
        # (Fernet), nunca en claro.
        purpose, detail = self.sql("SELECT purpose,detail FROM auth_challenges")[0]
        self.assertEqual(purpose, "oidc")
        self.assertTrue(detail.startswith(b"gAAAA"), detail[:12])
        self.assertNotIn(parameters["state"][0].encode(), detail)
        self.assertNotIn(parameters["nonce"][0].encode(), detail)

    def test_link_requires_verified_email_and_reauthentication(self):
        code, _, _ = self.request("/api/auth/google/start", {"mode": "link"})
        self.assertEqual(code, 403)  # sin reautenticación
        self.reauth()
        code, _, raw = self.request("/api/auth/google/start", {"mode": "link"})
        self.assertEqual(code, 403, raw.decode())  # sin email verificado
        self.verify_email()
        self.reauth()
        self.start("link")
        headers, location = self.callback(self.authorize(self.start("link")))
        self.assertEqual(location, "/?google=linked")
        identities = self.data("/api/settings")["identities"]
        self.assertEqual([item["provider"] for item in identities], ["google"])
        self.assertIn("sub-ficticio-1", self.sql("SELECT sub FROM identities")[0][0])

    def test_link_requires_a_session(self):
        self.cookie, self.csrf = "", ""
        code, _, _ = self.request("/api/auth/google/start", {"mode": "link"})
        self.assertEqual(code, 401)

    def test_link_requires_csrf(self):
        self.verify_email()
        self.reauth()
        code, _, _ = self.request("/api/auth/google/start", {"mode": "link"}, {"X-CSRF-Token": "malo"})
        self.assertEqual(code, 403)

    def test_login_after_linking_opens_a_normal_session(self):
        self.verify_email()
        self.reauth()
        self.complete("link")
        self.cookie, self.csrf = "", ""
        headers, location = self.callback(self.authorize(self.start("login")))
        self.assertEqual(location, "/?google=signed")
        self.assertIn("Set-Cookie", headers)
        settings = self.data("/api/settings")
        self.assertEqual(settings["user"]["username"], "owner")
        self.assertEqual([item["provider"] for item in settings["identities"]], ["google"])

    def test_login_without_a_linked_identity_never_merges_by_email(self):
        # Email verificado local con la misma dirección que Google: sin vínculo
        # no hay entrada, no hay merge y no se crea ninguna cuenta.
        self.verify_email("ana.tester@ejemplo.test")
        before = self.sql("SELECT COUNT(*) FROM users")[0][0]
        headers, location = self.callback(self.authorize(self.start("login")))
        self.assertEqual(location, "/?google=not-linked")
        self.assert_no_session(headers)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM users")[0][0], before)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM identities")[0][0], 0)

    def test_signup_creates_an_account_with_verified_email_and_deterministic_alias(self):
        self.cookie, self.csrf = "", ""
        headers, location = self.complete("signup")
        self.assertEqual(location, "/?google=signed")
        self.assertIn("Set-Cookie", headers)
        settings = self.data("/api/settings")
        user = settings["user"]
        self.assertEqual(user["email"], "ana.tester@ejemplo.test")
        self.assertTrue(user["email_verified"])
        self.assertEqual(user["username"], "ana.tester")
        self.assertEqual([item["provider"] for item in settings["identities"]], ["google"])
        # Ninguna sesión con la contraseña aleatoria: nadie la conoce.
        code, _, _ = self.request("/api/login", {"username": "ana.tester", "password": APP_PASSWORD})
        self.assertEqual(code, 401)

    def test_signup_with_a_taken_alias_gets_a_deterministic_suffix(self):
        # Una cuenta local ocupa el alias; el alta con Google no la pisa y
        # recibe un sufijo determinista derivado del `sub`.
        self.register("ana.tester")
        self.provider.scenario["claims"] = {"sub": "sub-ficticio-2",
                                            "email": "ana.tester@otro.ejemplo.test"}
        headers, location = self.complete("signup")
        self.assertEqual(location, "/?google=signed")
        usernames = {row[0] for row in self.sql("SELECT username FROM users")}
        expected = Store._alias_candidates("ana.tester@otro.ejemplo.test",
                                           self.provider.base_url, "sub-ficticio-2")[1]
        self.assertIn("ana.tester", usernames)
        self.assertIn(expected, usernames)
        # El mismo `sub` con el mismo email vuelve a dar siempre ese alias.
        self.assertEqual(Store._alias_candidates("ana.tester@otro.ejemplo.test",
                                                 self.provider.base_url, "sub-ficticio-2")[1],
                         expected)

    def test_signup_with_an_existing_email_is_rejected_without_merge(self):
        self.verify_email("ana.tester@ejemplo.test")
        before = self.sql("SELECT COUNT(*) FROM users")[0][0]
        _, location = self.complete("signup")
        self.assertEqual(location, "/?google=exists")
        self.assertEqual(self.sql("SELECT COUNT(*) FROM users")[0][0], before)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM identities")[0][0], 0)

    def test_signup_requires_a_verified_provider_email(self):
        self.provider.scenario["claims"] = {"email_verified": False}
        _, location = self.complete("signup")
        self.assertEqual(location, "/?google=error")
        self.assertEqual(self.sql("SELECT COUNT(*) FROM users")[0][0], 1)

    def test_state_is_single_use(self):
        parameters = self.authorize(self.start("login"))
        self.callback(parameters)
        headers, location = self.callback(parameters)
        self.assertEqual(location, "/?google=error")
        self.assert_no_session(headers)

    def test_expired_state_is_rejected(self):
        parameters = self.authorize(self.start("login"))
        self.sql_exec("UPDATE auth_challenges SET expires_at=1")
        headers, location = self.callback(parameters)
        self.assertEqual(location, "/?google=error")
        self.assert_no_session(headers)

    def test_provider_failure_leaves_no_session_and_consumes_the_state(self):
        self.provider.scenario["token_error"] = "invalid_grant"
        headers, location = self.complete("signup")
        self.assertEqual(location, "/?google=error")
        self.assert_no_session(headers)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM auth_challenges")[0][0], 0)

    def test_callback_without_a_valid_state_is_rejected(self):
        headers, location = self.callback({"code": "inventado", "state": "inventado"})
        self.assertEqual(location, "/?google=error")
        self.assert_no_session(headers)

    def test_denied_at_the_provider_is_reported_without_a_session(self):
        parameters = self.authorize(self.start("login"))
        headers, location = self.callback({"error": "access_denied",
                                           "state": parameters["state"][0]})
        self.assertEqual(location, "/?google=denied")
        self.assert_no_session(headers)

    def test_unlink_requires_reauth_and_keeps_the_account(self):
        self.verify_email()
        self.reauth()
        self.complete("link")
        account = self.data("/api/accounts/add", {"card": "111", "label": "Mía",
                                                  "password": "portal-otra-clave-1"})["account"]
        # La ventana de reautenticación se cierra y la desvinculación se niega.
        with self.server.lock:
            self.server.sessions[self.cookie.split("=", 1)[1]]["reauth_at"] = (
                time.monotonic() - REAUTH_TTL - 1)
        code, _, raw = self.request("/api/auth/google/unlink", {})
        self.assertEqual(code, 403, raw.decode())
        self.assertEqual(json.loads(raw)["code"], "reauth_required")
        self.reauth()
        self.data("/api/auth/google/unlink", {})
        self.assertEqual(self.sql("SELECT COUNT(*) FROM identities")[0][0], 0)
        # La cuenta, sus carnés y su email verificado siguen intactos.
        settings = self.data("/api/settings")
        self.assertEqual(settings["accounts"][0]["id"], account)
        self.assertTrue(settings["user"]["email_verified"])

    def test_the_same_google_account_cannot_be_linked_twice(self):
        self.verify_email()
        self.reauth()
        self.complete("link")
        self.register("otra")
        self.verify_email("otra@ejemplo.test")
        self.reauth()
        _, location = self.callback(self.authorize(self.start("link")))
        self.assertEqual(location, "/?google=exists")
        owners = self.sql("SELECT user_id FROM identities")
        self.assertEqual(len(owners), 1)

    def test_rate_limit_on_the_start_route(self):
        for index in range(20):
            self.start("login")
        self.data("/api/auth/google/start", {"mode": "login"}, status=429)


class GoogleBindingTests(OidcTestCase):
    """Login CSRF y vínculo atado a la sesión que lo inició (TODO-SEC-004).

    Dos contextos de navegador contra el mismo servidor: el que **inició** el
    flujo conserva la cookie de enlace y completa; cualquier transferencia del
    par `code`+`state` a otro navegador (o cookie ausente, ajena, reutilizada o
    caducada) se rechaza **antes** de canjear el `code` con el proveedor, sin
    abrir sesión ni escribir vínculos.
    """

    def test_peek_challenge_reads_the_state_without_consuming_it(self):
        self.store.put_challenge("oidc", None, "estado-x", 600, b"detalle")
        self.assertEqual(self.store.peek_challenge("oidc", "estado-x"), (None, b"detalle"))
        self.assertEqual(self.store.peek_challenge("oidc", "estado-x"), (None, b"detalle"))
        self.assertIsNone(self.store.peek_challenge("oidc", "otro-estado"))
        self.assertEqual(self.store.take_challenge("oidc", "estado-x"), (None, b"detalle"))
        self.assertIsNone(self.store.peek_challenge("oidc", "estado-x"))
        self.assertIsNone(self.store.take_challenge("oidc", "estado-x"))

    def test_start_emits_a_scoped_binding_cookie_and_stores_only_its_digest(self):
        authorize_url = self.start("signup")
        emitted = next(value for value in self.last_cookies
                       if value.startswith("biblio_oidc="))
        self.assertTrue(self.binding.startswith("biblio_oidc="), self.binding)
        value = self.binding.split("=", 1)[1]
        self.assertRegex(value, r"^[A-Za-z0-9_-]{40,}$")
        attributes = emitted.split(";", 1)[1]
        self.assertIn("Path=/api/auth/google", attributes)
        self.assertIn("HttpOnly", attributes)
        self.assertIn("SameSite=Lax", attributes)
        self.assertIn(f"Max-Age={OIDC_STATE_TTL}", attributes)
        # Servidor de pruebas sin `--secure`: no se emite `Secure`.
        self.assertNotIn("Secure", attributes)
        # El valor no viaja al proveedor, no va en la query y no se guarda en claro.
        self.assertNotIn(value, authorize_url)
        details = b"".join(row[0] for row in self.sql("SELECT detail FROM auth_challenges"))
        self.assertTrue(details)
        self.assertNotIn(value.encode(), details)

    def start_flow(self, mode):
        """Inicia un flujo y devuelve `(authorize_url, cookie_de_enlace)`."""
        return self.start(mode), self.binding

    def test_the_original_browser_completes_and_the_cookie_is_cleared(self):
        authorize_url, binding = self.start_flow("signup")
        self.assertTrue(binding)
        headers, location = self.callback(self.authorize(authorize_url), binding=binding)
        self.assertEqual(location, "/?google=signed")
        self.assertTrue(self.cookie.startswith("biblio_session="), self.cookie)
        self.assertTrue(any(value.startswith("biblio_oidc=;") for value in self.last_cookies),
                        self.last_cookies)
        self.assertEqual(self.binding, "", "el navegador retira la cookie al terminar")
        settings = self.data("/api/settings")
        self.assertEqual(settings["user"]["username"], "ana.tester")

    def test_a_callback_without_the_binding_cookie_is_rejected_before_the_provider(self):
        authorize_url, binding = self.start_flow("signup")
        query = self.authorize(authorize_url)
        headers, location = self.callback(query, binding="")
        self.assertEqual(location, "/?google=error")
        self.assert_no_session(headers)
        self.assertEqual(self.provider.seen, [], "el code no debe canjearse")
        self.assertTrue(self.provider.codes, "el code sigue vivo en el proveedor")
        self.assertEqual(self.sql("SELECT COUNT(*) FROM users")[0][0], 1)
        # El estado legítimo no se consume con el intento hostil: el navegador
        # que inició el flujo aún puede completarlo.
        headers, location = self.callback(query, binding=binding)
        self.assertEqual(location, "/?google=signed")
        self.assertEqual(len(self.provider.seen), 1)

    def test_a_wrong_binding_cookie_is_rejected_before_the_provider(self):
        authorize_url, _ = self.start_flow("signup")
        query = self.authorize(authorize_url)
        headers, location = self.callback(query, binding="biblio_oidc=" + "A" * 43)
        self.assertEqual(location, "/?google=error")
        self.assert_no_session(headers)
        self.assertEqual(self.provider.seen, [])
        self.assertTrue(self.provider.codes)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM identities")[0][0], 0)

    def test_a_flow_transferred_to_another_browser_is_rejected(self):
        # Atacante: inicia y autoriza en su navegador y obtiene `code`+`state`.
        attacker_url, attacker_binding = self.start_flow("signup")
        query = self.authorize(attacker_url)
        # Víctima: tiene su propio flujo pendiente, con otra cookie de enlace.
        _, victim_binding = self.start_flow("login")
        self.assertNotEqual(attacker_binding, victim_binding)
        headers, location = self.callback(query, binding=victim_binding)
        self.assertEqual(location, "/?google=error")
        self.assert_no_session(headers)
        self.assertEqual(self.provider.seen, [])
        # El navegador del atacante termina el suyo: la víctima no queda con
        # sesión ni cuenta de esa transferencia.
        headers, location = self.callback(query, binding=attacker_binding)
        self.assertEqual(location, "/?google=signed")
        self.assertEqual(len(self.provider.seen), 1)

    def test_a_replayed_callback_is_rejected(self):
        authorize_url, binding = self.start_flow("signup")
        query = self.authorize(authorize_url)
        headers, location = self.callback(query, binding=binding)
        self.assertEqual(location, "/?google=signed")
        headers, location = self.callback(query, binding=binding)
        self.assertEqual(location, "/?google=error")
        self.assert_no_session(headers)
        self.assertEqual(len(self.provider.seen), 1)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM users")[0][0], 2)

    def test_an_expired_flow_clears_the_cookie_and_is_rejected(self):
        authorize_url, binding = self.start_flow("signup")
        query = self.authorize(authorize_url)
        self.sql_exec("UPDATE auth_challenges SET expires_at=1")
        headers, location = self.callback(query, binding=binding)
        self.assertEqual(location, "/?google=error")
        self.assert_no_session(headers)
        self.assertEqual(self.provider.seen, [])
        # El estado caducado no puede usarse ni siquiera consumiéndolo a mano.
        state = query["state"][0]
        self.assertIsNone(self.store.peek_challenge("oidc", state))
        self.assertIsNone(self.store.take_challenge("oidc", state))

    def test_the_binding_value_never_leaks_outside_the_set_cookie(self):
        authorize_url, binding = self.start_flow("signup")
        value = binding.split("=", 1)[1]
        query = self.authorize(authorize_url)
        details = b"".join(row[0] for row in self.sql("SELECT detail FROM auth_challenges"))
        self.assertNotIn(value.encode(), details)
        to_provider = "&".join(f"{key}={item[0]}" for key, item in query.items())
        self.assertNotIn(value, to_provider)
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            headers, location = self.callback(query, binding=binding)
        written = output.getvalue() + location + "&".join(
            f"{key}={item}" for key, item in headers.items())
        self.assertNotIn(value, written)
        self.assertNotIn(query["state"][0], written)
        self.assertNotIn(value, str(self.provider.seen))

    def test_logout_while_the_link_is_pending_blocks_the_link(self):
        self.verify_email()
        self.reauth()
        authorize_url, binding = self.start_flow("link")
        query = self.authorize(authorize_url)
        self.data("/api/logout", {})
        headers, location = self.callback(query, binding=binding)
        self.assertEqual(location, "/?google=error")
        self.assert_no_session(headers)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM identities")[0][0], 0)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM users")[0][0], 1)

    def test_the_link_requires_the_initiating_session_to_still_be_live(self):
        # Cerrar sesión y abrir otra (token nuevo) no completa el vínculo viejo.
        self.verify_email()
        self.reauth()
        authorize_url, binding = self.start_flow("link")
        query = self.authorize(authorize_url)
        self.data("/api/logout", {})
        self.register("otra")
        headers, location = self.callback(query, binding=binding)
        self.assertEqual(location, "/?google=error")
        self.assertEqual(self.sql("SELECT COUNT(*) FROM identities")[0][0], 0)

    def test_the_final_link_gate_is_indivisible_with_respect_to_logout(self):
        # Ventana comprobación→escritura del gate final (revisión independiente).
        # Antes de la corrección, `link_session_live()` y `store.link_identity()`
        # eran dos pasos sin lock compartido: un logout que entraba en esa
        # ventana retiraba la sesión y el INSERT se escribía igual. Ahí el gate
        # retiene `server.lock` —el mismo que usa el logout— entre la
        # comprobación y la escritura, así que el logout **no puede** intercalarse.
        # Se fuerza de forma determinista lanzando el logout desde la propia
        # comprobación final y midiendo, desde ese hilo, si el lock del servidor
        # estaba libre: con el gate atómico está contendido (se ordena detrás);
        # sin él estaba libre (el logout se colaba).
        self.verify_email()
        self.reauth()
        token_before = self.cookie.split("=", 1)[1]
        authorize_url, binding = self.start_flow("link")
        query = self.authorize(authorize_url)
        real = Handler.link_session_live
        calls = {"n": 0}
        probe = {}

        def logout_contending_with_the_gate(handler, user_id, proof):
            outcome = real(handler, user_id, proof)
            calls["n"] += 1
            # 1 = comprobación previa al canje (fuera de lock).
            # 2 = entrada al gate atómico, ya bajo server.lock: aquí se lanza
            #     el logout contendiente. Cualquier llamada posterior ocurre
            #     dentro del gate y no debe re-lanzarlo.
            if calls["n"] != 2:
                return outcome

            def run():
                # El gate aún no ha soltado el lock: aquí debe estar contendido.
                probe["lock_free_during_gate"] = handler.server.lock.acquire(blocking=False)
                if probe["lock_free_during_gate"]:
                    handler.server.lock.release()
                try:
                    probe["logout"] = self.data("/api/logout", {})
                except Exception as error:  # se reporta abajo, no dentro del hilo
                    probe["error"] = error

            probe["thread"] = threading.Thread(target=run, daemon=True)
            probe["thread"].start()
            return outcome

        with unittest.mock.patch.object(Handler, "link_session_live",
                                        logout_contending_with_the_gate):
            # `headers` se ignora: el hilo del logout comparte el jar de cookies
            # de la prueba y su `Set-Cookie` de sesión sobrescribiría el del
            # callback, así que aquí no se comprueban cookies de esa respuesta.
            _, location = self.callback(query, binding=binding)
        probe["thread"].join(timeout=10)
        self.assertEqual(calls["n"], 2, "no se llegó al gate final")
        self.assertIsNone(probe.get("error"), probe.get("error"))
        # El discriminante: durante el gate el lock estaba contendido. Sin la
        # corrección este acquire habría tenido éxito y el logout se habría
        # colado entre la comprobación y el INSERT.
        self.assertFalse(probe["lock_free_during_gate"],
                         "el logout pudo obtener server.lock dentro del gate")
        # El gate decidió con la sesión viva: el vínculo se escribió; el logout,
        # ordenado detrás, solo cerró la sesión (no desvincula). No se usa
        # `assert_no_session`: el hilo del logout comparte el jar de cookies de
        # la prueba y su `Set-Cookie` de sesión sobrescribiría el del callback.
        self.assertEqual(location, "/?google=linked")
        self.assertEqual(self.sql("SELECT COUNT(*) FROM identities")[0][0], 1)
        self.assertEqual(probe["logout"], {"ok": True})
        self.assertNotIn(token_before, self.server.sessions,
                         "el logout debió retirar la sesión tras el gate")
        self.assertEqual(self.sql("SELECT COUNT(*) FROM auth_challenges")[0][0], 0)

    def test_link_identity_revalidates_the_holder_at_the_write_gate(self):
        # El gate atómico del store: con `require_verified=True` la existencia
        # y la verificación del email se comprueban dentro de la transacción
        # que escribe, así que un titular desaparecido o desverificado no deja
        # fila alguna (el logout, que no borra usuarios, ya no puede tornar el
        # resultado del gate).
        owner = self.data("/api/settings")["user"]
        with self.assertRaises(AppError) as caught:
            self.store.link_identity(owner["id"], "google", "issuer-x", "sub-x",
                                     require_verified=True)
        self.assertEqual(caught.exception.status, 401)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM identities")[0][0], 0)
        self.verify_email()
        self.store.link_identity(owner["id"], "google", "issuer-x", "sub-x",
                                 require_verified=True)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM identities")[0][0], 1)
        # Un usuario inexistente recibe el mismo rechazo, sin escribir nada.
        with self.assertRaises(AppError) as caught:
            self.store.link_identity("usuario-inexistente", "google", "otro", "sub-y",
                                     require_verified=True)
        self.assertEqual(caught.exception.status, 401)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM identities")[0][0], 1)

    def test_the_link_requires_the_email_to_still_be_verified(self):
        self.verify_email()
        self.reauth()
        authorize_url, binding = self.start_flow("link")
        query = self.authorize(authorize_url)
        self.sql_exec("UPDATE users SET email_verified_at=NULL")
        headers, location = self.callback(query, binding=binding)
        self.assertEqual(location, "/?google=error")
        self.assertEqual(self.sql("SELECT COUNT(*) FROM identities")[0][0], 0)

    def test_linking_still_works_from_the_initiating_browser(self):
        # Control positivo del vínculo: misma sesión, mismo navegador.
        self.verify_email()
        self.reauth()
        headers, location = self.complete("link")
        self.assertEqual(location, "/?google=linked")
        self.assertEqual([item["provider"] for item in self.data("/api/settings")["identities"]],
                         ["google"])


class GoogleTokenVerificationTests(OidcTestCase):
    """Verificación del token ID: firma, issuer, audiencia, expiración y nonce."""

    def verify(self, token, nonce="nonce-ficticio"):
        """Verificación real contra el proveedor falso (descubrimiento + JWKS)."""
        return GoogleProvider(self.server.google.config).verify_id_token(token, nonce)

    def test_a_well_formed_token_verifies(self):
        claims = self.verify(self.provider.mint())
        self.assertEqual(claims["sub"], "sub-ficticio-1")

    def test_signature_from_another_key_is_rejected(self):
        self.provider.scenario["wrong_key"] = True
        with self.assertRaises(AppError) as caught:
            self.verify(self.provider.mint())
        self.assertEqual(caught.exception.status, 401)

    def test_wrong_issuer_audience_and_nonce_are_rejected(self):
        cases = [{"iss": "https://otro.test"}, {"aud": "otro-cliente"},
                 {"nonce": "nonce-ajeno"}]
        for override in cases:
            with self.assertRaises(AppError) as caught:
                self.verify(self.provider.mint(**override))
            self.assertEqual(caught.exception.status, 401, override)

    def test_expired_token_is_rejected(self):
        import time
        with self.assertRaises(AppError) as caught:
            self.verify(self.provider.mint(exp=int(time.time()) - 3600))
        self.assertEqual(caught.exception.status, 401)

    def test_malformed_token_is_rejected(self):
        with self.assertRaises(AppError) as caught:
            self.verify("no-es-un-jwt")
        self.assertEqual(caught.exception.status, 401)

    def test_wrong_signature_also_closes_the_callback(self):
        self.provider.scenario["wrong_key"] = True
        headers, location = self.complete("signup")
        self.assertEqual(location, "/?google=error")
        self.assert_no_session(headers)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM auth_challenges")[0][0], 0)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM users")[0][0], 1)


class GoogleTrustedOriginTests(unittest.TestCase):
    """Callback OIDC desde un origen de confianza, nunca de un Host hostil (TODO-SEC-003)."""

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

    def start_server(self, secure=False, trusted=(), redirect_uri=None):
        provider = FakeOidcProvider()
        self.addCleanup(provider.stop)
        path = Path(self.temp.name) / f"biblio-{len(self.servers)}.sqlite3"
        store = Store(path, key=Fernet.generate_key())
        config = GoogleConfig(client_id=CLIENT_ID, client_secret=CLIENT_SECRET,
                              issuer=provider.base_url, redirect_uri=redirect_uri)
        server = AppServer(("127.0.0.1", 0), lambda card, password: FakeClient(card, password),
                           store=store, google=config, secure=secure, trusted_origins=trusted)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.servers.append((server, thread, store))
        return server

    def start(self, server, host):
        """POST /api/auth/google/start con Host arbitrario; devuelve (status, payload)."""
        connection = http.client.HTTPConnection(*server.server_address, timeout=10)
        connection.request("POST", "/api/auth/google/start", json.dumps({"mode": "login"}),
                           {"Content-Type": "application/json", "Host": host})
        response = connection.getresponse()
        payload = response.read()
        result = response.status, json.loads(payload) if payload else {}
        connection.close()
        return result

    def redirect_of(self, payload):
        return parse_qs(urlsplit(payload["authorize_url"]).query)["redirect_uri"][0]

    def test_a_hostile_host_cannot_select_the_redirect_uri(self):
        # Antes de la corrección el callback se derivaba del Host crudo.
        for secure, host in [(False, "evil.example"), (False, "192.0.2.10:8000"),
                             (True, "evil.example"), (True, "192.0.2.10:8000")]:
            server = self.start_server(secure=secure)
            code, payload = self.start(server, host)
            self.assertEqual(code, 403, f"secure={secure} host={host}: {payload}")

    def test_local_origins_derive_the_callback(self):
        server = self.start_server()
        host = f"127.0.0.1:{server.server_port}"
        code, payload = self.start(server, host)
        self.assertEqual(code, 200, payload)
        self.assertEqual(self.redirect_of(payload),
                         f"http://{host}/api/auth/google/callback")
        code, payload = self.start(server, f"localhost:{server.server_port}")
        self.assertEqual(code, 200, payload)
        self.assertEqual(self.redirect_of(payload),
                         f"http://localhost:{server.server_port}/api/auth/google/callback")

    def test_configured_https_callback_is_used_only_on_listed_origins(self):
        server = self.start_server(secure=True, trusted=["https://biblio.example.org"],
                                   redirect_uri="https://biblio.example.org/api/auth/google/callback")
        code, payload = self.start(server, "biblio.example.org")
        self.assertEqual(code, 200, payload)
        self.assertEqual(self.redirect_of(payload),
                         "https://biblio.example.org/api/auth/google/callback")
        code, payload = self.start(server, "evil.example")
        self.assertEqual(code, 403, payload)

    def test_a_configured_local_https_callback_needs_no_extra_list(self):
        # Escenario mkcert: https local con el callback fijo en la configuración.
        server = self.start_server(secure=True,
                                   redirect_uri="https://localhost:8443/api/auth/google/callback")
        for host in ["localhost:8443", f"127.0.0.1:{server.server_port}"]:
            code, payload = self.start(server, host)
            self.assertEqual(code, 200, f"{host}: {payload}")
            self.assertEqual(self.redirect_of(payload),
                             "https://localhost:8443/api/auth/google/callback")

    def test_invalid_configured_callbacks_answer_503(self):
        invalid = ["https://evil.example/api/auth/google/callback",
                   "http://192.0.2.10/api/auth/google/callback",
                   "https://biblio.example.org/otro",
                   "https://biblio.example.org/api/auth/google/callback?x=1",
                   "https://user@biblio.example.org/api/auth/google/callback",
                   "https://biblio.example.org:abc/api/auth/google/callback"]
        for redirect in invalid:
            server = self.start_server(secure=True, trusted=["https://biblio.example.org"],
                                       redirect_uri=redirect)
            code, payload = self.start(server, "biblio.example.org")
            self.assertEqual(code, 503, f"{redirect}: {payload}")

    def test_the_binding_cookie_is_secure_over_https(self):
        server = self.start_server(secure=True)
        connection = http.client.HTTPConnection(*server.server_address, timeout=10)
        connection.request("POST", "/api/auth/google/start", json.dumps({"mode": "login"}),
                           {"Content-Type": "application/json",
                            "Host": f"localhost:{server.server_port}"})
        response = connection.getresponse()
        status, payload = response.status, response.read()
        pairs = response.getheaders()
        connection.close()
        self.assertEqual(status, 200, payload)
        cookies = [value for key, value in pairs if key.lower() == "set-cookie"]
        binding = [value for value in cookies if value.startswith("biblio_oidc=")]
        self.assertEqual(len(binding), 1, cookies)
        attributes = binding[0].split(";", 1)[1]
        self.assertIn("Secure", attributes)
        self.assertIn("SameSite=Lax", attributes)
        self.assertIn("HttpOnly", attributes)


if __name__ == "__main__":
    unittest.main()
