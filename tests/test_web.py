"""Identidad, panel conjunto y permisos: HTTP real con OPAC simulado."""
import contextlib
import datetime as dt
import http.client
import io
import json
import socket
import struct
import tempfile
import threading
import time
import types
import unittest
import zlib
from pathlib import Path

from biblio.client import AuthError, OperationRefused, RenewResult
from biblio.models import Library, Reader, MarcRecord, Copy, Loan, Reservation, RenewalState
from biblio.store import AppError, Store
from biblio.web import AppServer, Handler

APP_PASSWORD = "app-password-123"
PORTAL_PASSWORD = "portal-only-secret-456"
# URL ficticia con la forma exacta que reparte el OPAC: token en el path.
COVER_URL = "https://gestiona3.madrid.org/biblio_publicas/cgi-bin/abnetopac/THREADTOKEN02?ACC=299&MLKOB=1553619074343"


def png(rgb=(22, 78, 67)):
    """PNG mínimo válido (1x1) para que el navegador acepte la portada falsa."""
    def chunk(tag, payload):
        body = tag + payload
        return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    pixels = b"\x00" + bytes(rgb)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b""))


COVER_PNG = png()


class FakeWrite:
    """`wfile` de handler que registra lo escrito y puede fallar de forma determinista.

    `fail(payload)` decide si esa escritura lanza `BrokenPipeError`: permite
    reproducir un cliente que se desconecta al recibir cabeceras o cuerpo sin
    depender de temporizaciones de red.
    """

    def __init__(self, fail=None):
        self.chunks = []
        self.fail = fail

    def write(self, payload):
        if self.fail and self.fail(payload):
            raise BrokenPipeError(32, "Broken pipe")
        self.chunks.append(payload)
        return len(payload)

    def flush(self):
        pass

    @property
    def body(self):
        return b"".join(self.chunks)


def status_codes(payload):
    """Status HTTP emitidos en un payload de respuesta, en orden."""
    codes = []
    for line in payload.split(b"\r\n"):
        parts = line.split(b" ")
        if line.startswith(b"HTTP/") and len(parts) > 1 and parts[1].isdigit():
            codes.append(int(parts[1]))
    return codes


class FakeClient:
    def __init__(self, card, password, state=None):
        self.card, self.password = card, password
        self.calls = []
        self.state = state if state is not None else {}

    def login(self):
        self.calls.append("login")
        if self.password == "bad":
            raise AuthError("private upstream message")

    def record_cover_url(self, record):
        self.calls.append(("record_cover", record))
        return COVER_URL if record == "123" else ""

    def my_library(self):
        if self.password == "expired":
            raise AuthError("private upstream message")
        renewed = self.state.get(self.card, False)
        due = dt.date(2030, 1, 20) if renewed else dt.date(2030, 1, 5)
        loan = Loan("123", "Libro de " + self.card + " / Autora", "Biblioteca", "Calle", dt.datetime.combine(due, dt.time(23, 59)),
                    due, 15 if renewed else 2, 1 if renewed else 0, 1, 5, 0,
                    RenewalState.LIMIT_REACHED if renewed else RenewalState.RENEWABLE, None,
                    record_id="123")
        reservation = Reservation("456", "Reserva de " + self.card, "123", "Pendiente", None, None, "A", "Sede", "1")
        return Library(Reader(self.card, "Lector " + self.card, False, False, dt.date(2030, 1, 1)), [loan], [reservation])

    def search(self, query, page=1):
        self.calls.append(("search", query, page))
        return 1, [MarcRecord("123", title="Un libro", cover_url=COVER_URL)]

    def cover(self, url):
        self.calls.append(("cover", url))
        return COVER_PNG, "image/png"

    def copies(self, record):
        return [Copy("123", "A", "Biblioteca", "Sede", "Sala", "Libro", "Disponible"),
                Copy("999", "B", "Biblioteca", "Sede reservas", "Sala", "Juegos", "Disponible después de 15/10/2026")]

    def renew(self, barcode):
        self.calls.append(("renew", barcode))
        if barcode == "999":
            raise OperationRefused("Todavía no se puede renovar")
        self.state[self.card] = True
        return RenewResult(True, "Renovado para " + self.card, dt.date(2030, 1, 5), dt.date(2030, 1, 20), 1, 1)

    def reserve(self, record, index, barcode=None):
        self.calls.append(("reserve", record, index, barcode))
        return "Reserva realizada para " + self.card

    def cancel_reservation(self, reservation):
        self.calls.append(("cancel", reservation))
        return "Reserva anulada para " + self.card

    def reservable_copies(self, record):
        return [{"index": 1, "barcode": "999", "row": "Sede reservas", "sequence": "private",
                 "library": "Biblioteca", "branch": "Sede reservas", "location": "Sala", "signature": "JUE SWI ley",
                 "copy_type": "Juegos de consola", "availability": "Disponible después de 15/10/2026"}]


class WebTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".biblio-test-", dir=Path(__file__).parents[1])
        self.path = Path(self.temp.name) / "biblio.sqlite3"
        self.store = Store(self.path)
        self.clients = []
        self.portal_state = {}

        def factory(card, password):
            client = FakeClient(card, password, state=self.portal_state)
            self.clients.append(client)
            return client

        self.server = AppServer(("127.0.0.1", 0), factory, store=self.store)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.cookie = ""
        self.csrf = ""

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.store.close()
        self.temp.cleanup()

    def request(self, path, body=None, extra=None):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        headers = {"Cookie": self.cookie}
        if body is not None:
            headers.update({"Content-Type": "application/json", "X-CSRF-Token": self.csrf})
        headers.update(extra or {})
        connection.request("POST" if body is not None else "GET", path, json.dumps(body) if body is not None else None, headers)
        response = connection.getresponse()
        data = response.read()
        result = response.status, dict(response.getheaders()), data
        connection.close()
        return result

    def data(self, path, body=None, status=200):
        code, _, raw = self.request(path, body)
        self.assertEqual(code, status, raw.decode())
        return json.loads(raw)

    def register(self, username="owner"):
        code, headers, raw = self.request("/api/register", {"username": username, "name": username.title(), "password": APP_PASSWORD})
        self.assertEqual(code, 200, raw)
        self.cookie = headers["Set-Cookie"].split(";")[0]
        self.csrf = json.loads(raw)["csrf"]
        return json.loads(raw)["user"]

    def login(self, username):
        code, headers, raw = self.request("/api/login", {"username": username, "password": APP_PASSWORD})
        self.assertEqual(code, 200, raw)
        self.cookie = headers["Set-Cookie"].split(";")[0]
        self.csrf = json.loads(raw)["csrf"]
        return headers

    def add(self, card="111", label="Mi biblioteca", password=PORTAL_PASSWORD):
        return self.data("/api/accounts/add", {"card": card, "label": label, "password": password})["account"]

    def share(self, requested="read", granted="read"):
        self.register("owner")
        account = self.add()
        self.register("requester")
        link = self.data("/api/links/request", {"username": "owner", "permission": requested})["id"]
        self.login("owner")
        self.data("/api/links/decide", {"id": link, "action": "approve", "permission": granted})
        self.login("requester")
        return account, link

    def hold_factory(self, method, started, release, timeout=10):
        """Fábrica de clientes cuya operación `method` se retiene en `release`.

        El hilo que atiende la petición espera en un Event, no en un sleep: la
        prueba controla exactamente cuándo continúa la operación.
        """
        original = getattr(FakeClient, method)

        def blocked(client, *args, **kwargs):
            started.set()
            if not release.wait(timeout):
                raise AssertionError(f"la operación {method} retenida no se soltó")
            return original(client, *args, **kwargs)

        def factory(card, password):
            client = FakeClient(card, password, state=self.portal_state)
            setattr(client, method, types.MethodType(blocked, client))
            self.clients.append(client)
            return client

        return factory

    @staticmethod
    def handler(wfile):
        """Handler sin socket real: solo escribe en el `wfile` de prueba."""
        instance = Handler.__new__(Handler)
        instance.wfile = wfile
        instance.requestline = "GET /api/test HTTP/1.1"
        instance.request_version = "HTTP/1.1"
        instance.close_connection = False
        return instance

    def test_private_access_requires_session(self):
        self.data("/api/library", status=401)
        self.data("/api/settings", status=401)
        self.assertFalse(self.data("/api/session")["authenticated"])

    def test_api_version_is_available_before_login_and_on_errors(self):
        status, headers, raw = self.request("/api/version")
        self.assertEqual(status, 200)
        self.assertEqual(headers["X-Biblio-API-Version"], "6")

        self.assertEqual(json.loads(raw)["api_version"], "6")
        self.assertEqual(self.data("/api/session")["api_version"], "6")
        status, headers, _ = self.request("/api/library")
        self.assertEqual(status, 401)
        self.assertEqual(headers["X-Biblio-API-Version"], "6")

    def test_second_server_cannot_share_the_same_listening_address(self):
        with self.assertRaises(OSError):
            AppServer(self.server.server_address, FakeClient, store=self.store)
        # A failed duplicate bind must leave the first server and its store usable.
        self.assertEqual(self.data("/api/version")["api_version"], "6")

    def test_old_unstructured_reservable_response_is_rejected_without_leaking_html(self):
        class LegacyClient(FakeClient):
            def reservable_copies(inner_self, record):
                return [{"index": 1, "barcode": "999", "row": 'copiasRes_locCont"> < a href="/abnetopac/PRIVATE_TOKEN'}]

        self.server.client_factory = LegacyClient
        self.register()
        account = self.add()
        status, _, raw = self.request(f"/api/reservable?account={account}&record=123")
        self.assertEqual(status, 502)
        self.assertNotIn(b"copiasRes", raw)
        self.assertNotIn(b"PRIVATE_TOKEN", raw)

    def test_reservable_api_never_exposes_the_legacy_row_field(self):
        class Client(FakeClient):
            def reservable_copies(inner_self, record):
                copies = super().reservable_copies(record)
                copies[0]["row"] = 'copiasRes_locCont"> < a href="/abnetopac/PRIVATE_TOKEN'
                return copies

        self.server.client_factory = Client
        self.register()
        account = self.add()
        status, headers, raw = self.request(f"/api/reservable?account={account}&record=123")
        self.assertEqual(status, 200)
        self.assertEqual(headers["X-Biblio-API-Version"], "6")
        copy = json.loads(raw)["copies"][0]
        self.assertEqual(copy["branch"], "Sede reservas")
        self.assertNotIn("row", copy)
        self.assertNotIn(b"copiasRes", raw)
        self.assertNotIn(b"PRIVATE_TOKEN", raw)

    def test_identity_is_separate_and_registration_validation(self):
        self.data("/api/register", {"username": "bad user", "name": "Nombre", "password": APP_PASSWORD}, 400)
        self.data("/api/register", {"username": "user", "name": "Nombre", "password": "short"}, 400)
        user = self.register("Reader")
        self.assertEqual(user["username"], "reader")
        self.assertFalse(self.clients)
        self.assertEqual(self.data("/api/library")["accounts"], [])
        self.data("/api/register", {"username": "READER", "name": "Nombre", "password": APP_PASSWORD}, 409)

    def test_login_cookie_and_sanitized_auth_failure(self):
        self.register()
        self.data("/api/logout", {})
        self.data("/api/login", {"username": "owner", "password": "bad"}, 401)
        self.data("/api/login", {"username": "unknown", "password": "bad"}, 401)
        headers = self.login("OWNER")
        self.assertIn("HttpOnly", headers["Set-Cookie"])
        self.assertIn("SameSite=Strict", headers["Set-Cookie"])
        self.assertEqual(self.data("/api/session")["user"]["username"], "owner")

    def test_link_verifies_credentials_before_persisting(self):
        self.register()
        raw = self.request("/api/accounts/add", {"card": "111", "label": "Cuenta", "password": "bad"})
        self.assertEqual(raw[0], 422)
        self.assertNotIn(b"private upstream", raw[2])
        self.assertEqual(self.data("/api/settings")["accounts"], [])
        account = self.add()
        self.assertEqual(self.clients[-1].calls, ["login"])
        self.assertEqual(self.data("/api/settings")["accounts"][0]["id"], account)

    def test_credentials_are_encrypted_and_not_returned(self):
        user = self.register()
        account = self.add()
        stored = self.store.db.execute("SELECT credentials FROM accounts").fetchone()[0]
        self.assertNotIn(PORTAL_PASSWORD.encode(), stored)
        self.assertNotIn(b'"card"', stored)
        self.assertEqual(self.store.credentials(account)["password"], PORTAL_PASSWORD)
        self.assertNotIn(PORTAL_PASSWORD.encode(), self.path.read_bytes())
        self.assertNotIn(APP_PASSWORD.encode(), self.path.read_bytes())
        for route in ("/api/session", "/api/settings", "/api/library"):
            self.assertNotIn(PORTAL_PASSWORD.encode(), self.request(route)[2])
        self.assertEqual(self.store.user(user["id"])["username"], "owner")

    def test_csrf_and_origin_protect_settings_and_mutations(self):
        self.register()
        body = {"card": "111", "label": "Cuenta", "password": PORTAL_PASSWORD}
        self.assertEqual(self.request("/api/accounts/add", body, {"X-CSRF-Token": "wrong"})[0], 403)
        self.assertEqual(self.request("/api/accounts/add", body, {"Origin": "https://evil.example"})[0], 403)
        self.assertEqual(self.request("/api/accounts/add", body, {"Content-Type": "text/plain"})[0], 415)
        self.assertFalse(self.clients)

    def test_pending_request_does_not_grant_access_and_cannot_self_approve(self):
        self.register("owner")
        account = self.add()
        self.register("requester")
        link = self.data("/api/links/request", {"username": "owner", "permission": "manage"})["id"]
        self.assertEqual(self.data("/api/library")["accounts"], [])
        self.data(f"/api/copies?account={account}&record=123", status=403)
        self.data("/api/links/decide", {"id": link, "action": "approve", "permission": "manage"}, 403)
        self.data("/api/links/decide", {"id": link, "action": "reject"}, 403)
        self.login("owner")
        incoming = self.data("/api/settings")["incoming"]
        self.assertEqual(incoming[0]["requester_username"], "requester")
        self.assertEqual(incoming[0]["status"], "pending")

    def test_read_permission_allows_queries_and_blocks_all_mutations(self):
        account, _ = self.share("manage", "read")
        self.assertEqual(self.data("/api/library")["accounts"][0]["permission"], "read")
        self.data(f"/api/search?account={account}&q=libro&page=2")
        self.data(f"/api/copies?account={account}&record=123")
        self.data(f"/api/reservable?account={account}&record=123")
        count = len(self.clients)
        for route, body in [("renew", {"barcode": "123"}), ("reserve", {"record": "123", "index": 1}), ("cancel", {"reservation": "456"})]:
            self.data("/api/" + route, dict(body, account=account), 403)
        self.assertEqual(len(self.clients), count, "Denied operations must not create an OPAC client")

    def test_manage_permission_targets_the_correct_account(self):
        account, _ = self.share("manage", "manage")
        own = self.add("222", "Otra biblioteca")
        for target, expected_card in ((account, "111"), (own, "222")):
            renewed = self.data("/api/renew", {"account": target, "barcode": "123"})
            self.assertEqual(renewed["message"], "Renovado para " + expected_card)
            reserved = self.data("/api/reserve", {"account": target, "record": "123", "index": 1})
            self.assertEqual(reserved["message"], "Reserva realizada para " + expected_card)
            self.data("/api/reserve", {"account": target, "record": "123", "index": 1, "barcode": "999"})
            self.assertEqual(self.clients[-1].calls[-1], ("reserve", "123", 1, "999"))
            self.data("/api/cancel", {"account": target, "reservation": "456"})
            self.assertEqual(self.clients[-1].card, expected_card)

    def test_aggregate_attributes_identical_barcodes_to_each_account(self):
        account, _ = self.share()
        own = self.add("222", "Mi segunda cuenta")
        code, headers, raw = self.request("/api/library")
        self.assertEqual(code, 200)
        self.assertEqual(headers["Cache-Control"], "no-store")
        result = json.loads(raw)
        self.assertEqual({l["account"]["id"] for l in result["loans"]}, {account, own})
        self.assertEqual({r["account"]["id"] for r in result["reservations"]}, {account, own})
        self.assertEqual(result["loans"][0]["clean_title"], "Libro de 222")
        self.assertEqual(len(result["loans"]), 2)

    def test_renewal_confirmation_matches_the_panel_from_a_new_client(self):
        self.register()
        account = self.add()
        result = self.data("/api/renew", {"account": account, "barcode": "123"})
        for _ in range(2):
            library = self.data("/api/library")
            loan = next(item for item in library["loans"] if item["account"]["id"] == account)
            self.assertEqual(loan["due_date"], result["new_due"])
            self.assertEqual(loan["due_date"], "2030-01-20")
            self.assertEqual(loan["days_left"], 15)
            self.assertEqual(loan["renewals_used"], result["renewals_used"])
            self.assertEqual(loan["renewal_state"], "limite_alcanzado")

    def test_revocation_takes_effect_in_existing_session(self):
        account, link = self.share("manage", "manage")
        requester_cookie, requester_csrf = self.cookie, self.csrf
        # A second browser must not rotate the requester's active session.
        self.cookie, self.csrf = "", ""
        self.login("owner")
        self.data("/api/links/decide", {"id": link, "action": "revoke"})
        self.cookie, self.csrf = requester_cookie, requester_csrf
        self.assertEqual(self.data("/api/library")["accounts"], [])
        self.data(f"/api/search?account={account}&q=libro", status=403)
        self.data("/api/renew", {"account": account, "barcode": "123"}, 403)

    def test_permission_downgrade_is_checked_again_on_every_request(self):
        account, link = self.share("manage", "manage")
        requester_cookie, requester_csrf = self.cookie, self.csrf
        self.cookie, self.csrf = "", ""
        self.login("owner")
        self.data("/api/links/decide", {"id": link, "action": "permission", "permission": "read"})
        self.cookie, self.csrf = requester_cookie, requester_csrf
        self.data("/api/reserve", {"account": account, "record": "123", "index": 1}, 403)
        self.data(f"/api/copies?account={account}&record=123")
        self.data("/api/links/decide", {"id": link, "action": "permission", "permission": "manage"}, 403)

    def test_grants_do_not_delegate_third_party_accounts(self):
        original, _ = self.share()
        requester_own = self.add("222")
        self.register("third")
        link = self.data("/api/links/request", {"username": "requester", "permission": "manage"})["id"]
        self.login("requester")
        self.data("/api/links/decide", {"id": link, "action": "approve", "permission": "manage"})
        self.login("third")
        self.assertEqual([a["id"] for a in self.data("/api/library")["accounts"]], [requester_own])
        self.data(f"/api/copies?account={original}&record=123", status=403)

    def test_unrelated_user_cannot_access_or_decide_other_peoples_requests(self):
        account, link = self.share()
        self.register("stranger")
        self.data(f"/api/copies?account={account}&record=123", status=403)
        for action in ("approve", "reject", "revoke", "permission"):
            self.data("/api/links/decide", {"id": link, "action": action, "permission": "manage"}, 403)

    def test_delegate_cannot_change_credentials_or_delete_account(self):
        account, _ = self.share("manage", "manage")
        count = len(self.clients)
        self.data("/api/accounts/update", {"account": account, "label": "Hijack", "password": "new"}, 403)
        self.data("/api/accounts/delete", {"account": account}, 403)
        self.assertEqual(len(self.clients), count)

    def test_owner_can_update_credentials_and_delete_account(self):
        self.register()
        account = self.add()
        self.data("/api/accounts/update", {"account": account, "label": "Nuevo nombre", "password": "new-secret"})
        self.assertEqual(self.store.credentials(account)["password"], "new-secret")
        self.assertEqual(self.data("/api/settings")["accounts"][0]["label"], "Nuevo nombre")
        self.data("/api/accounts/delete", {"account": account})
        self.assertEqual(self.data("/api/library")["accounts"], [])
        self.assertIsNone(self.store.db.execute("SELECT id FROM accounts WHERE id=?", (account,)).fetchone())

    def test_requests_duplicate_self_reject_and_resubmit(self):
        self.register("owner")
        self.register("requester")
        self.data("/api/links/request", {"username": "requester", "permission": "read"}, 400)
        self.data("/api/links/request", {"username": "missing", "permission": "read"}, 404)
        link = self.data("/api/links/request", {"username": "owner", "permission": "read"})["id"]
        self.data("/api/links/request", {"username": "owner", "permission": "manage"}, 409)
        self.login("owner")
        self.data("/api/links/decide", {"id": link, "action": "reject"})
        self.data("/api/links/decide", {"id": link, "action": "approve", "permission": "manage"}, 409)
        self.login("requester")
        self.assertEqual(self.data("/api/settings")["outgoing"][0]["status"], "rejected")
        self.assertEqual(self.data("/api/links/request", {"username": "owner", "permission": "read"})["id"], link)
        self.data("/api/links/decide", {"id": link, "action": "revoke"})
        self.assertEqual(self.data("/api/settings")["outgoing"][0]["status"], "revoked")

    def test_requester_can_leave_an_approved_share(self):
        account, link = self.share()
        self.data("/api/links/decide", {"id": link, "action": "revoke"})
        self.assertEqual(self.data("/api/library")["accounts"], [])
        self.data(f"/api/copies?account={account}&record=123", status=403)

    def test_duplicate_carnet_cannot_be_claimed_by_another_user(self):
        self.register("owner")
        self.add()
        self.register("requester")
        self.data("/api/accounts/add", {"card": "111", "label": "Cuenta", "password": PORTAL_PASSWORD}, 409)

    def test_failed_library_does_not_hide_other_accounts_or_logout(self):
        self.register()
        failed = self.add("111", password="expired")
        good = self.add("222")
        result = self.data("/api/library")
        self.assertEqual([l["account"]["id"] for l in result["loans"]], [good])
        self.assertIn("error", next(a for a in result["accounts"] if a["id"] == failed))
        self.assertTrue(self.data("/api/session")["authenticated"])

    def test_catalog_and_mutation_validation(self):
        self.register()
        account = self.add()
        self.assertEqual(self.data(f"/api/search?account={account}&q=libro&page=2")["records"][0]["record_id"], "123")
        self.assertTrue(self.data(f"/api/copies?account={account}&record=123")["copies"][0]["available_now"])
        self.assertNotIn(b"private", self.request(f"/api/reservable?account={account}&record=123")[2])
        reservable = self.data(f"/api/reservable?account={account}&record=123")["copies"]
        self.assertEqual(reservable[0]["branch"], "Sede reservas")
        self.assertEqual(reservable[0]["signature"], "JUE SWI ley")
        self.assertEqual(len(reservable), 1)
        self.assertEqual(len(self.data(f"/api/copies?account={account}&record=123")["copies"]), 2)
        self.data(f"/api/search?account={account}&q=libro&page=0", status=400)
        self.data(f"/api/copies?account={account}&record=../", status=400)
        self.data("/api/renew", {"account": account, "barcode": "999"}, 409)
        self.data("/api/reserve", {"account": account, "record": "123", "index": True}, 400)
        self.data("/api/renew", {"barcode": "123"}, 400)

    def test_search_cover_is_served_by_the_app_without_opac_tokens(self):
        self.register()
        account = self.add()
        status, _, raw = self.request(f"/api/search?account={account}&q=libro")
        self.assertEqual(status, 200)
        record = json.loads(raw)["records"][0]
        self.assertEqual(record["cover_url"], f"/api/cover?account={account}&record=123")
        self.assertNotIn(b"THREADTOKEN", raw)
        self.assertNotIn(b"abnetopac/", raw)
        self.assertNotIn(b"ACC=299", raw)

    def test_provider_urls_in_openurl_and_marc_are_dropped(self):
        class Client(FakeClient):
            def search(inner_self, query, page=1):
                record = MarcRecord(
                    "123",
                    title="Un libro",
                    cover_url=COVER_URL,
                    openurl={"rft.btitle": "Un libro",
                             "url_ver": "/biblio_publicas/cgi-bin/abnetopac/THREADTOKEN02?ACC=101"},
                    raw_marc={"TITN": ["123"],
                              "T856u": [COVER_URL + "&NT=9"]},
                )
                return 1, [record]

        self.server.client_factory = Client
        self.register()
        account = self.add()
        raw = self.request(f"/api/search?account={account}&q=libro")[2]
        record = json.loads(raw)["records"][0]
        self.assertEqual(record["openurl"]["rft.btitle"], "Un libro")
        self.assertEqual(record["openurl"]["url_ver"], "")
        self.assertEqual(record["raw_marc"]["TITN"], ["123"])
        self.assertEqual(record["raw_marc"]["T856u"], [])
        self.assertNotIn(b"THREADTOKEN", raw)

    def test_foreign_cover_urls_are_never_published(self):
        self.register()
        account = self.add()
        for bad in ("javascript:alert(1)", "https://evil.example/portada.png", "/otra/ruta.png"):
            with self.subTest(cover=bad):
                self.server.client_factory = type("Foreign", (FakeClient,), {
                    "search": lambda self, query, page=1, value=bad:
                        (1, [MarcRecord("123", title="Un libro", cover_url=value)])
                })
                raw = self.request(f"/api/search?account={account}&q=libro")[2]
                record = json.loads(raw)["records"][0]
                self.assertEqual(record["cover_url"], "")
                self.assertNotIn(bad.encode(), raw)

    def test_cover_endpoint_serves_the_registered_image(self):
        self.register()
        account = self.add()
        self.data(f"/api/search?account={account}&q=libro")
        status, headers, raw = self.request(f"/api/cover?account={account}&record=123")
        self.assertEqual(status, 200, raw)
        self.assertEqual(raw, COVER_PNG)
        self.assertEqual(headers["Content-Type"], "image/png")
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(headers["Referrer-Policy"], "no-referrer")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("sandbox", headers["Content-Security-Policy"])
        blob = raw + " ".join(f"{key}: {value}" for key, value in headers.items()).encode()
        self.assertNotIn(b"THREADTOKEN", blob)
        self.assertNotIn(b"abnetopac", blob)
        # El motor sí recibe la URL del proveedor; el navegador no.
        self.assertEqual(self.clients[-1].calls[-1], ("cover", COVER_URL))

    def test_cover_requires_a_session_and_access_to_the_account(self):
        self.register()
        account = self.add()
        self.data(f"/api/search?account={account}&q=libro")
        count = len(self.clients)
        self.cookie = ""
        self.data(f"/api/cover?account={account}&record=123", status=401)
        self.register("stranger")
        self.data(f"/api/cover?account={account}&record=123", status=403)
        self.assertEqual(len(self.clients), count, "una petición denegada no construye un cliente")
        fetched = [call for client in self.clients for call in client.calls
                   if isinstance(call, tuple) and call[0] == "cover"]
        self.assertEqual(fetched, [])

    def test_cover_rejects_unknown_records_and_invalid_ids(self):
        self.register()
        account = self.add()
        self.data(f"/api/search?account={account}&q=libro")
        self.data(f"/api/cover?account={account}&record=999", status=404)
        self.data(f"/api/cover?account={account}&record=abc", status=400)
        self.data(f"/api/cover?record=123", status=400)

    def test_cover_rejects_non_image_content_types(self):
        class Client(FakeClient):
            def cover(inner_self, url):
                return b"<svg onload=alert(1)>", "image/svg+xml"

            def record_cover_url(inner_self, record):
                inner_self.calls.append(("record_cover", record))
                return COVER_URL

        self.register()
        account = self.add()
        self.data(f"/api/search?account={account}&q=libro")
        # Una portada correcta se sirve y queda memorizada en memoria.
        self.assertEqual(self.request(f"/api/cover?account={account}&record=123")[0], 200)
        self.server.client_factory = Client
        # El portal devuelve un tipo prohibido para una ficha sin memoria: 502,
        # y esos bytes nunca se guardan, así que la petición siguiente vuelve a
        # comprobarlo en el portal. `record=123` no sirve aquí porque sus bytes
        # ya están memorizados por el caso anterior.
        status, _, raw = self.request(f"/api/cover?account={account}&record=777")
        self.assertEqual(status, 502)
        self.assertNotIn(b"svg", raw)
        self.assertNotIn(b"alert", raw)
        self.assertEqual(self.request(f"/api/cover?account={account}&record=777")[0], 502)

    def test_library_dto_attributes_covers_by_account_and_record(self):
        self.register()
        account = self.add()
        status, _, raw = self.request("/api/library")
        self.assertEqual(status, 200)
        payload = json.loads(raw)
        loan = payload["loans"][0]
        self.assertEqual(loan["record_id"], "123")
        self.assertEqual(loan["cover_url"], f"/api/cover?account={account}&record=123")
        reservation = payload["reservations"][0]
        self.assertEqual(reservation["record_id"], "123")
        self.assertEqual(reservation["cover_url"], f"/api/cover?account={account}&record=123")
        self.assertNotIn(b"THREADTOKEN", raw)
        self.assertNotIn(b"abnetopac", raw)
        self.assertNotIn(b"ACC=299", raw)

    def test_cover_is_discovered_from_the_record_page_when_it_is_not_registered(self):
        self.register()
        account = self.add()
        status, headers, raw = self.request(f"/api/cover?account={account}&record=123")
        self.assertEqual(status, 200, raw)
        self.assertEqual(raw, COVER_PNG)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(headers["Referrer-Policy"], "no-referrer")
        # Memoria: la segunda petición no vuelve a abrir la ficha.
        self.assertEqual(self.request(f"/api/cover?account={account}&record=123")[0], 200)
        discovered = [call for client in self.clients for call in client.calls
                      if isinstance(call, tuple) and call[0] == "record_cover"]
        self.assertEqual(discovered, [("record_cover", "123")])
        blob = raw + " ".join(f"{key}: {value}" for key, value in headers.items()).encode()
        self.assertNotIn(b"THREADTOKEN", blob)
        self.assertNotIn(b"abnetopac", blob)

    def test_a_record_without_cover_is_remembered_instead_of_refetched(self):
        class Client(FakeClient):
            def record_cover_url(inner_self, record):
                inner_self.calls.append(("record_cover", record))
                return ""

        def factory(card, password):
            client = Client(card, password, state=self.portal_state)
            self.clients.append(client)
            return client

        self.server.client_factory = factory
        self.register()
        account = self.add()
        self.assertEqual(self.request(f"/api/cover?account={account}&record=123")[0], 404)
        self.assertEqual(self.request(f"/api/cover?account={account}&record=123")[0], 404)
        discovered = [call for client in self.clients for call in client.calls
                      if isinstance(call, tuple) and call[0] == "record_cover"]
        self.assertEqual(len(discovered), 1, "la ausencia también se memoriza")

    def test_cover_discovery_never_runs_without_authorization(self):
        self.register()
        account = self.add()
        count = len(self.clients)
        self.cookie = ""
        self.assertEqual(self.request(f"/api/cover?account={account}&record=123")[0], 401)
        self.register("stranger")
        self.assertEqual(self.request(f"/api/cover?account={account}&record=123")[0], 403)
        self.assertEqual(len(self.clients), count, "una petición denegada no construye un cliente")
        discovered = [call for client in self.clients for call in client.calls
                      if isinstance(call, tuple) and call[0] == "record_cover"]
        self.assertEqual(discovered, [], "la autorización va antes de abrir la ficha")

    def test_repeated_cover_requests_hit_the_portal_only_once(self):
        """Los bytes válidos se memorizan: cada render no vuelve a descargarlos."""
        self.register()
        account = self.add()
        self.data(f"/api/search?account={account}&q=libro")
        created = len(self.clients)
        for _ in range(3):
            self.assertEqual(self.request(f"/api/cover?account={account}&record=123")[0], 200)
        fetched = [call for client in self.clients for call in client.calls
                   if isinstance(call, tuple) and call[0] == "cover"]
        self.assertEqual(fetched, [("cover", COVER_URL)],
                         f"descargas redundantes al portal: {len(fetched)}")
        self.assertEqual(len(self.clients) - created, 1,
                         "los aciertos de caché no deben construir cliente ni descifrar credenciales")

        # Contador de serialización: se mide el payload real de /api/library
        # para poder afirmar si la serialización es o no el cuello de botella.
        library = json.dumps(self.data("/api/library")).encode()
        start = time.perf_counter()
        for _ in range(10):
            json.dumps(json.loads(library))
        per_call = (time.perf_counter() - start) / 10
        self.assertLess(per_call, 0.05,
                        f"serialización de {len(library)} bytes: {per_call:.6f}s")

    def test_slow_cover_download_does_not_block_unrelated_requests(self):
        """NFR-SVC-002: una descarga de portada no ocupa la sesión ni el store."""
        self.register()
        account = self.add()
        self.data(f"/api/search?account={account}&q=libro")
        started, release = threading.Event(), threading.Event()
        self.server.client_factory = self.hold_factory("cover", started, release)
        fetched_status = {}
        holder = threading.Thread(
            target=lambda: fetched_status.update(
                status=self.request(f"/api/cover?account={account}&record=123")[0]))
        holder.start()
        try:
            self.assertTrue(started.wait(5), "la descarga no llegó al portal")
            probe_status = {}
            probe = threading.Thread(
                target=lambda: probe_status.update(status=self.request("/api/settings")[0]))
            probe.start()
            probe.join(3)
            self.assertFalse(probe.is_alive(),
                             "/api/settings esperó a la descarga de otra ruta")
            self.assertEqual(probe_status.get("status"), 200)
        finally:
            release.set()
            holder.join(5)
        self.assertFalse(holder.is_alive())
        self.assertEqual(fetched_status.get("status"), 200)
        # La portada sigue memorizándose: la repetición no vuelve al portal.
        self.assertEqual(self.request(f"/api/cover?account={account}&record=123")[0], 200)
        fetched = [call for client in self.clients for call in client.calls
                   if isinstance(call, tuple) and call[0] == "cover"]
        self.assertEqual(fetched, [("cover", COVER_URL)],
                         f"descargas redundantes al portal: {len(fetched)}")

    def test_slow_renew_does_not_block_unrelated_requests(self):
        """NFR-SVC-002: una renovación lenta no bloquea otra ruta de la misma sesión."""
        self.register()
        account = self.add()
        started, release = threading.Event(), threading.Event()
        self.server.client_factory = self.hold_factory("renew", started, release)
        renewed = {}
        holder = threading.Thread(
            target=lambda: renewed.update(
                status=self.request("/api/renew", {"account": account, "barcode": "123"})[0]))
        holder.start()
        try:
            self.assertTrue(started.wait(5), "la renovación no llegó al portal")
            probe_status = {}
            probe = threading.Thread(
                target=lambda: probe_status.update(status=self.request("/api/settings")[0]))
            probe.start()
            probe.join(3)
            self.assertFalse(probe.is_alive(),
                             "/api/settings esperó a la renovación en curso")
            self.assertEqual(probe_status.get("status"), 200)
        finally:
            release.set()
            holder.join(5)
        self.assertFalse(holder.is_alive())
        self.assertEqual(renewed.get("status"), 200)

    def test_slow_operation_of_one_user_does_not_block_another_user(self):
        """NFR-SVC-002: el lock global del store ya no serializa a todos los usuarios."""
        self.register()
        account = self.add()
        self.data(f"/api/search?account={account}&q=libro")
        owner_cookie = self.cookie
        # Un registro nuevo rota la sesión: la del titular queda en owner_cookie.
        self.cookie, self.csrf = "", ""
        self.register("other")
        started, release = threading.Event(), threading.Event()
        self.server.client_factory = self.hold_factory("cover", started, release)
        holder = threading.Thread(
            target=lambda: self.request(f"/api/cover?account={account}&record=123",
                                        extra={"Cookie": owner_cookie}))
        holder.start()
        try:
            self.assertTrue(started.wait(5), "la descarga no llegó al portal")
            probe_status = {}
            probe = threading.Thread(
                target=lambda: probe_status.update(status=self.request("/api/settings")[0]))
            probe.start()
            probe.join(3)
            self.assertFalse(probe.is_alive(),
                             "/api/settings de otro usuario esperó la operación de otro")
            self.assertEqual(probe_status.get("status"), 200)
        finally:
            release.set()
            holder.join(5)
        self.assertFalse(holder.is_alive())

    def _assert_permission_change_waits_for_the_operation_in_course(self, action, extra=None):
        """FR-LINK-002: el cambio de permiso espera a la operación en curso."""
        account, link = self.share("manage", "manage")
        requester_cookie, requester_csrf = self.cookie, self.csrf
        self.cookie, self.csrf = "", ""
        self.login("owner")
        owner_cookie, owner_csrf = self.cookie, self.csrf
        started, release = threading.Event(), threading.Event()
        self.server.client_factory = self.hold_factory("cover", started, release)
        order, changed = [], threading.Event()

        def operation():
            status, _, _ = self.request(f"/api/cover?account={account}&record=123",
                                        extra={"Cookie": requester_cookie})
            order.append(("operacion", status))

        def change():
            body = {"id": link, "action": action}
            body.update(extra or {})
            status, _, _ = self.request("/api/links/decide", body,
                                        extra={"Cookie": owner_cookie,
                                               "X-CSRF-Token": owner_csrf})
            order.append((action, status))
            changed.set()

        op_thread = threading.Thread(target=operation)
        change_thread = threading.Thread(target=change)
        settled = False
        op_thread.start()
        try:
            self.assertTrue(started.wait(5), "la operación no llegó al portal")
            change_thread.start()
            # Si el cambio no espera, termina mientras la operación sigue retenida.
            settled = changed.wait(0.3)
        finally:
            release.set()
            op_thread.join(5)
            change_thread.join(5)
        self.assertFalse(op_thread.is_alive())
        self.assertFalse(change_thread.is_alive())
        self.assertFalse(settled, f"la acción «{action}» no esperó a la operación en curso")
        self.assertEqual(order, [("operacion", 200), (action, 200)], order)

        # Las peticiones posteriores ya no tienen ese permiso, y la denegación
        # no construye un cliente del portal.
        self.cookie, self.csrf = requester_cookie, requester_csrf
        clients = len(self.clients)
        if action == "revoke":
            self.assertEqual(self.data("/api/library")["accounts"], [])
            self.assertEqual(self.request(f"/api/cover?account={account}&record=123")[0], 403)
        self.assertEqual(self.request("/api/renew", {"account": account, "barcode": "123"})[0], 403)
        self.assertEqual(len(self.clients), clients,
                         "las peticiones denegadas no deben crear un cliente")
        if action != "revoke":
            self.assertEqual(self.request(f"/api/copies?account={account}&record=123")[0], 200)

    def test_revocation_waits_until_the_operation_in_course_finishes(self):
        self._assert_permission_change_waits_for_the_operation_in_course("revoke")

    def test_permission_downgrade_waits_until_the_operation_in_course_finishes(self):
        self._assert_permission_change_waits_for_the_operation_in_course(
            "permission", extra={"permission": "read"})

    def test_account_delete_waits_for_the_operation_in_course(self):
        """NFR-SVC-002: desvincular cuenta espera a sus operaciones en curso."""
        self.register()
        account = self.add()
        started, release = threading.Event(), threading.Event()
        self.server.client_factory = self.hold_factory("renew", started, release)
        order, deleted = [], threading.Event()

        def operation():
            status, _, _ = self.request("/api/renew", {"account": account, "barcode": "123"})
            order.append(("operacion", status))

        def remove():
            status, _, _ = self.request("/api/accounts/delete", {"account": account})
            order.append(("delete", status))
            deleted.set()

        op_thread = threading.Thread(target=operation)
        delete_thread = threading.Thread(target=remove)
        settled = False
        op_thread.start()
        try:
            self.assertTrue(started.wait(5), "la renovación no llegó al portal")
            delete_thread.start()
            # Si borrar no espera, termina mientras la renovación sigue retenida.
            settled = deleted.wait(0.3)
        finally:
            release.set()
            op_thread.join(5)
            delete_thread.join(5)
        self.assertFalse(op_thread.is_alive())
        self.assertFalse(delete_thread.is_alive())
        self.assertFalse(settled, "accounts/delete no esperó a la operación en curso de esa cuenta")
        self.assertEqual(order, [("operacion", 200), ("delete", 200)], order)
        # Después de desvincilar, esa cuenta ya no llega al portal.
        clients = len(self.clients)
        self.assertEqual(self.request("/api/renew", {"account": account, "barcode": "123"})[0], 403)
        self.assertEqual(len(self.clients), clients,
                         "la cuenta desvinculada no debe construir un cliente")

    def test_account_update_waits_and_later_operations_use_the_new_credentials(self):
        """NFR-SVC-002: rotar credenciales espera y las siguientes descifran la nueva."""
        self.register()
        account = self.add()
        started, release = threading.Event(), threading.Event()
        self.server.client_factory = self.hold_factory("renew", started, release)
        order, updated = [], threading.Event()
        new_password = "rotated-secret-789"

        def operation():
            status, _, _ = self.request("/api/renew", {"account": account, "barcode": "123"})
            order.append(("operacion", status))

        def rotate():
            status, _, _ = self.request("/api/accounts/update",
                                        {"account": account, "label": "Rotada",
                                         "password": new_password})
            order.append(("update", status))
            updated.set()

        op_thread = threading.Thread(target=operation)
        update_thread = threading.Thread(target=rotate)
        settled = False
        op_thread.start()
        try:
            self.assertTrue(started.wait(5), "la renovación no llegó al portal")
            update_thread.start()
            settled = updated.wait(0.3)
        finally:
            release.set()
            op_thread.join(5)
            update_thread.join(5)
        self.assertFalse(op_thread.is_alive())
        self.assertFalse(update_thread.is_alive())
        self.assertFalse(settled, "accounts/update no esperó a la operación en curso de esa cuenta")
        self.assertEqual(order, [("operacion", 200), ("update", 200)], order)
        self.assertEqual(self.store.credentials(account)["password"], new_password)
        # El cliente que verificó la rotación y cualquier operación posterior
        # descifran la credencial vigente: nadie actúa con la foto anterior.
        self.assertEqual(self.clients[-1].password, new_password)
        self.assertEqual(self.request("/api/renew", {"account": account, "barcode": "123"})[0], 200)
        self.assertEqual(self.clients[-1].password, new_password,
                         "una operación posterior debe descifrar la credencial vigente")

    def test_delete_waits_for_an_operation_started_with_a_padded_account_id(self):
        """NFR-SVC-002: la puerta usa el id de cuenta normalizado como `store`."""
        self.register()
        account = self.add()
        started, release = threading.Event(), threading.Event()
        self.server.client_factory = self.hold_factory("renew", started, release)
        order, deleted = [], threading.Event()

        def operation():
            # `store.text` recorta el id: "  <id>  " y "<id>" son la misma cuenta.
            status, _, _ = self.request("/api/renew",
                                        {"account": f"  {account}  ", "barcode": "123"})
            order.append(("operacion", status))

        def remove():
            status, _, _ = self.request("/api/accounts/delete", {"account": account})
            order.append(("delete", status))
            deleted.set()

        op_thread = threading.Thread(target=operation)
        delete_thread = threading.Thread(target=remove)
        settled = False
        op_thread.start()
        try:
            self.assertTrue(started.wait(5), "la renovación no llegó al portal")
            delete_thread.start()
            settled = deleted.wait(0.3)
        finally:
            release.set()
            op_thread.join(5)
            delete_thread.join(5)
        self.assertFalse(settled,
                         "delete con id limpio no esperó a la operación con id con espacios")
        self.assertEqual(order, [("operacion", 200), ("delete", 200)], order)

    def test_slow_operation_on_one_account_does_not_block_another_account(self):
        """NFR-SVC-002: la puerta de cuenta es por cuenta, no global."""
        self.register()
        blocked_account = self.add("111", "Primera biblioteca")
        free_account = self.add("222", "Segunda biblioteca")
        started, release = threading.Event(), threading.Event()
        self.server.client_factory = self.hold_factory("renew", started, release)
        holder = threading.Thread(
            target=lambda: self.request("/api/renew", {"account": blocked_account, "barcode": "123"}))
        holder.start()
        try:
            self.assertTrue(started.wait(5), "la renovación no llegó al portal")
            probe_status = {}
            probe = threading.Thread(
                target=lambda: probe_status.update(
                    status=self.request(f"/api/copies?account={free_account}&record=123")[0]))
            probe.start()
            probe.join(3)
            self.assertFalse(probe.is_alive(),
                             "/api/copies de otra cuenta esperó a la operación de otra cuenta")
            self.assertEqual(probe_status.get("status"), 200)
        finally:
            release.set()
            holder.join(5)
        self.assertFalse(holder.is_alive())

    def test_disconnect_while_writing_an_image_is_not_answered_twice(self):
        """NFR-SVC-002: el fallo al escribir la portada no intenta un segundo 502."""
        wfile = FakeWrite(fail=lambda payload: payload.startswith(b"\x89PNG"))
        handler = self.handler(wfile)
        handler.dispatch = lambda method: handler.respond_image(COVER_PNG, "image/png")
        handler.api("GET")
        body = wfile.body
        self.assertEqual(status_codes(body), [200],
                         f"status emitidos en la misma conexión: {status_codes(body)}")
        self.assertNotIn(b"502 Bad Gateway", body)
        self.assertTrue(handler.client_gone, "la desconexión debe quedar registrada")
        self.assertTrue(handler.close_connection, "una respuesta incompleta obliga a cerrar")

    def test_header_write_failure_closes_without_a_second_response(self):
        """NFR-SVC-002: si ni las cabeceras se pueden escribir, no hay reintento."""
        wfile = FakeWrite(fail=lambda payload: True)
        handler = self.handler(wfile)
        handler.dispatch = lambda method: handler.respond(401, {"error": "Accede"})
        handler.api("GET")
        self.assertTrue(handler.client_gone)
        self.assertTrue(handler.close_connection)
        self.assertEqual(wfile.chunks, [], "no debe reintentarse ninguna escritura")

    def test_real_errors_keep_their_status_for_a_connected_client(self):
        """Los errores reales siguen traduciéndose: solo el socket fallante es desconexión."""
        cases = [(RuntimeError("boom"), 502), (ValueError("malo"), 400),
                 (AppError(429, "Demasiados intentos"), 429),
                 (AuthError("credenciales"), 422),
                 (OperationRefused("rechazada"), 409)]
        for error, status in cases:
            with self.subTest(error=type(error).__name__):
                wfile = FakeWrite()
                handler = self.handler(wfile)

                def dispatch(method, error=error):
                    raise error

                handler.dispatch = dispatch
                handler.api("GET")
                self.assertEqual(status_codes(wfile.body), [status], wfile.body)

    def test_client_reset_during_a_cover_response_leaves_the_server_usable(self):
        """Desconexión real (RST) durante una portada: sin traceback y servidor usable."""
        self.register()
        account = self.add()
        self.data(f"/api/search?account={account}&q=libro")
        started, release = threading.Event(), threading.Event()
        self.server.client_factory = self.hold_factory("cover", started, release)
        connection = socket.create_connection(self.server.server_address, timeout=5)
        connection.sendall(
            ("GET /api/cover?account=%s&record=123 HTTP/1.1\r\n"
             "Host: 127.0.0.1\r\nCookie: %s\r\n\r\n" % (account, self.cookie)).encode())
        self.assertTrue(started.wait(5), "la portada no llegó al portal")
        # El cliente desaparece con un RST antes de que el servidor escriba.
        connection.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
        connection.close()
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            release.set()
            deadline = time.monotonic() + 0.5
            while time.monotonic() < deadline and not stderr.getvalue():
                time.sleep(0.01)
        self.assertEqual(stderr.getvalue(), "",
                         "la desconexión escribió en stderr:\n" + stderr.getvalue())
        self.assertEqual(self.data("/api/version")["api_version"], "6")
        self.assertEqual(self.request(f"/api/cover?account={account}&record=123")[0], 200)

    def test_cover_memory_cache_is_never_served_without_read_authorization(self):
        account, link = self.share("read", "read")
        requester_cookie, requester_csrf = self.cookie, self.csrf
        self.assertEqual(self.request(f"/api/cover?account={account}&record=123")[0], 200)
        fetched = [call for client in self.clients for call in client.calls
                   if isinstance(call, tuple) and call[0] == "cover"]
        self.assertEqual(len(fetched), 1, "el calentamiento debe llegar al portal una sola vez")

        count = len(self.clients)
        # Sin sesión: la caché no sustituye la cookie.
        self.cookie = ""
        self.assertEqual(self.request(f"/api/cover?account={account}&record=123")[0], 401)
        # Tercero ajeno: 403 y ningún cliente del portal.
        self.register("stranger")
        self.assertEqual(self.request(f"/api/cover?account={account}&record=123")[0], 403)
        self.assertEqual(len(self.clients), count, "una petición denegada no construye un cliente")

        # Revocada la concesión, los bytes memorizados tampoco se sirven.
        self.cookie, self.csrf = "", ""
        self.login("owner")
        self.data("/api/links/decide", {"id": link, "action": "revoke"})
        self.cookie, self.csrf = requester_cookie, requester_csrf
        self.assertEqual(self.request(f"/api/cover?account={account}&record=123")[0], 403)
        self.assertEqual(len(self.clients), count)
        fetched = [call for client in self.clients for call in client.calls
                   if isinstance(call, tuple) and call[0] == "cover"]
        self.assertEqual(len(fetched), 1, "la autorización va antes de servir desde la memoria")

    def test_logout_expiry_and_session_rotation(self):
        self.register()
        old_cookie = self.cookie
        self.login("owner")
        new_cookie, new_csrf = self.cookie, self.csrf
        self.cookie = old_cookie
        self.data("/api/library", status=401)
        self.cookie, self.csrf = new_cookie, new_csrf
        self.data("/api/logout", {})
        self.data("/api/library", status=401)
        self.login("owner")
        for session in self.server.sessions.values():
            session["expires"] = 0
        self.data("/api/library", status=401)
        self.assertFalse(self.server.sessions)

    def test_authentication_attempt_limit(self):
        for _ in range(20):
            self.data("/api/login", {"username": "unknown", "password": "wrong"}, 401)
        self.data("/api/login", {"username": "unknown", "password": "wrong"}, 429)

    def test_users_credentials_and_authorization_survive_reopening_store(self):
        account, link = self.share("manage", "manage")
        second = Store(self.path)
        try:
            user = second.login("requester", APP_PASSWORD)
            self.assertEqual(second.access(user["id"], account, manage=True)["permission"], "manage")
            self.assertEqual(second.credentials(account)["password"], PORTAL_PASSWORD)
            self.assertEqual(second.settings(user["id"])["outgoing"][0]["id"], link)
        finally:
            second.close()

    def test_static_assets_and_traversal(self):
        for path in ("/", "/app.js", "/styles.css", "/manifest.webmanifest", "/sw.js", "/icon-192.png", "/icon-512.png"):
            self.assertEqual(self.request(path)[0], 200, path)
        self.assertEqual(self.request("/../accounts.py")[0], 404)
        self.assertEqual(self.request("/.biblio-data/secret.key")[0], 404)
        self.assertIn("frame-ancestors 'none'", self.request("/")[1]["Content-Security-Policy"])
        # La caché RAM de portada (ADR-014) pinta blob URLs creadas por esta
        # misma aplicación; el CSP del shell debe admitirlas sin abrir el
        # origen del DOM a ningún otro sitio.
        policy = self.request("/")[1]["Content-Security-Policy"]
        img_sources = next(part.split(" ", 1)[1] for part in policy.split("; ") if part.startswith("img-src "))
        self.assertEqual(img_sources, "'self' blob:", "img-src debe limitarse a self y blob")
        manifest = json.loads(self.request("/manifest.webmanifest")[2])
        self.assertEqual(manifest["display"], "standalone")
        for icon in manifest["icons"]:
            self.assertTrue(self.request(icon["src"])[2].startswith(b"\x89PNG"))

    def test_service_worker_excludes_private_routes(self):
        source = (Path(__file__).parents[1] / "biblio/static/sw.js").read_text()
        self.assertIn("!SHELL.includes(url.pathname)", source)
        self.assertNotIn("'/api/", source)


if __name__ == "__main__":
    unittest.main()
