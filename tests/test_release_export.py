"""Candidato público limpio (TODO-PUB-002): exportar y validar sin ignorados.

Usa repos Git temporales con material privado **ignorado** para comprobar que
la exportación no lo copia, y valida además el candidato real del proyecto
(documentación, escaneo e importación) sin ejecutar la suite completa.
"""
import io
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import release_export


def git(*args, cwd):
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout


def make_repo(files):
    """Repo Git temporal no inicializado (sin commit) con `files`."""
    folder = tempfile.TemporaryDirectory(prefix=".biblio-test-export-")
    root = Path(folder.name)
    git("init", "-q", cwd=root)
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return folder, root


def run_export(argv):
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = release_export.export_main(argv)
    return code, buffer.getvalue()


class ReleaseExportSelectionTest(unittest.TestCase):
    """La exportación copia solo el set publicable y nunca material ignorado."""

    PRIVATE = {
        ".gitignore": ".biblio-data/\ndocs/HANDOFF-SOL.md\n*.sqlite3\n",
        ".biblio-data/secret.key": "clave privada local\n",
        ".biblio-data/biblio.sqlite3": "binario de datos\n",
        "docs/HANDOFF-SOL.md": "handoff con datos personales\n",
        "notas.sqlite3": "base suelta\n",
        "README.md": "# público\n",
        "docs/estado.md": "documento público\n",
    }

    def test_ignored_private_files_are_never_copied(self):
        folder, root = make_repo(self.PRIVATE)
        self.addCleanup(folder.cleanup)
        out = Path(tempfile.mkdtemp(prefix=".biblio-test-out-"))
        self.addCleanup(shutil.rmtree, out, ignore_errors=True)
        code, output = run_export(["--root", str(root), "--out", str(out), "--no-checks"])
        self.assertEqual(code, 0, output)
        copied = sorted(path.relative_to(out).as_posix() for path in out.rglob("*")
                        if path.is_file())
        self.assertEqual(copied, [".gitignore", "README.md", "docs/estado.md"])
        self.assertIn("PASS ausencia-ignorados", output)
        self.assertIn("PASS conjunto-exacto", output)

    def test_private_material_planted_in_the_destination_is_flagged(self):
        folder, root = make_repo({"README.md": "# público\n"})
        self.addCleanup(folder.cleanup)
        out = Path(tempfile.mkdtemp(prefix=".biblio-test-out-"))
        self.addCleanup(shutil.rmtree, out, ignore_errors=True)
        planted = out / "docs" / "HANDOFF-SOL.md"
        planted.parent.mkdir(parents=True, exist_ok=True)
        planted.write_text("no debería estar\n", encoding="utf-8")
        code, output = run_export(["--root", str(root), "--out", str(out), "--no-checks"])
        self.assertEqual(code, 1, output)
        self.assertIn("FAIL ausencia-ignorados", output)
        self.assertIn("handoff", output)

    def test_a_destination_inside_the_repository_is_refused(self):
        code, output = run_export(["--root", str(ROOT), "--out", str(ROOT / "salida"),
                                   "--no-checks"])
        self.assertEqual(code, 2, output)
        self.assertIn("dentro del repositorio", output)
        self.assertFalse((ROOT / "salida").exists())


class ReleaseExportCandidateTest(unittest.TestCase):
    """El candidato real del proyecto pasa documentación, escaneo e importación.

    Requiere el repositorio vivo con `.git` (para calcular el set publicable).
    En un candidato exportado no hay `.git`, así que se omite: exportar dentro
    de una exportación carece de sentido, y el propio candidato ya probó estas
    mismas comprobaciones al crearse.
    """

    def test_the_real_candidate_is_valid_without_ignored_files(self):
        if not (ROOT / ".git").exists():
            self.skipTest("sin .git: fuera del repositorio vivo (candidato exportado)")
        out = Path(tempfile.mkdtemp(prefix=".biblio-test-candidate-"))
        self.addCleanup(shutil.rmtree, out, ignore_errors=True)
        code, output = run_export(["--root", str(ROOT), "--out", str(out)])
        self.assertEqual(code, 0, output)
        self.assertIn("PASS ausencia-ignorados", output)
        self.assertIn("PASS conjunto-exacto", output)
        self.assertIn("PASS release-scan", output)
        self.assertIn("PASS check-docs", output)
        self.assertIn("PASS import-paquete", output)
        # El handoff legado y la base local no existen en el candidato.
        self.assertFalse((out / "docs" / "HANDOFF-SOL.md").exists())
        self.assertFalse((out / ".biblio-data").exists())
        self.assertFalse(list(out.rglob("*.sqlite3")))


if __name__ == "__main__":
    unittest.main()
