"""CLI multipuenta.

Es la especificación ejecutable del motor: lo que se comprueba aquí es
exactamente lo que luego hay que portar a Kotlin.
"""

from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import sys

from .accounts import Account, Registry
from .client import AbsysClient, AuthError, OperationRefused, SessionExpired
from .http import Http
from .models import RenewalState

RENEWAL_LABEL = {
    RenewalState.RENEWABLE: "renovable",
    RenewalState.RENEWABLE_FROM_DATE: "aún no",
    RenewalState.LIMIT_REACHED: "límite alcanzado",
    RenewalState.NOT_RENEWABLE: "no",
    RenewalState.OVERDUE: "con retraso",
    RenewalState.READER_EXPIRED: "lector caducado",
    RenewalState.READER_SUSPENDED: "lector suspendido",
    RenewalState.UNKNOWN: "?",
}

def _barcode(char: str = "-") -> str:
    return char * 78


def _status_line(days_left: int) -> str:
    if days_left < 0:
        return f"RETRASO {-days_left}d"
    if days_left == 0:
        return "vence HOY"
    return f"{days_left}d"


def show_library(client: AbsysClient, today: dt.date | None = None) -> int:
    today = today or dt.date.today()
    library = client.my_library(today=today)
    reader = library.reader

    print(f"\n{_barcode('=')}")
    print(f"{reader.name}  ·  carné {reader.card}")
    flags = []
    if reader.suspended:
        flags.append("SUSPENDIDO")
    if reader.expired:
        flags.append("CARNÉ CADUCADO")
    if reader.card_expires:
        flags.append(f"carné hasta {reader.card_expires:%d/%m/%Y}")
    if flags:
        print("  " + "  ·  ".join(flags))
    print(_barcode("="))

    if not library.loans:
        print("  sin préstamos")
    else:
        print(f"  PRÉSTAMOS ({len(library.loans)})")
        for loan in sorted(library.loans, key=lambda item: item.due):
            mark = "!" if loan.overdue else " "
            print(f"   {mark} {loan.due:%d/%m/%Y}  {_status_line(loan.days_left):>12}  {loan.clean_title[:46]}")
            if loan.author:
                print(f"       {loan.author[:60]}")
            print(
                f"       {loan.library}"
                + (f"  ·  ren: {RENEWAL_LABEL[loan.renewal_state]}"
                   f" ({loan.renewals_used}/{loan.renewals_max})" if loan.renewals_max else "")
            )
            if loan.renewal_state is RenewalState.RENEWABLE_FROM_DATE and loan.renewal_available_from:
                print(f"       renovable a partir de {loan.renewal_available_from:%d/%m/%Y}")
            if loan.pending_holds:
                print(f"       {loan.pending_holds} persona(s) en cola")

    if library.reservations:
        print(f"  RESERVAS ({len(library.reservations)})")
        for res in library.reservations:
            expires = f"caduca {res.expires:%d/%m/%Y}" if res.expires else "sin caducidad"
            print(f"    - {res.title[:46]}")
            print(f"      {res.state}  ·  {expires}  ·  {res.branch}")
            print(f"      id={res.reservation_id}")
    return len(library.loans)


def cmd_library(registry: Registry, args) -> int:
    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
    total = 0
    failures = 0
    for account in registry.select(args.account):
        client = AbsysClient(
            account.card,
            account.resolve_password(interactive=not args.no_prompt),
            http=Http(base_delay=args.delay),
        )
        try:
            total += show_library(client, today=today)
        except AuthError as exc:
            failures += 1
            print(f"\n[{(account.label or account.id)}] ERROR: {exc}", file=sys.stderr)
        except SessionExpired as exc:
            failures += 1
            print(f"\n[{(account.label or account.id)}] SESIÓN CADUCADA: {exc}", file=sys.stderr)
    if failures:
        print(f"\n{failures} cuenta(s) con error", file=sys.stderr)
    return 1 if failures else 0


def cmd_search(registry: Registry, args) -> int:
    account = registry.select(args.account)[0]
    client = AbsysClient(
        account.card,
        account.resolve_password(interactive=not args.no_prompt),
        http=Http(base_delay=args.delay),
    )
    total, records = client.search(args.query, page=args.page)
    print(f"\n{total} resultado(s) — página {args.page}\n")
    for index, record in enumerate(records, start=1 + (args.page - 1) * 10):
        year = f" ({record.year})" if record.year else ""
        print(f"  {index:>3}. {record.title or '(sin título)'}{year}")
        if record.author:
            print(f"       {record.author}")
        if record.publication:
            print(f"       {record.publication}")
        if record.subjects:
            print(f"       {'; '.join(record.subjects[:3])}")
        if record.isbn:
            print(f"       ISBN {record.isbn}")
        print(f"       id={record.record_id}")
    if args.availability:
        for record in records:
            if not record.record_id:
                continue
            copies = client.copies(record.record_id)
            available = [c for c in copies if c.available_now]
            soon = [c for c in copies if c.expected and c.expected > dt.date.today()]
            print(f"\n  >> {record.title[:50]}")
            print(
                f"     {len(available)} disponibles ahora de {len(copies)} ejemplares"
                + (f"  ·  {len(soon)} vuelven pronto" if soon else "")
            )
            for copy in available[:5]:
                where = copy.branch or copy.library
                print(f"       {copy.signature:<28} {where}")
                print(f"         {copy.location}  ·  {copy.availability}")
            for copy in soon[:3]:
                print(
                    f"       {copy.signature:<28} {copy.branch}"
                    f"  ·  {copy.availability}"
                )
    return 0


def cmd_renew(registry: Registry, args) -> int:
    account = registry.select(args.account)[0]
    client = AbsysClient(
        account.card,
        account.resolve_password(interactive=not args.no_prompt),
        http=Http(base_delay=args.delay),
    )
    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
    library = client.my_library(today=today)
    by_barcode = {loan.barcode: loan for loan in library.loans}

    if not args.barcode:
        pending = [
            loan
            for loan in library.loans
            if loan.renewal_state is RenewalState.RENEWABLE
        ]
        if not pending:
            print("No hay préstamos renovables ahora mismo.")
            for loan in library.loans:
                if loan.renewal_state is RenewalState.RENEWABLE_FROM_DATE and loan.renewal_available_from:
                    print(f"  {loan.clean_title[:44]}: desde {loan.renewal_available_from:%d/%m/%Y}")
            return 0
        print(f"{len(pending)} préstamo(s) renovable(s). Usa --codigo-barras.")
        for loan in pending:
            print(f"  {loan.barcode}  {loan.clean_title[:50]}")
        return 0

    loan = by_barcode.get(args.barcode)
    if loan is None:
        print(f"El ejemplar {args.barcode} no está en tus préstamos", file=sys.stderr)
        return 1
    if loan.renewal_state is not RenewalState.RENEWABLE:
        print(
            f"No se puede renovar «{loan.clean_title}»: {RENEWAL_LABEL[loan.renewal_state]}"
            + (f" (desde {loan.renewal_available_from:%d/%m/%Y})"
               if loan.renewal_available_from else "")
        )
        return 1
    result = None
    try:
        result = client.renew(args.barcode, today=today)
    except OperationRefused as exc:
        print(f"No se renovó: {exc}", file=sys.stderr)
        return 1
    print(result.message)
    print(
        f"Renovaciones usadas: {result.renewals_used}/{result.renewals_max}"
        + ("  (agotadas)" if result.renewals_used >= result.renewals_max else "")
    )
    return 0


def cmd_reserve(registry: Registry, args) -> int:
    account = registry.select(args.account)[0]
    client = AbsysClient(
        account.card,
        account.resolve_password(interactive=not args.no_prompt),
        http=Http(base_delay=args.delay),
    )
    if args.action == "list":
        library = client.my_library()
        if not library.reservations:
            print("No tienes reservas.")
            return 0
        for res in library.reservations:
            expires = f"{res.expires:%d/%m/%Y}" if res.expires else "-"
            print(f"  {res.reservation_id}  {res.title[:44]:<46} {res.state:<12} caduca {expires}")
        return 0
    if args.action == "cancel":
        try:
            print(client.cancel_reservation(args.reservation_id))
        except OperationRefused as exc:
            print(f"No se pudo anular: {exc}", file=sys.stderr)
            return 1
        return 0
    if args.action == "show":
        for copy in client.reservable_copies(args.record_id):
            print(f"  [{copy['index']:>3}] {copy['barcode']}  {copy['row'][:90]}")
        return 0
    if args.action == "create":
        try:
            print(client.reserve(args.record_id, args.copy_index))
        except OperationRefused as exc:
            print(f"No se pudo reservar: {exc}", file=sys.stderr)
            return 1
        return 0
    return 2


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="biblio",
        description="Gestión de préstamos de las Bibliotecas de la Comunidad de Madrid.",
    )
    ap.add_argument("--registro", type=pathlib.Path, default=None, help="ruta de accounts.json")
    ap.add_argument("--cuenta", action="append", dest="account", help="cuenta(s) a usar (repetible)")
    ap.add_argument("--delay", type=float, default=1.0, help="segundos entre peticiones")
    ap.add_argument("--no-prompt", action="store_true", help="no pedir contraseñas")
    sub = ap.add_subparsers(dest="command", required=True)

    lib = sub.add_parser("prestamos", help="panel de préstamos de todas las cuentas")
    lib.add_argument("--today", help="fecha de referencia ISO (para tests)")
    lib.set_defaults(func=cmd_library)

    sea = sub.add_parser("buscar", help="búsqueda en el catálogo")
    sea.add_argument("query")
    sea.add_argument("--pagina", type=int, default=1, dest="page")
    sea.add_argument("--availability", action="store_true", help="consultar ejemplares")
    sea.set_defaults(func=cmd_search)

    ren = sub.add_parser("renovar", help="renovar un ejemplar")
    ren.add_argument("--codigo-barras", dest="barcode")
    ren.add_argument("--today")
    ren.set_defaults(func=cmd_renew)

    res = sub.add_parser("reservas", help="gestionar reservas")
    res.add_argument("action", choices=["list", "show", "create", "cancel"])
    res.add_argument("--record-id")
    res.add_argument("--copy-index", type=int, default=1)
    res.add_argument("--reservation-id")
    res.set_defaults(func=cmd_reserve)

    acc = sub.add_parser("cuentas", help="gestionar el registro de cuentas")
    acc.add_argument("action", choices=["list", "add", "remove"])
    acc.add_argument("--id")
    acc.add_argument("--carne", dest="card")
    acc.add_argument("--etiqueta", "--label", dest="label", help="nombre legible")
    acc.set_defaults(func=cmd_accounts)

    return ap


def cmd_accounts(registry: Registry, args) -> int:
    if args.action == "list":
        if not registry.accounts:
            print("No hay cuentas registradas. Usa:  biblio cuentas add --id nino --carne 12345678")
        for account in registry.accounts:
            source = "env" if account.password_from_env() else ("cifrada" if account.password else "—")
            print(f"  {account.id:<16} {account.card:<14} {(account.label or ''):<24} {source}")
        return 0
    if args.action == "add":
        if not args.id or not args.card:
            print("--id y --carne son obligatorios", file=sys.stderr)
            return 1
        registry.add(Account(id=args.id, card=args.card, label=args.label or ""))
        registry.save()
        print(f"Cuenta '{args.id}' guardada (sin contraseña en disco).")
        return 0
    registry.accounts = [a for a in registry.accounts if a.id != args.id]
    registry.save()
    print(f"Cuenta '{args.id}' eliminada.")
    return 0


def main(argv: list[str] | None = None) -> int:
    # La consola de Windows viene en cp1252 y se come los acentos del OPAC.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    args = build_parser().parse_args(argv)
    registry = Registry.load(args.registro)
    try:
        return args.func(registry, args)
    except KeyError as exc:
        print(str(exc).strip("'"), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())