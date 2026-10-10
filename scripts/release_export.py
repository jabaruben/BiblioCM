"""Candidato público limpio: exportar y validar antes de publicar (TODO-PUB-002).

Copia a un directorio **exactamente** los ficheros que Git publicaría (el set
publicable: rastreados y no ignorados) y valida sobre ese candidato que:

1. no falta ninguno y **no se cuela ningún fichero ignorado** — nunca
   `.biblio-data/`, `docs/HANDOFF-SOL.md`, `.biblio-test-*`, `*.sqlite3`,
   `.env` ni claves—;
2. el escáner de publicación sale limpio sobre el candidato, con su lista de
   rutas permitidas ([release_scan.py](release_scan.py));
3. `check_docs.py --tests` pasa **dentro** del candidato: los enlaces, anclas y
   recuentos de la documentación no dependen de ningún fichero ignorado;
4. el paquete se importa desde el candidato (`import biblio`, `biblio.web`,
   `biblio.cli`, `biblio.store`);
5. `node --check` de `app.js` y `sw.js` (omitido, no pasado, si no hay Node);
6. con `--run-tests`, la suite unittest completa dentro del candidato.

La exportación es una **validación local**: no crea commit, no hace push, no
publica y no toca el repositorio. Por defecto el candidato se borra al
terminar; `--keep` lo conserva para revisarlo a mano.

Uso: python scripts/release_export.py [--out RUTA] [--run-tests]
     [--no-checks] [--keep] [--root RUTA]
Código de salida: 0 todo correcto, 1 con fallos, 2 error de ejecución.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import release_scan  # noqa: E402

# Nombres/prefijos que nunca pueden aparecer en un candidato limpio, aunque
# alguien los copie a mano en el directorio de salida.
FORBIDDEN = (
    ("directorio de datos", lambda name: name.startswith(".biblio-data/")),
    ("temporales de pruebas", lambda name: "/.biblio-test-" in f"/{name}"),
    ("bases SQLite", lambda name: name.endswith(".sqlite3")),
    ("handoff legado", lambda name: name.startswith("docs/HANDOFF")),
    ("material de claves", lambda name: name.endswith((".pem", ".key", ".pfx", ".p12"))
     or name.endswith(".env") or "/.env" in name or name.endswith("secret.key")),
    ("caché de Python", lambda name: "/__pycache__/" in f"/{name}"),
)


def export_files(root, out):
    """Copia el set publicable a `out`; devuelve los nombres copiados."""
    files = release_scan.publishable_files(root)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    copied = []
    for relative in files:
        source = Path(root) / relative
        target = out / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append(relative.replace("\\", "/"))
    return sorted(copied)


def forbidden_in(out, copied):
    """`(motivo, ruta)` de material prohibido presente en el candidato."""
    problems = []
    present = set(copied) | {
        path.relative_to(out).as_posix() for path in Path(out).rglob("*") if path.is_file()}
    for name in sorted(present):
        for reason, matches in FORBIDDEN:
            if matches(name):
                problems.append((reason, name))
    return problems


def _clean(text):
    """Normaliza la salida de un paso para imprimirla en la consola de la persona.

    Sustituye los caracteres que la consola de Windows (cp1252) no puede
    codificar —p. ej. las comillas angulares «» o una marca de verificación—
    para que un fallo se pueda leer completo en lugar de romper el informe.
    """
    return text.encode("cp1252", "replace").decode("cp1252")


def run_step(name, command, cwd):
    """Ejecuta un paso finito; devuelve `(estado, detalle)`."""
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=900)
    detail = (result.stdout + result.stderr).strip().splitlines()
    tail = detail[-1] if detail else "(sin salida)"
    return ("PASS" if result.returncode == 0 else "FAIL",
            _clean(f"{name}: exit {result.returncode} - {tail}"))


def optional_step(name, command, cwd):
    """Igual que `run_step`, pero reporta NOT_RUN si el comando no existe."""
    if shutil.which(command[0]) is None and not command[0].endswith(".exe"):
        return "NOT_RUN", _clean(
            f"{name}: «{command[0]}» no está instalado; omitido, no contado como pase")
    return run_step(name, command, cwd)


def validate(out, run_tests=True):
    """Comprobaciones sobre el candidato ya exportado; lista de resultados."""
    out = Path(out)
    python = sys.executable
    # (nombre, comando, obligatorio): Node es opcional en algunas máquinas y,
    # si falta, el paso queda NOT_RUN —nunca un pase—.
    # El escáner de contenido se aplica desde aquí con `scan_root` y la lista
    # copiada: el candidato no es un repo Git, así que su propio
    # `release_scan.py` (que lista con `git ls-files`) no podría ejecutarse allí.
    steps = [
        ("check-docs", [python, "scripts/check_docs.py", "--tests"], True),
        ("import-paquete", [python, "-c",
                            "import biblio, biblio.cli, biblio.store, biblio.web"], True),
        ("node-app.js", ["node", "--check", "biblio/static/app.js"], False),
        ("node-sw.js", ["node", "--check", "biblio/static/sw.js"], False),
    ]
    if run_tests:
        steps.append(("suite-unittest",
                      [python, "-m", "unittest", "discover", "-s", "tests", "-t", "."], True))
    results = []
    for name, command, required in steps:
        if required:
            results.append(run_step(name, command, out))
        else:
            results.append(optional_step(name, command, out))
    return results


def export_main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Raíz del repositorio")
    parser.add_argument("--out", default=None,
                        help="Directorio del candidato (default: temporal del sistema)")
    parser.add_argument("--run-tests", action="store_true",
                        help="Ejecutar también la suite unittest dentro del candidato")
    parser.add_argument("--no-checks", action="store_true",
                        help="Solo exportar y validar ausencia de ignorados")
    parser.add_argument("--keep", action="store_true",
                        help="Conservar el candidato al terminar")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    if args.out is None:
        out = Path(tempfile.mkdtemp(prefix="biblio-public-"))
        temporary = True
    else:
        out = Path(args.out).resolve()
        if out == root or root in out.parents:
            print("release-export: el destino no puede estar dentro del repositorio")
            return 2
        temporary = False
    try:
        copied = export_files(root, out)
    except (OSError, RuntimeError) as exc:
        print(f"release-export: no se pudo exportar: {exc}")
        return 2
    print(f"release-export: {len(copied)} ficheros en {out}")
    failures = 0
    problems = forbidden_in(out, copied)
    if problems:
        failures += 1
        for reason, name in problems:
            print(f"FAIL ausencia-ignorados: {reason}: {name}")
    else:
        print(f"PASS ausencia-ignorados: sin material ignorado ni privado en {len(copied)} ficheros")
    listed = {path.relative_to(out).as_posix() for path in out.rglob("*") if path.is_file()}
    if listed != set(copied):
        failures += 1
        print(f"FAIL conjunto-exacto: sobran {sorted(listed - set(copied))} "
              f"faltan {sorted(set(copied) - listed)}")
    else:
        print("PASS conjunto-exacto: el candidato es exactamente el set publicable")
    if not args.no_checks:
        findings = release_scan.scan_root(out, copied, allowlist=release_scan.ALLOWED_TOP_LEVEL)
        if findings:
            failures += 1
            for rule, path, line in findings:
                print(f"FAIL release-scan: {rule} {path}:{line}" if line else
                      f"FAIL release-scan: {rule} {path}")
        else:
            print("PASS release-scan: 0 hallazgos sobre el candidato")
        for status, detail in validate(out, run_tests=args.run_tests):
            if status != "PASS":
                failures += 1
            print(f"{status} {detail}")
    if args.keep or not temporary:
        print(f"release-export: candidato conservado en {out}")
    else:
        shutil.rmtree(out, ignore_errors=True)
        print("release-export: candidato temporal eliminado (usa --keep para conservarlo)")
    if failures:
        print(f"release-export: {failures} comprobaciones fallidas")
        return 1
    print("release-export: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(export_main())
