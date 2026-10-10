"""Servidor PWA: identidad propia, panel conjunto y API del motor OPAC."""
from __future__ import annotations

import argparse
import contextlib
import dataclasses
import datetime
import enum
import hashlib
import json
import mimetypes
import os
import re
import secrets
import socket
import threading
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit

from . import origins
from . import passkeys as webauthn
from .client import AbsysClient, AuthError, OperationRefused, is_portal_url
from .mailer import Mailer, config_from_env
from .oidc import GoogleProvider, config_from_env as google_config_from_env, STATE_TTL as OIDC_STATE_TTL
from .store import AppError, CHALLENGE_TTL, Store, normalize_email, text

STATIC = Path(__file__).with_name("static")
TTL = 3600
# v6: se añaden las passkeys (FR-AUTH-004) y el acceso opcional con Google
# (FR-AUTH-005): rutas nuevas, `passkeys`/`identities` en el `settings`, y
# `google` en `session`; la forma de todo lo anterior no cambia.
API_VERSION = "6"
# Reautenticación explícita (FR-AUTH-004/005): la ventana en la que una
# contraseña o una passkey recién usadas autorizan a gestionar passkeys o
# identidades externas sin pedirla otra vez.
REAUTH_TTL = 300
# Nombres de identidad externa; por ahora solo Google, opt-in por entorno.
GOOGLE_PROVIDER = "google"
# Ruta fija del callback OIDC: la URI configurada o derivada debe apuntar aquí.
GOOGLE_CALLBACK = "/api/auth/google/callback"
# Cookie de enlace del flujo Google (login CSRF, TODO-SEC-004): la emite
# `google_start` en **ese** navegador y la exige `google_callback` antes de
# canjear el `code`. `SameSite=Lax` hace que viaje en la vuelta superior desde
# el proveedor (una `Strict` no viajaría); la ruta acota al propio flujo.
OIDC_BINDING_COOKIE = "biblio_oidc"
OIDC_BINDING_PATH = "/api/auth/google"
# Las portadas viven en memoria: caducan con el hilo del OPAC (~5 min) y no
# sobreviven a un reinicio, que es exactamente lo que queremos.
COVER_TTL = 600
COVER_LIMIT = 200
# Bytes de portada ya validados, solo en memoria. Acotados en número y en
# tamaño total porque cada imagen puede pesar hasta 1,5 MB: una sesión larga
# no debe poder crecer sin control. Nunca se persisten ni salen sin autorizar.
COVER_IMAGE_LIMIT = 40
COVER_IMAGE_BYTES = 8 * 1024 * 1024
# Solo tipos navegables como imagen. SVG queda fuera: se serviría en el mismo
# origen y un SVG con script podría ejecutarse al abrir la URL directamente.
COVER_TYPES = frozenset({
    "image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp",
    "image/avif", "image/x-icon", "image/vnd.microsoft.icon",
})
# Ruta de sesión del OPAC: `.../abnetopac/<TOKEN>`. Cualquier valor de un DTO
# que la contenga se retira antes de serializar.
OPAC_SESSION_PATH = re.compile(r"/abnetopac/[^/\s?#\"'<>]+", re.IGNORECASE)


def without_opac_tokens(value):
    """Limpia los valores de un DTO de catálogo.

    Una cadena con la ruta de sesión del OPAC pasa a cadena vacía; en las listas
    se eliminan los elementos vacíos. Las claves se conservan para no romper la
    forma del contrato.
    """
    if isinstance(value, str):
        return "" if OPAC_SESSION_PATH.search(value) else value
    if isinstance(value, list):
        return [item for item in (without_opac_tokens(v) for v in value) if item != ""]
    if isinstance(value, dict):
        return {key: without_opac_tokens(item) for key, item in value.items()}
    return value


def cover_path(account_id: str, record_id: str) -> str:
    """URL de portada de esta misma aplicación: sin tokens ni origen ajeno."""
    return f"/api/cover?account={quote(account_id, safe='')}&record={quote(record_id, safe='')}"


class CoverRegistry:
    """Portadas descubiertas en búsquedas y fichas recientes, solo en memoria.

    La URL del proveedor nunca sale de aquí: el navegador solo conoce la ruta
    que emite `cover_path`. Se limita el número de entradas para que una sesión
    larga no crezca sin control.

    Una entrada con URL vacía significa «esta ficha no tiene portada»: se
    recuerda durante el mismo TTL para no abrir la ficha otra vez en cada
    render. Ausente de la caché = desconocida, y ahí sí se descubre.

    Además de la URL se memorizan los **bytes ya validados** de la portada
    (`put_image`/`get_image`) con el mismo TTL y con tope de entradas y de
    tamaño total. El navegador recibe la imagen con `Cache-Control: no-store`,
    así que sin esta memoria cada render volvería a descargarla del portal.
    Quien decide sigue siendo `GET /api/cover`, que autoriza la cuenta antes de
    mirar aquí; una petición denegada no toca ni la URL ni los bytes.
    """

    def __init__(self, ttl=COVER_TTL, limit=COVER_LIMIT, clock=time.monotonic,
                 image_limit=COVER_IMAGE_LIMIT, image_max=COVER_IMAGE_BYTES):
        self.ttl = ttl
        self.limit = limit
        self.clock = clock
        self.image_limit = image_limit
        self.image_max = image_max
        self.entries = {}
        self.images = {}
        self.image_size = 0
        self.lock = threading.Lock()

    def _drop_image(self, key):
        """Quita unos bytes memorizados. Debe llamarse con `self.lock` tomado."""
        entry = self.images.pop(key, None)
        if entry:
            self.image_size -= len(entry[0])

    def register(self, account_id, record_id, url):
        if url is None:
            return
        with self.lock:
            now = self.clock()
            expired = [key for key, (_, expires) in self.entries.items() if expires <= now]
            for key in expired:
                del self.entries[key]
            key = (account_id, record_id)
            previous = self.entries.get(key)
            if previous is not None and previous[0] != url:
                # Cambió la portada del portal: los bytes memorizados ya no valen.
                self._drop_image(key)
            self.entries.pop(key, None)
            self.entries[key] = (url, now + self.ttl)
            while len(self.entries) > self.limit:
                self.entries.pop(next(iter(self.entries)))

    def put_image(self, account_id, record_id, data, content_type):
        """Memoriza bytes ya validados, con el mismo TTL que su URL."""
        key = (account_id, record_id)
        with self.lock:
            self._drop_image(key)
            now = self.clock()
            for expired in [k for k, (_, _, expires) in list(self.images.items()) if expires <= now]:
                self._drop_image(expired)
            self.images[key] = (data, content_type, now + self.ttl)
            self.image_size += len(data)
            while len(self.images) > 1 and (
                    len(self.images) > self.image_limit or self.image_size > self.image_max):
                oldest = next(iter(self.images))
                if oldest == key:
                    oldest = next(k for k in self.images if k != key)
                self._drop_image(oldest)

    def get_image(self, account_id, record_id):
        """`(bytes, content_type)` memorizados, o `None` si no están o caducaron."""
        with self.lock:
            entry = self.images.get((account_id, record_id))
            if not entry:
                return None
            data, content_type, expires = entry
            if expires <= self.clock():
                self._drop_image((account_id, record_id))
                return None
            return data, content_type

    def get(self, account_id, record_id):
        """URL registrada (posiblemente vacía) o `None` si no se conoce."""
        with self.lock:
            entry = self.entries.get((account_id, record_id))
            if not entry:
                return None
            url, expires = entry
            if expires <= self.clock():
                del self.entries[(account_id, record_id)]
                return None
            return url


def encode(value):
    if dataclasses.is_dataclass(value):
        result = dataclasses.asdict(value)
        for name in ("clean_title", "author", "overdue", "due_soon", "available_now"):
            if hasattr(value, name):
                result[name] = getattr(value, name)
        return result
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    if isinstance(value, enum.Enum):
        return value.value
    raise TypeError(type(value).__name__)


class OperationGate:
    """Puerta de operaciones por usuario o por cuenta (NFR-SVC-002, FR-LINK-002).

    Las operaciones autenticadas entran en **compartido** sobre la puerta de su
    usuario y, cuando trabajan con una cuenta, también sobre la de esa cuenta;
    un `links/decide` entra en **exclusivo** sobre la puerta del titular del
    permiso y `accounts/delete` / `accounts/update` sobre la de su cuenta. Así una revocación, una bajada o
    una desvinculación esperan a que termine la operación en curso afectada y
    se aplican antes de las siguientes, mientras que las peticiones sin
    relación —de otros usuarios, otras rutas u otras cuentas— no esperan entre
    sí. Los escritores tienen prioridad para que un cambio no se quede sin
    entrar entre lecturas continuas.
    """

    def __init__(self):
        self._condition = threading.Condition()
        self._shared = 0
        self._waiting_exclusive = 0
        self._exclusive = False

    @contextlib.contextmanager
    def lease(self, exclusive=False):
        with self._condition:
            if exclusive:
                self._waiting_exclusive += 1
                try:
                    while self._exclusive or self._shared:
                        self._condition.wait()
                finally:
                    self._waiting_exclusive -= 1
                self._exclusive = True
            else:
                while self._exclusive or self._waiting_exclusive:
                    self._condition.wait()
                self._shared += 1
        try:
            yield
        finally:
            with self._condition:
                if exclusive:
                    self._exclusive = False
                else:
                    self._shared -= 1
                self._condition.notify_all()


class GateSet:
    """Puertas `OperationGate` por clave opaca: una colección por namespace.

    Se usan dos instancias, una para identificadores de usuario y otra para
    identificadores de cuenta, de modo que los dos espacios nunca se mezclan.
    Una puerta por clave vista vive en RAM, como las sesiones, y muere con el
    proceso: no se elimina al borrar la clave porque podría haber hilos
    esperando en ella.
    """

    def __init__(self):
        self._gates = {}
        self._lock = threading.Lock()

    def lease(self, key, exclusive=False):
        with self._lock:
            gate = self._gates.setdefault(key, OperationGate())
        return gate.lease(exclusive)


class AppServer(ThreadingHTTPServer):
    daemon_threads = True
    # Windows SO_REUSEADDR allows two listeners to serve the same address.
    # Use exclusive binding there so a stale instance cannot steal requests.
    allow_reuse_address = os.name != "nt"

    def server_bind(self):
        if os.name == "nt":
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def __init__(self, address, client_factory=AbsysClient, secure=False, store=None,
                 data_dir=".biblio-data", mailer=None, google=None, trusted_origins=None):
        self.store = store or Store(Path(data_dir) / "biblio.sqlite3")
        self.owns_store = store is None
        super().__init__(address, Handler)
        self.client_factory = client_factory
        self.secure = secure
        self.mailer = mailer
        # Orígenes de confianza para passkeys y callback Google (NFR-SVC-003):
        # solo locales salvo la lista explícita de `BIBLIO_TRUSTED_ORIGINS`.
        self.trusted_origins = origins.TrustedOrigins(trusted_origins or ())
        # Acceso con Google: opt-in por entorno; sin configuración no hay
        # proveedor, no hay botón y el callback rechaza (FR-AUTH-005).
        self.google = GoogleProvider(google) if google is not None else None
        self.sessions = {}
        self.lock = threading.RLock()
        self.auth_attempts = {}
        self.covers = CoverRegistry()
        self.gates = GateSet()
        self.account_gates = GateSet()

    def close_user_sessions(self, user_id, keep_token=None):
        """Cierra las sesiones de un usuario (cambio/recuperación de contraseña).

        `keep_token` conserva la sesión que ejecuta el cambio (FR-AUTH-003):
        una petición ya autorizada puede terminar, pero las siguientes con una
        sesión cerrada reciben 401, igual que en el logout normal.
        """
        with self.lock:
            for key in list(self.sessions):
                if self.sessions[key]["user_id"] == user_id and key != keep_token:
                    del self.sessions[key]

    def operation_gate(self, user_id, exclusive=False):
        """Puerta de operaciones de un usuario; ver `OperationGate`."""
        return self.gates.lease(user_id, exclusive)

    def account_gate(self, account_id, exclusive=False):
        """Puerta de la cuenta: cubre autorizar, descifrar y operar.

        `accounts/delete` y `accounts/update` entran en exclusivo, así que
        ninguna operación en curso de esa cuenta —de cualquier usuario— sigue
        después de aplicarse y ninguna queda con credenciales obsoletas. La
        clave se recorta igual que `store.text`, de modo que un id enviado con
        espacios delimita la misma puerta que el id limpio. Sin identificador
        de cuenta no hay operación posible, así que una entrada inválida no se
        puentea: la rama correspondiente falla antes del portal.
        """
        if not isinstance(account_id, str):
            return contextlib.nullcontext()
        key = account_id.strip()
        if not key:
            return contextlib.nullcontext()
        return self.account_gates.lease(key, exclusive)

    def server_close(self):
        super().server_close()
        if self.owns_store:
            self.store.close()


class Handler(BaseHTTPRequestHandler):
    # Estado de la conexión actual; se restablece al empezar cada petición.
    response_started = False
    client_gone = False

    # Do not log account identifiers, query strings or credentials.
    def log_message(self, *args):
        pass

    def begin_response(self):
        """Nueva petición en esta conexión: aún no se ha emitido ni fallado nada."""
        self.response_started = False
        self.client_gone = False

    def _client_disconnected(self):
        """El socket no admite más escrituras: cerrar sin otra respuesta."""
        self.client_gone = True
        self.close_connection = True

    def error_response(self, status, value):
        """Error traducido; nunca una segunda respuesta en la misma conexión.

        Si la respuesta ya empezó (cabeceras de un 200 de portada, por
        ejemplo) o el socket ya falló, no hay nada que reenviar: se cierra la
        conexión en lugar de concatenar otro estado.
        """
        if self.response_started or self.client_gone:
            self.close_connection = True
            return
        self.respond(status, value)

    @staticmethod
    def _cookies(cookie):
        """Cookies de una respuesta: un valor o una lista, en ese orden."""
        if cookie is None:
            return ()
        return (cookie,) if isinstance(cookie, str) else tuple(cookie)

    def respond(self, status, value, cookie=None):
        if self.client_gone:
            return
        data = json.dumps(value, default=encode, ensure_ascii=False).encode()
        self.response_started = True
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Biblio-API-Version", API_VERSION)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(data)))
            for item in self._cookies(cookie):
                self.send_header("Set-Cookie", item)
            self.end_headers()
            self.wfile.write(data)
        except OSError:
            # Cliente desconectado mientras escribíamos: no se reintentará.
            self._client_disconnected()

    def respond_redirect(self, location, cookie=None):
        """Redirección del callback OIDC: 303 con `no-store` y cookie opcional.

        Es la única respuesta del API que no es JSON: el navegador llega aquí
        por una navegación de ida y vuelta desde el proveedor, y vuelve a la app
        con `/?google=…` para que la UI publique el resultado. El cookie de la
        sesión de login se emite aquí; la cookie `SameSite=Strict` se guarda en
        cualquier respuesta y se envía en las peticiones posteriores de este
        mismo origen, que es donde la app consulta la sesión. `cookie` admite
        una lista (p. ej. retirar la cookie de enlace y emitir la de sesión).
        """
        if self.client_gone:
            return
        self.response_started = True
        try:
            self.send_response(303)
            self.send_header("Location", location)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Biblio-API-Version", API_VERSION)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", "0")
            for item in self._cookies(cookie):
                self.send_header("Set-Cookie", item)
            self.end_headers()
        except OSError:
            self._client_disconnected()

    def respond_image(self, data, content_type):
        """Portada: bytes ya validados, sin caché persistente y sin referrer."""
        if self.client_gone:
            return
        self.response_started = True
        try:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Biblio-API-Version", API_VERSION)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'none'; sandbox")
            self.end_headers()
            self.wfile.write(data)
        except OSError:
            self._client_disconnected()

    def session(self):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
            token = cookie["biblio_session"].value if "biblio_session" in cookie else ""
        except Exception:
            token = ""
        now = time.monotonic()
        with self.server.lock:
            for key in list(self.server.sessions):
                if self.server.sessions[key]["expires"] < now:
                    del self.server.sessions[key]
            session = self.server.sessions.get(token)
            if session:
                session["expires"] = now + TTL
        return token, session

    def session_cookie(self, token):
        return (f"biblio_session={token}; Path=/; HttpOnly; SameSite=Strict"
                + ("; Secure" if self.server.secure else ""))

    def binding_cookie(self, value):
        """Cookie de enlace del flujo Google en **este** navegador.

        `HttpOnly` (el JS no la lee), `SameSite=Lax` (debe viajar en la vuelta
        superior desde el proveedor, algo que `Strict` no haría), ruta del
        callback y la misma caducidad que el `state`; `Secure` solo sobre
        HTTPS, igual que la de sesión. El valor es aleatorio criptográfico de
        32 bytes: nunca se pide ni se guarda en la base de datos.
        """
        cookie = (f"{OIDC_BINDING_COOKIE}={value}; Path={OIDC_BINDING_PATH}; "
                  f"HttpOnly; SameSite=Lax; Max-Age={OIDC_STATE_TTL}")
        return cookie + ("; Secure" if self.server.secure else "")

    def clear_binding_cookie(self):
        """Retirada de la cookie de enlace: al completar y en cada error."""
        cookie = (f"{OIDC_BINDING_COOKIE}=; Path={OIDC_BINDING_PATH}; "
                  "HttpOnly; SameSite=Lax; Max-Age=0")
        return cookie + ("; Secure" if self.server.secure else "")

    def binding_value(self):
        """Valor de la cookie de enlace del navegador, o vacío si no hay."""
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
            return cookie[OIDC_BINDING_COOKIE].value if OIDC_BINDING_COOKIE in cookie else ""
        except Exception:
            return ""

    def binding_matches(self, stored):
        """El navegador que vuelve es el que inició el flujo (login CSRF).

        `stored` es el SHA-256 del valor que se emitió en `start`, guardado con
        el estado. Se compara el **digest** calculado aquí contra el guardado, en
        tiempo constante (`compare_digest`) y **antes** de canjear el `code`,
        abrir sesión o escribir un vínculo. Sin cookie, con cookie ajena o con
        un estado que no guardó digest, la respuesta es la misma: rechazo.
        """
        if not isinstance(stored, str) or not stored:
            return False
        value = self.binding_value()
        if not value:
            return False
        digest = hashlib.sha256(value.encode("utf-8", "replace")).hexdigest()
        return secrets.compare_digest(digest.encode(), stored.encode())

    def link_session_live(self, user_id, proof):
        """La sesión que inició el modo `link` sigue viva y autorizada.

        `proof` es el SHA-256 del token de esa sesión guardado en el estado.
        Se comprueba contra las sesiones vivas **del servidor** (la cookie de
        sesión es `SameSite=Strict` y no viaja en la vuelta desde el proveedor,
        así que no puede leerse aquí): un logout —o cualquier rotación de
        token— mientras el flujo estaba pendiente invalida la vinculación. El
        usuario debe seguir existiendo con email verificado (FR-AUTH-005).
        """
        if not user_id or not isinstance(proof, str) or not proof:
            return False
        now = time.monotonic()
        found = False
        with self.server.lock:
            for token, entry in self.server.sessions.items():
                if entry["expires"] < now or entry["user_id"] != user_id:
                    continue
                digest = hashlib.sha256(token.encode()).hexdigest()
                if secrets.compare_digest(digest.encode(), proof.encode()):
                    found = True
                    break
        if not found:
            return False
        try:
            return bool(self.server.store.user(user_id)["email_verified"])
        except AppError:
            return False

    def store_link_with_live_session(self, user_id, proof, issuer, sub, email):
        """Gate final atómico del modo `link`: sesión viva + titular verificado.

        `server.lock` es el mismo lock que el logout necesita para retirar la
        sesión (y el que usa `close_user_sessions`): retenerlo aquí hace que la
        comprobación de la sesión y la escritura del vínculo sean **indivisibles**
        respecto al logout. Un logout que llega antes se ordena delante (la
        comprobación falla y no se escribe nada); uno que llega mientras el gate
        está en curso se ordena detrás: la sesión seguía viva en el momento de
        escribir, el vínculo queda comprometido y el logout solo cierra la
        sesión (desvincular sigue siendo una acción aparte con reautenticación).
        Dentro, `link_identity(require_verified=True)` revalida existencia y
        email verificado en la **misma transacción** que escribe, bajo
        `store.lock`.

        Seguridad de locks: orden `server.lock` → `store.lock`, ya usado hoy por
        `link_session_live`/`open_session`; el store nunca toca locks del
        servidor ni de sesión, y ninguna ruta toma `server.lock` y después una
        puerta de operación, así que no hay ciclo. La E/I con el proveedor
        ocurre **antes** de entrar aquí, nunca bajo este lock.
        """
        with self.server.lock:
            if not self.link_session_live(user_id, proof):
                return False
            self.server.store.link_identity(user_id, GOOGLE_PROVIDER, issuer, sub,
                                            email, require_verified=True)
            return True

    def request_origin(self):
        """Origen canónico del pedido: esquema de `--secure` + Host estricto.

        `None` cuando el `Host` no es una autoridad canónica; la comparación de
        `Origin` y la selección del callback OIDC usan este valor, nunca el
        Host crudo (NFR-SVC-003 / TODO-SEC-003).
        """
        scheme = "https" if self.server.secure else "http"
        return origins.canonical_origin(scheme, self.headers.get("Host", ""))

    def webauthn_context(self):
        """`(rp_id, origin)` WebAuthn derivados del origen de confiable del pedido."""
        return webauthn.rp_context(self.headers.get("Host", ""), self.server.secure,
                                   self.server.trusted_origins)

    def open_session(self, user, previous_token=None, reauth=False):
        """Abre sesión con token y CSRF nuevos (login, passkey o Google).

        La rotación es la misma que en el login por contraseña: la petición que
        autentica retira el token anterior y el cliente recibe cookie nueva.
        `reauth` marca la sesión como recién autenticada con un factor fuerte
        (una passkey), que es lo que habilita a gestionar passkeys dentro de
        la ventana `REAUTH_TTL` sin pedir la contraseña otra vez (FR-AUTH-004).
        """
        new_token = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(32)
        with self.server.lock:
            if previous_token:
                self.server.sessions.pop(previous_token, None)
            if len(self.server.sessions) >= 100:
                raise AppError(503, "Demasiadas sesiones activas")
            entry = {"user_id": user["id"], "csrf": csrf,
                     "expires": time.monotonic() + TTL, "lock": threading.RLock()}
            if reauth:
                entry["reauth_at"] = time.monotonic()
            self.server.sessions[new_token] = entry
        return {"authenticated": True, "csrf": csrf, "user": user}, self.session_cookie(new_token)

    def require_reauth(self, session):
        """Reautenticación explícita (FR-AUTH-004 / FR-AUTH-005).

        Solo la ventana `REAUTH_TTL` tras una contraseña verificada o una
        passkey usada cuenta como reautenticación; fuera de ella la respuesta
        lleva `code: reauth_required` para que la UI pida el dato (los mensajes
        siguen sin ser claves de lógica de cliente). Una sesión **sin** marca
        `reauth_at` nunca reautenticó y queda fuera de la ventana con cualquier
        valor del reloj: tratar su ausencia como `0` hacía que un host cuyo
        `time.monotonic()` aún no llegara a `REAUTH_TTL` (equipo/VM recién
        arrancado) aceptara la gestión sin reautenticar (TODO-SEC-005).
        """
        stamp = session.get("reauth_at") if isinstance(session, dict) else None
        if not isinstance(stamp, (int, float)) or time.monotonic() - stamp > REAUTH_TTL:
            raise AppError(403, "Confirma tu contraseña para gestionar passkeys o identidades externas.",
                           code="reauth_required")

    def do_GET(self):
        self.begin_response()
        path = urlsplit(self.path).path
        if path.startswith("/api/"):
            self.api("GET")
            return
        files = {"/": "index.html", "/index.html": "index.html", "/app.js": "app.js",
                 "/styles.css": "styles.css", "/manifest.webmanifest": "manifest.webmanifest",
                 "/sw.js": "sw.js", "/icon.svg": "icon.svg", "/icon-192.png": "icon-192.png",
                 "/icon-512.png": "icon-512.png"}
        filename = files.get(path)
        if not filename or not (STATIC / filename).is_file():
            self.respond(404, {"error": "Página no encontrada"})
            return
        data = (STATIC / filename).read_bytes()
        self.response_started = True
        try:
            self.send_response(200)
            mime = "application/manifest+json" if filename.endswith("webmanifest") else mimetypes.guess_type(filename)[0] or "application/octet-stream"
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            # `img-src` admite además `blob:` porque la caché RAM de portada
            # (ADR-014) pinta las imágenes ya descargadas como blob URL creada
            # por este mismo documento; no abre el DOM a ningún otro origen.
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
            self.end_headers()
            self.wfile.write(data)
        except OSError:
            self._client_disconnected()

    def do_POST(self):
        self.begin_response()
        self.api("POST")

    def api(self, method):
        try:
            self.dispatch(method)
        except AppError as exc:
            payload = {"error": str(exc)}
            if exc.code:
                payload["code"] = exc.code
            self.error_response(exc.status, payload)
        except (ValueError, KeyError, TypeError):
            self.error_response(400, {"error": "Datos de solicitud no válidos"})
        except AuthError:
            self.error_response(422, {"error": "No se pudo validar el carné de biblioteca. Revisa sus credenciales en Configuración."})
        except OperationRefused as exc:
            self.error_response(409, {"error": str(exc)})
        except Exception:
            self.error_response(502, {"error": "No se pudo completar la conexión con la biblioteca. Inténtalo de nuevo."})

    def dispatch(self, method):
        parts = urlsplit(self.path)
        path = parts.path
        query = parse_qs(parts.query)
        token, session = self.session()
        body = {}
        if method == "POST":
            origin = self.headers.get("Origin")
            expected = self.request_origin()
            if origin and (expected is None or origin != expected):
                self.respond(403, {"error": "Origen no permitido"})
                return
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                self.respond(415, {"error": "Se requiere JSON"})
                return
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0 or length > 8192:
                self.respond(413, {"error": "Solicitud demasiado grande"})
                return
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError()
        if path == "/api/version" and method == "GET":
            self.respond(200, {"api_version": API_VERSION})
            return
        if path == "/api/session" and method == "GET":
            self.respond(200, {"authenticated": bool(session), "csrf": session["csrf"] if session else None,
                               "user": self.server.store.user(session["user_id"]) if session else None,
                               "api_version": API_VERSION,
                               # Opt-in de Google: la UI solo pinta los botones
                               # cuando el servidor lo tiene configurado.
                               "google": {"enabled": self.server.google is not None}})
            return
        if path in ("/api/login", "/api/register") and method == "POST":
            self.limit("auth")
            store = self.server.store
            if path == "/api/register":
                user = store.register(body.get("username"), body.get("name"), body.get("password"))
            else:
                user = store.login(body.get("username"), body.get("password"))
            data, cookie = self.open_session(user, previous_token=token)
            self.respond(200, data, cookie)
            return
        # Identidad sin sesión (FR-AUTH-002 / FR-AUTH-003): la verificación y
        # la recuperación viajan por correo con códigos de un solo uso. Llevan
        # su propio límite por IP y ruta, sin diluir el de registro/login.
        if (path, method) == ("/api/auth/email/verify", "POST"):
            self.limit("verify")
            user = self.server.store.user(self.server.store.verify_email(body.get("token")))
            self.respond(200, {"verified": True, "user": user})
            return
        if (path, method) == ("/api/auth/password/recovery/request", "POST"):
            self.limit("recovery")
            # El fallo de correo es global y previo: no depende de si el email
            # existe, así que no convierte la ausencia de envío en un oráculo.
            if self.server.mailer is None:
                raise AppError(503, "El envío de correo no está configurado en este servidor.")
            store = self.server.store
            email = normalize_email(body.get("email"))
            raw = store.reset_token(email)
            if raw:
                try:
                    self.server.mailer.send_recovery(email, raw, 60)
                except Exception:
                    # Una incidencia del proveedor no puede distinguir una
                    # cuenta existente de una inexistente: se retira el código
                    # y se responde igual que si no hubiera correo que enviar
                    # (revisión independiente; el detalle queda en el servidor).
                    store.discard_raw_token(raw)
            self.respond(200, {"ok": True,
                               "message": "Si ese email está verificado en BiblioCM, recibirás un código para elegir una contraseña nueva."})
            return
        if (path, method) == ("/api/auth/password/recovery/reset", "POST"):
            self.limit("recovery")
            user_id = self.server.store.reset_password(body.get("token"), body.get("password"))
            self.server.close_user_sessions(user_id)
            self.respond(200, {"ok": True,
                               "message": "Contraseña actualizada. Entra con la contraseña nueva."})
            return
        # Passkeys (FR-AUTH-004): login público con credencial descubrible.
        # Las opciones no llevan identificador ni `allowCredentials`, así que la
        # respuesta es la misma exista o no esa persona (sin enumeración).
        if (path, method) == ("/api/auth/passkeys/login/options", "POST"):
            self.limit("passkey_login")
            rp_id, _ = self.webauthn_context()
            public_key, _ = webauthn.authentication_options(rp_id)
            self.server.store.put_challenge("webauthn_login", None, public_key["challenge"], CHALLENGE_TTL)
            self.respond(200, {"publicKey": public_key})
            return
        if (path, method) == ("/api/auth/passkeys/login", "POST"):
            self.limit("passkey_login")
            self.passkey_login(body, token)
            return
        # Google (FR-AUTH-005): opt-in por entorno. Sin configuración no hay
        # botón en la UI y el servidor rechaza start y callback.
        if (path, method) == ("/api/auth/google/start", "POST") and not session:
            self.limit("oidc")
            self.google_start(body, None, token)
            return
        if path == GOOGLE_CALLBACK and method == "GET":
            self.google_callback(query)
            return
        if not session:
            self.respond(401, {"error": "Accede a BiblioCM para continuar"})
            return
        if method == "POST" and not secrets.compare_digest(self.headers.get("X-CSRF-Token", ""), session["csrf"]):
            self.respond(403, {"error": "Sesión de formulario no válida. Recarga la aplicación."})
            return
        # Reautenticación explícita (FR-AUTH-004/005): contraseña fresca que
        # habilita a gestionar passkeys y vínculos durante `REAUTH_TTL`.
        if (path, method) == ("/api/auth/reauth", "POST"):
            self.limit("reauth")
            self.server.store.verify_password(session["user_id"], body.get("password"))
            session["reauth_at"] = time.monotonic()
            self.respond(200, {"ok": True, "expires_in": REAUTH_TTL})
            return
        # El lock de la sesión cubre la validación y el registro de la operación
        # en curso; la E/I con el portal ocurre después, sin retener ese lock ni
        # el global del store (NFR-SVC-002). La autorización se consulta en el
        # servidor en cada operación; ningún cliente queda en la sesión.
        store = self.server.store
        with contextlib.ExitStack() as pending:
            with session["lock"]:
                with self.server.lock:
                    if self.server.sessions.get(token) is not session:
                        self.respond(401, {"error": "La sesión se ha cerrado. Vuelve a acceder."})
                        return
                if path == "/api/logout" and method == "POST":
                    with self.server.lock:
                        self.server.sessions.pop(token, None)
                    self.respond(200, {"ok": True}, "biblio_session=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict")
                    return
                # Un cambio de permiso se sincroniza con las operaciones en
                # curso del titular del permiso, no con las del que decide.
                if (path, method) == ("/api/links/decide", "POST"):
                    target = store.link_requester(body.get("id"))
                else:
                    target = None
                pending.enter_context(self.server.operation_gate(
                    target or session["user_id"], exclusive=target is not None))
            self.authenticated(path, method, query, body, session["user_id"], token, session)

    def limit(self, bucket):
        """Rate limit por IP y ruta: cada `bucket` tiene su propio contador.

        El de registro/login («auth») conserva su 20 intentos cada 5 minutos;
        verificación y recuperación añaden los suyos sin compartirlos, así que
        tocar una ruta no diluye el límite de otra (NFR-SEC-002).
        """
        now = time.monotonic()
        with self.server.lock:
            for key in list(self.server.auth_attempts):
                if self.server.auth_attempts[key][1] < now:
                    del self.server.auth_attempts[key]
            key = (bucket, self.client_address[0])
            attempts, expires = self.server.auth_attempts.get(key, (0, now + 300))
            if attempts >= 20:
                raise AppError(429, "Demasiados intentos. Espera unos minutos y vuelve a intentarlo.")
            self.server.auth_attempts[key] = (attempts + 1, expires)

    def account_client(self, user_id, account_id, manage=False):
        account = self.server.store.access(user_id, account_id, manage)
        credentials = self.server.store.credentials(account["id"])
        return account, self.server.client_factory(credentials["card"], credentials["password"])

    def public_record(self, record, account_id):
        """DTO de catálogo sin ninguna URL del proveedor.

        La portada se registra en memoria con su URL real y sale como ruta de
        esta misma aplicación; el resto de valores pasan por
        `without_opac_tokens`, que retira la ruta de sesión del OPAC.
        """
        provider_url = getattr(record, "cover_url", "") or ""
        record_id = getattr(record, "record_id", "")
        usable = bool(provider_url) and isinstance(record_id, str) and record_id.isdigit()
        if usable and is_portal_url(provider_url):
            self.server.covers.register(account_id, record_id, provider_url)
            data = cover_path(account_id, record_id)
        else:
            data = ""
        payload = without_opac_tokens(encode(record))
        payload["cover_url"] = data
        return payload

    @staticmethod
    def panel_cover(item, account_id):
        """Ruta de portada de un préstamo/reserva: cuenta + registro, nunca título.

        El panel no abre fichas para averiguar si hay portada: entrega la ruta
        cuando el elemento trae identidad bibliográfica y quien decide es
        `GET /api/cover`, que la descubre bajo demanda si hace falta.
        """
        record_id = getattr(item, "record_id", "")
        if isinstance(record_id, str) and record_id.isdigit():
            return cover_path(account_id, record_id)
        return ""

    def passkey_login(self, body, token):
        """Autentica con passkey: misma sesión, mismos permisos y token rotado.

        El reto se consume **antes** de mirar la credencial, así que un segundo
        uso del mismo reto (o uno caducado) recibe el mismo rechazo genérico;
        la verificación de origen, RP ID, firma, UV y contador es de la
        librería, contra la clave pública guardada de esa passkey.
        """
        store = self.server.store
        rp_id, origin = self.webauthn_context()
        payload = body.get("credential")
        if not isinstance(payload, dict):
            raise AppError(400, webauthn.INVALID)
        raw = webauthn.client_challenge(payload)
        if store.take_challenge("webauthn_login", raw) is None:
            raise AppError(401, "No se pudo validar la passkey. Inténtalo de nuevo.")
        record = store.passkey(payload.get("id"))
        if not record:
            raise AppError(401, "No se pudo validar la passkey. Inténtalo de nuevo.")
        verified = webauthn.verify_authentication(
            rp_id, origin, webauthn.base64url_decode(raw), payload,
            record["public_key"], record["sign_count"])
        store.set_sign_count(record["credential_id"], verified.new_sign_count)
        data, cookie = self.open_session(store.user(record["user_id"]), previous_token=token, reauth=True)
        self.respond(200, data, cookie)

    def google_redirect_uri(self):
        """URI de callback desde un origen de confiable, nunca de un Host arbitrario.

        El origen canónico del pedido debe estar en la lista de confianza (local
        o `BIBLIO_TRUSTED_ORIGINS`) en cualquier caso. Con
        `BIBLIO_GOOGLE_REDIRECT_URI` la URI además debe ser canónica y apuntar a
        `/api/auth/google/callback`; sin ella se deriva de ese origen de
        confianza. Una configuración inválida responde 503 y un Host hostil, 403.
        """
        origin = self.request_origin()
        if origin is None or not self.server.trusted_origins.trusted(origin):
            raise AppError(403, "Origen no permitido para el acceso con Google. "
                                "Configura el origen público en BIBLIO_TRUSTED_ORIGINS.")
        configured = getattr(self.server.google.config, "redirect_uri", None)
        if configured:
            parts = urlsplit(configured)
            canonical = origins.parse_origin(f"{parts.scheme}://{parts.netloc}")
            if (canonical is None or parts.path != GOOGLE_CALLBACK or parts.query
                    or parts.fragment or not self.server.trusted_origins.trusted(canonical)):
                raise AppError(503, "La configuración de acceso con Google no es válida en este servidor.")
            return configured
        return origin + GOOGLE_CALLBACK

    def google_start(self, body, session, token=""):
        """Inicia el flujo de código con `state`/`nonce`/PKCE de un solo uso.

        `mode` es `login` o `signup` sin sesión y `link` **solo** con sesión,
        reautenticación y email verificado: el email del token nunca encuentra
        ni crea cuentas de forma implícita (FR-AUTH-005).

        Cada flujo queda además **atado a este navegador** con una cookie de
        enlace aleatoria (login CSRF): en la base solo vive su SHA-256, en el
        mismo estado que `nonce`/PKCE, y el callback la exige en tiempo
        constante antes de canjear el `code`. En modo `link` se guarda también
        el digest del token de la sesión que inicia el flujo: nunca el token
        mismo, y el gate final exige que esa sesión siga viva (TODO-SEC-004).
        """
        provider = self.server.google
        if provider is None:
            raise AppError(503, "El acceso con Google no está configurado en este servidor.")
        mode = body.get("mode")
        if mode not in ("login", "signup", "link"):
            raise AppError(400, "Elige una opción de acceso con Google válida.")
        store = self.server.store
        user_id = None
        if mode == "link":
            if not session:
                raise AppError(401, "Accede a BiblioCM para vincular Google.")
            self.require_reauth(session)
            user = store.user(session["user_id"])
            if not user["email_verified"]:
                raise AppError(403, "Verifica tu email de BiblioCM antes de vincular Google.")
            user_id = user["id"]
        elif session:
            raise AppError(409, "Cierra sesión para entrar o crearte una cuenta con Google.")
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        binding = secrets.token_urlsafe(32)
        redirect_uri = self.google_redirect_uri()
        detail = {"mode": mode, "nonce": nonce, "verifier": verifier,
                  "redirect_uri": redirect_uri,
                  "bind": hashlib.sha256(binding.encode()).hexdigest()}
        if mode == "link":
            detail["session"] = hashlib.sha256(token.encode()).hexdigest()
        stored = store.cipher.encrypt(json.dumps(detail).encode())
        store.put_challenge("oidc", user_id, state, OIDC_STATE_TTL, stored)
        self.respond(200, {"authorize_url": provider.authorization_url(
            redirect_uri, state, nonce, verifier)}, self.binding_cookie(binding))

    def google_callback(self, query):
        """Callback del proveedor: consume el `state` y redirige a la app.

        Antes de canjear el `code` se exige que el `state` siga vivo **y** que
        la cookie de enlace del navegador coincida con su digest: un callback
        copiado de un navegador a otro (login CSRF) se rechaza sin ninguna
        llamada al proveedor y sin consumir el estado, así que el navegador
        que inició el flujo aún puede terminarlo. Validado ese enlace, el
        estado es de un solo uso, así que un fallo posterior (código
        invalidado, token malformado, firma o claims incorrectos) deja el
        flujo cerrado sin sesión abierta y sin transacción que reutilizar. En
        modo `link`, además, la sesión que inició el flujo debe seguir viva
        para el mismo usuario con email verificado: se comprueba antes de
        canjear el code (para no tocar al proveedor de más) y, de forma
        atómica respecto al logout, en el gate final
        (`store_link_with_live_session`), justo antes de escribir el vínculo.
        """
        provider = self.server.google
        if provider is None:
            raise AppError(503, "El acceso con Google no está configurado en este servidor.")
        self.limit("oidc")
        store = self.server.store
        state = query.get("state", [""])[0]
        code = query.get("code", [""])[0]
        provider_error = query.get("error", [""])[0]
        peeked = store.peek_challenge("oidc", state)
        if peeked is None:
            self.respond_redirect("/?google=error", self.clear_binding_cookie())
            return
        user_id, detail = peeked
        try:
            data = json.loads(store.cipher.decrypt(detail))
        except Exception:
            # Estado con detalle ilegible: se retira y se cierra sin sesión.
            store.take_challenge("oidc", state)
            self.respond_redirect("/?google=error", self.clear_binding_cookie())
            return
        if not self.binding_matches(data.get("bind")):
            # Este navegador no inició el flujo: ni se consume el estado ni se
            # toca al proveedor. La cookie se retira igual para cerrar el intento.
            self.respond_redirect("/?google=error", self.clear_binding_cookie())
            return
        if store.take_challenge("oidc", state) is None or provider_error or not code:
            outcome = "denied" if provider_error == "access_denied" else "error"
            self.respond_redirect("/?google=" + outcome, self.clear_binding_cookie())
            return
        mode, issuer = data.get("mode"), provider.config.issuer
        if mode == "link" and not self.link_session_live(user_id, data.get("session")):
            # Logout (o verificación revocada) con el flujo aún pendiente:
            # no se canjea el code y no se vincula nada.
            self.respond_redirect("/?google=error", self.clear_binding_cookie())
            return
        try:
            tokens = provider.exchange_code(data["redirect_uri"], code, data["verifier"])
            claims = provider.verify_id_token(tokens["id_token"], data["nonce"])
        except AppError:
            self.respond_redirect("/?google=error", self.clear_binding_cookie())
            return
        except Exception:
            # Estado consumido con detalle ilegible: se cierra sin sesión.
            self.respond_redirect("/?google=error", self.clear_binding_cookie())
            return
        sub = claims["sub"]
        if mode == "link":
            try:
                # Gate atómico respecto al logout (ver store_link_with_live_session):
                # la sesión viva y el titular verificado se revalidan dentro del
                # propio lock que usa el logout y dentro de la transacción que
                # escribe. La E/I con el proveedor ya ocurrió fuera del lock.
                linked = self.store_link_with_live_session(
                    user_id, data.get("session"), issuer, sub, claims.get("email"))
            except AppError as exc:
                # 409 = conflicto de vínculo (ya vinculada a otra/tuya); el
                # 401 del gate atómico (titular ya no válido) cierra en `error`.
                self.respond_redirect("/?google=exists" if exc.status == 409
                                      else "/?google=error",
                                      self.clear_binding_cookie())
                return
            if not linked:
                self.respond_redirect("/?google=error", self.clear_binding_cookie())
                return
            self.respond_redirect("/?google=linked", self.clear_binding_cookie())
            return
        owner = store.identity_user(GOOGLE_PROVIDER, issuer, sub) if mode == "login" else None
        if mode == "login":
            if owner is None:
                # Ni merge por email ni alta implícita: esa cuenta no está vinculada.
                self.respond_redirect("/?google=not-linked", self.clear_binding_cookie())
                return
            data_response, cookie = self.open_session(store.user(owner))
            self.respond_redirect("/?google=signed", [self.clear_binding_cookie(), cookie])
            return
        if mode == "signup":
            email, verified = claims.get("email"), claims.get("email_verified")
            if not isinstance(email, str) or verified is not True:
                self.respond_redirect("/?google=error", self.clear_binding_cookie())
                return
            name = claims.get("name")
            if not isinstance(name, str) or not name.strip():
                name = email.split("@", 1)[0]
            try:
                user = store.register_with_identity(
                    name, email, secrets.token_urlsafe(24), GOOGLE_PROVIDER, issuer, sub)
            except AppError as exc:
                self.respond_redirect("/?google=exists" if exc.status == 409 else "/?google=error",
                                      self.clear_binding_cookie())
                return
            data_response, cookie = self.open_session(user)
            self.respond_redirect("/?google=signed", [self.clear_binding_cookie(), cookie])
            return
        self.respond_redirect("/?google=error", self.clear_binding_cookie())

    def authenticated(self, path, method, query, body, user_id, token=None, session=None):
        store = self.server.store
        if path == "/api/settings" and method == "GET":
            self.respond(200, store.settings(user_id))
            return
        # Passkeys (FR-AUTH-004): añadir o borrar exige reautenticación
        # explícita, no solo la sesión abierta.
        if (path, method) == ("/api/auth/passkeys/register/options", "POST"):
            self.limit("passkey")
            self.require_reauth(session)
            rp_id, _ = self.webauthn_context()
            public_key, _ = webauthn.registration_options(
                rp_id, store.user(user_id), store.passkeys(user_id))
            store.put_challenge("webauthn_register", user_id, public_key["challenge"], CHALLENGE_TTL)
            self.respond(200, {"publicKey": public_key})
            return
        if (path, method) == ("/api/auth/passkeys/register", "POST"):
            self.limit("passkey")
            self.require_reauth(session)
            rp_id, origin = self.webauthn_context()
            payload = body.get("credential")
            if not isinstance(payload, dict):
                raise AppError(400, webauthn.INVALID)
            raw = webauthn.client_challenge(payload)
            taken = store.take_challenge("webauthn_register", raw)
            # El reto pertenece a esta sesión: otro usuario (o un reto de login)
            # no puede registrarse con él.
            if taken is None or taken[0] != user_id:
                raise AppError(400, webauthn.INVALID)
            verified = webauthn.verify_registration(
                rp_id, origin, webauthn.base64url_decode(raw), payload)
            credential_id = webauthn.base64url_encode(verified.credential_id)
            transports = [value for value in (payload.get("response") or {}).get("transports", [])
                          if isinstance(value, str) and value in
                          {"usb", "nfc", "ble", "smart-card", "internal", "cable", "hybrid"}]
            store.add_passkey(user_id, credential_id, verified.credential_public_key,
                              verified.sign_count, transports, text(body.get("label") or "Passkey", 40))
            meta = next(item for item in store.passkeys(user_id) if item["id"] == credential_id)
            self.respond(200, {"ok": True, "passkey": meta,
                               "message": "Passkey añadida. Ya puedes usarla para entrar."})
            return
        if (path, method) == ("/api/auth/passkeys/delete", "POST"):
            self.limit("passkey")
            self.require_reauth(session)
            if not store.delete_passkey(user_id, body.get("id")):
                # Mismo rechazo si no existe o si es de otra persona.
                raise AppError(403, "No tienes ninguna passkey con ese identificador.")
            self.respond(200, {"ok": True, "message": "Passkey eliminada."})
            return
        # Google (FR-AUTH-005): vincular/desvincular con sesión + reautenticación.
        if (path, method) == ("/api/auth/google/start", "POST"):
            self.limit("oidc")
            self.google_start(body, session, token)
            return
        if (path, method) == ("/api/auth/google/unlink", "POST"):
            self.limit("oidc")
            self.require_reauth(session)
            if not store.unlink_identity(user_id, GOOGLE_PROVIDER):
                raise AppError(404, "No tienes ninguna cuenta de Google vinculada.")
            self.respond(200, {"ok": True,
                               "message": "Cuenta de Google desvinculada. Tu cuenta y tus carnés siguen intactos."})
            return
        if (path, method) == ("/api/auth/email/request", "POST"):
            # Pedir verificar el propio email desde la sesión (FR-AUTH-002).
            # Sin correo configurado el fallo es global; si el email ya es de
            # otra cuenta, el store devuelve None y la respuesta es igual; y
            # si el proveedor falla, se retira el código y se responde igual
            # que con un envío satisfactorio: la incidencia no debe revelar si
            # la dirección está en uso (revisión independiente).
            self.limit("email")
            if self.server.mailer is None:
                raise AppError(503, "El envío de correo no está configurado en este servidor.")
            email = normalize_email(body.get("email"))
            raw = store.email_verification_token(user_id, email)
            if raw:
                try:
                    self.server.mailer.send_verification(email, raw, 24)
                except Exception:
                    store.discard_raw_token(raw)
            self.respond(200, {"ok": True,
                               "message": "Si el email es válido y no está en uso, recibirás un código para verificarlo."})
            return
        if (path, method) == ("/api/auth/password/change", "POST"):
            self.limit("change")
            store.change_password(user_id, body.get("current_password"), body.get("password"))
            # La sesión que cambia la contraseña sigue viva; las demás se
            # cierran (FR-AUTH-003), sin tocar cifrado, carnés ni vínculos.
            self.server.close_user_sessions(user_id, keep_token=token)
            self.respond(200, {"ok": True,
                               "message": "Contraseña actualizada. Las demás sesiones se han cerrado."})
            return
        if path in ("/api/accounts/add", "/api/accounts/update") and method == "POST":
            label = text(body.get("label"), 80)
            password = body.get("password")
            if not isinstance(password, str) or not 1 <= len(password) <= 200:
                raise ValueError()
            if path.endswith("update"):
                account_id = text(body.get("account"), 100)
                # Exclusivo: mientras rota credenciales, ninguna operación de
                # esa cuenta puede quedar con la foto anterior descifrada, y
                # las que estaban en curso terminan antes de aplicar el cambio.
                with self.server.account_gate(account_id, exclusive=True):
                    store.require_owner(user_id, account_id)
                    card = store.credentials(account_id)["card"]
                    self.server.client_factory(card, password).login()
                    store.update_account(user_id, account_id, label, card, password)
            else:
                card = text(body.get("card"), 100)
                self.server.client_factory(card, password).login()
                account_id = store.add_account(user_id, label, card, password)
            self.respond(200, {"account": account_id, "message": "Cuenta de biblioteca vinculada y verificada."})
            return
        if path == "/api/accounts/delete" and method == "POST":
            account_id = text(body.get("account"), 100)
            # Exclusivo: ninguna operación en curso de esa cuenta —de cualquier
            # usuario— sigue después de desvincilarla (NFR-SVC-002).
            with self.server.account_gate(account_id, exclusive=True):
                store.delete_account(user_id, account_id)
            self.respond(200, {"message": "Cuenta desvinculada. Sus credenciales han sido eliminadas."})
            return
        if path == "/api/links/request" and method == "POST":
            link_id = store.request_link(user_id, body.get("username"), body.get("permission"))
            self.respond(200, {"id": link_id, "message": "Solicitud enviada. El titular podrá aprobarla en Configuración."})
            return
        if path == "/api/links/decide" and method == "POST":
            store.decide_link(user_id, body.get("id"), body.get("action"), body.get("permission"))
            self.respond(200, {"message": "Solicitud y permisos actualizados."})
            return
        if path == "/api/library" and method == "GET":
            accounts, loans, reservations = [], [], []
            for account in store.accessible_accounts(user_id):
                result = dict(account)
                try:
                    # Una cuenta cada vez: autorizar, descifrar y consultar el
                    # portal bajo su puerta; nunca dos cuentas a la vez.
                    with self.server.account_gate(account["id"]):
                        _, client = self.account_client(user_id, account["id"])
                        library = client.my_library()
                        result["reader"] = library.reader
                        for loan in library.loans:
                            loans.append(dict(encode(loan), account=account,
                                              cover_url=self.panel_cover(loan, account["id"])))
                        for reservation in library.reservations:
                            reservations.append(dict(encode(reservation), account=account,
                                                     cover_url=self.panel_cover(reservation, account["id"])))
                except AuthError:
                    result["error"] = "Credenciales de biblioteca no válidas. El titular debe actualizarlas."
                except Exception:
                    result["error"] = "No se pudo consultar esta biblioteca. Vuelve a intentarlo."
                accounts.append(result)
            self.respond(200, {"user": store.user(user_id), "accounts": accounts, "loans": loans, "reservations": reservations})
            return
        if (path, method) == ("/api/cover", "GET"):
            record_id = query.get("record", [""])[0]
            if not record_id.isdigit():
                raise ValueError()
            account_id = query.get("account", [""])[0]
            # Autorizar antes de mirar el registro o la memoria: un 403/404 no
            # debe filtrar qué portadas existen para una cuenta ajena, y ni la
            # descubierta bajo demanda ni los bytes memorizados pueden saltarse
            # esa comprobación. Autorizar, descifrar y descargar ocurren bajo
            # la puerta de la cuenta, así que una desvinculación o una rotación
            # esperan a esta operación y no puede quedar ninguna acción de
            # portal después de aplicarse (NFR-SVC-002).
            with self.server.account_gate(account_id):
                store.access(user_id, account_id)
                cached = self.server.covers.get_image(account_id, record_id)
                if cached is not None:
                    self.respond_image(*cached)
                    return
                _, client = self.account_client(user_id, account_id)
                registered = self.server.covers.get(account_id, record_id)
                if registered is None:
                    # Ficha nunca buscada, entrada caducada o reinicio: se abre la
                    # ficha una sola vez y se memoriza también la ausencia.
                    discovered = client.record_cover_url(record_id)
                    if discovered and is_portal_url(discovered):
                        self.server.covers.register(account_id, record_id, discovered)
                        registered = discovered
                    else:
                        self.server.covers.register(account_id, record_id, "")
                if not registered:
                    raise AppError(404, "No hay portada disponible para esta ficha.")
                data, content_type = client.cover(registered)
                if content_type not in COVER_TYPES:
                    raise AppError(502, "La portada recibida no es una imagen segura.")
                # Los bytes ya pasaron origen/CGI/tipo/tamaño: se memorizan para que
                # el siguiente render (no-store en el navegador) no vuelva al portal.
                self.server.covers.put_image(account_id, record_id, data, content_type)
                self.respond_image(data, content_type)
            return
        routes = {("/api/search", "GET"), ("/api/copies", "GET"), ("/api/reservable", "GET"),
                  ("/api/renew", "POST"), ("/api/reserve", "POST"), ("/api/cancel", "POST")}
        if (path, method) not in routes:
            self.respond(404, {"error": "Operación no encontrada"})
            return
        account_id = body.get("account") if method == "POST" else query.get("account", [None])[0]
        # Autorizar, descifrar y operar con el portal bajo la puerta de esa
        # cuenta: desvincular o rotar credenciales espera a esta operación y
        # ninguna posterior llega al portal sin autorizar de nuevo (NFR-SVC-002).
        with self.server.account_gate(account_id):
            _, client = self.account_client(user_id, account_id, manage=method == "POST")
            if path == "/api/search":
                query_text = query.get("q", [""])[0].strip()
                page = int(query.get("page", ["1"])[0])
                if not query_text or len(query_text) > 300 or not 1 <= page <= 1000:
                    raise ValueError()
                total, records = client.search(query_text, page=page)
                self.respond(200, {"total": total, "page": page,
                                   "records": [self.public_record(record, account_id) for record in records]})
            elif path == "/api/copies":
                record = query.get("record", [""])[0]
                if not record.isdigit():
                    raise ValueError()
                self.respond(200, {"copies": client.copies(record)})
            elif path == "/api/reservable":
                record = query.get("record", [""])[0]
                if not record.isdigit():
                    raise ValueError()
                copies = client.reservable_copies(record)
                if any(not (c.get("library") or c.get("branch")) for c in copies):
                    raise AppError(502, "No se han recibido los datos de biblioteca de los reservables. Actualiza el servidor y vuelve a consultar.")
                # Never expose the old unstructured HTML-snippet fallback to the UI.
                public_fields = ("index", "barcode", "library", "branch", "location", "signature", "copy_type", "availability")
                self.respond(200, {"copies": [{key: c.get(key, "") for key in public_fields} for c in copies]})
            elif path == "/api/renew":
                barcode = body["barcode"]
                if not isinstance(barcode, str) or not barcode.isdigit():
                    raise ValueError()
                self.respond(200, client.renew(barcode))
            elif path == "/api/reserve":
                record, index = body["record"], body["index"]
                if not isinstance(record, str) or not record.isdigit() or type(index) is not int or index < 1:
                    raise ValueError()
                barcode = body.get("barcode")
                if barcode is not None and (not isinstance(barcode, str) or not barcode.isdigit()):
                    raise ValueError()
                message = client.reserve(record, index, barcode=barcode) if barcode is not None else client.reserve(record, index)
                self.respond(200, {"message": message})
            elif path == "/api/cancel":
                reservation = body["reservation"]
                if not isinstance(reservation, str) or not reservation.isdigit():
                    raise ValueError()
                self.respond(200, {"message": client.cancel_reservation(reservation)})


def main():
    parser = argparse.ArgumentParser(description="BiblioCM · aplicación web instalable")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--secure", action="store_true", help="Cookies Secure detrás de un proxy HTTPS")
    parser.add_argument("--data-dir", default=".biblio-data", help="Directorio de SQLite y clave de cifrado")
    args = parser.parse_args()
    mail_config = config_from_env()
    mailer = Mailer(mail_config) if mail_config else None
    if mailer is None:
        print("BiblioCM: sin BIBLIO_SMTP_HOST no se enviarán correos de verificación "
              "ni de recuperación.", flush=True)
    google = google_config_from_env()
    if google is None:
        print("BiblioCM: sin BIBLIO_GOOGLE_CLIENT_ID/BIBLIO_GOOGLE_CLIENT_SECRET no "
              "habrá acceso ni vinculación con Google.", flush=True)
    try:
        trusted = origins.parse_trusted_origins(os.environ.get("BIBLIO_TRUSTED_ORIGINS"))
    except AppError as exc:
        raise SystemExit(f"BiblioCM: {exc}") from None
    if args.secure and not trusted:
        print("BiblioCM: sin BIBLIO_TRUSTED_ORIGINS solo se aceptan orígenes locales "
              "(localhost/127.0.0.1) para passkeys y Google.", flush=True)
    with AppServer((args.host, args.port), secure=args.secure, data_dir=args.data_dir,
                   mailer=mailer, google=google, trusted_origins=trusted) as server:
        print(f"BiblioCM API v{API_VERSION}: http://{args.host}:{args.port} · Ctrl+C para salir", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
