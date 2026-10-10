"""Escaneo de secretos previo a publicar (TODO-SEC-002 / TODO-PUB-002 / ADR-016).

Recorre los ficheros que Git publicaría (rastreados y no ignorados), aplica
reglas de material privado y una **lista de rutas permitidas** de primer nivel,
y reporta **solo regla + ruta + línea**: nunca imprime el contenido encontrado.
Es un guardia previo a publicar, no una auditoría de seguridad completa, y una
expresión regular nunca es una prueba de privacidad: complementa la revisión
manual registrada en la tarea de publicación.

La regla `opac-reader-identity` (TODO-PRIV-001) es **semántica y acotada**: solo
comprueba que los marcadores de identidad de lector del OPAC (`lenlec`,
`nombre`, `apellidos`) lleven valores sintéticos declarados en
`SYNTHETIC_READER_VALUES`. La regla `opac-loan-identifier` hace lo propio con
los códigos de ejemplar y de reserva del OPAC (`data-prbarc`, `data-cobarc`,
`data-prppsq`, `data-di`, `prbarc`, `CP<código>`, `lector_box…`, `abnRenov…`,
`lector_renovMen…`, `DI=`) frente a `SYNTHETIC_LOAN_IDS`: son historiales
personales de préstamo/reserva. Ninguna de las dos es un detector de datos
personales arbitrarios: otro dato personal que no use esos marcadores queda
fuera de su alcance.

Uso: python scripts/release_scan.py [--root RUTA] [--no-allowlist]
Código de salida: 0 limpio, 1 con hallazgos, 2 error de ejecución.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

MAX_BYTES = 5_000_000

# Exclusiones explícitas del recorrido de contenido (las reglas de **nombre**
# sí se aplican a todos los ficheros del set publicable):
# - ficheros mayores que `MAX_BYTES`: solo reglas de nombre;
# - binarios (NUL en los primeros 8 KB): solo reglas de nombre.
EXCLUDED_BY_SIZE = f">{MAX_BYTES} bytes"
EXCLUDED_BINARY = "NUL en los primeros 8 KB"

# Lista de rutas permitidas: solo estas entradas de primer nivel pueden
# publicarse. Una entrada nueva fuera de esta lista se reporta como
# `path-not-allowlisted` aunque su contenido sea limpio: es la barrera contra
# un fichero inesperado (notas personales, exportaciones, handoffs) que nadie
# revisó. Añadir un nombre aquí es una decisión explícita de la tarea que lo
# introduce.
ALLOWED_TOP_LEVEL = frozenset({
    ".github", ".gitignore", "AGENTS.md", "LICENSE", "README.md", "SECURITY.md",
    "TODO.md", "biblio", "docs", "pyproject.toml", "scripts", "tests",
})

# Reglas sobre contenido: umbral de entropía pensado para no marcar los tokens
# ficticios cortos de los fixtures (THREADTOKEN02 y similares, ≤13 caracteres).
RULES = (
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("fernet-token", re.compile(r"\bgAAAAA[A-Za-z0-9_=-]{20,}")),
    ("provider-token", re.compile(
        r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}"
        r"|github_pat_[A-Za-z0-9_]{20,}"
        r"|AKIA[0-9A-Z]{16}\b"
        r"|AIza[0-9A-Za-z_-]{35}\b"
        r"|xox[baprs]-[A-Za-z0-9-]{10,})")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")),
    ("opac-session-path", re.compile(r"/abnetopac/[A-Za-z0-9]{16,}")),
)

# Regla semántica de identidad de lector (TODO-PRIV-001): los marcadores del
# OPAC `lenlec`, `nombre` y `apellidos` solo admiten valores sintéticos. La
# lista es deliberadamente explícita: añadir el valor de un fixture nuevo es una
# decisión revisada de la tarea que lo introduce, y un valor no listado se
# reporta igual que el resto de hallazgos (regla, ruta y línea, nunca el dato).
# Su alcance termina aquí: **no** es un detector de datos personales
# arbitrarios, solo comprueba estos marcadores.
READER_MARKERS = frozenset({"lenlec", "nombre", "apellidos"})

SYNTHETIC_READER_VALUES = frozenset({
    # carnés sintéticos (con y sin relleno de ceros)
    "12345678", "22222222", "022222222",
    # nombre en un solo span / nombre partido en dos spans (nombre + apellidos)
    "PERSONA DE PRUEBA APELLIDO", "PERSONA", "DE PRUEBA APELLIDO",
})

READER_FIELD = re.compile(r'<span\b[^>]*class="([^"]*)"[^>]*>([^<]*)</span>')


def reader_identity_finding(line):
    """`True` si un marcador de identidad lleva un valor que no es sintético."""
    for match in READER_FIELD.finditer(line):
        if not READER_MARKERS.intersection(match[1].split()):
            continue
        value = match[2].strip()
        if value and value not in SYNTHETIC_READER_VALUES:
            return True
    return False


# Regla semántica de identificadores de préstamo/reserva (TODO-PRIV-001): los
# códigos de ejemplar y de reserva del OPAC son historiales personales, aunque
# el bloque del lector sea sintético, así que solo se admiten los valores de
# `SYNTHETIC_LOAN_IDS`. Se comprueban las marcas canónicas **y** las referencias
# derivadas que repiten el mismo código (`CP<código>`, `lector_box…`,
# `abnRenov…`, `lector_renovMen…`, `DI=`), de modo que un fixture no puede
# conservar un código real detrás de un identificador generado. Solo se juzgan
# valores **todos dígitos** (el contrato dice que estos IDs son strings de
# dígitos): los marcadores con un placeholder como `<prbarc>` no son datos.
# Mismo alcance acotado que la regla anterior: **no** es un detector de datos
# personales arbitrarios, y no cubre los identificadores de ficha del catálogo
# (`TITN`, `data-bc`, `rebarc_`), que son inventario público.
LOAN_ID_FIELD = re.compile(
    r'\bdata-(?:prbarc|cobarc|prppsq|di)="([^"]*)"'
    r'|<span class="prbarc">([^<]*)</span>'
    r'|name="CP([^"]*)"'
    r'|id="(?:lector_box|abnRenov|lector_renovMen)([^"]*)"'
    r'|\bDI=(\d+)')

SYNTHETIC_LOAN_IDS = frozenset({
    "999",                      # fila de préstamo de my_library_with_reservation
    "9001",                     # `data-prppsq` (secuencia)
    "9000001",                  # id de reserva (`data-di` / `DI=`)
    "9000000002",               # formulario de renovación en docstrings/docs
    "9000000011", "9000000012",  # my_library_renovable
    "9000000021", "9000000022", "9000000023",  # my_library_loans
})


def loan_identifier_finding(line):
    """`True` si una marca de préstamo/reserva lleva un ID que no es sintético."""
    for match in LOAN_ID_FIELD.finditer(line):
        value = next(group for group in match.groups() if group is not None)
        if value.isdigit() and value not in SYNTHETIC_LOAN_IDS:
            return True
    return False


# Reglas sobre el nombre publicable: ficheros de datos/claves que no deberían
# viajar en el repositorio aunque alguien quite una línea del .gitignore.
NAME_RULES = (
    ("secret-file", re.compile(
        r"(^|/)(secret\.key|\.env(\..+)?|id_rsa|id_ed25519|.+\.pem|.+\.pfx"
        r"|.+\.p12|.+\.sqlite3|credentials\.json)$", re.I)),
    # Handoff legado con datos personales (docs/HANDOFF-SOL.md está ignorado);
    # si alguien lo trackea o copia con otro nombre, el escáner lo señala.
    ("private-handoff", re.compile(r"(^|/)HANDOFF[^/]*\.md$", re.I)),
)


def publishable_files(root):
    """Ficheros que Git publicaría desde `root` (rastreados y no ignorados)."""
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root, capture_output=True)
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git ls-files falló: {detail or 'error desconocido'}")
    return sorted(
        name.decode("utf-8", errors="replace")
        for name in result.stdout.split(b"\0") if name)


def scan_root(root, files=None, allowlist=None):
    """Devuelve [(regla, ruta, línea|None)] para el set publicable de `root`.

    `allowlist` (p. ej. `ALLOWED_TOP_LEVEL`) añade una política de rutas:
    cualquier entrada de primer nivel fuera de la lista produce el hallazgo
    `path-not-allowlisted`. `None` deja el escáner solo con sus reglas.
    """
    root = Path(root)
    paths = files if files is not None else publishable_files(root)
    findings = []
    for relative in paths:
        posix = relative.replace("\\", "/")
        if allowlist is not None and posix.split("/", 1)[0] not in allowlist:
            findings.append(("path-not-allowlisted", posix, None))
        for name, pattern in NAME_RULES:
            if pattern.search(posix):
                findings.append((name, posix, None))
        path = root / relative
        if not path.is_file() or path.stat().st_size > MAX_BYTES:
            continue  # exclusión por tamaño: solo reglas de nombre
        data = path.read_bytes()
        if b"\0" in data[:8192]:
            continue  # binario: solo se le aplican las reglas de nombre
        text = data.decode("utf-8", errors="replace")
        for line_number, line in enumerate(text.splitlines(), 1):
            for name, pattern in RULES:
                if pattern.search(line):
                    findings.append((name, posix, line_number))
            if reader_identity_finding(line):
                findings.append(("opac-reader-identity", posix, line_number))
            if loan_identifier_finding(line):
                findings.append(("opac-loan-identifier", posix, line_number))
    return findings


def scan_main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Raíz del repositorio a escanear")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    try:
        files = publishable_files(root)
    except (OSError, RuntimeError) as exc:
        print(f"release-scan: no se pudo listar el set publicable: {exc}")
        return 2
    findings = scan_root(root, files)
    for rule, path, line in findings:
        location = f"{path}:{line}" if line is not None else path
        print(f"HALLAZGO {rule} {location}")
    print(f"release-scan: {len(files)} ficheros, {len(findings)} hallazgos")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(scan_main())
