"""Regresiones del asistente de reservas: HTML completo e índices del portal."""
import unittest
from pathlib import Path
from unittest.mock import Mock

from biblio import parser
from biblio.client import AbsysClient, OperationRefused
from biblio.http import Response
from biblio.models import Library, Reader, Reservation

FIXTURE = Path(__file__).with_name("fixtures") / "reservable_copies.html"


class ReservationParserTests(unittest.TestCase):
    def setUp(self):
        self.html = FIXTURE.read_text(encoding="utf-8")
        self.copies = parser.parse_reservable_copies(self.html)

    def test_complete_rows_without_markup_or_session_urls(self):
        first = self.copies[0]
        self.assertEqual(first["library"], "MÓSTOLES. Bibliotecas Municipales")
        self.assertEqual(first["branch"], "B. Móstoles CENTRAL ALMUDENA GRANDES")
        self.assertEqual(first["location"], "Sala Infantil")
        self.assertEqual(first["signature"], "JUE SWI ley")
        self.assertEqual(first["copy_type"], "Juegos de consola")
        self.assertEqual(first["availability"], "Disponible después de 15/10/2026")
        for copy in self.copies:
            for unwanted in ("SESSIONTOKEN", "abnetopac", "<", "copiasRes_", "Solicitar", "Biblioteca / Sucursal", "Localización / Signatura"):
                self.assertNotIn(unwanted, copy["row"])

    def test_nonconsecutive_indices_are_not_lost_or_renumbered(self):
        self.assertEqual([copy["index"] for copy in self.copies], [1, 3])
        self.assertEqual([copy["barcode"] for copy in self.copies], ["9000000001", "9000000003"])
        self.assertEqual(self.copies[1]["sequence"], "30")
        self.assertEqual(self.copies[1]["branch"], "José Luis Sampedro")

    def test_hold_count_is_preserved_without_script_contents(self):
        self.assertEqual(self.copies[1]["availability"], "Disponible después de 13/10/2026 Nº de reservas: 1")
        self.assertNotIn("template", self.copies[1]["row"])

    def test_long_text_is_not_truncated_at_arbitrary_html_boundaries(self):
        name = "Biblioteca " + "Municipal " * 45
        copies = parser.parse_reservable_copies(self.html.replace("B. Móstoles CENTRAL ALMUDENA GRANDES", name))
        self.assertEqual(copies[0]["branch"], name.strip())
        self.assertIn("Disponible después de 15/10/2026", copies[0]["row"])

    def test_empty_or_missing_form(self):
        self.assertEqual(parser.parse_reservable_copies("<p>Sin formulario</p>"), [])
        self.assertEqual(parser.parse_reservable_copies('<form id="abnformRes"></form>'), [])

    def test_no_double_quote_dependency(self):
        copies = parser.parse_reservable_copies(self.html.replace('"', "'"))
        self.assertEqual(copies[0]["branch"], self.copies[0]["branch"])
        self.assertEqual([copy["index"] for copy in copies], [1, 3])

    def test_missing_table_row_still_preserves_form_identifiers(self):
        html = '<form id="abnformRes"><input name="rebarc_7" value="700"></form>'
        copies = parser.parse_reservable_copies(html)
        self.assertEqual(copies[0]["index"], 7)
        self.assertEqual(copies[0]["barcode"], "700")
        self.assertEqual(copies[0]["row"], "")

    def test_client_uses_full_wizard_and_all_indices(self):
        class Http:
            def get(inner_self, url):
                text = self.html if "ACC=193" in url else '<a href="?ACC=193">Solicitar reserva</a>'
                return Response(url, text)

        client = AbsysClient("fake", "fake", http=Http())
        client._base = "https://example.test/cgi-bin/abnetopac/SESSIONTOKEN/NT4"
        copies = client.reservable_copies("2261318")
        self.assertEqual([copy["index"] for copy in copies], [1, 3])
        self.assertEqual(copies[0]["branch"], self.copies[0]["branch"])


class ReservationClientTests(unittest.TestCase):
    def setUp(self):
        fixture = FIXTURE.read_text(encoding="utf-8")
        self.posts = []
        self.post_response = '<p class="varJSONmain">Reserva realizada</p>'

        class Http:
            def get(inner_self, url):
                text = fixture if "ACC=193" in url else '<a href="?ACC=193">Solicitar reserva</a>'
                return Response(url, text)

            def post(inner_self, url, payload):
                self.posts.append(payload)
                return Response(url, self.post_response)

        self.client = AbsysClient("fake", "fake", http=Http())
        self.client._base = "https://example.test/cgi-bin/abnetopac/SESSIONTOKEN/NT4"
        self.reader = Reader("fake", "Lector", False, False, None)
        self.created = Reservation("42", "Leyendas Pokémon : Z-A", "2261318", "Pendiente", None, None,
                                   "JUE SWI ley", "Central Almudena Grandes", "1")
        self.client.my_library = Mock(side_effect=[Library(self.reader, [], []), Library(self.reader, [], [self.created])])

    def test_success_requires_a_new_reservation_and_only_sends_one_copy(self):
        message = self.client.reserve("2261318", 1, barcode="9000000001")
        self.assertIn("Leyendas Pokémon : Z-A", message)
        self.assertIn("Central Almudena Grandes", message)
        self.assertEqual(self.client.my_library.call_count, 2)
        self.assertEqual(self.posts[0]["NCOP"], "1")
        self.assertEqual(self.posts[0]["rebarc_1"], "9000000001")
        self.assertNotIn("rebarc_3", self.posts[0])
        self.assertNotIn("xcheck_3", self.posts[0])

    def test_message_dictionary_does_not_confirm_success(self):
        self.client.my_library = Mock(return_value=Library(self.reader, [], []))
        with self.assertRaisesRegex(OperationRefused, "no confirmó"):
            self.client.reserve("2261318", 1)

    def test_existing_reservation_does_not_confirm_another_creation(self):
        self.client.my_library = Mock(return_value=Library(self.reader, [], [self.created]))
        with self.assertRaisesRegex(OperationRefused, "no confirmó"):
            self.client.reserve("2261318", 1)

    def test_new_reservation_for_a_different_record_is_not_confirmation(self):
        self.created.record_id = "12345"
        with self.assertRaisesRegex(OperationRefused, "no confirmó"):
            self.client.reserve("2261318", 1)

    def test_explicit_portal_error_is_reported(self):
        self.post_response = '<p class="c-alert">No se puede reservar este ejemplar</p>'
        with self.assertRaisesRegex(OperationRefused, "No se puede reservar"):
            self.client.reserve("2261318", 1)
        self.assertEqual(self.client.my_library.call_count, 1)

    def test_sparse_cli_index_is_preserved(self):
        self.client.reserve("2261318", 3)
        self.assertEqual(self.posts[0]["rebarc_3"], "9000000003")
        self.assertEqual(self.posts[0]["xcheck_3"], "1")
        self.assertNotIn("rebarc_1", self.posts[0])

    def test_selected_barcode_overrides_a_stale_index(self):
        self.client.reserve("2261318", 1, barcode="9000000003")
        self.assertEqual(self.posts[0]["rebarc_3"], "9000000003")
        self.assertNotIn("rebarc_1", self.posts[0])

    def test_copy_no_longer_reservable_never_posts_a_different_copy(self):
        with self.assertRaisesRegex(OperationRefused, "ya no admite reserva"):
            self.client.reserve("2261318", 1, barcode="9000000999")
        self.assertEqual(self.posts, [])


if __name__ == "__main__":
    unittest.main()
