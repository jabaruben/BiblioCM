"""Valida documentación, requisitos y backlog; --tests cuenta tests sin ejecutarlos."""
from __future__ import annotations

import argparse
import re
import sys
import unittest
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    "README.md", "AGENTS.md", "TODO.md", "docs/README.md", "docs/specification.md",
    "docs/architecture.md", "docs/backend.md", "docs/frontend.md", "docs/api.md",
    "docs/testing.md", "docs/status.md", "docs/operations.md", "docs/decisions.md",
    "docs/incidents.md", "docs/absys-opac-protocol.md",
)
STATES = {"proposed", "pending", "in_progress", "blocked", "done", "cancelled"}
REQ_ID = r"(?:FR|NFR)-[A-Z0-9]+-\d{3}"
TASK_ID = r"TODO-[A-Z0-9]+-\d{3}"
REQ = re.compile(rf"\b{REQ_ID}\b")
TASK = re.compile(rf"\b{TASK_ID}\b")
LINK = re.compile(r"!?\[[^\]\n]*\]\(([^\s)]+)(?:\s+\"[^\"]*\")?\)")


def prose(text):
    return re.sub(r"^```[^\n]*\n.*?^```\s*$", "", text, flags=re.M | re.S)


def anchors(text):
    found = set(re.findall(r'<a\s+id="([^"]+)"', text))
    repeats = {}
    for heading in re.findall(r"^#{1,6}\s+(.+?)\s*$", prose(text), re.M):
        slug = re.sub(r"[^\w\-\s]", "", heading.lower().strip())
        slug = re.sub(r"\s", "-", slug)
        number = repeats.get(slug, 0)
        repeats[slug] = number + 1
        found.add(slug if not number else f"{slug}-{number}")
    return found


def validate():
    errors = []
    for name in REQUIRED:
        if not (ROOT / name).is_file():
            errors.append(f"Missing required document: {name}")
    if errors:
        return errors, ""
    paths = [ROOT / name for name in ("README.md", "AGENTS.md", "TODO.md")]
    paths += sorted((ROOT / "docs").rglob("*.md"))
    texts = {path.resolve(): prose(path.read_text(encoding="utf-8")) for path in paths}
    specification = texts[(ROOT / "docs/specification.md").resolve()]
    definitions = re.findall(rf"^## ({REQ_ID})\s*$", specification, re.M)
    requirements = set(definitions)
    if not requirements:
        errors.append("No requirement definitions")
    if len(requirements) != len(definitions):
        errors.append("Duplicate requirement definitions")

    backlog = texts[(ROOT / "TODO.md").resolve()]
    headings = list(re.finditer(rf"^### ({TASK_ID})\b.*$", backlog, re.M))
    task_ids = [match[1] for match in headings]
    if not task_ids:
        errors.append("No task definitions")
    if len(set(task_ids)) != len(task_ids):
        errors.append("Duplicate task definitions")
    index = {}
    for task_id, state, priority in re.findall(rf"^\| ({TASK_ID}) \| ([a-z_]+) \| (P[123]) \|", backlog, re.M):
        if task_id in index:
            errors.append(f"Duplicate backlog index row: {task_id}")
        index[task_id] = (state, priority)
    if set(index) != set(task_ids):
        errors.append("Backlog index and task definitions differ")
    for position, match in enumerate(headings):
        stop = headings[position + 1].start() if position + 1 < len(headings) else len(backlog)
        block = backlog[match.end():stop]
        field = re.search(r"^\*\*Estado:\*\* `([^`]+)`", block, re.M)
        state = field[1] if field else None
        if state not in STATES:
            errors.append(f"Invalid/missing task state: {match[1]}")
        elif index.get(match[1], (None, None))[0] != state:
            errors.append(f"Index/state mismatch: {match[1]}")
        priority = re.search(r"^\*\*Prioridad:\*\* (P[123])\s*$", block, re.M)
        if not priority or index.get(match[1], (None, None))[1] != priority[1]:
            errors.append(f"Invalid or inconsistent task priority: {match[1]}")
        for label in ("Prioridad", "Tipo", "Responsable", "Actualizado", "Requisitos"):
            if not re.search(rf"^\*\*{label}:\*\* .+", block, re.M):
                errors.append(f"Missing task field {label}: {match[1]}")
        if state == "done" and "Evidencia:" not in block:
            errors.append(f"Done task without evidence: {match[1]}")

    links = 0
    for path, text in texts.items():
        name = path.relative_to(ROOT).as_posix()
        for requirement in set(REQ.findall(text)) - requirements:
            errors.append(f"Undefined requirement {requirement}: {name}")
        for task_id in set(TASK.findall(text)) - set(task_ids):
            errors.append(f"Undefined task {task_id}: {name}")
        for match in LINK.finditer(text):
            url = urlsplit(match[1])
            if url.scheme or url.netloc:
                continue
            target = (path.parent / unquote(url.path)).resolve() if url.path else path
            links += 1
            if not target.is_relative_to(ROOT):
                errors.append(f"Local link outside workspace: {name} -> {match[1]}")
            elif not target.exists():
                errors.append(f"Broken local link: {name} -> {match[1]}")
            elif url.fragment and target.suffix == ".md":
                target_text = texts.get(target) or target.read_text(encoding="utf-8")
                if unquote(url.fragment) not in anchors(target_text):
                    errors.append(f"Unknown anchor: {name} -> {match[1]}")
    summary = f"{len(texts)} documents, {len(requirements)} requirements, {len(task_ids)} tasks, {links} local links"
    return errors, summary


def check_tests():
    sys.path.insert(0, str(ROOT))
    loader = unittest.TestLoader()
    counts = {}
    for path in sorted((ROOT / "tests").glob("test_*.py")):
        module = "tests." + path.stem
        counts[module] = loader.loadTestsFromName(module).countTestCases()
    if loader.errors:
        return ["Test modules could not be loaded; install project dependencies and inspect unittest discovery."], ""
    total = sum(counts.values())
    status = (ROOT / "docs/status.md").read_text(encoding="utf-8")
    expected = re.search(r"Suite estándar: \*\*(\d+) tests", status)
    errors = []
    if not expected or int(expected[1]) != total:
        errors.append(f"Documented test baseline differs from discovery: actual {total}")
    for module, count in counts.items():
        if not re.search(rf"\| `{re.escape(module)}` \| {count} \|", status):
            errors.append(f"Documented suite count differs: {module} = {count}")
    return errors, f"{total} discoverable tests (counted, not executed)"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tests", action="store_true", help="Comprobar recuento de unittest documentado, sin ejecutar tests")
    args = parser.parse_args()
    errors, summary = validate()
    if args.tests and not errors:
        test_errors, test_summary = check_tests()
        errors.extend(test_errors)
        summary += "; " + test_summary
    for error in errors:
        print("ERROR: " + error)
    if errors:
        return 1
    print("Docs OK: " + summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
