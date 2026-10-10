"""Modelos de datos del dominio biblioteca."""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from enum import Enum

# `tititu` llega como "título / autor". El autor puede venir vacío ("título /"),
# así que el separador tiene que tolerar esa barra final suelta.
_TITLE_SPLIT = re.compile(r"\s+/\s*")


class RenewalState(str, Enum):
    """Estado de renovación, tal y como lo renderiza el OPAC.

    OJO: `RENOVABLE_FROM_A_DATE` no es renovable todavía. Confundirlos renewal
    fallaría con "No se puede renovar" o, peor, wasting un intento.
    """

    RENEWABLE = "renovable"
    RENEWABLE_FROM_DATE = "renovable_desde"
    LIMIT_REACHED = "limite_alcanzado"
    NOT_RENEWABLE = "no_renovable"
    OVERDUE = "prestado_con_retraso"
    READER_EXPIRED = "lector_caducado"
    READER_SUSPENDED = "lector_suspendido"
    UNKNOWN = "desconocido"

    @property
    def can_renew(self) -> bool:
        return self is RenewalState.RENEWABLE


@dataclass(frozen=True)
class Reader:
    card: str
    name: str
    suspended: bool
    expired: bool
    card_expires: dt.date | None


@dataclass
class Loan:
    barcode: str
    title: str
    library: str
    branch_address: str
    due: dt.datetime
    due_date: dt.date
    days_left: int
    renewals_used: int
    renewals_max: int
    renew_window_days: int
    pending_holds: int
    renewal_state: RenewalState
    renewal_available_from: dt.date | None
    branch_code: str = ""
    signature: str = ""
    # `TITN` del enlace de ficha del préstamo; vacío si el portal no lo da.
    # Es la identidad bibliográfica con la que se atribuye la portada: nunca se
    # deduce del título.
    record_id: str = ""

    @property
    def overdue(self) -> bool:
        return self.days_left < 0

    @property
    def due_soon(self) -> bool:
        return 0 <= self.days_left <= 3

    @property
    def author(self) -> str:
        """Absys mete "título / autor" en el mismo campo (`tititu`)."""
        parts = _TITLE_SPLIT.split(self.title, maxsplit=1)
        return parts[1].strip() if len(parts) > 1 else ""

    @property
    def clean_title(self) -> str:
        parts = _TITLE_SPLIT.split(self.title, maxsplit=1)
        return parts[0].strip()


@dataclass
class Reservation:
    """Ojo: a diferencia de los préstamos, las reservas NO traen bloque JSON.

    Se parsean del HTML renderizado (etiquetas estables + `data-di`).
    """

    reservation_id: str
    title: str
    record_id: str
    state: str
    expires: dt.date | None
    created: dt.datetime | None
    signature: str
    branch: str
    branch_code: str


@dataclass
class MarcRecord:
    record_id: str
    title: str = ""
    author: str = ""
    publication: str = ""
    year: str = ""
    language: str = ""
    isbn: str = ""
    classification: str = ""
    extent: str = ""
    summary: str = ""
    subjects: list[str] = field(default_factory=list)
    cover_url: str = ""
    openurl: dict[str, str] = field(default_factory=dict)
    doc_type: str = ""
    raw_marc: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class Copy:
    barcode: str
    signature: str
    library: str
    branch: str
    location: str
    copy_type: str
    availability: str
    support: str = ""
    expected: dt.date | None = None

    @property
    def available_now(self) -> bool:
        """Cuidado: "Disponible después de 24/10/2026" **no** está disponible hoy.

        Es la diferencia entre "puedes ir a por él" y "vuelve a mirarlo el 24/10".
        """
        return self.availability.strip().lower() == "disponible"


@dataclass
class Library:
    reader: Reader
    loans: list[Loan]
    reservations: list[Reservation]