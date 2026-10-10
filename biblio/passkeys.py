"""Passkeys WebAuthn con la librería mantenida `webauthn` (FR-AUTH-004).

El servidor nunca confía en los datos del navegador: `Origin`, RP ID, firma,
flags (UP/UV) y contador los verifica la librería contra el challenge que emitió
y que solo puede usarse una vez y dentro de su caducidad (`Store.take_challenge`).
La criptografía WebAuthn no está escrita a mano; este módulo solo traduce tipos,
codificación base64url y errores de la librería al envelope del API.

Origen de confianza (NFR-SVC-003): el RP ID y el origen esperado salen del
origen **canónico del pedido** validado contra la lista de confianza del
servidor (`origins.TrustedOrigins`): local por defecto, público solo si está en
`BIBLIO_TRUSTED_ORIGINS`. Un Host arbitrario queda fuera (403) incluso sobre
TLS, y un Host no canónico responde 400 antes de mirar el cuerpo.
"""
from __future__ import annotations

import base64
import json

from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url, options_to_json
from webauthn.helpers.exceptions import WebAuthnException
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from . import origins
from .store import AppError, CHALLENGE_TTL

RP_NAME = "BiblioCM"
INVALID = "La passkey no es válida o ha caducado. Inténtalo de nuevo."


def base64url_decode(value):
    """Decodifica base64url con o sin relleno (solo codificación, no cripto)."""
    if not isinstance(value, str):
        raise AppError(400, INVALID)
    padding = "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode(value + padding)
    except Exception:
        raise AppError(400, INVALID) from None


def base64url_encode(value):
    """Codifica bytes como base64url sin relleno (identificador de credencial)."""
    return bytes_to_base64url(value)


def rp_context(host_header, secure, trusted):
    """`(rp_id, origin)` del pedido con el origen en la lista de confianza.

    El origen esperado es el canónico del pedido (esquema + Host parseado de
    forma estricta) y solo se acepta si `trusted` lo incluye: local por
    defecto, público solo con `BIBLIO_TRUSTED_ORIGINS`. El RP ID es el
    hostname de ese origen. Un Host arbitrario —incluso sobre TLS— queda fuera
    (403); un Host que no es una autoridad canónica responde 400, y un origen
    confiable con hostname sin forma de dominio (IPv6) también se rechaza.
    """
    scheme = "https" if secure else "http"
    origin = origins.canonical_origin(scheme, host_header)
    if origin is None:
        raise AppError(400, INVALID)
    if not trusted.trusted(origin):
        raise AppError(403, "Las passkeys solo están disponibles en un origen de "
                            "confianza: http://127.0.0.1, localhost o un HTTPS "
                            "configurado en BIBLIO_TRUSTED_ORIGINS.")
    hostname = origins.host_of(origin)
    if not origins.HOSTNAME_RE.fullmatch(hostname):
        raise AppError(403, "Las passkeys solo están disponibles en un origen de "
                            "confianza: http://127.0.0.1, localhost o un HTTPS "
                            "configurado en BIBLIO_TRUSTED_ORIGINS.")
    return hostname, origin


def registration_options(rp_id, user, credentials):
    """Opciones de registro con UV obligatorio y credencial descubrible.

    `credentials` son las passkeys ya registradas: se excluyen para que el
    navegador no permita registrar dos veces la misma llave.
    """
    existing = [PublicKeyCredentialDescriptor(id=base64url_to_bytes(row["id"]))
                for row in credentials]
    options = generate_registration_options(
        rp_id=rp_id,
        rp_name=RP_NAME,
        user_name=user["username"],
        user_id=user["id"].encode("utf-8"),
        user_display_name=user["name"],
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        exclude_credentials=existing,
        timeout=CHALLENGE_TTL * 1000,
    )
    public_key = json.loads(options_to_json(options))
    return public_key, options.challenge


def authentication_options(rp_id):
    """Opciones de login descubrible: sin `allowCredentials`, sin enumerar usuarios."""
    options = generate_authentication_options(
        rp_id=rp_id,
        user_verification=UserVerificationRequirement.REQUIRED,
        timeout=CHALLENGE_TTL * 1000,
    )
    return json.loads(options_to_json(options)), options.challenge


def client_challenge(payload):
    """Reto devuelto por el navegador en `clientDataJSON` (solo codificación)."""
    response = payload.get("response") if isinstance(payload, dict) else None
    if not isinstance(response, dict):
        raise AppError(400, INVALID)
    data = json.loads(base64url_decode(response.get("clientDataJSON")))
    if not isinstance(data, dict) or not isinstance(data.get("challenge"), str) or not data["challenge"]:
        raise AppError(400, INVALID)
    return data["challenge"]


def _translate(error):
    """Error de la librería al envelope del API sin filtrar motivos internos."""
    return AppError(400, INVALID) if isinstance(error, WebAuthnException) else AppError(400, INVALID)


def verify_registration(rp_id, origin, challenge, payload):
    try:
        return verify_registration_response(
            credential=payload,
            expected_challenge=challenge,
            expected_rp_id=rp_id,
            expected_origin=origin,
            require_user_verification=True,
        )
    except (WebAuthnException, ValueError, TypeError, KeyError) as exc:
        raise _translate(exc) from None


def verify_authentication(rp_id, origin, challenge, payload, public_key, sign_count):
    try:
        return verify_authentication_response(
            credential=payload,
            expected_challenge=challenge,
            expected_rp_id=rp_id,
            expected_origin=origin,
            credential_public_key=public_key,
            credential_current_sign_count=sign_count,
            require_user_verification=True,
        )
    except (WebAuthnException, ValueError, TypeError, KeyError) as exc:
        raise _translate(exc) from None
