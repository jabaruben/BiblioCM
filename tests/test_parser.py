"""Tests de los parsers. Sin red y sin credenciales: todo va contra fixtures."""

from __future__ import annotations

import datetime as dt
import pathlib
import unittest

from biblio import parser
from biblio.models import Reader, RenewalState

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
TODAY = dt.date(2026, 10, 2)  # la fecha en la que se capturaron los fixtures


def load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class DatesTest(unittest.TestCase):
    def test_date(self):
        self.assertEqual(parser.parse_date("12/10/2026 23:59"), dt.date(2026, 10, 12))
        self.assertEqual(parser.parse_date("31/03/2027"), dt.date(2027, 3, 31))
        self.assertIsNone(parser.parse_date("sin fecha"))
        self.assertIsNone(parser.parse_date("32/13/2026"))

    def test_datetime_defaults_to_end_of_day(self):
        self.assertEqual(
            parser.parse_datetime("12/10/2026 23:59"), dt.datetime(2026, 10, 12, 23, 59)
        )
        self.assertEqual(
            parser.parse_datetime("19/10/2026"), dt.datetime(2026, 10, 19, 23, 59)
        )


class RenewalHintTest(unittest.TestCase):
    """El bug que costó una tarde: "Renovable a partir de X" empieza por "Renovable"."""

    def test_renovable(self):
        self.assertEqual(parser.parse_renewal_hint("Renovable")[0], RenewalState.RENEWABLE)

    def test_renovable_desde_no_es_renovable(self):
        state, date = parser.parse_renewal_hint("Renovable a partir de 7/10/2026")
        self.assertEqual(state, RenewalState.RENEWABLE_FROM_DATE)
        self.assertEqual(date, dt.date(2026, 10, 7))
        self.assertFalse(state.can_renew, "no se debe poder renovar antes de la fecha")

    def test_limite_alcanzado(self):
        state, _ = parser.parse_renewal_hint("Se ha alcanzado el límite de renovaciones")
        self.assertEqual(state, RenewalState.LIMIT_REACHED)
        self.assertFalse(state.can_renew)

    def test_no_renovable(self):
        self.assertEqual(
            parser.parse_renewal_hint("No se puede renovar")[0], RenewalState.NOT_RENEWABLE
        )

    def test_lector_flags(self):
        self.assertEqual(parser.parse_renewal_hint("Lector caducado")[0], RenewalState.READER_EXPIRED)
        self.assertEqual(parser.parse_renewal_hint("Lector suspendido")[0], RenewalState.READER_SUSPENDED)

    def test_desconocido(self):
        self.assertEqual(parser.parse_renewal_hint("")[0], RenewalState.UNKNOWN)


class ReaderTest(unittest.TestCase):
    def test_lector(self):
        reader = parser.parse_reader(load("my_library_loans.html"))
        self.assertIsNotNone(reader)
        assert reader
        self.assertEqual(reader.card, "12345678")
        self.assertEqual(reader.name, "PERSONA DE PRUEBA APELLIDO")
        self.assertFalse(reader.suspended)
        self.assertFalse(reader.expired)
        self.assertEqual(reader.card_expires, dt.date(2033, 11, 17))

    def test_ausencia_de_lector(self):
        self.assertIsNone(parser.parse_reader(load("opac_home.html")))


class LoansTest(unittest.TestCase):
    def setUp(self):
        self.loans = parser.parse_loans(load("my_library_loans.html"), today=TODAY)
        self.by_barcode = {loan.barcode: loan for loan in self.loans}

    def test_numero(self):
        self.assertEqual(len(self.loans), 3)

    def test_campos_de_un_prestamo(self):
        loan = self.by_barcode["9000000021"]
        self.assertEqual(loan.title, "El libro del otoño /")
        self.assertEqual(loan.clean_title, "El libro del otoño")
        self.assertEqual(loan.library, "Biblioteca Municipal María Moliner")
        self.assertEqual(loan.branch_code, "BMVEL1")
        self.assertEqual(loan.signature, "J-525 OTT lib")
        self.assertEqual(loan.due_date, dt.date(2026, 10, 12))
        self.assertEqual(loan.due, dt.datetime(2026, 10, 12, 23, 59))
        self.assertEqual(loan.days_left, 10)
        self.assertEqual(loan.renewals_used, 0)
        self.assertEqual(loan.renewals_max, 1)
        self.assertEqual(loan.renew_window_days, 5)
        self.assertEqual(loan.pending_holds, 0)

    def test_estado_renovacion_desde_fecha(self):
        loan = self.by_barcode["9000000021"]
        self.assertEqual(loan.renewal_state, RenewalState.RENEWABLE_FROM_DATE)
        self.assertEqual(loan.renewal_available_from, dt.date(2026, 10, 7))
        self.assertFalse(loan.renewal_state.can_renew)

    def test_limite_de_renovaciones_alcanzado(self):
        # este ejemplar ya gastó su 1 de 1
        loan = self.by_barcode["9000000022"]
        self.assertEqual(loan.renewal_state, RenewalState.LIMIT_REACHED)
        self.assertEqual(loan.renewals_used, 1)
        self.assertEqual(loan.renewals_max, 1)

    def test_colas_se_leen_igual(self):
        loan = self.by_barcode["9000000022"]
        self.assertEqual(loan.pending_holds, 2)

    def test_renovable_al_llegar_al_umbral(self):
        loans = parser.parse_loans(load("my_library_loans.html"), today=dt.date(2026, 10, 7))
        loan = {l.barcode: l for l in loans}["9000000021"]
        self.assertEqual(loan.renewal_state, RenewalState.RENEWABLE)
        self.assertTrue(loan.renewal_state.can_renew)

    def test_no_renovable_por_retraso(self):
        loan = self.by_barcode["9000000023"]
        self.assertEqual(loan.renewal_state, RenewalState.NOT_RENEWABLE)

    def test_retraso(self):
        loan = self.by_barcode["9000000023"]
        self.assertEqual(loan.due_date, dt.date(2026, 10, 1))
        self.assertEqual(loan.days_left, -1)
        self.assertTrue(loan.overdue)

    def test_colas_y_limites_se_leen_aunque_el_texto_diga_renovable(self):
        """El texto renderizado manda, pero los datos numéricos se leen igual."""
        loan = self.by_barcode["9000000022"]
        self.assertEqual(loan.pending_holds, 2)
        self.assertEqual(loan.renewals_used, 1)
        self.assertEqual(loan.renewals_max, 1)

    def test_colas_y_limites_se_leen_aunque_el_estado_bloquee(self):
        """Los datos numéricos se leen siempre, aunque no se pueda renovar."""
        loan = self.by_barcode["9000000022"]
        self.assertEqual(loan.pending_holds, 2)
        self.assertEqual(loan.renewals_used, 1)
        self.assertEqual(loan.renewals_max, 1)

    def test_retraso(self):
        loan = self.by_barcode["9000000023"]
        self.assertEqual(loan.due_date, dt.date(2026, 10, 1))
        self.assertEqual(loan.days_left, -1)
        self.assertTrue(loan.overdue)

    def test_orden_por_urgencia(self):
        ordered = sorted(self.loans, key=lambda loan: loan.due)
        self.assertEqual([loan.due_date.day for loan in ordered], [1, 12, 14])

    def test_seccion_inexistente(self):
        self.assertEqual(parser.parse_loans(load("opac_home.html")), [])

    def test_identidad_bibliografica_del_prestamo(self):
        """El `href?TITN=` del título da el registro al que atribuir la portada."""
        self.assertEqual(self.by_barcode["9000000021"].record_id, "288993")
        self.assertEqual(self.by_barcode["9000000022"].record_id, "467925")
        self.assertEqual(self.by_barcode["9000000023"].record_id, "1234")

    def test_prestamo_sin_enlace_de_ficha_no_inventa_un_registro(self):
        loans = parser.parse_loans(load("my_library_with_reservation.html"), today=TODAY)
        self.assertEqual(len(loans), 1)
        self.assertEqual(loans[0].record_id, "")


class ReservationsTest(unittest.TestCase):
    def test_cero_reservas_no_es_error(self):
        """Con 0 reservas la sección ni se renderiza."""
        self.assertEqual(parser.parse_reservations(load("my_library_loans.html")), [])

    def test_reserva(self):
        reservations = parser.parse_reservations(load("my_library_with_reservation.html"))
        self.assertEqual(len(reservations), 1)
        res = reservations[0]
        self.assertEqual(res.reservation_id, "9000001")
        self.assertEqual(res.record_id, "2250070")
        self.assertEqual(res.title, "La ciudad de las luces muertas /")
        self.assertEqual(res.state, "Reservada")
        self.assertEqual(res.expires, dt.date(2027, 3, 31))
        self.assertEqual(res.created, dt.datetime(2026, 10, 2, 12, 55))
        self.assertEqual(res.branch, "B.P.M. Cardenal Cisneros")
        self.assertEqual(res.branch_code, "BMALC1")
        self.assertIn("N UCL ciu", res.signature)


class SearchResultsTest(unittest.TestCase):
    def setUp(self):
        self.total, self.records = parser.parse_search_results(load("search_results.html"))

    def test_total(self):
        self.assertEqual(self.total, 1029)

    def test_numero(self):
        self.assertEqual(len(self.records), 2)

    def test_campos_visibles(self):
        first = self.records[0]
        self.assertEqual(first.title, "La ciudad de las luces muertas")
        self.assertEqual(first.author, "Uclés, David (1990-)")

    def test_marc_embebido(self):
        first = self.records[0]
        self.assertEqual(first.record_id, "2250070")
        self.assertEqual(first.isbn, "978-84-233-6922-5")
        self.assertEqual(first.language, "spa")
        self.assertEqual(first.classification, "821.134.2-31\"20")
        self.assertEqual(first.extent, "282 p. ;")
        self.assertEqual(first.year, "2026")
        self.assertEqual(first.doc_type, "a")
        self.assertEqual(first.subjects, ["Barcelona-Novelas", "Novelas fantásticas"])
        self.assertEqual(first.raw_marc["T245"][0], "La ciudad de las luces muertas / David Uclés")

    def test_resumen_sin_el_sufijo_de_cubierta(self):
        first = self.records[0]
        self.assertTrue(first.summary.startswith("La luz se va en Barcelona"))
        self.assertFalse(first.summary.endswith("Cubierta"))

    def test_openurl(self):
        first = self.records[0]
        self.assertEqual(first.openurl["rft.btitle"], "La ciudad de las luces muertas")
        self.assertEqual(first.openurl["rft.isbn"], "978-84-233-6922-5")

    def test_portada(self):
        self.assertIn("ACC=299", self.records[0].cover_url)
        self.assertEqual(self.records[1].cover_url, "")

    def test_publicacion_reconstruida(self):
        # No se duplican los dos puntos de `T260ab` y se añade el año de `T260c`.
        self.assertEqual(self.records[0].publication, "Barcelona : Destino, 2026")

    def test_titulo_con_autor(self):
        loan_html = load("my_library_loans.html")
        loan = parser.parse_loans(loan_html, today=TODAY)[0]
        self.assertEqual(loan.clean_title, "El libro del otoño")
        self.assertEqual(loan.author, "")  # `tititu` llega como "título /" sin autor


class VarJsonTest(unittest.TestCase):
    def test_lectura_de_claves(self):
        data = parser.varjson(load("my_library_loans.html"))
        self.assertEqual(data["renov"], "228")
        self.assertEqual(data["delres"], "238")

    def test_cgi(self):
        self.assertEqual(
            parser.cgi_endpoint(load("my_library_loans.html")),
            "/biblio_publicas/cgi-bin/abnetopac/THREADTOKEN01/NT41",
        )

    def test_ausencia(self):
        self.assertEqual(parser.varjson(load("opac_home.html")).get("renov"), None)


class FormsTest(unittest.TestCase):
    def test_campos_del_formulario_de_login(self):
        form = parser.form_by_id(load("opac_home.html"), "abnopid")
        self.assertIsNotNone(form)
        assert form
        fields = parser.form_fields(form)
        self.assertEqual(fields["FBC"], "316")
        self.assertEqual(fields["NAC"], "317")
        self.assertEqual(fields["ACC"], "201")
        self.assertNotIn("", fields, "los campos vacíos no deben pisar los enviados")

    def test_campos_del_formulario_de_busqueda(self):
        form = parser.form_by_id(load("opac_home.html"), "abnformSearch")
        assert form
        self.assertEqual(parser.form_fields(form)["ACC"], "131")

    def test_se_envian_dos_inputs_igual(self):
        """`xcheck` aparece duplicado en el HTML real; `form_fields` lo resuelve."""
        form = parser.form_by_id(load("opac_home.html"), "abnopid")
        assert form
        self.assertEqual(len(parser.form_fields(form)), 5)


class HelpersTest(unittest.TestCase):
    def test_detectar_caducidad_por_url(self):
        self.assertTrue(parser.is_expired("", "https://x/timeout.htm?dir=/biblio_publicas"))

    def test_detectar_caducidad_por_texto(self):
        self.assertTrue(parser.is_expired("<html>Sesión expirada</html>"))

    def test_sano(self):
        self.assertFalse(parser.is_expired(load("my_library_loans.html")))

    def test_buscar_hilo_por_acc(self):
        href = parser.link_with_acc(load("my_library_with_reservation.html"), "238")
        self.assertIn("ACC=238", href or "")
        self.assertIsNone(parser.link_with_acc(load("my_library_loans.html"), "999"))


class DomTest(unittest.TestCase):
    def test_anidamiento_y_texto(self):
        html = "<div id='a'><p class='x'>hola <b>mundo</b></p><span>fin</span></div>"
        root = parser.parse(html)
        node = root.by_id("a")
        assert node
        self.assertEqual(node.text(), "hola mundo fin")
        self.assertEqual(len(node.by_class("x")), 1)

    def test_atributos_vacios(self):
        root = parser.parse("<input disabled name='x'>")
        self.assertEqual(root.find("input").attrs, {"disabled": "", "name": "x"})


class DerivedRenewalTest(unittest.TestCase):
    """El texto de renovación lo rellena el JS del portal: en el HTML va vacío.

    Hay que derivarlo de `varJSONpr`, que es la única fuente real.
    """

    def test_umbral_es_devolucion_menos_la_ventana(self):
        state, date = parser.derive_renewal_state(
            due_date=dt.date(2026, 10, 12),
            today=dt.date(2026, 10, 2),
            renew_window_days=5,
            renewals_used=0,
            renewals_max=1,
            overdue=False,
        )
        self.assertEqual(state, RenewalState.RENEWABLE_FROM_DATE)
        self.assertEqual(date, dt.date(2026, 10, 7))

    def test_justo_en_el_umbral_ya_se_puede(self):
        state, _ = parser.derive_renewal_state(
            due_date=dt.date(2026, 10, 12),
            today=dt.date(2026, 10, 7),
            renew_window_days=5,
            renewals_used=0,
            renewals_max=1,
            overdue=False,
        )
        self.assertEqual(state, RenewalState.RENEWABLE)
        self.assertTrue(state.can_renew)

    def test_sobrepaso_bloquea(self):
        state, _ = parser.derive_renewal_state(
            due_date=dt.date(2026, 10, 12),
            today=dt.date(2026, 10, 20),
            renew_window_days=5,
            renewals_used=0,
            renewals_max=1,
            overdue=True,
        )
        self.assertEqual(state, RenewalState.NOT_RENEWABLE)

    def test_limite_de_renovaciones(self):
        state, _ = parser.derive_renewal_state(
            due_date=dt.date(2026, 10, 12),
            today=dt.date(2026, 10, 10),
            renew_window_days=5,
            renewals_used=1,
            renewals_max=1,
            overdue=False,
        )
        self.assertEqual(state, RenewalState.LIMIT_REACHED)

    def test_lector_suspendido_bloquea_todo(self):
        reader = Reader(card="1", name="X", suspended=True, expired=False, card_expires=None)
        state, _ = parser.derive_renewal_state(
            due_date=dt.date(2026, 10, 12),
            today=dt.date(2026, 10, 10),
            renew_window_days=5,
            renewals_used=0,
            renewals_max=1,
            overdue=False,
            reader=reader,
        )
        self.assertEqual(state, RenewalState.NOT_RENEWABLE)

    def test_material_no_renovable(self):
        """Sin ventana de renovación no hay fecha umbral que respetar."""
        state, _ = parser.derive_renewal_state(
            due_date=dt.date(2026, 10, 12),
            today=dt.date(2026, 10, 2),
            renew_window_days=0,
            renewals_used=0,
            renewals_max=1,
            overdue=False,
        )
        self.assertEqual(state, RenewalState.RENEWABLE)


class OverdueMarkerTest(unittest.TestCase):
    def test_el_span_de_fecha_no_es_marca_de_retraso(self):
        """`.js-lectorPresta_xsfdev` está en TODOS los préstamos.

        La marca de sobrepaso es un `.cr` dentro de él, tal como hace el JS
        del portal. Sin esto, los 9 préstamos salían como retrasados.
        """
        loans = parser.parse_loans(load("my_library_loans.html"), today=TODAY)
        not_overdue = [loan for loan in loans if loan.barcode in ("9000000021", "9000000022")]
        self.assertEqual(len(not_overdue), 2)
        for loan in not_overdue:
            self.assertFalse(loan.overdue)
            self.assertIsNot(
                loan.renewal_state,
                RenewalState.NOT_RENEWABLE,
                "un préstamo a 10 días no puede bloquearse por retraso",
            )

    def test_retraso_detectado_por_cr(self):
        html = load("my_library_loans.html").replace(
            '<span class="js-lectorPresta_xsfdev">Fecha de devolución: 12/10/2026</span>',
            '<span class="js-lectorPresta_xsfdev"><span class="cr">'
            "Fecha de devolución: 12/10/2026</span></span>",
        )
        loan = {l.barcode: l for l in parser.parse_loans(html, today=TODAY)}["9000000021"]
        self.assertEqual(loan.renewal_state, RenewalState.NOT_RENEWABLE)

    def test_no_renovable_por_retraso_gana_al_texto_del_portal(self):
        """El JS da prioridad al sobrepaso, aunque el texto diga 'Renovable'."""
        html = load("my_library_loans.html").replace(
            '<span class="js-lectorPresta_xsfdev">Fecha de devolución: 12/10/2026</span>',
            '<span class="js-lectorPresta_xsfdev"><span class="cr">'
            "Fecha de devolución: 12/10/2026</span></span>",
        ).replace(
            'data-prbarc="9000000021"></span>',
            'data-prbarc="9000000021">Renovable</span>',
        )
        loan = {l.barcode: l for l in parser.parse_loans(html, today=TODAY)}["9000000021"]
        self.assertEqual(loan.renewal_state, RenewalState.NOT_RENEWABLE)


class CopiesTest(unittest.TestCase):
    def setUp(self):
        self.copies = parser.parse_copies(load("record_copies.html"))

    def test_numero(self):
        self.assertEqual(len(self.copies), 3)

    def test_campos(self):
        first = self.copies[0]
        self.assertEqual(first.barcode, "1501725736")
        self.assertEqual(first.signature, "N UCL ciu")
        self.assertEqual(first.branch, "Biblioteca Municipal de El Álamo")
        self.assertEqual(first.location, "Sala adultos")
        self.assertEqual(first.copy_type, "Prestable. Libros")
        self.assertEqual(first.support, "Libro")

    def test_agrupacion_por_sucursal(self):
        branches = [c.branch for c in self.copies]
        self.assertEqual(
            branches,
            [
                "Biblioteca Municipal de El Álamo",
                "Biblioteca Municipal de El Álamo",
                "B.P.M. María Moliner",
            ],
        )

    def test_recorre_todos_los_bloques(self):
        """La página tiene varios `.copias_accordion`; leer solo el primero
        perdía los ejemplares del resto de sucursales."""
        html = load("record_copies.html")
        self.assertEqual(
            html.count('class="copias_accordion c-accordion js-copias_accordion"'), 2
        )
        self.assertEqual(len(parser.parse_copies(html)), 3)
        self.assertEqual(self.copies[-1].branch, "B.P.M. María Moliner")

    def test_disponible_despues_no_esta_disponible_ahora(self):
        """El fallo que inflaba el recuento de disponibilidad."""
        available_now = [c for c in self.copies if c.available_now]
        soon = [c for c in self.copies if not c.available_now]
        self.assertEqual(len(available_now), 2)
        self.assertEqual(len(soon), 1)
        self.assertEqual(soon[0].barcode, "1501620201")

    def test_fecha_esperada(self):
        soon = [c for c in self.copies if not c.available_now][0]
        self.assertEqual(soon.expected, dt.date(2026, 10, 24))

    def test_sin_ejemplares(self):
        self.assertEqual(parser.parse_copies(load("search_results.html")), [])

    def test_barras_duplicadas_se_descartan(self):
        html = load("record_copies.html").replace('data-bc="1501620201"', 'data-bc="1501725736"')
        self.assertEqual(len(parser.parse_copies(html)), 2)


def test_isbn_sin_subcampo_marc(self):
        """`T020a` llega con el $c de MARC pegado: "978-84-679-6740-1 ("."""
        html = load("search_results.html").replace(
            '<span class="js-T020a">978-84-233-6922-5</span>',
            '<span class="js-T020a">978-84-679-6740-1 (</span>',
        )
        _, records = parser.parse_search_results(html)
        self.assertEqual(records[0].isbn, "978-84-679-6740-1")


class RenewalFormTest(unittest.TestCase):
    """El campo NO se llama como el código de barras, sino `CP<código>`."""

    def setUp(self):
        self.html = load("my_library_renovable.html")

    def test_lee_el_formulario_real(self):
        form = parser.renewal_form(self.html, "9000000011")
        self.assertIsNotNone(form)
        action, fields = form
        assert action
        self.assertTrue(action.endswith("/NT3"))
        self.assertEqual(fields["ACC"], "228")
        self.assertEqual(fields["CP9000000011"], "1")

    def test_nombre_del_campo(self):
        """Si se mandara `9000000011=1` el servidor responde 'Error en los campos'."""
        _, fields = parser.renewal_form(self.html, "9000000011")
        self.assertNotIn("9000000011", fields)

    def test_sin_formulario_no_hay_renovacion(self):
        """El formulario solo existe si la renovación está disponible."""
        self.assertIsNone(parser.renewal_form(self.html, "9000000012"))

    def test_codigo_inexistente(self):
        self.assertIsNone(parser.renewal_form(self.html, "9999999999"))

    def test_dias_de_prorroga_del_boton(self):
        self.assertEqual(parser.renewal_days_from_label("Renovar 15 días"), 15)
        self.assertEqual(parser.renewal_days_from_label("Renovar 30 días"), 30)
        self.assertIsNone(parser.renewal_days_from_label("Renovar"))


class OperationErrorTest(unittest.TestCase):
    """El bug que hacía pasar un fallo por un éxito."""

    def test_detecta_error_en_los_campos(self):
        html = '<html><body><p class="c-alert c-alert_warning">Error en los campos:</p></body></html>'
        self.assertIsNotNone(parser.operation_error(html))

    def test_no_confunde_el_diccionario_de_mensajes(self):
        """La página completa incluye 'Ejemplar renovado' como texto de plantilla."""
        html = (
            "<html><body><p class='varJSONmain'>Renovando ejemplar Ejemplar renovado "
            "Reserva eliminada</p></body></html>"
        )
        self.assertIsNone(parser.operation_error(html))

    def test_no_se_puede_renovar(self):
        html = '<p class="c-alert">No se puede renovar</p>'
        self.assertIn("no se puede", (parser.operation_error(html) or "").lower())

    def test_html_limpio(self):
        self.assertIsNone(parser.operation_error("<p>Renovando ejemplar</p>"))


class ReaderSplitNameTest(unittest.TestCase):
    """En `my_library_renovable` el nombre viene en dos spans; en
    `my_library_loans`, en uno solo (ver `test_nombre_en_un_solo_span`)."""

    def setUp(self):
        self.html = load("my_library_renovable.html")

    def test_nombre_partido_se_une(self):
        reader = parser.parse_reader(self.html)
        assert reader
        self.assertEqual(reader.name, "PERSONA DE PRUEBA APELLIDO")

    def test_flags_no_se_desplazan(self):
        reader = parser.parse_reader(self.html)
        assert reader
        self.assertFalse(reader.suspended)
        self.assertFalse(reader.expired)
        self.assertIsNone(reader.card_expires, "sin fecha de caducidad no se inventa una")

    def test_carné(self):
        reader = parser.parse_reader(self.html)
        assert reader
        # El carné aparece dos veces (con y sin relleno de ceros); se toma el
        # primero y el relleno no desplaza los campos siguientes.
        self.assertEqual(reader.card, "22222222")

    def test_nombre_en_un_solo_span(self):
        reader = parser.parse_reader(load("my_library_loans.html"))
        assert reader
        self.assertEqual(reader.name, "PERSONA DE PRUEBA APELLIDO")
        self.assertEqual(reader.card_expires, dt.date(2033, 11, 17))

    def test_lector_suspendido_se_entiende(self):
        html = self.html.replace('<span class="susp">false</span>', '<span class="susp">true</span>')
        reader = parser.parse_reader(html)
        assert reader
        self.assertTrue(reader.suspended)
        self.assertFalse(reader.expired)


class HiddenAlertTest(unittest.TestCase):
    """El aviso de 'préstamos sobrepasados' SIEMPRE está en el HTML, pero oculto.

    `js-dn ns-dn` = lo muestra el JS cuando procede. Leer su presencia como
    "tiene retrasos" es un falso positivo.
    """

    def test_el_aviso_existe_pero_esta_oculto(self):
        html = load("my_library_renovable.html")
        root = parser.parse(html)
        banner = root.find(predicate=lambda n: n.has_class("lector_sobrePresta"))
        self.assertIsNotNone(banner)
        self.assertTrue(banner.has_class("js-dn"))
        self.assertTrue(banner.has_class("ns-dn"))

    def test_ningun_prestamo_marcado_como_retraso(self):
        loans = parser.parse_loans(load("my_library_renovable.html"), today=TODAY)
        self.assertEqual(len(loans), 2)
        for loan in loans:
            self.assertFalse(loan.overdue)


if __name__ == "__main__":
    unittest.main()