"""Cliente del OPAC: sesión, autenticación y operaciones.

Dos reglas que gobiernan todo este fichero:

1. **Nunca hardcodear una URL.** El token de sesión vive en el path y *cambia en
   cada navegación*. Se sigue siempre el `href`/`action` que devuelve la página
   anterior, o `#varJSONmain #cgi`.
2. **Los códigos ACC se leen de `#varJSONmain`.** Si el proveedor los cambia,
   el cliente los sigue sin tocar código.
"""

from __future__ import annotations

import datetime as dt
import urllib.parse
from dataclasses import dataclass
from typing import Any

from . import parser
from .http import Http, HttpError, Response, decoded_path, has_unsafe_path, has_unsafe_url_chars, origin
from .models import (
    Copy,
    Library,
    Loan,
    MarcRecord,
    RenewalState,
    Reservation,
)

RENEWAL_LABEL = {
    RenewalState.RENEWABLE: "ya se puede renovar",
    RenewalState.RENEWABLE_FROM_DATE: "todavía no se puede renovar",
    RenewalState.LIMIT_REACHED: "límite de renovaciones alcanzado",
    RenewalState.NOT_RENEWABLE: "no se puede renovar",
    RenewalState.OVERDUE: "tiene préstamos sobrepasados",
    RenewalState.READER_EXPIRED: "carné caducado",
    RenewalState.READER_SUSPENDED: "lector suspendido",
    RenewalState.UNKNOWN: "estado desconocido",
}

BASE_URL = "https://gestiona3.madrid.org/biblio_publicas/"
OPAC = "cgi-bin/abnetopac"

ACC_LOGIN = "201"
ACC_LIBRARY = "210"
ACC_HOME = "101"
ACC_LOGOUT = "301"
ACC_RECORD = "165"
ACC_PAGE = "161"


def is_portal_url(url: str, base_url: str = BASE_URL) -> bool:
    """¿Es una URL http(s) del CGI del OPAC en el origen de `base_url`?

    Es la única puerta de salida para descargar portadas: esquema, host, puerto
    y prefijo del CGI proceden de constantes del cliente, nunca del dato que
    llega del HTML. Además del origen, se descartan userinfo y puertos
    malformados, caracteres de control, dot segments en crudo o codificados y
    separadores percent-codificados, para que una URL forjada no se convierta
    ni en un proxy abierto ni en una petición a otra ruta del mismo host.
    """
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return False
    if has_unsafe_url_chars(url):
        return False
    page_origin = origin(url)
    if not page_origin or page_origin != origin(base_url):
        return False
    if has_unsafe_path(url):
        return False
    cgi = urllib.parse.urlsplit(urllib.parse.urljoin(base_url, OPAC))
    for candidate in (parts.path, decoded_path(parts.path)):
        if candidate != cgi.path and not candidate.startswith(cgi.path + "/"):
            return False
    return True


class AuthError(RuntimeError):
    pass


class SessionExpired(AuthError):
    pass


class OperationRefused(RuntimeError):
    """El servidor respondió con un error funcional (no renovable, sin plaza...)."""

    def __init__(self, message: str, response: Response | None = None):
        super().__init__(message)
        self.response = response


@dataclass(frozen=True)
class RenewResult:
    ok: bool
    message: str
    previous_due: dt.date
    new_due: dt.date
    renewals_used: int
    renewals_max: int


class AbsysClient:
    """Un cliente = una cuenta.

    Cada instancia mantiene su propio hilo de sesión, así que varias cuentas
    pueden convivir sin interferir: es el modo multicuenta.
    """

    def __init__(
        self,
        card: str,
        password: str,
        base_url: str = BASE_URL,
        http: Http | None = None,
    ):
        self.card = card
        self._password = password
        self.base_url = base_url
        self.http = http or Http()
        self._base: str = ""
        self._acc: dict[str, str] = {}

    # -- infraestructura -------------------------------------------------
    @property
    def logged_in(self) -> bool:
        return bool(self._base)

    def _opac_url(self) -> str:
        return urllib.parse.urljoin(self.base_url, OPAC)

    def _split(self, url: str) -> tuple[str, str]:
        parts = urllib.parse.urlsplit(url)
        return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, "", "")), parts.query

    def _refresh(self, response: Response) -> None:
        """Adopta el hilo de sesión que el servidor acaba de servir."""
        base, _ = self._split(response.url)
        self._base = base
        acc = parser.varjson(response.text)
        if acc:
            self._acc = acc

    def _acc_code(self, name: str, fallback: str) -> str:
        return self._acc.get(name) or fallback

    def _get(self, url: str, refresh: bool = True) -> Response:
        response = self.http.get(url)
        if refresh and "abnetopac" in response.url:
            self._refresh(response)
        return response

    def _auth_get(self, acc: str) -> Response:
        """GET autenticado con re-login automático si la sesión caducó."""
        if not self._base:
            self.login()
        base, _ = self._split(self._base)
        response = self._get(f"{base}?ACC={acc}")
        if self._looks_expired(response):
            self.login()
            base, _ = self._split(self._base)
            response = self._get(f"{base}?ACC={acc}")
            if self._looks_expired(response):
                raise SessionExpired("no se pudo recuperar la sesión")
        return response

    @staticmethod
    def _looks_expired(response: Response) -> bool:
        if parser.is_expired(response.text, response.url):
            return True
        # Si pedimos el área de usuario y no aparece el nombre del lector,
        # la sesión se ha perdido.
        return False

    def _auth_post(self, fields: dict[str, str], extra_acc: str | None = None) -> Response:
        if not self._base:
            self.login()
        base, _ = self._split(self._base)
        target = self._acc.get("cgi") or ""
        cgi = urllib.parse.urljoin(base, target) if target else base
        payload = dict(fields)
        if extra_acc:
            payload["ACC"] = extra_acc
        response = self.http.post(cgi, payload)
        self._refresh(response)
        return response

    # -- autenticación ---------------------------------------------------
    def login(self) -> None:
        """Abre un hilo invitado, valida el carné y adopta el hilo autenticado.

        Clave: al validar bien, el servidor **minta un token distinto** para la
        sesión autenticada. Hay que descubrirlo en los enlaces de la respuesta.
        """
        self._base = ""
        self._acc = {}

        home = self.http.get(self.base_url)
        root = parser.parse(home.text)
        if root.by_id("abnopid") is None:
            raise AuthError("no se encontró el formulario de acceso")

        form = root.by_id("abnopid")
        action = urllib.parse.urljoin(home.url, form.attr("action"))
        fields = parser.form_fields(form)
        fields.update(
            {
                "leid": self.card,
                "lepass": self._password,
                "ACC": ACC_LOGIN,
            }
        )
        response = self.http.post(action, fields)

        if not self._login_succeeded(response.text):
            message = _error_text(response.text) or "credenciales no aceptadas"
            raise AuthError(f"login fallido: {message}")

        href = parser.link_with_acc(response.text, ACC_LIBRARY) or parser.link_with_acc(
            response.text, ACC_LOGOUT
        )
        if not href:
            raise AuthError("login correcto pero no se encontró el hilo autenticado")

        auth_url = urllib.parse.urljoin(response.url, href)
        library = self._get(auth_url)
        if parser.is_expired(library.text, library.url):
            raise AuthError("el hilo autenticado no ha establecido la sesión")
        if parser.parse_reader(library.text) is None:
            raise AuthError("el hilo autenticado no expone el área de lector")
        return

    @staticmethod
    def _login_succeeded(html: str) -> bool:
        lowered = html.lower()
        if "la contraseña es incorrecta" in lowered:
            return False
        return "cerrar sesión" in lowered

    def logout(self) -> None:
        if not self._base:
            return
        base, _ = self._split(self._base)
        self._get(f"{base}?ACC={ACC_LOGOUT}")
        self._base = ""
        self._acc = {}

    # -- lectura ---------------------------------------------------------
    def my_library(self, today: dt.date | None = None) -> Library:
        response = self._auth_get(ACC_LIBRARY)
        reader = parser.parse_reader(response.text)
        if reader is None:
            raise SessionExpired("no se pudo leer la ficha del lector")
        return Library(
            reader=reader,
            loans=parser.parse_loans(response.text, today, reader=reader),
            reservations=parser.parse_reservations(response.text),
        )

    # -- renovación ------------------------------------------------------
    def renew(self, barcode: str, today: dt.date | None = None) -> RenewResult:
        """Renueva un ejemplar leyendo su formulario real, y **verifica** el resultado.

        No se fía del mensaje del servidor: la página incluye el diccionario de
        mensajes del portal (que contiene "Ejemplar renovado"), así que un escaneo
        ingenuo del texto daba falsos positivos. La certeza viene de releer la
        biblioteca desde un acceso nuevo y comprobar que avanzan la fecha y el
        contador de renovaciones. Así se consulta el mismo estado que al recargar
        la web, en vez de conservar el hilo anterior a la operación.
        """
        before = {loan.barcode: loan for loan in self.my_library(today=today).loans}
        if barcode not in before:
            raise OperationRefused(f"el ejemplar {barcode} no está en tus préstamos")

        # El formulario solo existe si la renovación está disponible.
        page = self._auth_get(ACC_LIBRARY)
        form = parser.renewal_form(page.text, barcode)
        if form is None:
            loan = before[barcode]
            reason = (
                f"hasta {loan.renewal_available_from:%d/%m/%Y}"
                if loan.renewal_available_from
                else RENEWAL_LABEL.get(loan.renewal_state, loan.renewal_state.value)
            )
            raise OperationRefused(f"«{loan.clean_title}» no se puede renovar aún ({reason})")

        action, fields = form
        target = urllib.parse.urljoin(page.url, action)
        response = self.http.post(target, fields)
        self._refresh(response)

        # Verify through a fresh authenticated session, exactly as a new panel
        # request does. Re-login is read-only with respect to the loan: never
        # repeat the renewal POST while checking its result.
        self.login()

        after = {loan.barcode: loan for loan in self.my_library(today=today).loans}
        old, new = before[barcode], after.get(barcode)
        if new is None:
            raise OperationRefused("el ejemplar desapareció del panel tras renovar")
        if new.due_date <= old.due_date or new.renewals_used <= old.renewals_used:
            error = parser.operation_error(response.text)
            if error:
                raise OperationRefused(error, response)
            raise OperationRefused(
                "el servidor no confirmó una nueva fecha y renovación; "
                f"la fecha actual es {new.due_date:%d/%m/%Y}. "
                "Revisa tus préstamos antes de volver a intentarlo"
            )
        return RenewResult(
            ok=True,
            message=f"«{new.clean_title}» renovado: {old.due_date:%d/%m/%Y} → {new.due_date:%d/%m/%Y}",
            previous_due=old.due_date,
            new_due=new.due_date,
            renewals_used=new.renewals_used,
            renewals_max=new.renewals_max,
        )

    # -- reservas --------------------------------------------------------
    def cancel_reservation(self, reservation_id: str) -> str:
        """Anula una reserva y verifica que ya no está."""
        before = {r.reservation_id for r in self.my_library().reservations}
        if reservation_id not in before:
            raise OperationRefused(f"la reserva {reservation_id} no está en tu cuenta")

        acc = self._acc_code("delres", "238")
        response = self._auth_post({"DI": reservation_id}, extra_acc=acc)
        error = parser.operation_error(response.text)
        if error:
            raise OperationRefused(error, response)

        after = {r.reservation_id for r in self.my_library().reservations}
        if reservation_id in after:
            raise OperationRefused("el servidor no confirmó la anulación")
        return f"Reserva {reservation_id} anulada"

    def reservable_copies(self, record_id: str) -> list[dict[str, Any]]:
        """Ejemplares que admite la reserva, con sus campos de formulario.

        El orden de llamadas importa: primero la ficha (fija el documento en el
        estado de la sesión), después el asistente ACC=193.
        """
        record = self._auth_get_record(record_id)
        href = parser.link_with_acc(record.text, "193")
        if not href:
            raise OperationRefused("este título no admite reservas")
        wizard = self._get(urllib.parse.urljoin(record.url, href))

        form = parser.form_by_id(wizard.text, "abnformRes")
        if form is None:
            raise OperationRefused("no se encontró el formulario de reserva")

        return parser.parse_reservable_copies(wizard.text)

    def reserve(self, record_id: str, copy_index: int, barcode: str | None = None) -> str:
        """Crea una reserva y verifica su aparición en la biblioteca.

        La web envía el código del ejemplar elegido: si el asistente cambia de
        orden, se busca su índice actual en vez de reservar otro por accidente.
        La CLI conserva su selección por índice (base 1).
        """
        before = {reservation.reservation_id for reservation in self.my_library().reservations}
        record = self._auth_get_record(record_id)
        href = parser.link_with_acc(record.text, "193")
        if not href:
            raise OperationRefused("este título no admite reservas")
        wizard = self._get(urllib.parse.urljoin(record.url, href))
        form = parser.form_by_id(wizard.text, "abnformRes")
        if form is None:
            raise OperationRefused("no se encontró el formulario de reserva")

        fields = parser.form_fields(form)
        if barcode is not None:
            chosen = next((copy for copy in parser.parse_reservable_copies(wizard.text) if copy["barcode"] == barcode), None)
            if chosen is None:
                raise OperationRefused("el ejemplar elegido ya no admite reserva; vuelve a consultar los ejemplares")
            copy_index = chosen["index"]
        keys = [f"{p}_{copy_index}" for p in ("rebarc", "ppnseq", "pprper", "pprprc")]
        if fields.get(f"rebarc_{copy_index}") is None:
            raise OperationRefused(f"el ejemplar {copy_index} no está en la lista")

        action = urllib.parse.urljoin(wizard.url, form.attr("action"))
        # Solo los campos del ejemplar elegido: reenviar el formulario entero
        # marcaría los 135 ejemplares de un título popular.
        payload: dict[str, str] = {
            "ACC": self._acc_code("res", "194"),
            "EMAIL": "on",
            "NCOP": "1",
            f"xcheck_{copy_index}": "1",
        }
        for key in keys:
            payload[key] = fields[key]
        response = self.http.post(action, payload)
        self._refresh(response)
        error = parser.operation_error(response.text)
        if error:
            raise OperationRefused(error, response)
        after = self.my_library().reservations
        created = next((reservation for reservation in after
                        if reservation.reservation_id not in before and reservation.record_id == record_id), None)
        if created is None:
            raise OperationRefused("el servidor no confirmó una nueva reserva; revisa tu biblioteca antes de volver a solicitarla")
        return f"Reserva realizada: «{created.title}»" + (f" en {created.branch}" if created.branch else "")

    # -- catálogo --------------------------------------------------------
    def search(self, query: str, page: int = 1, subcat: str = "/") -> tuple[int, list[MarcRecord]]:
        """Búsqueda general.

        Con un único resultado el servidor salta directamente a la ficha
        (`Documento`) en lugar de a la lista; se devuelve igualmente el registro.
        """
        if not self._base:
            self.login()
        base, _ = self._split(self._base)
        home = self._get(f"{base}?ACC={ACC_HOME}")
        form = parser.form_by_id(home.text, "abnformSearch")
        if form is None:
            form = parser.form_by_id(self._get(f"{base}?ACC={ACC_HOME}").text, "abnformSearch")
        if form is None:
            raise RuntimeError("no se encontró el formulario de búsqueda")

        fields = parser.form_fields(form)
        fields.update({"xsqf01": query, "subcat": subcat, "START": "1"})
        action = urllib.parse.urljoin(home.url, form.attr("action"))
        response = self.http.post(action, fields)
        self._refresh(response)

        if page > 1:
            acc = self._acc_code("page", ACC_PAGE)
            response = self._get(f"{self._split(self._base)[0]}?ACC={acc}&DOC={page}")
            self._refresh(response)

        total, records = parser.parse_search_results(response.text)
        if not records and records_from_document_page(response.text):
            records = [record_from_document_page(response.text)]
            total = total or 1
        for record in records:
            if record.cover_url:
                # El HTML trae la portada como ruta con el token del hilo. Se
                # resuelve aquí, contra la última respuesta, para que nadie
                # tenga que reconstruirla más adelante.
                record.cover_url = urllib.parse.urljoin(response.url, record.cover_url)
        return total, records

    def cover(self, cover_url: str) -> tuple[bytes, str]:
        """Descarga una portada descubierta en una búsqueda anterior.

        La URL la registró la API desde el último HTML; este método vuelve a
        comprobar esquema, origen y CGI antes de pedirla, de modo que una URL
        forjada nunca sale de la máquina y la descarga no sigue redirecciones
        a otros orígenes.
        """
        if not isinstance(cover_url, str) or not cover_url:
            raise HttpError("falta la URL de la portada")
        if has_unsafe_url_chars(cover_url):
            # `urljoin`/`urlsplit` normalizan los controles: se rechaza el texto
            # original, no la versión ya limpiada.
            raise HttpError("URL de portada con caracteres no permitidos")
        target = urllib.parse.urljoin(self.base_url, cover_url)
        if not is_portal_url(target, self.base_url):
            raise HttpError("URL de portada fuera del portal del OPAC")
        return self.http.get_image(target, origin(self.base_url))

    def record_cover_url(self, record_id: str) -> str:
        """Portada de una ficha que todavía no está registrada.

        Una sola apertura de ficha por llamada: quién la memoriza (y durante
        cuánto tiempo) decide la API, que además recuerda la ausencia para no
        repetirla. La URL se resuelve contra la última respuesta y vuelve a
        pasar por `is_portal_url`, así que una ficha que enlace a otro origen o
        a otra ruta del host no produce portada.
        """
        response = self._auth_get_record(record_id)
        record = record_from_document_page(response.text)
        if not record.cover_url:
            return ""
        target = urllib.parse.urljoin(response.url, record.cover_url)
        return target if is_portal_url(target, self.base_url) else ""

    def record(self, record_id: str) -> Response:
        return self._auth_get_record(record_id)

    def _auth_get_record(self, record_id: str) -> Response:
        if not self._base:
            self.login()
        base, _ = self._split(self._base)
        response = self._get(f"{base}?TITN={record_id}")
        if parser.is_expired(response.text, response.url):
            self.login()
            base, _ = self._split(self._base)
            response = self._get(f"{base}?TITN={record_id}")
        return response

    def copies(self, record_id: str) -> list[Copy]:
        return parser.parse_copies(self._auth_get_record(record_id).text)

    def copy_detail(self, signature: str, barcode: str) -> Response:
        if not self._base:
            self.login()
        base, _ = self._split(self._base)
        return self._get(f"{base}?ACC=143&SIGN={urllib.parse.quote(signature)}&BC={barcode}")


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _error_text(html: str) -> str:
    return parser.operation_error(html) or ""


def wait(seconds: float) -> None:
    import time

    time.sleep(seconds)


def records_from_document_page(html: str) -> bool:
    root = parser.parse(html)
    return root.find("h1", lambda n: n.text().strip() == "Documento") is not None


def record_from_document_page(html: str) -> MarcRecord:
    root = parser.parse(html)
    fields: dict[str, list[str]] = {}
    for span in root.find_all("span"):
        for cls in span.attr("class").split():
            if cls.startswith("js-"):
                fields.setdefault(cls[3:], []).append(span.own_text().strip())
    title = _first_span_text(root)
    return MarcRecord(
        record_id=_first_span(fields, "TITN"),
        title=title,
        author=_first_span(fields, "T1XX"),
        publication=_first_span(fields, "T260ab"),
        year=_first_span(fields, "FEPU", "T260c"),
        language=_first_span(fields, "LENG"),
        isbn=_first_span(fields, "T020a"),
        classification=_first_span(fields, "T080"),
        extent=_first_span(fields, "T300a"),
        summary=_first_span(fields, "T520"),
        subjects=fields.get("MATE") or fields.get("T655") or [],
        cover_url=parser.cover_src(root),
        raw_marc=fields,
    )


def _first_span(fields: dict[str, list[str]], *keys: str) -> str:
    for key in keys:
        if fields.get(key):
            return fields[key][0].strip()
    return ""


def _first_span_text(root) -> str:
    node = root.find("h1")
    return node.text() if node else ""


def wait(seconds: float) -> None:
    time.sleep(seconds)
