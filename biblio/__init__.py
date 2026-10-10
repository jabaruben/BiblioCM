"""Motor de gestión de préstamos de las Bibliotecas de la Comunidad de Madrid.

Ver `docs/absys-opac-protocol.md` para el protocolo inversionado.
"""

from .client import AbsysClient, AuthError, OperationRefused, SessionExpired
from .http import Http
from .models import (
    Copy,
    Library,
    Loan,
    MarcRecord,
    Reader,
    RenewalState,
    Reservation,
)

__all__ = [
    "AbsysClient",
    "AuthError",
    "OperationRefused",
    "SessionExpired",
    "Http",
    "Copy",
    "Library",
    "Loan",
    "MarcRecord",
    "Reader",
    "RenewalState",
    "Reservation",
]