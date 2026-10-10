"""Identidad BiblioCM, credenciales cifradas y autorizaciones persistentes."""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import sqlite3
import threading
import time
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

# Versión del esquema que entiende este código; ver `_migrate`.
SCHEMA_VERSION = 2
# Vida de los códigos de un solo uso: el de verificación viaja por correo y el
# de recuperación da acceso a cambiar la contraseña, así que caducan pronto.
VERIFY_TTL = 24 * 60 * 60
RESET_TTL = 60 * 60
# Retos WebAuthn y transacciones OIDC: se emiten para una ceremonia inmediata.
CHALLENGE_TTL = 300
OIDC_STATE_TTL = 600
# Tope de passkeys por cuenta: acota el crecimiento de la tabla y un registro
# olvidado no puede quedarse sin gestión posible.
PASSKEY_LIMIT = 10
EMAIL_MAX = 254
EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


class AppError(Exception):
    """Error traducible al envelope del API; `code` es opcional y lo pide la UI.

    Los mensajes son texto informativo (no una clave para la lógica de cliente);
    `code` sí es estable y solo se usa para lo que la UI debe resolver de forma
    programática — hoy, pedir reautenticación (`reauth_required`).
    """

    def __init__(self, status, message, code=None):
        self.status = status
        self.code = code
        super().__init__(message)


def text(value, maximum=200):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise AppError(400, "Completa los campos con datos válidos.")
    return value.strip()


def permission(value):
    if value not in ("read", "manage"):
        raise AppError(400, "Elige solo lectura o gestión completa.")
    return value


def password_hash(password, salt):
    return hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1, dklen=32)


def normalize_email(value):
    """Email normalizado para almacenar o buscar; nunca se guarda sin pasar por aquí."""
    email = text(value, EMAIL_MAX).lower()
    if len(email) < 5 or not EMAIL_RE.fullmatch(email):
        raise AppError(400, "Introduce un email válido.")
    return email


def token_digest(raw):
    """Hash almacenable de un código de un solo uso: el claro nunca se persiste."""
    return hashlib.sha256(raw.encode()).hexdigest()


class Store:
    def __init__(self, path, key=None):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        key_path = path.parent / "secret.key"
        key = key or os.environ.get("BIBLIO_SECRET_KEY")
        if not key:
            if not key_path.exists():
                # Never silently create a new key for an existing database.
                if path.exists() and path.stat().st_size:
                    raise RuntimeError("Falta la clave de cifrado: restaura secret.key o BIBLIO_SECRET_KEY.")
                generated = Fernet.generate_key()
                try:
                    fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                    with os.fdopen(fd, "wb") as handle:
                        handle.write(generated)
                except FileExistsError:
                    pass
            key = key_path.read_bytes().strip()
        self.cipher = Fernet(key.encode() if isinstance(key, str) else key)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA secure_delete=ON")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL, salt BLOB NOT NULL, password_hash BLOB NOT NULL
            );
            CREATE TABLE IF NOT EXISTS accounts (
                id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id),
                label TEXT NOT NULL, card_digest TEXT NOT NULL UNIQUE,
                credentials BLOB NOT NULL
            );
            CREATE TABLE IF NOT EXISTS links (
                id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id),
                requester_id TEXT NOT NULL REFERENCES users(id),
                permission TEXT NOT NULL CHECK(permission IN ('read','manage')),
                status TEXT NOT NULL CHECK(status IN ('pending','approved','rejected','revoked')),
                UNIQUE(owner_id, requester_id), CHECK(owner_id != requester_id)
            );
        """)
        try:
            self._migrate()
        except Exception:
            # Cerrar antes de propagar: en Windows una conexión abierta dejaría
            # el fichero bloqueado e impediría corregir el obstáculo y reabrir.
            self.db.close()
            raise
        # Fail at startup rather than making every saved account unusable later.
        try:
            with self.lock:
                for row in self.db.execute("SELECT credentials FROM accounts"):
                    self.cipher.decrypt(row["credentials"])
        except InvalidToken:
            self.db.close()
            raise RuntimeError("La clave de cifrado no corresponde a la base de datos o los datos están dañados.") from None

    def close(self):
        with self.lock:
            self.db.close()

    def _migrate(self):
        """Migración de esquema en una única transacción (NFR-DATA-001 parcial).

        - **v0 → v1**: email verificado y tabla de códigos de un solo uso.
        - **v1 → v2**: passkeys, retos/transacciones de identidad externa e
          identidades vinculadas (Google), sin tocar identificadores, vínculos,
          carnés ni credenciales cifradas.

        Un fichero v0 recorre las dos etapas en la misma transacción, así que o
        acaba en v2 o queda exactamente como estaba. SQLite admite DDL
        transaccional, así que un fallo revierte todo —incluido
        `user_version`— y los datos quedan como estaban; en ese caso se levanta
        un error en el arranque en lugar de dejar una base a medias. Solo se
        migran copias/bases temporales durante el desarrollo: migrar datos reales
        exige respaldo previo (operations.md).
        """
        with self.lock:
            version = self.db.execute("PRAGMA user_version").fetchone()[0]
            if version >= SCHEMA_VERSION:
                return
            # El módulo sqlite3 no abre transacción implícita para DDL, así que
            # se controla a mano: sin BEGIN explícito un ALTER quedaría aplicado
            # aunque el resto de la migración fallara.
            previous_isolation = self.db.isolation_level
            self.db.isolation_level = None
            try:
                self.db.execute("BEGIN")
                if version == 0:
                    columns = {row[1] for row in self.db.execute("PRAGMA table_info(users)")}
                    if "email" not in columns:
                        self.db.execute("ALTER TABLE users ADD COLUMN email TEXT")
                    if "email_verified_at" not in columns:
                        self.db.execute("ALTER TABLE users ADD COLUMN email_verified_at TEXT")
                    self.db.execute("""
                        CREATE TABLE IF NOT EXISTS identity_tokens (
                            token_hash TEXT PRIMARY KEY,
                            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                            purpose TEXT NOT NULL CHECK(purpose IN ('email_verify','password_reset')),
                            detail TEXT NOT NULL DEFAULT '',
                            expires_at INTEGER NOT NULL,
                            created_at INTEGER NOT NULL
                        );
                    """)
                    self.db.execute(
                        "CREATE UNIQUE INDEX IF NOT EXISTS users_email_unique "
                        "ON users(email) WHERE email IS NOT NULL")
                    self.db.execute(
                        "CREATE INDEX IF NOT EXISTS identity_tokens_user_purpose "
                        "ON identity_tokens(user_id, purpose)")
                if version <= 1:
                    # Solo se añaden tablas e índices: nada existente se reescribe.
                    self.db.execute("""
                        CREATE TABLE IF NOT EXISTS passkeys (
                            credential_id TEXT PRIMARY KEY,
                            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                            public_key BLOB NOT NULL,
                            sign_count INTEGER NOT NULL DEFAULT 0,
                            transports TEXT NOT NULL DEFAULT '',
                            label TEXT NOT NULL DEFAULT '',
                            created_at INTEGER NOT NULL
                        );
                    """)
                    self.db.execute(
                        "CREATE INDEX IF NOT EXISTS passkeys_user_id ON passkeys(user_id)")
                    self.db.execute("""
                        CREATE TABLE IF NOT EXISTS auth_challenges (
                            challenge_hash TEXT PRIMARY KEY,
                            purpose TEXT NOT NULL,
                            user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
                            detail BLOB NOT NULL DEFAULT X'',
                            expires_at INTEGER NOT NULL,
                            created_at INTEGER NOT NULL
                        );
                    """)
                    self.db.execute(
                        "CREATE INDEX IF NOT EXISTS auth_challenges_purpose_expiry "
                        "ON auth_challenges(purpose, expires_at)")
                    self.db.execute("""
                        CREATE TABLE IF NOT EXISTS identities (
                            id TEXT PRIMARY KEY,
                            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                            provider TEXT NOT NULL,
                            issuer TEXT NOT NULL,
                            sub TEXT NOT NULL,
                            email TEXT,
                            created_at INTEGER NOT NULL,
                            UNIQUE(issuer, sub),
                            UNIQUE(user_id, provider)
                        );
                    """)
                    self.db.execute(
                        "CREATE INDEX IF NOT EXISTS identities_user_id ON identities(user_id)")
                self.db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
                self.db.execute("COMMIT")
            except Exception:
                try:
                    self.db.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                raise RuntimeError(
                    "La base de datos no pudo migrar a la versión "
                    f"{SCHEMA_VERSION}; los datos no se han modificado. Restaura "
                    "una copia o corrige el obstáculo y vuelve a arrancar.") from None
            finally:
                self.db.isolation_level = previous_isolation

    def user(self, user_id):
        with self.lock:
            row = self.db.execute(
                "SELECT id,username,name,email,email_verified_at FROM users WHERE id=?",
                (user_id,)).fetchone()
            if not row:
                raise AppError(401, "La sesión ya no es válida. Vuelve a acceder.")
            return {"id": row["id"], "username": row["username"], "name": row["name"],
                    "email": row["email"], "email_verified": bool(row["email_verified_at"])}

    def register(self, username, name, password):
        username = text(username, 40).lower()
        if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{2,39}", username):
            raise AppError(400, "El usuario debe tener entre 3 y 40 caracteres: letras, números, punto, guion o guion bajo.")
        name = text(name, 80)
        if not isinstance(password, str) or not 10 <= len(password) <= 200:
            raise AppError(400, "La contraseña de BiblioCM debe tener entre 10 y 200 caracteres.")
        user_id, salt = secrets.token_urlsafe(18), secrets.token_bytes(16)
        hashed = password_hash(password, salt)
        with self.lock, self.db:
            try:
                self.db.execute(
                    "INSERT INTO users (id,username,name,salt,password_hash) VALUES (?,?,?,?,?)",
                    (user_id, username, name, salt, hashed))
            except sqlite3.IntegrityError:
                raise AppError(409, "Ese nombre de usuario ya está registrado.") from None
        return self.user(user_id)

    def login(self, username, password):
        # Alias legado: el username sigue entrando igual que siempre; el email
        # solo abre sesión cuando está verificado (FR-AUTH-002). Un email sin
        # verificar recibe el mismo error genérico que una contraseña mala.
        maximum = 254 if isinstance(username, str) and "@" in username else 40
        identity = text(username, maximum).lower()
        if not isinstance(password, str) or not 1 <= len(password) <= 200:
            raise AppError(400, "Introduce una contraseña válida.")
        with self.lock:
            if "@" in identity:
                row = self.db.execute(
                    "SELECT * FROM users WHERE email=? AND email_verified_at IS NOT NULL",
                    (identity,)).fetchone()
            else:
                row = self.db.execute("SELECT * FROM users WHERE username=?", (identity,)).fetchone()
        hashed = password_hash(password, row["salt"] if row else b"\0" * 16)
        if not row or not secrets.compare_digest(hashed, row["password_hash"]):
            raise AppError(401, "Usuario o contraseña de BiblioCM incorrectos.")
        return self.user(row["id"])

    def verify_password(self, user_id, password):
        """Verifica la contraseña vigente sin abrir sesión (reautenticación).

        Responde 403 y no 401: un 401 significa «sesión inválida» en el API y
        la UI cerraría la sesión en lugar de pedir el dato otra vez.
        """
        if not isinstance(password, str) or not 1 <= len(password) <= 200:
            raise AppError(403, "La contraseña no es correcta.")
        with self.lock:
            row = self.db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        hashed = password_hash(password, row["salt"] if row else b"\0" * 16)
        if not row or not secrets.compare_digest(hashed, row["password_hash"]):
            raise AppError(403, "La contraseña no es correcta.")

    def _purge_tokens(self, now):
        """Quita códigos caducados. Debe llamarse con lock y transacción tomados."""
        self.db.execute("DELETE FROM identity_tokens WHERE expires_at<=?", (now,))

    def _insert_token(self, user_id, purpose, detail, raw, now, ttl):
        self.db.execute("DELETE FROM identity_tokens WHERE user_id=? AND purpose=?",
                        (user_id, purpose))
        self._purge_tokens(now)
        self.db.execute("INSERT INTO identity_tokens VALUES (?,?,?,?,?,?)",
                        (token_digest(raw), user_id, purpose, detail, now + ttl, now))

    def email_verification_token(self, user_id, email, now=None):
        """Código para verificar `email` como alias de acceso; `None` si está en uso.

        Silencioso cuando el email pertenece a otra cuenta: la respuesta no
        revela si una dirección está registrada (anti-enumeración). Un fallo de
        envío posterior lo retira la capa web con `discard_tokens`.
        """
        email = normalize_email(email)
        now = int(time.time() if now is None else now)
        with self.lock, self.db:
            taken = self.db.execute("SELECT id FROM users WHERE email=? AND id!=?",
                                    (email, user_id)).fetchone()
            if taken:
                return None
            raw = secrets.token_urlsafe(32)
            self._insert_token(user_id, "email_verify", email, raw, now, VERIFY_TTL)
            return raw

    def verify_email(self, raw, now=None):
        """Consume un código de verificación: una sola vez, con caducidad."""
        now = int(time.time() if now is None else now)
        if not isinstance(raw, str) or not raw:
            raise AppError(400, "El código no es válido o ha caducado. Pide uno nuevo.")
        digest = token_digest(raw)
        with self.lock, self.db:
            row = self.db.execute(
                "SELECT * FROM identity_tokens WHERE token_hash=? AND purpose='email_verify'",
                (digest,)).fetchone()
            if not row or row["expires_at"] <= now:
                if row:
                    self.db.execute("DELETE FROM identity_tokens WHERE token_hash=?", (digest,))
                raise AppError(400, "El código no es válido o ha caducado. Pide uno nuevo.")
            self.db.execute("DELETE FROM identity_tokens WHERE token_hash=?", (digest,))
            try:
                self.db.execute(
                    "UPDATE users SET email=?, email_verified_at=? WHERE id=?",
                    (row["detail"], time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(now)),
                     row["user_id"]))
            except sqlite3.IntegrityError:
                raise AppError(400, "El código no es válido o ha caducado. Pide uno nuevo.") from None
            return row["user_id"]

    def discard_tokens(self, user_id, purpose):
        """Retira los códigos de un usuario/purpose (p. ej. si el envío falló)."""
        with self.lock, self.db:
            self.db.execute("DELETE FROM identity_tokens WHERE user_id=? AND purpose=?",
                            (user_id, purpose))

    def discard_raw_token(self, raw):
        """Retira un código concreto por su valor (p. ej. si su envío falló)."""
        if not isinstance(raw, str) or not raw:
            return
        with self.lock, self.db:
            self.db.execute("DELETE FROM identity_tokens WHERE token_hash=?", (token_digest(raw),))

    # ---------------------------------------------------------------------
    # Retos de un solo uso: passkeys y transacciones OIDC (v2)
    # ---------------------------------------------------------------------

    def _purge_challenges(self, now):
        """Quita retos caducados. Debe llamarse con lock y transacción tomados."""
        self.db.execute("DELETE FROM auth_challenges WHERE expires_at<=?", (now,))

    def put_challenge(self, purpose, user_id, raw, ttl, detail=b"", now=None):
        """Guarda un reto/transacción con caducidad; solo vive su SHA-256.

        `detail` es opaco para el store (los estados OIDC van cifrados con
        Fernet): ni el nonce ni el verificador PKCE se guardan en claro.
        """
        if not isinstance(raw, str) or not raw:
            raise AppError(400, "La solicitud no es válida. Inténtalo de nuevo.")
        now = int(time.time() if now is None else now)
        with self.lock, self.db:
            self._purge_challenges(now)
            self.db.execute(
                "INSERT OR REPLACE INTO auth_challenges VALUES (?,?,?,?,?,?)",
                (token_digest(raw), purpose, user_id, detail, now + ttl, now))

    def peek_challenge(self, purpose, raw, now=None):
        """Lee un reto sin consumirlo, para una comprobación previa.

        Devuelve `(user_id, detail)` o `None` igual que `take_challenge`, pero
        **no** retira la fila y no escribe nada: así el callback OIDC puede
        comparar primero el enlace de navegador contra el digest guardado y un
        intento hostil no consume el `state` del navegador que sí inició el
        flujo. La caducidad se comprueba aquí sin borrar (el purgado sigue
        siendo de `put_challenge`/`take_challenge`); el consumo sigue siendo
        `take_challenge`, de un solo uso.
        """
        if not isinstance(raw, str) or not raw:
            return None
        now = int(time.time() if now is None else now)
        with self.lock:
            row = self.db.execute(
                "SELECT * FROM auth_challenges WHERE challenge_hash=?",
                (token_digest(raw),)).fetchone()
            if not row or row["purpose"] != purpose or row["expires_at"] <= now:
                return None
            return row["user_id"], bytes(row["detail"])

    def take_challenge(self, purpose, raw, now=None):
        """Consume un reto: una sola vez y solo si no ha caducado.

        Devuelve `(user_id, detail)` o `None` cuando no existe, pertenece a
        otro propósito o ya caducó (y en ese caso retira la fila).
        """
        if not isinstance(raw, str) or not raw:
            return None
        now = int(time.time() if now is None else now)
        with self.lock, self.db:
            self._purge_challenges(now)
            row = self.db.execute(
                "SELECT * FROM auth_challenges WHERE challenge_hash=?",
                (token_digest(raw),)).fetchone()
            if not row or row["purpose"] != purpose:
                return None
            self.db.execute("DELETE FROM auth_challenges WHERE challenge_hash=?", (row["challenge_hash"],))
            return row["user_id"], bytes(row["detail"])

    # ---------------------------------------------------------------------
    # Passkeys (FR-AUTH-004)
    # ---------------------------------------------------------------------

    def passkeys(self, user_id):
        """Passkeys de una cuenta: id, etiqueta y fecha; nunca la clave pública."""
        with self.lock:
            rows = self.db.execute(
                "SELECT credential_id,label,created_at FROM passkeys WHERE user_id=? "
                "ORDER BY created_at DESC, credential_id", (user_id,)).fetchall()
            return [{"id": row["credential_id"], "label": row["label"],
                     "created_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(row["created_at"]))}
                    for row in rows]

    def passkey(self, credential_id):
        """Fila completa de una passkey o `None`; la llama el login sin sesión."""
        if not isinstance(credential_id, str) or not credential_id:
            return None
        with self.lock:
            row = self.db.execute(
                "SELECT * FROM passkeys WHERE credential_id=?", (credential_id,)).fetchone()
            return dict(row) if row else None

    def add_passkey(self, user_id, credential_id, public_key, sign_count, transports, label):
        """Registra una passkey ya verificada por la librería."""
        with self.lock, self.db:
            count = self.db.execute(
                "SELECT COUNT(*) FROM passkeys WHERE user_id=?", (user_id,)).fetchone()[0]
            if count >= PASSKEY_LIMIT:
                raise AppError(409, f"Ya tienes {PASSKEY_LIMIT} passkeys. Borra alguna antes de añadir otra.")
            try:
                self.db.execute(
                    "INSERT INTO passkeys VALUES (?,?,?,?,?,?,?)",
                    (credential_id, user_id, public_key, int(sign_count),
                     json.dumps(list(transports or [])), text(label, 40), int(time.time())))
            except sqlite3.IntegrityError:
                raise AppError(409, "Esa passkey ya está registrada.") from None

    def set_sign_count(self, credential_id, sign_count):
        """Avanza el contador solo hacia adelante (la librería ya rechaza retrocesos)."""
        with self.lock, self.db:
            self.db.execute(
                "UPDATE passkeys SET sign_count=? WHERE credential_id=? AND sign_count<?",
                (int(sign_count), credential_id, int(sign_count)))

    def delete_passkey(self, user_id, credential_id):
        """Borra la passkey **del propio usuario**; `False` si no era suya."""
        if not isinstance(credential_id, str) or not credential_id:
            return False
        with self.lock, self.db:
            cursor = self.db.execute(
                "DELETE FROM passkeys WHERE credential_id=? AND user_id=?",
                (credential_id, user_id))
            return cursor.rowcount > 0

    # ---------------------------------------------------------------------
    # Identidades externas: Google (FR-AUTH-005)
    # ---------------------------------------------------------------------

    def identities(self, user_id):
        """Identidades externas vinculadas a la cuenta, sin `sub` ni email ajeno."""
        with self.lock:
            rows = self.db.execute(
                "SELECT provider,created_at FROM identities WHERE user_id=? ORDER BY provider",
                (user_id,)).fetchall()
            return [{"provider": row["provider"],
                     "created_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(row["created_at"]))}
                    for row in rows]

    def identity_user(self, provider, issuer, sub):
        """Titular de una identidad externa; `None` si no está vinculada."""
        with self.lock:
            row = self.db.execute(
                "SELECT user_id FROM identities WHERE provider=? AND issuer=? AND sub=?",
                (provider, issuer, sub)).fetchone()
            return row["user_id"] if row else None

    def link_identity(self, user_id, provider, issuer, sub, email=None,
                      require_verified=False):
        """Vincula una identidad externa; nunca de forma implícita ni con merge.

        Con `require_verified=True` el titular debe seguir existiendo **y** con
        email verificado en el momento exacto del escritura, dentro de esta misma
        transacción bajo `self.lock`: es el gate atómico que impide que un
        `logout` —o cualquier pérdida de verificación— situado entre la
        comprobación de sesión y el INSERT llegue a escribir el vínculo. Un
        usuario desaparecido o desverificado recibe el mismo `AppError` que
        `user()` (401), sin dejar fila.
        """
        with self.lock, self.db:
            if require_verified:
                row = self.db.execute(
                    "SELECT email_verified_at FROM users WHERE id=?", (user_id,)).fetchone()
                if not row or not row["email_verified_at"]:
                    raise AppError(401, "La sesión ya no es válida. Vuelve a acceder.")
            owner = self.identity_user(provider, issuer, sub)
            if owner is not None and owner != user_id:
                raise AppError(409, "Esa cuenta de Google ya está vinculada a otra persona de esta instancia.")
            if owner == user_id:
                raise AppError(409, "Esa cuenta de Google ya está vinculada a tu cuenta.")
            existing = self.db.execute(
                "SELECT id FROM identities WHERE user_id=? AND provider=?",
                (user_id, provider)).fetchone()
            if existing:
                raise AppError(409, "Ya tienes una cuenta de Google vinculada. Desvincula la actual antes de añadir otra.")
            try:
                self.db.execute(
                    "INSERT INTO identities VALUES (?,?,?,?,?,?,?)",
                    (secrets.token_urlsafe(18), user_id, provider, issuer, sub,
                     email, int(time.time())))
            except sqlite3.IntegrityError:
                raise AppError(409, "Esa cuenta de Google ya está vinculada a otra persona de esta instancia.") from None

    def unlink_identity(self, user_id, provider):
        """Desvincula sin borrar la cuenta ni sus carnés; `False` si no había."""
        with self.lock, self.db:
            cursor = self.db.execute(
                "DELETE FROM identities WHERE user_id=? AND provider=?", (user_id, provider))
            return cursor.rowcount > 0

    @staticmethod
    def _alias_candidates(email, issuer, sub):
        """Alias públicos deterministas y únicos derivados del email y del `sub`.

        Base: la parte local del email saneada al formato de usuario; si está
        ocupada, sufijo determinista de la identidad (`sub`), y como último
        recurso un identificador derivado del `sub`. Nunca parte del `sub` se
        expone como alias legible.
        """
        digest = hashlib.sha256((issuer + "\0" + sub).encode()).hexdigest()
        local = re.sub(r"[^a-z0-9_.-]", "", email.split("@", 1)[0].lower()).strip("._-")
        valid = lambda value: bool(re.fullmatch(r"[a-z0-9][a-z0-9_.-]{2,39}", value))
        candidates = []
        if valid(local):
            candidates.append(local)
        suffix = digest[:7]
        stem = local[:40 - len(suffix) - 1]
        if stem and valid(f"{stem}-{suffix}"):
            candidates.append(f"{stem}-{suffix}")
        fallback = "g" + digest[:15]
        candidates.append(fallback)
        for number in range(2, 20):
            candidates.append(fallback[:32] + str(number))
        return candidates

    def register_with_identity(self, name, email, password, provider, issuer, sub):
        """Alta explícita con Google: email verificado por el proveedor.

        No es un merge: si el email ya pertenece a otra cuenta se rechaza y
        queda en manos de esa cuenta vincular desde su sesión. La contraseña es
        aleatoria (nadie la conoce); quien quiera una puede fijarla con la
        recuperación por el email verificado.
        """
        email = normalize_email(email)
        name = text(name, 80)
        if not isinstance(password, str) or not 10 <= len(password) <= 200:
            raise AppError(400, "La contraseña de BiblioCM debe tener entre 10 y 200 caracteres.")
        salt = secrets.token_bytes(16)
        hashed = password_hash(password, salt)
        verified_at = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
        with self.lock, self.db:
            taken = self.db.execute(
                "SELECT id FROM users WHERE email=?", (email,)).fetchone()
            if taken:
                raise AppError(409, "Ya existe una cuenta de BiblioCM con ese email. "
                                    "Entra con ella y vincula Google desde Configuración.")
            for username in self._alias_candidates(email, issuer, sub):
                user_id = secrets.token_urlsafe(18)
                try:
                    self.db.execute(
                        "INSERT INTO users (id,username,name,salt,password_hash,email,email_verified_at) "
                        "VALUES (?,?,?,?,?,?,?)",
                        (user_id, username, name, salt, hashed, email, verified_at))
                    # Vincular en la misma transacción: si la identidad no cabe
                    # (ya asignada a otra cuenta), el alta entera se revierte.
                    self.db.execute(
                        "INSERT INTO identities VALUES (?,?,?,?,?,?,?)",
                        (secrets.token_urlsafe(18), user_id, provider, issuer, sub,
                         email, int(time.time())))
                except sqlite3.IntegrityError as exc:
                    conflict = str(exc)
                    if "identities." in conflict:
                        raise AppError(409, "Esa cuenta de Google ya está vinculada a otra persona "
                                            "de esta instancia.") from None
                    if "users.email" in conflict:
                        raise AppError(409, "Ya existe una cuenta de BiblioCM con ese email. "
                                            "Entra con ella y vincula Google desde Configuración.") from None
                    if "users.username" in conflict:
                        # Alias ocupado por una cuenta local: siguiente candidato.
                        continue
                    raise
                return self.user(user_id)
            raise AppError(409, "No se pudo crear la cuenta con Google. Inténtalo de nuevo.")

    def change_password(self, user_id, current, new):
        """Cambia la contraseña de la sesión vigente; no toca cifrado ni vínculos.

        Verificar la contraseña actual y escribir la nueva ocurre en la **misma**
        sección crítica (lock + transacción): si la verificación se hiciera
        soltando el lock antes de escribir, dos cambios concurrentes —o un cambio
        y un reset— podrían ambos verificar contra la contraseña vieja y
        pisarse (revisión independiente). El coste es mantener el lock del store
        durante los dos scrypt (~100 ms) solo en esta operación rara.
        """
        if not isinstance(current, str) or not 1 <= len(current) <= 200:
            raise AppError(401, "La contraseña actual no es correcta.")
        if not isinstance(new, str) or not 10 <= len(new) <= 200:
            raise AppError(400, "La contraseña de BiblioCM debe tener entre 10 y 200 caracteres.")
        if secrets.compare_digest(current, new):
            raise AppError(400, "La nueva contraseña debe ser distinta de la actual.")
        with self.lock, self.db:
            row = self.db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
            if not row or not secrets.compare_digest(password_hash(current, row["salt"]),
                                                     row["password_hash"]):
                raise AppError(401, "La contraseña actual no es correcta.")
            salt = secrets.token_bytes(16)
            self.db.execute("UPDATE users SET salt=?,password_hash=? WHERE id=?",
                            (salt, password_hash(new, salt), user_id))

    def reset_token(self, email, now=None):
        """Código de recuperación si el email existe verificado; `None` si no.

        La capa web responde igual en ambos casos (anti-enumeración) y solo
        envía correo cuando hay código.
        """
        email = normalize_email(email)
        now = int(time.time() if now is None else now)
        with self.lock, self.db:
            row = self.db.execute(
                "SELECT id FROM users WHERE email=? AND email_verified_at IS NOT NULL",
                (email,)).fetchone()
            if not row:
                return None
            raw = secrets.token_urlsafe(32)
            self._insert_token(row["id"], "password_reset", "", raw, now, RESET_TTL)
            return raw

    def reset_password(self, raw, new, now=None):
        """Fija la contraseña con un código de recuperación de un solo uso."""
        now = int(time.time() if now is None else now)
        if not isinstance(new, str) or not 10 <= len(new) <= 200:
            raise AppError(400, "La contraseña de BiblioCM debe tener entre 10 y 200 caracteres.")
        if not isinstance(raw, str) or not raw:
            raise AppError(400, "El código no es válido o ha caducado. Pide uno nuevo.")
        digest = token_digest(raw)
        with self.lock, self.db:
            row = self.db.execute(
                "SELECT * FROM identity_tokens WHERE token_hash=? AND purpose='password_reset'",
                (digest,)).fetchone()
            if not row or row["expires_at"] <= now:
                if row:
                    self.db.execute("DELETE FROM identity_tokens WHERE token_hash=?", (digest,))
                raise AppError(400, "El código no es válido o ha caducado. Pide uno nuevo.")
            self.db.execute("DELETE FROM identity_tokens WHERE token_hash=?", (digest,))
            salt = secrets.token_bytes(16)
            self.db.execute("UPDATE users SET salt=?,password_hash=? WHERE id=?",
                            (salt, password_hash(new, salt), row["user_id"]))
            return row["user_id"]

    def add_account(self, user_id, label, card, password):
        account_id = secrets.token_urlsafe(18)
        encrypted = self.cipher.encrypt(json.dumps({"card": card, "password": password}).encode())
        digest = hashlib.sha256(card.encode()).hexdigest()
        with self.lock, self.db:
            try:
                self.db.execute("INSERT INTO accounts VALUES (?,?,?,?,?)", (account_id, user_id, label, digest, encrypted))
            except sqlite3.IntegrityError:
                raise AppError(409, "Este carné ya está vinculado. Solicita acceso a su titular en BiblioCM.") from None
        return account_id

    def accessible_accounts(self, user_id):
        with self.lock:
            rows = self.db.execute("""
                SELECT a.id,a.owner_id,a.label,u.username,u.name,
                    CASE WHEN a.owner_id=? THEN 'manage' ELSE l.permission END AS permission
                FROM accounts a JOIN users u ON u.id=a.owner_id
                LEFT JOIN links l ON l.owner_id=a.owner_id AND l.requester_id=? AND l.status='approved'
                WHERE a.owner_id=? OR l.id IS NOT NULL
                ORDER BY CASE WHEN a.owner_id=? THEN 0 ELSE 1 END,a.label,a.id
            """, (user_id, user_id, user_id, user_id)).fetchall()
            return [dict(row, own=row["owner_id"] == user_id) for row in rows]

    def access(self, user_id, account_id, manage=False):
        account_id = text(account_id, 100)
        account = next((a for a in self.accessible_accounts(user_id) if a["id"] == account_id), None)
        if not account:
            raise AppError(403, "No tienes acceso a esta cuenta de biblioteca.")
        if manage and account["permission"] != "manage":
            raise AppError(403, "Esta autorización es de solo lectura.")
        return account

    def credentials(self, account_id):
        # Internal only: callers must authorize before decrypting.
        with self.lock:
            row = self.db.execute("SELECT credentials FROM accounts WHERE id=?", (account_id,)).fetchone()
            if not row:
                raise AppError(404, "Cuenta no encontrada.")
            return json.loads(self.cipher.decrypt(row["credentials"]))

    def update_account(self, user_id, account_id, label, card, password):
        encrypted = self.cipher.encrypt(json.dumps({"card": card, "password": password}).encode())
        with self.lock, self.db:
            self.require_owner(user_id, account_id)
            old = self.credentials(account_id)
            if card != old["card"]:
                raise AppError(400, "Para cambiar de carné, elimina la cuenta y vincula la nueva.")
            self.db.execute("UPDATE accounts SET label=?,credentials=? WHERE id=?", (label, encrypted, account_id))

    def require_owner(self, user_id, account_id):
        account = self.access(user_id, account_id)
        if not account["own"]:
            raise AppError(403, "Solo el titular puede modificar las credenciales vinculadas.")

    def delete_account(self, user_id, account_id):
        with self.lock, self.db:
            self.require_owner(user_id, account_id)
            self.db.execute("DELETE FROM accounts WHERE id=?", (account_id,))

    def request_link(self, user_id, username, requested_permission):
        username = text(username, 40).lower()
        permission(requested_permission)
        with self.lock, self.db:
            owner = self.db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
            if not owner:
                raise AppError(404, "No se encontró ese usuario de BiblioCM.")
            if owner["id"] == user_id:
                raise AppError(400, "Tus propias cuentas ya están disponibles en tu panel.")
            existing = self.db.execute("SELECT * FROM links WHERE owner_id=? AND requester_id=?", (owner["id"], user_id)).fetchone()
            if existing and existing["status"] in ("pending", "approved"):
                raise AppError(409, "Ya tienes una solicitud pendiente o acceso a este usuario.")
            link_id = existing["id"] if existing else secrets.token_urlsafe(18)
            if existing:
                self.db.execute("UPDATE links SET status='pending',permission=? WHERE id=?", (requested_permission, link_id))
            else:
                self.db.execute("INSERT INTO links VALUES (?,?,?,?,?)", (link_id, owner["id"], user_id, requested_permission, "pending"))
            return link_id

    def decide_link(self, user_id, link_id, action, granted_permission=None):
        with self.lock, self.db:
            row = self.db.execute("SELECT * FROM links WHERE id=?", (text(link_id, 100),)).fetchone()
            if not row or user_id not in (row["owner_id"], row["requester_id"]):
                raise AppError(403, "No puedes modificar esta solicitud.")
            if action == "approve":
                if user_id != row["owner_id"]:
                    raise AppError(403, "Solo el titular puede aprobar la solicitud.")
                if row["status"] != "pending":
                    raise AppError(409, "La solicitud ya no está pendiente.")
                granted_permission = permission(granted_permission)
                status = "approved"
            elif action == "reject":
                if user_id != row["owner_id"]:
                    raise AppError(403, "Solo el titular puede rechazar la solicitud.")
                if row["status"] != "pending":
                    raise AppError(409, "La solicitud ya no está pendiente.")
                status = "rejected"
            elif action == "revoke":
                if row["status"] not in ("pending", "approved"):
                    raise AppError(409, "La autorización ya está cerrada.")
                status = "revoked"
            elif action == "permission":
                if user_id != row["owner_id"]:
                    raise AppError(403, "Solo el titular puede cambiar los permisos.")
                if row["status"] != "approved":
                    raise AppError(409, "Esta autorización no está activa.")
                granted_permission = permission(granted_permission)
                status = "approved"
            else:
                raise AppError(400, "Decisión no válida.")
            self.db.execute("UPDATE links SET status=?,permission=? WHERE id=?", (status, granted_permission or row["permission"], link_id))

    def link_requester(self, link_id):
        """`requester_id` de un enlace: titular del permiso que puede cambiar.

        La capa web lo usa para entrar en la puerta de operaciones de ese
        usuario antes de aplicar una revocación o bajada (FR-LINK-002).
        Devuelve `None` si el enlace no existe; quien decide sigue recibiendo
        desde `decide_link` el mismo 403 de siempre.
        """
        with self.lock:
            row = self.db.execute("SELECT requester_id FROM links WHERE id=?",
                                  (text(link_id, 100),)).fetchone()
            return row["requester_id"] if row else None

    def settings(self, user_id):
        with self.lock:
            links = self.db.execute("""
                SELECT l.id,l.owner_id,l.requester_id,l.permission,l.status,
                    o.username AS owner_username,o.name AS owner_name,
                    r.username AS requester_username,r.name AS requester_name
                FROM links l JOIN users o ON o.id=l.owner_id JOIN users r ON r.id=l.requester_id
                WHERE l.owner_id=? OR l.requester_id=? ORDER BY l.rowid DESC
            """, (user_id, user_id)).fetchall()
            accounts = self.accessible_accounts(user_id)
            for account in accounts:
                if account["own"]:
                    card = self.credentials(account["id"])["card"]
                    account["masked_card"] = "••••" + card[-4:]
            return {"user": self.user(user_id), "accounts": accounts,
                    "incoming": [dict(l) for l in links if l["owner_id"] == user_id],
                    "outgoing": [dict(l) for l in links if l["requester_id"] == user_id],
                    "passkeys": self.passkeys(user_id),
                    "identities": self.identities(user_id)}
