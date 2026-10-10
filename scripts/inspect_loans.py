"""Consulta fechas y estados de préstamos concretos, sin renovar ni mostrar claves."""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from biblio import parser
from biblio.client import AbsysClient, ACC_LIBRARY
from biblio.store import Store


def main():
    args_parser = argparse.ArgumentParser(description=__doc__)
    args_parser.add_argument("--label")
    args_parser.add_argument("--title", action="append", default=[])
    args_parser.add_argument("--list-accounts", action="store_true")
    args_parser.add_argument("--data-dir", default=str(ROOT / ".biblio-data"))
    args = args_parser.parse_args()
    path = Path(args.data_dir) / "biblio.sqlite3"
    if not path.is_file():
        raise RuntimeError("No hay una base de datos de cuentas vinculadas.")
    store = Store(path)
    try:
        if args.list_accounts:
            print(json.dumps([dict(row) for row in store.db.execute("SELECT label,count(*) AS count FROM accounts GROUP BY label")], ensure_ascii=True))
            return
        if not args.label or not args.title:
            args_parser.error("Indica --label y al menos un --title, o usa --list-accounts.")
        accounts = store.db.execute("SELECT id FROM accounts WHERE lower(label)=lower(?)", (args.label,)).fetchall()
        if len(accounts) != 1:
            raise RuntimeError("La etiqueta debe identificar exactamente un carné.")
        credentials = store.credentials(accounts[0]["id"])
    finally:
        store.close()
    client = AbsysClient(credentials["card"], credentials["password"])
    for round_number in (1, 2):
        response = client._auth_get(ACC_LIBRARY)
        reader = parser.parse_reader(response.text)
        loans = parser.parse_loans(response.text, reader=reader)
        root = parser.parse(response.text)
        print(json.dumps({"round": round_number, "today": dt.date.today().isoformat(),
                          "loans": len(loans), "renewable": sum(loan.renewal_state.can_renew for loan in loans)}, ensure_ascii=True))
        for loan in loans:
            if not any(term.casefold() in loan.title.casefold() for term in args.title):
                continue
            block = root.find(predicate=lambda n: n.has_class("varJSONpr") and bool(n.find("span", lambda s: s.has_class("prbarc") and s.text() == loan.barcode)))
            row = block.parent if block else None
            while row and row.tag != "li":
                row = row.parent
            data = {span.attr("class").split()[0]: span.own_text() for span in block.find_all("span") if span.attr("class")} if block else {}
            info = parser._info_pairs(row) if row else {}
            print(json.dumps({"title": loan.clean_title, "due_date": loan.due_date.isoformat(),
                "days_left": loan.days_left, "renewals_used": loan.renewals_used, "renewals_max": loan.renewals_max,
                "renewal_state": loan.renewal_state.value,
                "portal_fields": {name: value for name, value in data.items() if name.startswith(("prf", "prnren", "ppd", "ppp", "xsf", "xsresv"))},
                "visible_dates": {label: value for label, value in info.items() if any(term in label.casefold() for term in ("fecha", "fin", "devol", "renov"))}}, ensure_ascii=True))


if __name__ == "__main__":
    main()
