"""Parsers puros: HTML -> modelos.

Son funciones sin red y sin estado, para poder testearlas contra fixtures.
Todas leen de anclas estables (ids, clases y `data-*`), nunca de texto libre
suelto, porque el proveedor puede reformatear el texto en cualquier momento.
"""

from __future__ import annotations

import datetime as dt
import re
import urllib.parse

from .dom import Node, parse
from .models import (
    Copy,
    Loan,
    MarcRecord,
    Reader,
    RenewalState,
    Reservation,
)

DATE_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")
DATETIME_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})[\s]+(\d{1,2}):(\d{2})")

EXPIRED_MARKERS = ("sesión expirada", "sesion expirada", "la sesión ha expirado")


# --------------------------------------------------------------------------
# utilidades
# --------------------------------------------------------------------------
def _element_siblings(node: Node) -> list[Node]:
    """Elementos que siguen a `node` dentro de su mismo padre."""
    parent = node.parent
    if parent is None:
        return []
    elements = [c for c in parent.children if isinstance(c, Node)]
    try:
        index = elements.index(node)
    except ValueError:
        return elements
    return elements[index + 1 :]


def parse_date(value: str) -> dt.date | None:
    m = DATE_RE.search(value or "")
    if not m:
        return None
    day, month, year = (int(x) for x in m.groups())
    try:
        return dt.date(year, month, day)
    except ValueError:
        return None


def parse_datetime(value: str) -> dt.datetime | None:
    m = DATETIME_RE.search(value or "")
    if not m:
        date = parse_date(value)
        return dt.datetime.combine(date, dt.time(23, 59)) if date else None
    day, month, year, hour, minute = (int(x) for x in m.groups())
    try:
        return dt.datetime(year, month, day, hour, minute)
    except ValueError:
        return None


def renewal_form(html: str, barcode: str) -> tuple[str, dict[str, str]] | None:
    """Formulario de renovación de un ejemplar: `(action, campos)`.

    El nombre del campo **no** es el código de barras, sino `CP<código>`:

        <form id="abnRenov9000000002" class="js-evn-lectorPresta-renov"
              data-cobarc="9000000002" action="<cgi>">
          <input type="hidden" name="ACC" value="228"/>
          <input type="hidden" name="CP9000000002" value="1"/>
          <button>Renovar 15 días</button>
        </form>

    Mandar `<código>=1` (que es lo que hace el módulo JS del camino AJAX) devuelve
    `Error en los campos:`. Se lee el formulario real en vez de construirlo a mano,
    igual que con cualquier otro enlace del OPAC.
    """
    root = parse(html)
    for form in root.find_all("form"):
        if form.attr("data-cobarc") == barcode or form.attr("id") == f"abnRenov{barcode}":
            fields = {
                name: value
                for name, value in form_fields(form).items()
                if name and name != "submit"
            }
            return form.attr("action"), fields
    return None


def renewal_days_from_label(label: str) -> int | None:
    """El botón dice "Renovar 15 días"."""
    match = re.search(r"(\d+)\s*d[ií]as", label or "", re.IGNORECASE)
    return int(match.group(1)) if match else None


ERROR_MARKERS = (
    "error en los campos",
    "la contraseña es incorrecta",
    "no se puede",
    "no hay",
    "no existe",
)


def operation_error(html: str) -> str | None:
    """Mensaje de error explícito de una operación, o `None`.

    OJO: hay que buscar solo en los nodos de aviso, nunca en el texto entero de la
    página. La página incluye el diccionario de mensajes del portal, que contiene
    cadenas como "Ejemplar renovado"; buscarlas en el documento entero daba un falso
    positivo y hacía pasar un fallo por un éxito.
    """
    root = parse(html)
    for node in root.find_all(
        predicate=lambda n: "alert" in n.attr("class").lower() or n.attr("role") == "alert"
    ):
        text = node.text()
        if not text:
            continue
        lowered = text.lower()
        if any(marker in lowered for marker in ERROR_MARKERS):
            return text
    if re.search(r"error en los campos", (root.text()[:2000]).lower()):
        return "Error en los campos"
    return None


def is_document_page(html: str) -> bool:
    """`True` si el servidor devolvió una página completa en vez de un fragmento."""
    return "<html" in html[:400].lower()


def is_expired(response_text: str, url: str = "") -> bool:
    """La sesión caduca a los ~292 s; el portal lo avisa con `timeout.htm`."""
    if "timeout.htm" in url:
        return True
    lowered = response_text[:4000].lower()
    return any(marker in lowered for marker in EXPIRED_MARKERS)


def varjson(html: str) -> dict[str, str]:
    """Lee el bloque `<p id="varJSONmain">`: cada span `id` es su clave."""
    root = parse(html)
    block = root.by_id("varJSONmain")
    if block is None:
        return {}
    out: dict[str, str] = {}
    for span in block.find_all("span"):
        key = span.attr("id")
        if key:
            out[key] = span.text().strip()
    return out


def cgi_endpoint(html: str) -> str | None:
    """`#cgi` es el endpoint base al que se hace POST.

    Los ACC no están hardcodeados en el cliente: se leen de aquí para
    sobrevivir a un cambio del proveedor.
    """
    root = parse(html)
    block = root.by_id("varJSONmain")
    if block is None:
        return None
    node = block.find("span", lambda n: n.attr("id") == "cgi")
    return node.own_text().strip() if node else None


def form_by_id(html: str, form_id: str) -> Node | None:
    root = parse(html)
    return root.find("form", lambda n: n.attr("id") == form_id)


def form_fields(form: Node) -> dict[str, str]:
    out: dict[str, str] = {}
    for field in form.find_all("input"):
        name = field.attr("name")
        if not name:
            continue
        field_type = field.attr("type").lower()
        if field_type in ("submit", "button", "reset"):
            continue
        out[name] = field.attr("value")
    return out


def link_with_acc(html: str, acc: str) -> str | None:
    """Primer `href` que contiene `ACC=<acc>`. Se usa para descubrir hilos."""
    root = parse(html)
    marker = f"ACC={acc}"
    for anchor in root.find_all("a"):
        href = anchor.attr("href")
        if marker in href:
            return href
    return None


# --------------------------------------------------------------------------
# lector
# --------------------------------------------------------------------------
def parse_reader(html: str) -> Reader | None:
    """Lee `varJSONlector`.

    Los spans son **posicionales**, pero no de forma fiable: según el lector el
    nombre va en un solo span (`PERSONA DE PRUEBA APELLIDO`, como en
    `my_library_loans`) o partido en dos (nombre / apellidos, `PERSONA` +
    `DE PRUEBA APELLIDO`, como en `my_library_renovable`). Un parser
    posicional leía mal los flags del segundo caso.

    Solución: clasificar cada span por su forma en vez de por su posición.
    Los carnés son dígitos, los flags son `true`/`false`, la caducidad es una fecha,
    y el resto es nombre.
    """
    root = parse(html)
    block = root.by_id("varJSONlector")
    if block is None:
        return None
    values = [span.own_text().strip() for span in block.find_all("span")]
    values = [value for value in values if value]

    cards = [v for v in values if re.fullmatch(r"\d{5,}", v)]
    flags = [v for v in values if v.lower() in ("true", "false")]
    dates = [v for v in values if parse_date(v)]
    names = [
        v
        for v in values
        if not re.fullmatch(r"\d{5,}", v) and v.lower() not in ("true", "false") and not parse_date(v)
    ]
    if not names:
        return None

    return Reader(
        card=cards[0] if cards else "",
        name=" ".join(names),
        # el orden de los flags es el que documenta el JS: suspendido, caducado
        suspended=len(flags) > 0 and flags[0].lower() == "true",
        expired=len(flags) > 1 and flags[1].lower() == "true",
        card_expires=parse_date(dates[0]) if dates else None,
    )


# --------------------------------------------------------------------------
# préstamos
# --------------------------------------------------------------------------
_RENEWAL_LABELS = (
    (RenewalState.READER_SUSPENDED, "lector suspendido"),
    (RenewalState.READER_EXPIRED, "lector caducado"),
    (RenewalState.OVERDUE, "préstamos sobrepasados"),
    # OJO: "Renovable a partir de X" empieza por "Renovable", hay que mirar antes.
    (RenewalState.RENEWABLE_FROM_DATE, "renovable a partir de"),
    (RenewalState.LIMIT_REACHED, "límite de renovaciones"),
    (RenewalState.NOT_RENEWABLE, "no se puede renovar"),
    (RenewalState.RENEWABLE, "renovable"),
)


def parse_renewal_hint(text: str) -> tuple[RenewalState, dt.date | None]:
    lowered = (text or "").strip().lower()
    if not lowered:
        return RenewalState.UNKNOWN, None
    for state, marker in _RENEWAL_LABELS:
        if marker in lowered:
            return state, parse_date(text) if state is RenewalState.RENEWABLE_FROM_DATE else None
    return RenewalState.UNKNOWN, None


def _label_value(node: Node) -> str:
    """Valor asociado a un `.lector_boxDataInfoLbl`, que va en el siguiente hermano."""
    for sibling in _element_siblings(node):
        for cls in ("lector_boxDataInfoTxt",):
            if sibling.has_class(cls):
                return sibling.text()
        value = sibling.text()
        if value:
            return value
    return ""


def _info_pairs(scope: Node) -> dict[str, str]:
    pairs: dict[str, str] = {}
    for label in scope.find_all(predicate=lambda n: n.has_class("lector_boxDataInfoLbl")):
        pairs[label.text().strip().rstrip(":")] = _label_value(label)
    return pairs


def parse_loans(
    html: str,
    today: dt.date | None = None,
    reader: Reader | None = None,
) -> list[Loan]:
    """Cada préstamo trae un bloque JSON legible en `p.varJSONpr`.

    Es la única parte del OPAC con datos estructurados de verdad, y la que hace
    que esto no sea un scrapeo de texto suelto.
    """
    today = today or dt.date.today()
    root = parse(html)
    section = root.by_id("lector_PR")
    if section is None:
        return []

    loans: list[Loan] = []
    for li in section.find_all("li"):
        block = li.find(predicate=lambda n: n.has_class("varJSONpr"))
        if block is None:
            continue
        data: dict[str, str] = {}
        for span in block.find_all("span"):
            key = span.attr("class").split()[0] if span.attr("class") else ""
            if key:
                data[key] = span.own_text().strip()

        barcode = data.get("prbarc") or li.attr("data-prbarc")
        due_dt = parse_datetime(data.get("prfdev", ""))
        if not barcode or due_dt is None:
            continue

        overdue = _is_overdue(li)
        renewals_used = _int(data.get("prnren"))
        renewals_max = _int(data.get("ppdrnm"))
        window = _int(data.get("ppdrna"))
        holds = _int(data.get("xsresv"))

        state, renew_from = derive_renewal_state(
            due_date=due_dt.date(),
            today=today,
            renew_window_days=window,
            renewals_used=renewals_used,
            renewals_max=renewals_max,
            overdue=overdue,
            reader=reader,
        )

        # Fallback: si algún día el servidor renderizara el texto y no tuvieramos
        # datos suficientes para derivarlo. Nunca *levanta* un bloqueo, porque el
        # JS del portal da prioridad al sobrepaso (sobrepasa > límite > fecha).
        if state is RenewalState.UNKNOWN:
            hint_node = li.find(predicate=lambda n: n.has_class("lector_renovMen"))
            if hint_node is not None and hint_node.text().strip():
                state, hint_date = parse_renewal_hint(hint_node.text())
                renew_from = renew_from or hint_date

        branch_node = li.find(predicate=lambda n: n.attr("data-su") != "")
        info = _info_pairs(li)
        title_link = li.find("a", lambda n: "TITN=" in n.attr("href"))

        loans.append(
            Loan(
                barcode=barcode,
                title=data.get("tititu", ""),
                library=data.get("description", ""),
                branch_address=data.get("address", "").strip(),
                due=due_dt,
                due_date=due_dt.date(),
                days_left=(due_dt.date() - today).days,
                renewals_used=renewals_used,
                renewals_max=renewals_max,
                renew_window_days=window,
                pending_holds=holds,
                renewal_state=state,
                renewal_available_from=renew_from,
                branch_code=branch_node.attr("data-su") if branch_node else "",
                signature=info.get("Signatura", ""),
                record_id=_titn_of(title_link.attr("href") if title_link else ""),
            )
        )
    return loans


def _is_overdue(li: Node) -> bool:
    """El portal marca el sobrepaso con un `.cr` DENTRO de `.js-lectorPresta_xsfdev`.

    El span en sí aparece en todos los préstamos, así que usarlo como marca
    daria todos como retrasados.
    """
    marker = li.find(predicate=lambda n: n.has_class("js-lectorPresta_xsfdev"))
    if marker is None:
        return False
    return marker.find(predicate=lambda n: n.has_class("cr")) is not None


def derive_renewal_state(
    due_date: dt.date,
    today: dt.date,
    renew_window_days: int,
    renewals_used: int,
    renewals_max: int,
    overdue: bool,
    reader: Reader | None = None,
) -> tuple[RenewalState, dt.date | None]:
    """Reproduce la máquina de estados de `js/modules/mylibrary.min.js`.

    El texto que ve el usuario lo inyecta el JavaScript del portal, así que en
    el HTML crudo el `.lector_renovMen` viene **vacío**. El estado hay que
    calcularlo con los datos de `varJSONpr`, que es la única fuente disponible.

    El umbral es `devolución - ppdrna` días. El JS restaría `ppdrna - 1`, pero
    comprobado contra los tres grupos de préstamos de una cuenta real
    (12/10→7/10, 19/10→14/10, 03/11→29/10) el portal muestra siempre `- ppdrna`.
    """
    if overdue or (reader is not None and (reader.suspended or reader.expired)):
        return RenewalState.NOT_RENEWABLE, None
    if renewals_used >= renewals_max:
        return RenewalState.LIMIT_REACHED, None
    if renew_window_days <= 0:
        return RenewalState.RENEWABLE, None
    threshold = due_date - dt.timedelta(days=renew_window_days)
    if today < threshold:
        return RenewalState.RENEWABLE_FROM_DATE, threshold
    return RenewalState.RENEWABLE, None


def _int(value: str | None, default: int = 0) -> int:
    try:
        return int((value or "").strip())
    except (TypeError, ValueError):
        return default


# --------------------------------------------------------------------------
# reservas
# --------------------------------------------------------------------------
def parse_reservations(html: str) -> list[Reservation]:
    """A diferencia de los préstamos, aquí no hay bloque JSON.

    `varJSONlectorReserv` existe pero llega vacío, así que tocamos el HTML
    renderizado. Todas las anclas que usamos son estables.
    """
    root = parse(html)
    section = root.by_id("lector_RE")
    if section is None:
        # Con 0 reservas la sección no se renderiza: es una lista vacía, no un fallo.
        return []

    reservations: list[Reservation] = []
    for li in section.find_all("li"):
        delete = li.find(predicate=lambda n: n.has_class("js-evn-myLibrary-delRes"))
        if delete is None:
            continue
        title_link = li.find("a", lambda n: "TITN=" in n.attr("href"))
        alert = li.first_by_class("c-alert--content")
        info = _info_pairs(li)
        branch = li.find(predicate=lambda n: n.attr("data-su") != "" and not n.has_class("lector_boxTitle"))
        holder = li.find(
            predicate=lambda n: n.has_class("t-we--500")
        )

        reservations.append(
            Reservation(
                reservation_id=delete.attr("data-di"),
                title=title_link.text() if title_link else "",
                record_id=_titn_of(title_link.attr("href") if title_link else ""),
                state=_strip_label(alert.text()) if alert else "",
                expires=parse_date(holder.text()) if holder else None,
                created=parse_datetime(info.get("Fecha de creación", "")),
                signature=info.get("Signatura", ""),
                branch=branch.text() if branch else "",
                branch_code=branch.attr("data-su") if branch else "",
            )
        )
    return reservations


def _titn_of(href: str) -> str:
    match = re.search(r"TITN=(\d+)", href)
    return match.group(1) if match else ""


def _strip_label(text: str) -> str:
    return re.sub(r"^Estado:\s*", "", (text or "").strip())


# --------------------------------------------------------------------------
# catálogo
# --------------------------------------------------------------------------
MARC_KEY = re.compile(r"^js-(.+)$")


def _marc_fields(scope: Node) -> dict[str, list[str]]:
    fields: dict[str, list[str]] = {}
    block = scope.find(predicate=lambda n: n.has_class("c-docs_marc"))
    if block is None:
        return fields
    for span in block.find_all("span"):
        for cls in span.attr("class").split():
            m = MARC_KEY.match(cls)
            if m:
                fields.setdefault(m.group(1), []).append(span.own_text().strip())
    return fields


def _clean_isbn(value: str) -> str:
    """`T020a` llega con el subcampo MARC $c pegado: "978-84-679-6740-1 ("."""
    return re.sub(r"[\s(]+$", "", (value or "").strip())


def _first_span(fields: dict[str, list[str]], *keys: str) -> str:
    for key in keys:
        if fields.get(key):
            return fields[key][0].strip()
    return ""


def _parse_openurl(node: Node | None) -> dict[str, str]:
    if node is None:
        return {}
    params = urllib.parse.parse_qs(node.attr("title"), keep_blank_values=False)
    return {k: v[0] for k, v in params.items()}


def cover_src(scope: Node) -> str:
    """Imagen de portada de una tarjeta de lista o de una ficha.

    Regla única para las dos superficies (resultado de búsqueda y ficha):

    1. la imagen etiquetada «Cubierta…» — así aparece en la lista
       (`alt="Cubierta - 1"`) y en la ficha (`alt="Cubierta"`);
    2. si no, la imagen dentro del enlace de portada (`…&MLKOB=…`);
    3. en la lista, la del contenedor `c-docs_img`.

    Cualquier otra imagen de la tarjeta (iconos de la ficha, logotipos) no es
    una portada: tomar el primer `<img>` daba una URL que después rechazaba
    `is_portal_url` y la portada desaparecía.
    """
    for img in scope.find_all("img"):
        if img.attr("alt", "").strip().lower().startswith("cubierta") and img.attr("src"):
            return img.attr("src")
    link = scope.find("a", lambda n: "MLKOB=" in n.attr("href"))
    if link is not None:
        img = link.find("img")
        if img is not None and img.attr("src"):
            return img.attr("src")
    box = scope.find(predicate=lambda n: n.has_class("c-docs_img"))
    if box is not None:
        img = box.find("img")
        if img is not None and img.attr("src"):
            return img.attr("src")
    return ""


def parse_search_results(html: str) -> tuple[int, list[MarcRecord]]:
    """Lista de resultados.

    Cada `li.c-docs_unit` trae el MARC completo embebido y un OpenURL, así que
    pintar 10 resultados no cuesta ni una petición extra.
    """
    root = parse(html)
    records: list[MarcRecord] = []
    for li in root.find_all(predicate=lambda n: n.has_class("c-docs_unit")):
        fields = _marc_fields(li)
        title_node = li.first_by_class("c-docs_title")
        author_node = li.first_by_class("c-docs_author")
        openurl = _parse_openurl(li.find(predicate=lambda n: n.has_class("Z3988")))
        cover = cover_src(li)

        subjects = fields.get("MATE") or fields.get("T655") or []
        publication = _publication(fields)

        records.append(
            MarcRecord(
                record_id=_first_span(fields, "TITN"),
                title=title_node.text() if title_node else _first_span(fields, "T245"),
                author=author_node.text() if author_node else _first_span(fields, "T1XX"),
                publication=publication,
                year=_first_span(fields, "FEPU", "T260c", "T008"),
                language=_first_span(fields, "LENG"),
                isbn=_clean_isbn(_first_span(fields, "T020a")),
                classification=_first_span(fields, "T080"),
                extent=_first_span(fields, "T300a"),
                summary=re.sub(r"\s+--\s*Cubierta\s*$", "", _first_span(fields, "T520")).strip(),
                subjects=[s.strip() for s in subjects if s.strip()],
                cover_url=cover,
                openurl=openurl,
                doc_type=_first_span(fields, "ld06"),
                raw_marc=fields,
            )
        )

    total = 0
    match = re.search(r"([\d.,]+)\s*resultados?", root.text(), re.IGNORECASE)
    if match:
        try:
            total = int(re.sub(r"[^\d]", "", match.group(1)))
        except ValueError:
            total = 0
    return total, records


def _publication(fields: dict[str, list[str]]) -> str:
    """`T260ab` es "Barcelona : Destino, " y `T260c` el año.

    Unir a pelo los subcampos `a`/`b` duplicaba los dos puntos, así que se
    reconstruye desde el campo combinado tal como lo emite el OPAC.
    """
    combined = _first_span(fields, "T260ab").strip().rstrip(",").strip()
    if not combined:
        parts = [p.strip().rstrip(":").strip() for p in (_first_span(fields, "T260a"), _first_span(fields, "T260b")) if p.strip()]
        combined = " : ".join(p for p in parts if p)
    year = _first_span(fields, "T260c", "FEPU").strip()
    if year and year not in combined:
        combined = f"{combined}, {year}" if combined else year
    return combined


DOC_TYPE_NAMES = {
    "a": "texto",
    "e": "recursos electrónicos",
    "g": "partituras",
    "i": "material no proyectable",
    "j": "material proyectable",
    "m": "partitura",
    "p": "material mixto no proyectable",
    "t": "manuscritos",
}


def _cell_value(cell: Node) -> str:
    """Valor de una celda, sin el texto de la etiqueta.

    Las celdas llevan un `span.copias_label` ("Tipo de ejemplar") en modo móvil,
    así que el texto crudo mezcla la etiqueta con el valor.
    """
    parts: list[str] = []

    def collect(node: Node) -> None:
        if node.tag in ("script", "style", "input", "button") or node.has_class("copias_label") or node.has_class("copiasRes_label"):
            return
        for child in node.children:
            if isinstance(child, str):
                parts.append(child)
            else:
                collect(child)

    collect(cell)
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def parse_reservable_copies(html: str) -> list[dict]:
    """Lee filas completas del asistente; nunca recorta fragmentos de HTML.

    Los índices pertenecen al formulario real y pueden tener huecos. No deben
    renumerarse: se usan después para seleccionar el ejemplar en el portal.
    """
    form = form_by_id(html, "abnformRes")
    if form is None:
        return []
    fields = form_fields(form)
    inputs = {field.attr("name"): field for field in form.find_all("input")
              if re.fullmatch(r"rebarc_\d+", field.attr("name"))}
    copies: list[dict] = []
    for name in sorted(inputs, key=lambda value: int(value.rsplit("_", 1)[1])):
        index = int(name.rsplit("_", 1)[1])
        barcode = fields.get(name, "")
        if not barcode or index < 1:
            continue
        row = inputs[name].parent
        while row is not None and row is not form and row.tag != "tr":
            row = row.parent
        cells = row.find_all("td") if row is not None and row.tag == "tr" else []

        def parts(cell: Node) -> list[str]:
            return [value for child in cell.children
                    if isinstance(child, Node) and (value := _cell_value(child))]

        where = parts(cells[0]) if cells else []
        location = parts(cells[1]) if len(cells) > 1 else []
        copy = {
            "index": index, "barcode": barcode,
            "sequence": fields.get(f"ppnseq_{index}", ""),
            "period": fields.get(f"pprper_{index}", ""),
            "price": fields.get(f"pprprc_{index}", ""),
            "library": where[0] if where else "",
            "branch": " · ".join(where[1:]) if len(where) > 1 else "",
            "location": location[0] if location else "",
            "signature": " · ".join(location[1:]) if len(location) > 1 else "",
            "copy_type": _cell_value(cells[2]) if len(cells) > 2 else "",
            "availability": _cell_value(cells[3]) if len(cells) > 3 else "",
        }
        copy["row"] = " · ".join(copy[key] for key in ("library", "branch", "location", "signature", "copy_type", "availability") if copy[key])
        copies.append(copy)
    return copies


def parse_copies(html: str) -> list[Copy]:
    """Ejemplares de una ficha.

    Marcado real:
        div.copias_accordion
          div.c-accordion_item          <- una sucursal
            .c-accordion_h              -> "Sucursal: <nombre>"
            table > tr[data-disp]       <- un ejemplar
              td .icm_locSign           -> "Sala adultos"
              td a[data-bc][data-sign]  -> código de barras y signatura
              td .copias_tableDisp      -> disponibilidad
    """
    root = parse(html)
    accordions = root.find_all(predicate=lambda n: n.has_class("copias_accordion"))
    if not accordions:
        return []

    copies: list[Copy] = []
    seen: set[str] = set()
    # Ojo: hay VARIOS `copias_accordion` en la página (uno por bloque), no uno solo.
    for accordion in accordions:
        for item in accordion.by_class("c-accordion_item"):
            header = item.find(predicate=lambda n: n.has_class("c-accordion_h"))
            branch = (
                re.sub(r"^Sucursal:\s*", "", header.text().strip(), flags=re.IGNORECASE)
                if header
                else ""
            )

            for row in item.find_all("tr", lambda n: n.attr("data-disp") != ""):
                anchor = row.find(predicate=lambda n: n.attr("data-bc") != "")
                if anchor is None:
                    continue
                barcode = anchor.attr("data-bc")
                if barcode in seen:
                    continue
                seen.add(barcode)

                cells = row.find_all("td")
                location_node = row.find(predicate=lambda n: n.has_class("icm_locSign"))
                location = location_node.text() if location_node else ""
                signature = anchor.attr("data-sign") or anchor.text().strip()
                copy_type = _cell_value(cells[1]) if len(cells) > 1 else ""
                support = _cell_value(cells[2]) if len(cells) > 2 else ""
                availability = row.attr("data-disp").strip()

                expected = None
                if "despu" in availability.lower() or "después de" in availability.lower():
                    expected = parse_date(availability)

                copies.append(
                    Copy(
                        barcode=barcode,
                        signature=signature,
                        library=branch,
                        branch=branch,
                        location=location,
                        copy_type=copy_type,
                        support=support,
                        availability=availability,
                        expected=expected,
                    )
                )
    return copies
