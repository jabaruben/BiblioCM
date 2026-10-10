"""Identidad ampliada (TODO-AUTH-002 / TODO-AUTH-001): email verificado,
login por email verificado, cambio y recuperación de contraseña, con un
servidor SMTP falso local. Sin correo real, sin portal ni credenciales reales.

Los tokens se construyen por concatenación donde hace falta un valor sintético;
el correo falso solo vive en estas pruebas y escucha en 127.0.0.1 con puerto
efímero, sin instalar confianza ni abrir puertos externos.
"""
import http.client
import json
import re
import secrets
import socketserver
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

from cryptography.fernet import Fernet

from biblio.client import AuthError, OperationRefused, RenewResult
from biblio.models import Library, Reader, MarcRecord, Copy, Loan, Reservation, RenewalState
from biblio.store import AppError, SCHEMA_VERSION, Store
from biblio import mailer as mailer_module
from biblio.web import AppServer
from tests.test_web import FakeClient, APP_PASSWORD, PORTAL_PASSWORD

TOKEN_RE = re.compile(r"Código: ([A-Za-z0-9_\-]{20,})")


class _SmtpHandler(socketserver.StreamRequestHandler):
    """Diálogo SMTP mínimo: captura el DATA en `server.messages`.

    No anuncia AUTH ni STARTTLS, de modo que `smtplib` entrega en claro dentro
    del localhost; `server.blocked` cierra la conexión al conectar para
    reproducir un proveedor que no responde.
    """
    def handle(self):
        if getattr(self.server, "blocked", False):
            return
        self.wfile.write(b"220 fake ESMTP ready\r\n")
        while True:
            line = self.rfile.readline()
            if not line:
                return
            command = line.strip().upper()
            if command.startswith(b"EHLO"):
                self.wfile.write(b"250-fake\r\n250 SIZE 10240000\r\n")
            elif command.startswith(b"HELO"):
                self.wfile.write(b"250 fake\r\n")
            elif command.startswith(b"DATA"):
                self.wfile.write(b"354 Termina con un punto solo\r\n")
                body = []
                while True:
                    chunk = self.rfile.readline()
                    if not chunk:
                        return
                    if chunk.rstrip(b"\r\n") == b".":
                        break
                    body.append(chunk)
                self.server.messages.append(b"".join(body).decode("utf-8", "replace"))
                self.wfile.write(b"250 OK en cola\r\n")
            elif command.startswith(b"QUIT"):
                self.wfile.write(b"221 adios\r\n")
                return
            else:
                # MAIL FROM / RCPT TO / RSET y cualquier comando no anunciado.
                self.wfile.write(b"250 OK\r\n")


class FakeSmtpServer(socketserver.ThreadingTCPServer):
    """Servidor SMTP falso solo en pruebas: 127.0.0.1 y puerto efímero."""
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self):
        self.messages = []
        self.blocked = False
        super().__init__(("127.0.0.1", 0), _SmtpHandler)

    @property
    def port(self):
        return self.server_address[1]

    def last_token(self):
        matches = TOKEN_RE.findall(self.messages[-1])
        assert matches, f"sin código en el correo: {self.messages[-1]!r}"
        return matches[0]


def start_smtp():
    server = FakeSmtpServer()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def smtp_config(port):
    return mailer_module.MailConfig(host="127.0.0.1", port=port, starttls=False,
                                    from_addr="BiblioCM <no-responder@fake.test>")


V0_SCHEMA = """
    CREATE TABLE users (
        id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL, salt BLOB NOT NULL, password_hash BLOB NOT NULL
    );
    CREATE TABLE accounts (
        id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id),
        label TEXT NOT NULL, card_digest TEXT NOT NULL UNIQUE,
        credentials BLOB NOT NULL
    );
    CREATE TABLE links (
        id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id),
        requester_id TEXT NOT NULL REFERENCES users(id),
        permission TEXT NOT NULL CHECK(permission IN ('read','manage')),
        status TEXT NOT NULL CHECK(status IN ('pending','approved','rejected','revoked')),
        UNIQUE(owner_id, requester_id), CHECK(owner_id != requester_id)
    );
"""


def make_v0_database(path, key):
    """Base en el esquema anterior (sin email ni tokens) con datos reales."""
    db = sqlite3.connect(path)
    db.executescript(V0_SCHEMA)
    fernet = Fernet(key)
    salt = b"\x01" * 16
    from biblio.store import password_hash
    db.execute("INSERT INTO users VALUES (?,?,?,?,?)",
               ("u1", "legacy", "Legacy", salt, password_hash(APP_PASSWORD, salt)))
    db.execute("INSERT INTO users VALUES (?,?,?,?,?)",
               ("u2", "otra", "Otra", salt, password_hash(APP_PASSWORD, salt)))
    encrypted = fernet.encrypt(json.dumps({"card": "111", "password": PORTAL_PASSWORD}).encode())
    db.execute("INSERT INTO accounts VALUES (?,?,?,?,?)",
               ("a1", "u1", "Vieja", "digest-111", encrypted))
    db.execute("INSERT INTO links VALUES (?,?,?,?,?)", ("l1", "u1", "u2", "manage", "approved"))
    db.commit()
    db.close()


class IdentityTestCase(unittest.TestCase):
    """Base: servidor con OPAC falso y SMTP falso configurable por prueba."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".biblio-test-", dir=Path(__file__).parents[1])
        self.path = Path(self.temp.name) / "biblio.sqlite3"
        self.key = Fernet.generate_key()
        self.store = Store(self.path, key=self.key)
        self.smtp, self.smtp_thread = start_smtp()
        self.clients = []
        self.portal_state = {}

        def factory(card, password):
            client = FakeClient(card, password, state=self.portal_state)
            self.clients.append(client)
            return client

        self.server = AppServer(("127.0.0.1", 0), factory, store=self.store,
                                mailer=mailer_module.Mailer(smtp_config(self.smtp.port)))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.cookie = ""
        self.csrf = ""

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.smtp.shutdown()
        self.smtp.server_close()
        self.smtp_thread.join()
        self.store.close()
        self.temp.cleanup()

    def break_smtp(self):
        """El proveedor de correo deja de aceptar conexiones (fallo simulado)."""
        self.smtp.blocked = True

    def request(self, path, body=None, extra=None):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        headers = {"Cookie": self.cookie}
        if body is not None:
            headers.update({"Content-Type": "application/json", "X-CSRF-Token": self.csrf})
        headers.update(extra or {})
        connection.request("POST" if body is not None else "GET",
                           path, json.dumps(body) if body is not None else None, headers)
        response = connection.getresponse()
        data = response.read()
        result = response.status, dict(response.getheaders()), data
        connection.close()
        return result

    def data(self, path, body=None, status=200):
        code, _, raw = self.request(path, body)
        self.assertEqual(code, status, raw.decode())
        return json.loads(raw)

    def sql(self, statement, params=()):
        """Consulta directa a la BD temporal; cierra la conexión (Windows)."""
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

    def login(self, username, password=APP_PASSWORD):
        code, headers, raw = self.request("/api/login", {"username": username, "password": password})
        self.assertEqual(code, 200, raw)
        self.cookie = headers["Set-Cookie"].split(";")[0]
        self.csrf = json.loads(raw)["csrf"]
        return json.loads(raw)["user"]

    def verify_email(self, email="lector@ejemplo.test"):
        """Solicita y consume el código: devuelve el email verificado."""
        self.data("/api/auth/email/request", {"email": email})
        self.data("/api/auth/email/verify", {"token": self.smtp.last_token()})
        return email


class EmailVerificationTests(IdentityTestCase):
    """FR-AUTH-002: email verificado con username como alias."""

    def test_request_sends_code_and_verification_enables_email_login(self):
        self.register("owner")
        self.data("/api/auth/email/request", {"email": "Lector@Ejemplo.test"})
        self.assertEqual(len(self.smtp.messages), 1)
        self.assertIn("lector@ejemplo.test", self.smtp.messages[0].lower())
        token = self.smtp.last_token()
        # Solo el hash vive en la base de datos, nunca el código en claro.
        rows = self.sql("SELECT token_hash FROM identity_tokens")
        self.assertEqual(len(rows), 1)
        self.assertNotIn(token, rows[0][0])
        self.data("/api/auth/email/verify", {"token": token})
        user = self.login("lector@ejemplo.test")
        self.assertEqual(user["username"], "owner")
        self.assertTrue(user["email_verified"])
        # El alias de usuario sigue funcionando igual que antes.
        self.login("owner")

    def test_code_is_single_use(self):
        self.register("owner")
        self.data("/api/auth/email/request", {"email": "lector@ejemplo.test"})
        token = self.smtp.last_token()
        self.data("/api/auth/email/verify", {"token": token})
        self.data("/api/auth/email/verify", {"token": token}, status=400)

    def test_expired_code_is_rejected(self):
        self.register("owner")
        self.data("/api/auth/email/request", {"email": "lector@ejemplo.test"})
        token = self.smtp.last_token()
        self.sql_exec("UPDATE identity_tokens SET expires_at=1")
        self.data("/api/auth/email/verify", {"token": token}, status=400)
        self.data("/api/login", {"username": "lector@ejemplo.test", "password": APP_PASSWORD}, 401)

    def test_unknown_code_answer_is_generic(self):
        self.register("owner")
        first = self.request("/api/auth/email/verify", {"token": "no-existe-este-codigo-ficticio-000"})
        self.request("/api/auth/email/verify", {"token": "tambien-inexistente-ficticio-111"})
        self.assertEqual(first[0], 400)
        self.assertEqual(first[2], self.request(
            "/api/auth/email/verify", {"token": "otro-token-ficticio-largo-222"})[2],
            "la respuesta no distingue un código malo de uno desconocido")

    def test_login_with_unverified_email_is_rejected(self):
        self.register("owner")
        self.data("/api/auth/email/request", {"email": "lector@ejemplo.test"})
        self.data("/api/login", {"username": "lector@ejemplo.test", "password": APP_PASSWORD}, 401)
        # La base existe pero sin verificar: el username legado sigue abriendo sesión.
        self.login("owner")

    def test_email_already_used_by_another_user_is_silent(self):
        self.register("owner")
        self.verify_email("ocupado@ejemplo.test")
        self.register("otra")
        before = len(self.smtp.messages)
        answer = self.data("/api/auth/email/request", {"email": "ocupado@ejemplo.test"})
        self.assertTrue(answer["ok"])
        self.assertEqual(len(self.smtp.messages), before, "se envió un correo ajeno")
        count = self.sql("SELECT COUNT(*) FROM identity_tokens WHERE purpose='email_verify'")[0][0]
        self.assertEqual(count, 0, "quedó un token utilizable de otro usuario")

    def test_invalid_email_is_rejected(self):
        self.register("owner")
        for bad in ["sin-arroba", "a@b", "con espacios@ejemplo.test", "@" * 10 + "x.es", None, 42]:
            self.data("/api/auth/email/request", {"email": bad}, status=400)

    def test_request_requires_session_and_csrf(self):
        self.cookie, self.csrf = "", ""
        self.data("/api/auth/email/request", {"email": "lector@ejemplo.test"}, status=401)
        self.register("owner")
        code, _, _ = self.request("/api/auth/email/request", {"email": "lector@ejemplo.test"},
                                  {"X-CSRF-Token": "incorrecto"})
        self.assertEqual(code, 403)

    def test_new_code_replaces_the_previous_one(self):
        self.register("owner")
        self.data("/api/auth/email/request", {"email": "lector@ejemplo.test"})
        first = self.smtp.last_token()
        self.data("/api/auth/email/request", {"email": "lector@ejemplo.test"})
        second = self.smtp.last_token()
        self.data("/api/auth/email/verify", {"token": first}, status=400)
        self.data("/api/auth/email/verify", {"token": second})

    def test_smtp_failure_leaves_no_usable_code(self):
        self.register("owner")
        self.smtp.shutdown()
        self.smtp.server_close()
        self.smtp_thread.join()
        # Tras la revisión independiente el fallo de envío responde el mismo
        # 200 genérico que un envío satisfactorio (sin oráculo); lo sustantivo
        # es que no queda ningún código utilizable.
        self.data("/api/auth/email/request", {"email": "lector@ejemplo.test"})
        count = self.sql("SELECT COUNT(*) FROM identity_tokens")[0][0]
        self.assertEqual(count, 0, "un fallo de envío dejó un token vivo")

    def test_delivery_failure_is_not_an_oracle_for_email_request(self):
        # Revisión independiente: si el fallo de correo respondiera distinto
        # según el email exista, la incidencia del proveedor sería un oráculo
        # de enumeración. Con el SMTP caído, «email libre» y «email ajeno»
        # deben responder exactamente lo mismo.
        self.register("owner")
        self.verify_email("ocupado@ejemplo.test")
        self.register("otra")
        self.break_smtp()
        taken = self.request("/api/auth/email/request", {"email": "ocupado@ejemplo.test"})
        free = self.request("/api/auth/email/request", {"email": "libre@ejemplo.test"})
        self.assertEqual(taken[0], free[0], f"estatus distintos: {taken[0]} vs {free[0]}")
        self.assertEqual(taken[2], free[2], "el cuerpo distingue un email ocupado de uno libre")
        count = self.sql("SELECT COUNT(*) FROM identity_tokens")[0][0]
        self.assertEqual(count, 0, "quedó un token cuyo correo no pudo entregarse")

    def test_rate_limit_per_route(self):
        self.register("owner")
        for index in range(20):
            self.data("/api/auth/email/request", {"email": f"r{index}@ejemplo.test"}, status=200)
        self.data("/api/auth/email/request", {"email": "otro@ejemplo.test"}, status=429)


class PasswordChangeTests(IdentityTestCase):
    """FR-AUTH-003: cambio de contraseña desde sesión autenticada."""

    def test_change_rotates_password_and_closes_other_sessions(self):
        self.register("owner")
        first_cookie = self.cookie
        # Un segundo acceso sin arrastrar la cookie anterior: el login rota la
        # sesión de quien lo pide, pero la primera sigue viva por su cookie.
        self.cookie = ""
        self.login("owner")
        current_cookie, current_csrf = self.cookie, self.csrf
        self.cookie = first_cookie
        self.data("/api/settings", status=200)
        self.cookie, self.csrf = current_cookie, current_csrf
        self.data("/api/auth/password/change",
                  {"current_password": APP_PASSWORD, "password": "nueva-clave-segura-9"})
        # La sesión que cambia la contraseña continúa viva.
        self.data("/api/settings", status=200)
        self.cookie = first_cookie
        self.data("/api/settings", status=401)
        self.login("owner", "nueva-clave-segura-9")
        self.data("/api/login", {"username": "owner", "password": APP_PASSWORD}, 401)

    def test_change_requires_current_password_and_a_different_one(self):
        self.register("owner")
        self.data("/api/auth/password/change",
                  {"current_password": "incorrecta-valor-1", "password": "otra-clave-larga-1"}, status=401)
        self.data("/api/auth/password/change",
                  {"current_password": APP_PASSWORD, "password": APP_PASSWORD}, status=400)
        self.data("/api/auth/password/change",
                  {"current_password": APP_PASSWORD, "password": "corta"}, status=400)
        self.login("owner")

    def test_change_preserves_fernet_credentials_and_links(self):
        self.register("owner")
        account = self.data("/api/accounts/add", {"card": "111", "label": "Mía",
                                                  "password": PORTAL_PASSWORD})["account"]
        self.register("requester")
        self.data("/api/links/request", {"username": "owner", "permission": "read"})
        self.login("owner")
        self.data("/api/auth/password/change",
                  {"current_password": APP_PASSWORD, "password": "nueva-clave-segura-9"})
        second = Store(self.path, key=self.key)
        try:
            user = second.login("owner", "nueva-clave-segura-9")
            self.assertEqual(second.credentials(account)["password"], PORTAL_PASSWORD)
            self.assertEqual(second.access(user["id"], account)["label"], "Mía")
            settings = second.settings(user["id"])
            self.assertEqual(settings["incoming"][0]["status"], "pending")
        finally:
            second.close()


class RecoveryTests(IdentityTestCase):
    """FR-AUTH-003: recuperación por email verificado."""

    def test_recovery_flow_sets_password_and_closes_every_session(self):
        self.register("owner")
        first_cookie = self.cookie
        self.verify_email("lector@ejemplo.test")
        self.login("owner")
        self.data("/api/settings", status=200)
        before = len(self.smtp.messages)
        self.data("/api/auth/password/recovery/request", {"email": "lector@ejemplo.test"})
        self.assertEqual(len(self.smtp.messages), before + 1)
        token = self.smtp.last_token()
        self.data("/api/auth/password/recovery/reset",
                  {"token": token, "password": "clave-recuperada-7"})
        self.login("owner", "clave-recuperada-7")
        self.cookie = first_cookie
        self.data("/api/settings", status=401)
        self.data("/api/login", {"username": "owner", "password": APP_PASSWORD}, 401)

    def test_recovery_answer_does_not_enumerate(self):
        self.register("owner")
        self.verify_email("lector@ejemplo.test")
        unknown = self.request("/api/auth/password/recovery/request",
                               {"email": "nadie@ejemplo.test"})
        known = self.request("/api/auth/password/recovery/request",
                             {"email": "lector@ejemplo.test"})
        self.assertEqual(unknown[0], 200)
        self.assertEqual(unknown[2], known[2], "la respuesta distingue email existente")
        self.data("/api/auth/password/recovery/request", {"email": "sin-verificar@ejemplo.test"})
        self.assertEqual(len(self.smtp.messages), 2,
                         "se envió correo sin verificar o a una cuenta inexistente")

    def test_reset_token_is_single_use_and_expires(self):
        self.register("owner")
        self.verify_email("lector@ejemplo.test")
        self.data("/api/auth/password/recovery/request", {"email": "lector@ejemplo.test"})
        token = self.smtp.last_token()
        self.data("/api/auth/password/recovery/reset", {"token": token, "password": "clave-recuperada-7"})
        self.data("/api/auth/password/recovery/reset", {"token": token, "password": "otra-clave-mas-8"}, status=400)
        self.data("/api/auth/password/recovery/request", {"email": "lector@ejemplo.test"})
        token = self.smtp.last_token()
        self.sql_exec("UPDATE identity_tokens SET expires_at=1")
        self.data("/api/auth/password/recovery/reset", {"token": token, "password": "clave-recuperada-7"}, status=400)
        self.login("owner", "clave-recuperada-7")

    def test_recovery_requires_verified_email(self):
        self.register("owner")
        self.data("/api/auth/email/request", {"email": "lector@ejemplo.test"})
        before = len(self.smtp.messages)
        self.data("/api/auth/password/recovery/request", {"email": "lector@ejemplo.test"})
        self.assertEqual(len(self.smtp.messages), before, "recovery sin verificar envió correo")

    def test_reset_without_mail_configured_is_global_error(self):
        self.register("owner")
        self.verify_email("lector@ejemplo.test")
        self.server.mailer = None
        # El error es global y previo: no depende de si el email existe.
        unknown = self.request("/api/auth/password/recovery/request", {"email": "nadie@ejemplo.test"})
        self.assertEqual(unknown[0], 503)
        known = self.request("/api/auth/password/recovery/request", {"email": "lector@ejemplo.test"})
        self.assertEqual(known[0], 503)
        self.assertEqual(known[2], unknown[2])

    def test_recovery_rate_limit_per_route(self):
        for _ in range(20):
            self.data("/api/auth/password/recovery/request", {"email": "nadie@ejemplo.test"}, status=200)
        self.data("/api/auth/password/recovery/request", {"email": "nadie@ejemplo.test"}, status=429)

    def test_delivery_failure_is_not_an_oracle_for_recovery(self):
        # Revisión independiente: durante una incidencia de correo la respuesta
        # no puede revelar si el email está verificado en BiblioCM.
        self.register("owner")
        self.verify_email("lector@ejemplo.test")
        self.break_smtp()
        known = self.request("/api/auth/password/recovery/request",
                             {"email": "lector@ejemplo.test"})
        unknown = self.request("/api/auth/password/recovery/request",
                               {"email": "nadie@ejemplo.test"})
        self.assertEqual(known[0], 200, known[2].decode())
        self.assertEqual(known[0], unknown[0], "estatus distintos durante el fallo de correo")
        self.assertEqual(known[2], unknown[2], "el cuerpo distingue una cuenta existente")
        count = self.sql("SELECT COUNT(*) FROM identity_tokens")[0][0]
        self.assertEqual(count, 0, "quedó un token de recuperación sin entregar")


class PasswordMutationRaceTests(IdentityTestCase):
    """Revisión independiente: verificar la contraseña vieja y escribir la nueva
    deben ocurrir en la misma sección crítica del store. Si la verificación se
    hace bajo el lock y la escritura después de soltarlo, dos cambios (o un
    cambio y un reset) concurrentes pueden verificar contra la contraseña vieja
    y pisarse: ambos reportan éxito y solo una de las dos funciona."""

    def test_concurrent_changes_cannot_both_verify_the_old_password(self):
        self.register("owner")
        user = self.store.login("owner", APP_PASSWORD)
        barrier = threading.Barrier(2)
        results = []

        def run(index):
            barrier.wait()
            password = f"clave-numero-{index}-segura"
            try:
                self.store.change_password(user["id"], APP_PASSWORD, password)
                results.append(("ok", password))
            except AppError as exc:
                results.append(("err", exc.status))

        threads = [threading.Thread(target=run, args=(index,)) for index in (1, 2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        succeeded = [password for outcome, password in results if outcome == "ok"]
        self.assertEqual(len(succeeded), 1,
                         f"ambos cambios verificaron contra la contraseña vieja: {results}")
        winner = succeeded[0]
        loser = next(password for password in ("clave-numero-1-segura", "clave-numero-2-segura")
                     if password != winner)
        self.login("owner", winner)
        self.data("/api/login", {"username": "owner", "password": loser}, 401)
        self.data("/api/login", {"username": "owner", "password": APP_PASSWORD}, 401)

    def test_concurrent_change_and_reset_leave_one_consistent_password(self):
        self.register("owner")
        user = self.store.login("owner", APP_PASSWORD)
        self.verify_email("lector@ejemplo.test")
        self.data("/api/auth/password/recovery/request", {"email": "lector@ejemplo.test"})
        reset_token = self.smtp.last_token()
        barrier = threading.Barrier(2)

        def run_change():
            barrier.wait()
            try:
                self.store.change_password(user["id"], APP_PASSWORD, "cambio-concurrente-1")
            except AppError:
                pass

        def run_reset():
            barrier.wait()
            try:
                self.store.reset_password(reset_token, "reset-concurrente-2")
            except AppError:
                pass

        threads = [threading.Thread(target=run_change), threading.Thread(target=run_reset)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        # Cualquiera de los dos puede ganar; lo prohibido es un estado a medias
        # o que las dos queden activas a la vez.
        working = [password for password in ("cambio-concurrente-1", "reset-concurrente-2")
                   if self._accepts(user["id"], password)]
        self.assertLessEqual(len(working), 1,
                             f"dos contraseñas distintas quedaron activas: {working}")
        self.assertTrue(working, "ninguna de las dos operaciones dejó contraseña activa")
        self.data("/api/login", {"username": "owner", "password": APP_PASSWORD}, 401)

    def _accepts(self, user_id, password):
        from biblio.store import password_hash
        with self.store.lock:
            row = self.store.db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        return secrets.compare_digest(password_hash(password, row["salt"]), row["password_hash"])


def make_v1_database(path, key):
    """Base en el esquema de identidad (v1) con un email ya verificado."""
    make_v0_database(path, key)
    db = sqlite3.connect(path)
    db.executescript("""
        ALTER TABLE users ADD COLUMN email TEXT;
        ALTER TABLE users ADD COLUMN email_verified_at TEXT;
        CREATE TABLE identity_tokens (
            token_hash TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            purpose TEXT NOT NULL CHECK(purpose IN ('email_verify','password_reset')),
            detail TEXT NOT NULL DEFAULT '',
            expires_at INTEGER NOT NULL,
            created_at INTEGER NOT NULL
        );
        CREATE UNIQUE INDEX users_email_unique ON users(email) WHERE email IS NOT NULL;
        CREATE INDEX identity_tokens_user_purpose ON identity_tokens(user_id, purpose);
        UPDATE users SET email='legacy@ejemplo.test', email_verified_at='2026-10-01T00:00:00'
            WHERE id='u1';
        PRAGMA user_version=1;
    """)
    db.commit()
    db.close()


class SchemaMigrationTests(unittest.TestCase):
    """Migraciones sobre copias temporales: antigua (v0), reciente (v1), fresca y rollback.

    Ninguna prueba toca una base real; TODAS usan fixtures temporales y la
    verificación incluye reapertura (v2 no vuelve a migrar) y que IDs, vínculos,
    carnés y credenciales cifradas siguen intactos.
    """

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".biblio-test-", dir=Path(__file__).parents[1])
        self.path = Path(self.temp.name) / "biblio.sqlite3"
        self.key = Fernet.generate_key()

    def tearDown(self):
        self.temp.cleanup()

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

    def tables(self):
        return {row[0] for row in self.sql("SELECT name FROM sqlite_master WHERE type='table'")}

    def test_migration_preserves_ids_links_cards_and_crypto(self):
        make_v0_database(self.path, self.key)
        store = Store(self.path, key=self.key)
        try:
            version = self.sql("PRAGMA user_version")[0][0]
            columns = {row[1] for row in self.sql("PRAGMA table_info(users)")}
            self.assertEqual(version, SCHEMA_VERSION)
            self.assertIn("email", columns)
            self.assertIn("email_verified_at", columns)
            user = store.login("legacy", APP_PASSWORD)
            self.assertEqual(user["id"], "u1")
            self.assertIsNone(user["email"])
            self.assertFalse(user["email_verified"])
            self.assertEqual(store.credentials("a1")["password"], PORTAL_PASSWORD)
            self.assertEqual(store.access(user["id"], "a1")["label"], "Vieja")
            settings = store.settings(user["id"])
            self.assertEqual(settings["incoming"][0]["id"], "l1")
            self.assertEqual(settings["incoming"][0]["status"], "approved")
            # Las tablas de passkeys/OIDC existen y empiezan vacías.
            self.assertEqual(self.tables() & {"passkeys", "auth_challenges", "identities"},
                             {"passkeys", "auth_challenges", "identities"})
            self.assertEqual(settings["passkeys"], [])
            self.assertEqual(settings["identities"], [])
        finally:
            store.close()

    def test_reopening_a_migrated_database_does_not_migrate_again(self):
        make_v1_database(self.path, self.key)
        first = Store(self.path, key=self.key)
        first.close()
        self.assertEqual(self.sql("PRAGMA user_version")[0][0], SCHEMA_VERSION)
        second = Store(self.path, key=self.key)
        try:
            user = second.login("legacy", APP_PASSWORD)
            self.assertEqual(user["email"], "legacy@ejemplo.test")
            self.assertTrue(user["email_verified"])
            self.assertEqual(self.sql("SELECT COUNT(*) FROM users")[0][0], 2)
            self.assertEqual(self.sql("SELECT COUNT(*) FROM accounts")[0][0], 1)
        finally:
            second.close()

    def test_fresh_database_is_created_at_the_current_version(self):
        store = Store(self.path)
        try:
            self.assertEqual(self.sql("PRAGMA user_version")[0][0], SCHEMA_VERSION)
            self.assertTrue({"users", "accounts", "links", "identity_tokens",
                             "passkeys", "auth_challenges", "identities"} <= self.tables())
            user = store.register("nueva", "Nueva", APP_PASSWORD)
            self.assertEqual(store.passkeys(user["id"]), [])
            self.assertEqual(store.identities(user["id"]), [])
        finally:
            store.close()

    def test_failed_migration_rolls_back_atomically(self):
        make_v0_database(self.path, self.key)
        self.sql_exec("CREATE TABLE identity_tokens (wrong TEXT)")
        with self.assertRaises(Exception):
            Store(self.path, key=self.key)
        self.assertEqual(self.sql("PRAGMA user_version")[0][0], 0,
                         "la migración fallida avanzó la versión")
        columns = {row[1] for row in self.sql("PRAGMA table_info(users)")}
        self.assertNotIn("email", columns, "la migración fallida dejó columnas a medias")
        self.assertEqual(self.sql("SELECT COUNT(*) FROM links")[0][0], 1)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM accounts")[0][0], 1)
        # Arreglar el obstáculo permite migrar sin tocar los datos.
        self.sql_exec("DROP TABLE identity_tokens")
        store = Store(self.path, key=self.key)
        try:
            user = store.login("legacy", APP_PASSWORD)
            self.assertEqual(user["id"], "u1")
            self.assertEqual(store.credentials("a1")["card"], "111")
        finally:
            store.close()

    def test_failed_v1_to_v2_migration_rolls_back_to_version_one(self):
        make_v1_database(self.path, self.key)
        self.sql_exec("CREATE TABLE passkeys (wrong TEXT)")
        with self.assertRaises(Exception):
            Store(self.path, key=self.key)
        self.assertEqual(self.sql("PRAGMA user_version")[0][0], 1,
                         "la migración fallida de v2 no revirtió la versión")
        self.assertNotIn("auth_challenges", self.tables(), "quedó una tabla a medias")
        self.assertEqual(self.sql("SELECT COUNT(*) FROM links")[0][0], 1)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM accounts")[0][0], 1)
        self.assertEqual(self.sql("SELECT email FROM users WHERE id='u1'")[0][0],
                         "legacy@ejemplo.test")
        # Arreglar el obstáculo permite llegar a v2 sin tocar los datos.
        self.sql_exec("DROP TABLE passkeys")
        store = Store(self.path, key=self.key)
        try:
            user = store.login("legacy", APP_PASSWORD)
            self.assertEqual(user["id"], "u1")
            self.assertEqual(user["email"], "legacy@ejemplo.test")
            self.assertEqual(store.credentials("a1")["password"], PORTAL_PASSWORD)
            self.assertEqual(self.sql("PRAGMA user_version")[0][0], SCHEMA_VERSION)
        finally:
            store.close()

    def test_migrated_database_serves_passkeys_and_identities(self):
        """La v1 migrada ya puede registrar retos y passkeys sin tocar lo anterior."""
        make_v1_database(self.path, self.key)
        store = Store(self.path, key=self.key)
        try:
            user = store.login("legacy", APP_PASSWORD)
            store.put_challenge("webauthn_register", user["id"], "reto-ficticio-000", 300)
            self.assertIsNotNone(store.take_challenge("webauthn_register", "reto-ficticio-000"))
            self.assertIsNone(store.take_challenge("webauthn_register", "reto-ficticio-000"),
                              "el reto no era de un solo uso")
            store.add_passkey(user["id"], "cred-ficticia-000", b"\x01\x02", 0, ["internal"], "Llave")
            self.assertEqual(store.passkeys(user["id"])[0]["label"], "Llave")
            store.link_identity(user["id"], "google", "https://ejemplo.test", "sub-1", "legacy@ejemplo.test")
            self.assertEqual(store.identity_user("google", "https://ejemplo.test", "sub-1"), user["id"])
            # La identidad no cambia el login por contraseña ni los carnés.
            store.login("legacy", APP_PASSWORD)
            self.assertEqual(store.credentials("a1")["card"], "111")
        finally:
            store.close()


class MailConfigTests(unittest.TestCase):
    """Configuración SMTP por entorno, sin enviar nada."""

    def test_missing_host_disables_mail(self):
        self.assertIsNone(mailer_module.config_from_env({}))

    def test_env_builds_configuration(self):
        config = mailer_module.config_from_env({
            "BIBLIO_SMTP_HOST": "smtp.ejemplo.test", "BIBLIO_SMTP_PORT": "2525",
            "BIBLIO_SMTP_STARTTLS": "0", "BIBLIO_SMTP_FROM": "BiblioCM <app@ejemplo.test>"})
        self.assertEqual(config.host, "smtp.ejemplo.test")
        self.assertEqual(config.port, 2525)
        self.assertFalse(config.starttls)
        self.assertEqual(config.from_addr, "BiblioCM <app@ejemplo.test>")

    def test_defaults_enable_starttls(self):
        config = mailer_module.config_from_env({"BIBLIO_SMTP_HOST": "smtp.ejemplo.test"})
        self.assertTrue(config.starttls)
        self.assertEqual(config.port, 587)


if __name__ == "__main__":
    unittest.main()
