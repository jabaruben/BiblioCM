"""Autenticador WebAuthn sintético solo para pruebas (sin hardware ni credenciales reales).

Construye exactamente lo que entregaría un navegador real: `clientDataJSON`, un
`attestationObject` CBOR con formato `none`, `authenticatorData` y una firma
ECDSA P-256 sobre `authenticatorData || SHA-256(clientDataJSON)`. La criptografía
de **producto** no está aquí: la verificación sigue siendo la de la librería
`webauthn` en el servidor; esto es el lado del dispositivo simulado, igual que el
OPAC falso del resto de la suite.
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets

import cbor2
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

FLAG_UP = 0x01
FLAG_UV = 0x04
FLAG_AT = 0x40


def b64u(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


class FakeAuthenticator:
    """Passkey virtual: una clave P-256, un ID de credencial y un contador."""

    def __init__(self, rp_id, origin, uv=True):
        self.rp_id = rp_id
        self.origin = origin
        self.uv = uv
        self.private_key = ec.generate_private_key(ec.SECP256R1())
        self.credential_id = secrets.token_bytes(32)
        self.sign_count = 0

    def _client_data(self, kind, challenge):
        return json.dumps({"type": kind, "challenge": challenge, "origin": self.origin,
                           "crossOrigin": False}, separators=(",", ":")).encode()

    def registration(self, challenge):
        """Credencial de creación (`navigator.credentials.create`)."""
        client_data = self._client_data("webauthn.create", challenge)
        rp_hash = hashlib.sha256(self.rp_id.encode()).digest()
        flags = FLAG_UP | FLAG_AT | (FLAG_UV if self.uv else 0)
        numbers = self.private_key.public_key().public_numbers()
        cose = cbor2.dumps({1: 2, 3: -7, -1: 1,
                            -2: numbers.x.to_bytes(32, "big"),
                            -3: numbers.y.to_bytes(32, "big")})
        attested = (b"\x00" * 16 + len(self.credential_id).to_bytes(2, "big")
                    + self.credential_id + cose)
        auth_data = rp_hash + bytes([flags]) + self.sign_count.to_bytes(4, "big") + attested
        attestation = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})
        return {"id": b64u(self.credential_id), "rawId": b64u(self.credential_id),
                "type": "public-key",
                "response": {"clientDataJSON": b64u(client_data),
                             "attestationObject": b64u(attestation),
                             "transports": ["internal"]}}

    def authentication(self, challenge, user_handle=None, increment=True):
        """Asertión de autenticación (`navigator.credentials.get`)."""
        client_data = self._client_data("webauthn.get", challenge)
        rp_hash = hashlib.sha256(self.rp_id.encode()).digest()
        if increment:
            self.sign_count += 1
        flags = FLAG_UP | (FLAG_UV if self.uv else 0)
        auth_data = rp_hash + bytes([flags]) + self.sign_count.to_bytes(4, "big")
        signature = self.private_key.sign(auth_data + hashlib.sha256(client_data).digest(),
                                          ec.ECDSA(hashes.SHA256()))
        return {"id": b64u(self.credential_id), "rawId": b64u(self.credential_id),
                "type": "public-key",
                "response": {"clientDataJSON": b64u(client_data),
                             "authenticatorData": b64u(auth_data),
                             "signature": b64u(signature),
                             "userHandle": b64u(user_handle) if user_handle else None}}
