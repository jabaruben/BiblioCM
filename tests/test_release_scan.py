"""Escaneo de publicación (TODO-SEC-002): detecta material privado sin imprimirlo.

Estas pruebas usan repositorios Git temporales con contenido ficticio. Los
secretos se construyen por concatenación para que el propio fichero de tests
no contenga cadenas que el escáner marque al revisar el proyecto real.
"""
import io
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import release_scan


def fake_fernet():
    return "gAAAAA" + "D" * 28 + "A" * 12


def fake_github_token():
    return "ghp_" + "A1b2C3d4E5f6" * 3


def fake_private_key():
    return "-----BEGIN " + "RSA PRIVATE KEY-----"


def fake_jwt():
    header = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    payload = "eyJzdWIiOiIxMjM0NTY3ODkwIn0"
    signature = "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJVadQssw5c"
    return f"{header}.{payload}.{signature}"


def fake_opac_session():
    return "/abnetopac/" + "aB3xY7zQ9" * 3


def git(*args, cwd):
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout


def make_repo(files):
    """Crea un repo Git temporal no inicializado (sin commit) con `files`."""
    folder = tempfile.TemporaryDirectory(prefix=".biblio-test-scan-")
    root = Path(folder.name)
    git("init", "-q", cwd=root)
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return folder, root


def findings_text(findings):
    return "\n".join(f"{rule}:{path}:{line}" for rule, path, line in findings)


class ReleaseScanRulesTest(unittest.TestCase):
    """Reglas de material privado sobre ficheros sintéticos."""

    def scan(self, name, content):
        folder, root = make_repo({name: content})
        self.addCleanup(folder.cleanup)
        return release_scan.scan_root(root)

    def test_private_key_block_is_reported(self):
        findings = self.scan("notes.txt", "cabecera\n" + fake_private_key() + "\ncuerpo\n")
        self.assertIn("private-key", [rule for rule, _, _ in findings])

    def test_fernet_token_is_reported(self):
        findings = self.scan("notes.txt", "clave: " + fake_fernet() + "\n")
        self.assertIn("fernet-token", [rule for rule, _, _ in findings])

    def test_github_token_is_reported(self):
        findings = self.scan("notes.txt", "TOKEN=" + fake_github_token() + "\n")
        self.assertIn("provider-token", [rule for rule, _, _ in findings])

    def test_jwt_is_reported(self):
        findings = self.scan("notes.txt", "jwt " + fake_jwt() + "\n")
        self.assertIn("jwt", [rule for rule, _, _ in findings])

    def test_opac_session_path_is_reported(self):
        findings = self.scan("notes.txt", "GET https://x" + fake_opac_session() + "?ACC=101\n")
        self.assertIn("opac-session-path", [rule for rule, _, _ in findings])

    def test_clean_file_has_no_findings(self):
        findings = self.scan("notes.txt", "texto normal con contrase\n")
        self.assertEqual(findings, [])

    def test_fixture_session_tokens_are_not_reported(self):
        # Los tokens ficticios de los fixtures (≤13 caracteres) no son material
        # privado: el umbral de entropía evita falsos positivos sobre el repo.
        findings = self.scan("fixture.html", "…/abnetopac/THREADTOKEN02?ACC=210…\n")
        self.assertEqual(findings, [])


class ReleaseScanReaderIdentityTest(unittest.TestCase):
    """Marcadores OPAC de identidad de lector: solo valores sintéticos.

    El marcador se construye en tiempo de ejecución, igual que los secretos de
    más arriba: el propio fichero de tests no debe contener una línea que el
    escáner marque al revisar el proyecto real.
    """

    def scan(self, name, content):
        folder, root = make_repo({name: content})
        self.addCleanup(folder.cleanup)
        return release_scan.scan_root(root)

    @staticmethod
    def reader_span(field, value):
        return '<span class="' + field + '">' + value + '</span>'

    def test_non_synthetic_reader_card_is_reported(self):
        card = "91" + "2345678"
        findings = self.scan("fixture.html", self.reader_span("lenlec", card) + "\n")
        self.assertIn("opac-reader-identity", [rule for rule, _, _ in findings])

    def test_non_synthetic_name_and_surname_are_reported(self):
        html = "\n".join([
            self.reader_span("nombre", "OTRA" + "PERSONA"),
            self.reader_span("apellidos", "APELLIDOS DE" + " EJEMPLO"),
        ]) + "\n"
        findings = self.scan("fixture.html", html)
        self.assertEqual(
            [rule for rule, _, _ in findings],
            ["opac-reader-identity", "opac-reader-identity"],
        )

    def test_synthetic_reader_values_are_not_reported(self):
        html = "\n".join([
            self.reader_span("lenlec", "1234" + "5678"),
            self.reader_span("lenlec", "2222" + "2222"),
            self.reader_span("lenlec", "02222" + "2222"),
            self.reader_span("nombre", "PERSONA"),
            self.reader_span("apellidos", "DE PRUEBA APELLIDO"),
            self.reader_span("nombre", "PERSONA DE PRUEBA APELLIDO"),
        ]) + "\n"
        self.assertEqual(self.scan("fixture.html", html), [])

    def test_fields_that_are_not_reader_markers_are_not_reported(self):
        html = self.reader_span("tititu", "Título de un libro") + "\n"
        self.assertEqual(self.scan("fixture.html", html), [])

    def test_report_names_rule_path_line_but_never_the_value(self):
        card = "91" + "2345678"
        folder, root = make_repo(
            {"fixture.html": self.reader_span("lenlec", card) + "\n"})
        self.addCleanup(folder.cleanup)
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = release_scan.scan_main(["--root", str(root)])
        output = buffer.getvalue()
        self.assertEqual(code, 1, "un hallazgo debe dar código de salida 1")
        self.assertIn("opac-reader-identity", output)
        self.assertIn("fixture.html:1", output)
        self.assertNotIn(card, output, "el reporte filtró la identidad del lector")
        self.assertNotIn(card[:6], output)


class ReleaseScanLoanIdentifierTest(unittest.TestCase):
    """Identificadores de préstamo/reserva del OPAC: solo valores sintéticos.

    Las marcas se construyen en tiempo de ejecución, por el mismo motivo que los
    secretos de más arriba: el fichero de tests no debe contener una línea que
    el escáner marque al revisar el proyecto real.
    """

    def scan(self, name, content):
        folder, root = make_repo({name: content})
        self.addCleanup(folder.cleanup)
        return release_scan.scan_root(root)

    @staticmethod
    def attribute(name, value):
        return '<li ' + name + '="' + value + '">'

    @staticmethod
    def span(name, value):
        return '<span class="' + name + '">' + value + '</span>'

    @staticmethod
    def field(prefix, value):
        return '<input ' + 'name="' + prefix + value + '"/>'

    @staticmethod
    def cancel_link(value):
        return '<a href="?ACC=238&amp;DI=' + value + '"></a>'

    def test_non_synthetic_loan_barcode_is_reported(self):
        barcode = "90" + "123456789"
        findings = self.scan("fixture.html", self.attribute("data-prbarc", barcode) + "\n")
        self.assertIn("opac-loan-identifier", [rule for rule, _, _ in findings])

    def test_non_synthetic_reservation_id_is_reported(self):
        value = "900" + "0123456"
        findings = self.scan("fixture.html", self.cancel_link(value) + "\n")
        self.assertIn("opac-loan-identifier", [rule for rule, _, _ in findings])

    def test_derived_form_references_are_reported_when_not_synthetic(self):
        value = "90" + "123456789"
        html = "\n".join([
            self.field("CP", value),
            self.attribute("id", "lector_box" + value),
            self.span("prbarc", value),
        ]) + "\n"
        findings = self.scan("fixture.html", html)
        self.assertEqual(
            [rule for rule, _, _ in findings],
            ["opac-loan-identifier"] * 3,
            findings,
        )

    def test_synthetic_loan_identifiers_are_not_reported(self):
        html = "\n".join([
            self.attribute("data-prbarc", "9000000021"),
            self.attribute("data-cobarc", "9000000011"),
            self.attribute("data-prppsq", "9001"),
            self.attribute("data-di", "9000001"),
            self.attribute("id", "lector_box" + "999"),
            self.attribute("id", "abnRenov" + "9000000011"),
            self.field("CP", "9000000011"),
            self.span("prbarc", "999"),
            self.cancel_link("9000001"),
        ]) + "\n"
        self.assertEqual(self.scan("fixture.html", html), [])

    def test_report_names_rule_path_line_but_never_the_identifier(self):
        barcode = "90" + "123456789"
        folder, root = make_repo(
            {"fixture.html": self.attribute("data-prbarc", barcode) + "\n"})
        self.addCleanup(folder.cleanup)
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = release_scan.scan_main(["--root", str(root)])
        output = buffer.getvalue()
        self.assertEqual(code, 1, "un hallazgo debe dar código de salida 1")
        self.assertIn("opac-loan-identifier", output)
        self.assertIn("fixture.html:1", output)
        self.assertNotIn(barcode, output, "el reporte filtró el identificador")
        self.assertNotIn(barcode[:6], output)


class ReleaseScanOutputTest(unittest.TestCase):
    """El reporte nunca imprime el contenido hallado."""

    def test_report_names_rule_path_line_but_never_the_secret(self):
        secret = fake_fernet()
        folder, root = make_repo({"notes.txt": "valor=" + secret + "\n"})
        self.addCleanup(folder.cleanup)
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = release_scan.scan_main(["--root", str(root)])
        output = buffer.getvalue()
        self.assertEqual(code, 1, "un hallazgo debe dar código de salida 1")
        self.assertIn("fernet-token", output)
        self.assertIn("notes.txt", output)
        self.assertNotIn(secret, output, "el reporte filtró material privado")
        # Ni siquiera un fragmento suficiente para reconstruirlo.
        self.assertNotIn(secret[:16], output)

    def test_clean_repo_exits_zero(self):
        folder, root = make_repo({"readme.txt": "hola\n"})
        self.addCleanup(folder.cleanup)
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = release_scan.scan_main(["--root", str(root)])
        self.assertEqual(code, 0, buffer.getvalue())


class ReleaseScanFileRulesTest(unittest.TestCase):
    """Ficheros que nunca deberían publicarse aunque estén trackeados."""

    def test_tracked_secret_key_filename_is_reported(self):
        folder, root = make_repo({"secret.key": "x"})
        self.addCleanup(folder.cleanup)
        git("add", "secret.key", cwd=root)
        findings = release_scan.scan_root(root)
        self.assertIn("secret-file", [rule for rule, _, _ in findings])

    def test_gitignored_data_directory_is_not_scanned(self):
        folder, root = make_repo({
            ".gitignore": ".biblio-data/\n",
            ".biblio-data/secret.key": fake_fernet(),
        })
        self.addCleanup(folder.cleanup)
        findings = release_scan.scan_root(root)
        self.assertEqual(findings, [], "una BD ignorada no forma parte de la publicación")

    def test_tracked_handoff_filename_is_reported(self):
        folder, root = make_repo({"docs/HANDOFF-someone.md": "notas privadas\n"})
        self.addCleanup(folder.cleanup)
        git("add", "docs/HANDOFF-someone.md", cwd=root)
        findings = release_scan.scan_root(root)
        self.assertIn("private-handoff", [rule for rule, _, _ in findings])


class ReleaseScanPathPolicyTest(unittest.TestCase):
    """La lista de rutas permitidas señala entradas nuevas fuera de política."""

    def test_a_path_outside_the_allowlist_is_reported(self):
        folder, root = make_repo({"notes/personal.md": "texto normal\n"})
        self.addCleanup(folder.cleanup)
        findings = release_scan.scan_root(root, allowlist=release_scan.ALLOWED_TOP_LEVEL)
        self.assertEqual([rule for rule, _, _ in findings], ["path-not-allowlisted"])
        self.assertEqual(findings[0][1], "notes/personal.md")

    def test_allowed_top_level_paths_are_not_flagged(self):
        folder, root = make_repo({"docs/notas.md": "texto normal\n", "README.md": "# x\n"})
        self.addCleanup(folder.cleanup)
        findings = release_scan.scan_root(root, allowlist=release_scan.ALLOWED_TOP_LEVEL)
        self.assertEqual(findings, [])

    def test_without_allowlist_only_content_rules_apply(self):
        folder, root = make_repo({"notes/personal.md": "texto normal\n"})
        self.addCleanup(folder.cleanup)
        self.assertEqual(release_scan.scan_root(root), [])


class ReleaseScanRealRepoTest(unittest.TestCase):
    """El propio repositorio publicable debe salir limpio y dentro de política.

    Estas cuatro pruebas inspeccionan el repositorio vivo mediante `git
    ls-files`. En un candidato exportado no hay `.git` —correcto: un candidato
    es material para publicar, no un checkout—, así que ahí se omiten con
    `skipUnless`. Su cobertura en el candidato la aporta
    [test_release_export.py](test_release_export.py), que compara el árbol
    exportado con el set publicable calculado **desde el repositorio real**.
    """

    @classmethod
    def setUpClass(cls):
        cls.in_git_repo = (ROOT / ".git").exists()

    def _require_git(self):
        if not self.in_git_repo:
            self.skipTest("sin .git: fuera del repositorio vivo (candidato exportado)")

    def test_project_publishable_set_is_clean(self):
        self._require_git()
        findings = release_scan.scan_root(ROOT, allowlist=release_scan.ALLOWED_TOP_LEVEL)
        self.assertEqual(
            findings, [],
            "material privado en el set publicable:\n" + findings_text(findings))

    def test_publishable_set_has_only_synthetic_reader_fields(self):
        """Ningún marcador `lenlec`/`nombre`/`apellidos` con valor real."""
        self._require_git()
        findings = [
            (rule, path, line)
            for rule, path, line in release_scan.scan_root(
                ROOT, allowlist=release_scan.ALLOWED_TOP_LEVEL)
            if rule == "opac-reader-identity"
        ]
        self.assertEqual(
            findings, [],
            "identidad de lector no sintética en el set publicable:\n"
            + findings_text(findings))

    def test_publishable_set_has_only_synthetic_loan_ids(self):
        """Ningún código de ejemplar/reserva real en préstamos, reservas o docs."""
        self._require_git()
        findings = [
            (rule, path, line)
            for rule, path, line in release_scan.scan_root(
                ROOT, allowlist=release_scan.ALLOWED_TOP_LEVEL)
            if rule == "opac-loan-identifier"
        ]
        self.assertEqual(
            findings, [],
            "identificador de préstamo/reserva no sintético en el set publicable:\n"
            + findings_text(findings))

    def test_project_publishable_set_is_non_empty(self):
        self._require_git()
        files = release_scan.publishable_files(ROOT)
        self.assertGreater(len(files), 10)
        self.assertIn("biblio/web.py", files)

    def test_project_publishable_set_stays_inside_the_allowlist(self):
        self._require_git()
        files = release_scan.publishable_files(ROOT)
        top = {name.replace("\\", "/").split("/", 1)[0] for name in files}
        self.assertEqual(top - set(release_scan.ALLOWED_TOP_LEVEL), set())

    def test_project_ignored_private_material_is_absent_from_the_set(self):
        self._require_git()
        files = {name.replace("\\", "/") for name in release_scan.publishable_files(ROOT)}
        self.assertNotIn("docs/HANDOFF-SOL.md", files)
        self.assertFalse([name for name in files if name.startswith(".biblio-data/")])
        self.assertFalse([name for name in files if name.endswith(".sqlite3")])
        self.assertFalse([name for name in files if name.startswith(".biblio-test-")])


if __name__ == "__main__":
    unittest.main()
