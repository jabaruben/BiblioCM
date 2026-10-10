"""Renovaciones: sesión del POST, fecha definitiva y una única mutación."""
import datetime as dt
import unittest
from pathlib import Path
from unittest.mock import Mock

from biblio.client import AbsysClient, AuthError, OperationRefused
from biblio.http import Response

TODAY = dt.date(2026, 10, 5)
BARCODE = "9000000011"
BASE = "https://example.test/biblio_publicas/cgi-bin/abnetopac/"


class RenewalClientTests(unittest.TestCase):
    def setUp(self):
        self.before = (Path(__file__).with_name("fixtures") / "my_library_renovable.html").read_text(encoding="utf-8")
        self.final_date = "20/10/2026"
        self.final_count = 1
        self.fresh = False
        self.posts = []
        self.gets = []
        intermediate = self.updated("12/10/2026", 1)
        self.reply = Response(BASE + "POSTTHREAD/NT3", intermediate)

        class Http:
            def get(inner_self, url):
                self.gets.append(url)
                if self.fresh:
                    html = self.updated(self.final_date, self.final_count).replace("THREADTOKEN01", "FRESH_AUTH")
                elif self.posts:
                    html = intermediate
                else:
                    html = self.before
                return Response(url, html)

            def post(inner_self, url, fields):
                self.posts.append((url, dict(fields)))
                return self.reply

        self.client = AbsysClient("fake", "fake", http=Http())
        self.client._base = BASE + "THREADTOKEN01/NT3"

        def login():
            self.fresh = True
            self.client._base = BASE + "FRESH_AUTH/NT3"
            self.client._acc = {}

        self.client.login = Mock(side_effect=login)
        self.client._refresh = Mock(wraps=self.client._refresh)

    def updated(self, date, count):
        return self.before.replace("05/10/2026", date).replace(
            '<span class="prnren">0</span>', f'<span class="prnren">{count}</span>', 1)

    def test_intermediate_seven_day_state_is_not_reported_as_final(self):
        result = self.client.renew(BARCODE, today=TODAY)
        self.assertTrue(result.ok)
        self.assertEqual(result.previous_due, dt.date(2026, 10, 5))
        self.assertEqual(result.new_due, dt.date(2026, 10, 20))
        self.assertEqual(result.renewals_used, 1)
        self.assertIn("20/10/2026", result.message)
        self.assertNotIn("12/10/2026", result.message)
        self.assertEqual((result.new_due - TODAY).days, 15)
        self.client.login.assert_called_once_with()
        self.assertIn("FRESH_AUTH", self.gets[-1])
        self.assertEqual(len(self.posts), 1)
        self.assertEqual(self.posts[0][1], {"ACC": "228", "CP9000000011": "1"})

    def test_post_response_is_adopted_instead_of_the_old_form_page(self):
        self.client.renew(BARCODE, today=TODAY)
        self.client._refresh.assert_any_call(self.reply)

    def test_unchanged_due_date_is_not_a_success(self):
        self.final_date = "05/10/2026"
        with self.assertRaisesRegex(OperationRefused, "no confirmó"):
            self.client.renew(BARCODE, today=TODAY)
        self.assertEqual(len(self.posts), 1)

    def test_shortened_due_date_is_not_a_success(self):
        self.final_date = "04/10/2026"
        with self.assertRaisesRegex(OperationRefused, "no confirmó"):
            self.client.renew(BARCODE, today=TODAY)

    def test_advanced_due_without_renewal_counter_change_is_not_confirmation(self):
        self.final_count = 0
        with self.assertRaisesRegex(OperationRefused, "no confirmó"):
            self.client.renew(BARCODE, today=TODAY)

    def test_explicit_refusal_is_reported_when_the_loan_did_not_change(self):
        self.reply = Response(BASE + "POSTTHREAD/NT3", '<p class="c-alert">No se puede renovar</p>')
        self.final_date, self.final_count = "05/10/2026", 0
        with self.assertRaisesRegex(OperationRefused, "No se puede renovar"):
            self.client.renew(BARCODE, today=TODAY)

    def test_no_available_form_never_posts_or_reauthenticates(self):
        with self.assertRaisesRegex(OperationRefused, "no se puede renovar aún"):
            self.client.renew("9000000012", today=TODAY)
        self.assertEqual(self.posts, [])
        self.client.login.assert_not_called()

    def test_unknown_barcode_never_posts(self):
        with self.assertRaisesRegex(OperationRefused, "no está en tus préstamos"):
            self.client.renew("999", today=TODAY)
        self.assertEqual(self.posts, [])

    def test_verification_failure_never_repeats_the_renewal_post(self):
        self.client.login.side_effect = AuthError("verification unavailable")
        with self.assertRaises(AuthError):
            self.client.renew(BARCODE, today=TODAY)
        self.assertEqual(len(self.posts), 1)


if __name__ == "__main__":
    unittest.main()
