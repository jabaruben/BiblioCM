"""Diagnóstico de solo lectura del catálogo, sin mostrar claves ni URLs de sesión."""
import argparse
import json
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from biblio import parser
from biblio.client import AbsysClient
from biblio.store import Store


def main():
    args_parser = argparse.ArgumentParser(description=__doc__)
    args_parser.add_argument("query")
    args_parser.add_argument("--title", default="")
    args_parser.add_argument("--record", help="Consultar directamente una ficha sin buscar")
    args_parser.add_argument("--label", required=True)
    args_parser.add_argument("--data-dir", default=str(ROOT / ".biblio-data"))
    args = args_parser.parse_args()
    store = Store(Path(args.data_dir) / "biblio.sqlite3")
    try:
        accounts = store.db.execute("SELECT id FROM accounts WHERE lower(label)=lower(?)", (args.label,)).fetchall()
        if len(accounts) != 1:
            raise RuntimeError("La etiqueta debe identificar exactamente una cuenta vinculada.")
        credentials = store.credentials(accounts[0]["id"])
        client = AbsysClient(credentials["card"], credentials["password"])
        if args.record:
            from biblio.models import MarcRecord
            total, records = 1, [MarcRecord(args.record)]
        else:
            total, records = client.search(args.query)
        print(json.dumps({"total": total, "results": [{"id": r.record_id, "title": r.title, "publication": r.publication, "extent": r.extent} for r in records]}, ensure_ascii=True))
        for record in records:
            if args.title and args.title.casefold() not in record.title.casefold():
                continue
            response = client.record(record.record_id)
            root = parser.parse(response.text)
            copies = parser.parse_copies(response.text)
            print(json.dumps({"record": record.record_id, "title": record.title,
                "copy_count": len(copies), "branches": sorted({c.branch for c in copies}),
                "accordion_count": len(root.by_class("copias_accordion")),
                "availability_row_count": len(root.find_all("tr", lambda n: bool(n.attr("data-disp")))),
                "copies": [{"branch": c.branch, "location": c.location, "signature": c.signature,
                            "availability": c.availability, "support": c.support} for c in copies]}, ensure_ascii=True))
            href = parser.link_with_acc(response.text, "193")
            if not href:
                print("Este registro no ofrece un asistente de reservas.")
                continue
            wizard = client._get(urllib.parse.urljoin(response.url, href))
            root = parser.parse(wizard.text)
            public_fields = ("index", "barcode", "library", "branch", "location", "signature", "copy_type", "availability", "row")
            print(json.dumps({"reservable": [{key: copy[key] for key in public_fields} for copy in parser.parse_reservable_copies(wizard.text)]}, ensure_ascii=True))
            form = root.by_id("abnformRes")
            if form:
                for row in form.find_all("tr", lambda n: bool(n.find("input", lambda f: f.attr("name").startswith("rebarc_")))):
                    print(json.dumps({"reservation_row": [{"class": cell.attr("class"), "text": cell.text(),
                        "children": [{"tag": child.tag, "class": child.attr("class"), "text": child.text(),
                            "spans": [{"class": span.attr("class"), "text": span.text()} for span in child.find_all("span")]} for child in cell.children if isinstance(child, parser.Node)]} for cell in row.find_all("td")],
                        "inputs": [{"name": n.attr("name"), "type": n.attr("type"), "disabled": "disabled" in n.attrs} for n in row.find_all("input")]}, ensure_ascii=True))
            filters = root.by_id("abnformResMos")
            if filters:
                print(json.dumps({"filter_fields": [n.attr("name") for n in filters.find_all("input")],
                    "selects": [{"name": s.attr("name"), "options": [{"value": o.attr("value"), "text": o.text(), "selected": "selected" in o.attrs} for o in s.find_all("option")]} for s in filters.find_all("select")]}, ensure_ascii=True))
    finally:
        store.close()


if __name__ == "__main__":
    main()
