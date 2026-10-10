"""Verifica API + interfaz de reservables con el OPAC real, sin crear reservas.

Usa las credenciales de un carné ya vinculado en una instancia temporal de la
aplicación. No modifica los usuarios ni permisos de la instancia habitual.
"""
import argparse
import secrets
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from biblio.store import Store
from biblio.web import AppServer, API_VERSION


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    parser.add_argument("--record", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--data-dir", default=str(ROOT / ".biblio-data"))
    parser.add_argument("--channel", default="msedge")
    parser.add_argument("--playwright-path")
    parser.add_argument("--screenshot")
    args = parser.parse_args()
    if args.playwright_path:
        sys.path.insert(0, args.playwright_path)
    from playwright.sync_api import sync_playwright, expect

    path = Path(args.data_dir) / "biblio.sqlite3"
    if not path.is_file():
        raise RuntimeError("No existe una base de datos de cuentas vinculadas.")
    original = Store(path)
    try:
        accounts = original.db.execute("SELECT id FROM accounts WHERE lower(label)=lower(?)", (args.label,)).fetchall()
        if len(accounts) != 1:
            raise RuntimeError("La etiqueta debe identificar exactamente un carné.")
        credentials = original.credentials(accounts[0]["id"])
    finally:
        original.close()

    with tempfile.TemporaryDirectory(prefix=".biblio-test-", dir=ROOT) as folder:
        store = Store(Path(folder) / "biblio.sqlite3")
        password = secrets.token_urlsafe(32)
        user = store.register("inspection", "Verificación temporal", password)
        account = store.add_account(user["id"], args.label, credentials["card"], credentials["password"])
        server = AppServer(("127.0.0.1", 0), store=store)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{server.server_port}"
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel=args.channel, headless=True)
                context = browser.new_context(viewport={"width": 1280, "height": 1440})
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                # Refuse any accidental attempt to create/change a library operation.
                page.route("**/api/reserve", lambda route: route.abort())
                page.route("**/api/renew", lambda route: route.abort())
                page.route("**/api/cancel", lambda route: route.abort())
                login = context.request.post(url + "/api/login", data={"username": "inspection", "password": password})
                assert login.status == 200, "El acceso de la instancia temporal falló"
                assert login.headers["x-biblio-api-version"] == API_VERSION
                page.goto(url)
                expect(page.locator("#greeting")).to_contain_text("Verificación temporal", timeout=90000)
                page.locator('[data-view="catalog"]').click()
                page.locator("#catalog-account").select_option(account)
                page.locator("#query").fill(args.query)
                page.locator("#search button").click()
                result = page.locator("#results .book").filter(has=page.get_by_role("heading", name=args.title, exact=True))
                expect(result).to_have_count(1, timeout=90000)
                result.get_by_role("button", name="Ver ejemplares y reservar →").click()
                expect(page.locator(".detail-summary")).to_be_visible(timeout=90000)
                with page.expect_response(lambda response: "/api/reservable?" in response.url, timeout=90000) as pending:
                    page.get_by_role("button", name="Consultar ejemplares reservables").click()
                response = pending.value
                assert response.status == 200, "El portal no devolvió opciones reservables"
                assert response.headers["x-biblio-api-version"] == API_VERSION
                assert "record=" + args.record in response.url
                copies = response.json()["copies"]
                assert copies, "No hay ejemplares reservables en esta consulta"
                for copy in copies:
                    assert "row" not in copy, "La API aún expone el texto antiguo"
                    assert copy["branch"] or copy["library"], "Faltan los datos de biblioteca"
                    expect(page.locator("#reservable-options")).to_contain_text(copy["branch"] or copy["library"])
                expect(page.locator("#reservable-options button")).to_have_count(len(copies))
                for unwanted in ("copiasRes_", "abnetopac", "< a href"):
                    expect(page.locator("#detail-content")).not_to_contain_text(unwanted)
                assert not errors, errors
                if args.screenshot:
                    page.locator("#detail").screenshot(path=args.screenshot)
                print(f"OPAC real + API HTTP v{API_VERSION} + navegador OK: ficha {args.record}, {len(copies)} opciones estructuradas, sin HTML ni URLs de sesión.")
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
            store.close()


if __name__ == "__main__":
    main()
