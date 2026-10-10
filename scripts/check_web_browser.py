"""Prueba opcional de UI con dos navegadores aislados y OPAC simulado.

Requiere Playwright y un navegador Chromium (por defecto Edge instalado).
No consulta bibliotecas reales ni conserva usuarios o credenciales de prueba.
"""
import argparse
import json
import re
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from urllib.parse import urlsplit

from biblio import mailer as mailer_module
from biblio import web as web_module
from biblio.oidc import GoogleConfig
from biblio.store import Store
from biblio.web import GOOGLE_CALLBACK as GOOGLE_CALLBACK_PATH, REAUTH_TTL, AppServer
from tests.fake_oidc import CLIENT_ID, CLIENT_SECRET, FakeOidcProvider
from tests.test_identity import FakeSmtpServer
from tests.test_web import FakeClient, APP_PASSWORD, PORTAL_PASSWORD


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--channel", default="msedge")
    parser.add_argument("--playwright-path", help="Directorio opcional donde está instalado Playwright")
    args = parser.parse_args()
    if args.playwright_path:
        sys.path.insert(0, args.playwright_path)
    from playwright.sync_api import sync_playwright, expect

    with tempfile.TemporaryDirectory(prefix=".biblio-test-", dir=ROOT) as folder:
        store = Store(Path(folder) / "biblio.sqlite3")
        portal_state = {}
        # SMTP falso local para verificar email y recuperar contraseña sin
        # tocar ningún proveedor real (FR-AUTH-002 / FR-AUTH-003).
        smtp = FakeSmtpServer()
        smtp_thread = threading.Thread(target=smtp.serve_forever, daemon=True)
        smtp_thread.start()
        mailer = mailer_module.Mailer(mailer_module.MailConfig(
            host="127.0.0.1", port=smtp.port, starttls=False,
            from_addr="BiblioCM <no-responder@fake.test>"))
        # Proveedor OIDC falso local (FR-AUTH-005): discovery, JWKS y token con
        # firma RS256 de prueba; nunca se habla con Google.
        oidc = FakeOidcProvider()
        server = AppServer(("127.0.0.1", 0), lambda card, password: FakeClient(card, password, state=portal_state),
                           store=store, mailer=mailer,
                           google=GoogleConfig(client_id=CLIENT_ID, client_secret=CLIENT_SECRET,
                                               issuer=oidc.base_url))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{server.server_port}"
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel=args.channel, headless=True)
                owner_context = browser.new_context(viewport={"width": 1280, "height": 900})
                viewer_context = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
                owner, viewer = owner_context.new_page(), viewer_context.new_page()
                errors = []
                for page in (owner, viewer):
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.on("dialog", lambda dialog: dialog.accept())
                    # Instrumentación de la caché de portada (ADR-014): registra
                    # blob URLs creadas y revocadas para poder exigir la
                    # invalidación sin exponer hooks de depuración en app.js.
                    page.add_init_script("""
                        window.__blobs = {created: [], revoked: []};
                        const createBlob = URL.createObjectURL.bind(URL);
                        const revokeBlob = URL.revokeObjectURL.bind(URL);
                        URL.createObjectURL = object => {
                          const url = createBlob(object);
                          window.__blobs.created.push(url);
                          return url;
                        };
                        URL.revokeObjectURL = url => {
                          window.__blobs.revoked.push(url);
                          return revokeBlob(url);
                        };
                    """)

                def register(page, username, base=None):
                    page.goto(base or url)
                    page.locator("#show-register").click()
                    page.locator("#register-name").fill(username.title())
                    page.locator("#register-username").fill(username)
                    page.locator("#register-password").fill(APP_PASSWORD)
                    page.locator("#register button[type=submit]").click()
                    expect(page.locator("#settings")).to_be_visible()
                    expect(page.locator("#my-identity")).to_contain_text("@" + username)

                def add_account(page, card, label):
                    page.locator('[data-view="settings"]').click()
                    page.locator("#account-label").fill(label)
                    page.locator("#account-card").fill(card)
                    page.locator("#account-password").fill(PORTAL_PASSWORD)
                    page.locator("#link-account button[type=submit]").click()
                    expect(page.locator("#linked-accounts")).to_contain_text(label)
                    expect(page.locator("#account-password")).to_have_value("")

                # Una petición retenida (sin dormir en el enrutador) permite
                # observar el estado de la UI mientras sigue en vuelo: los
                # `time.sleep` dentro de un enrutador bloquean las aserciones de
                # Playwright y hacen las esperas indeterminadas.
                def hold(bucket):
                    def handler(route):
                        bucket.append(route)
                    return handler

                def wait_held(page, bucket, label):
                    # El bucle debe bombea el event loop de Playwright: un
                    # `time.sleep` solo no llega a invocar el enrutador.
                    deadline = time.time() + 5
                    while time.time() < deadline and not bucket:
                        page.evaluate("1")
                        time.sleep(0.02)
                    if not bucket:
                        raise AssertionError(label)

                def release_held(bucket):
                    while bucket:
                        bucket.pop(0).continue_()

                def spinner_style(locator):
                    """Display/animación y caja dibujada del spinner, no su nodo."""
                    return locator.evaluate("""el => {
                        const style = getComputedStyle(el);
                        const box = el.getBoundingClientRect();
                        return {display: style.display, animation: style.animationName,
                                duration: style.animationDuration,
                                width: box.width, height: box.height};
                    }""")

                def assert_boot_rendered(page, label):
                    """El arranque debe renderizarse de verdad, no solo existir.

                    Comprueba el display calculado, la animación estándar, que
                    el bloque cae dentro del viewport y que con
                    `prefers-reduced-motion: reduce` la rotación continua se
                    detiene sin perder el indicador estático.
                    """
                    boot = page.locator("#boot-loading")
                    rendered = boot.evaluate("""el => {
                        const box = el.getBoundingClientRect();
                        return {display: getComputedStyle(el).display,
                                x: box.x, y: box.y, width: box.width, height: box.height,
                                viewportWidth: window.innerWidth,
                                viewportHeight: window.innerHeight};
                    }""")
                    assert rendered["display"] == "flex", f"{label}: display calculado {rendered['display']}"
                    spin = spinner_style(page.locator("#boot-loading .spinner"))
                    assert spin["animation"] == "spin", f"{label}: animation-name {spin['animation']}"
                    assert spin["width"] > 0 and spin["height"] > 0, f"{label}: spinner sin caja dibujada {spin}"
                    assert rendered["width"] > 0 and rendered["height"] > 0, f"{label}: bloque sin caja dibujada"
                    assert rendered["x"] >= -1 and rendered["y"] >= -1, f"{label}: fuera del borde {rendered}"
                    assert rendered["x"] + rendered["width"] <= rendered["viewportWidth"] + 1, \
                        f"{label}: excede el viewport en horizontal {rendered}"
                    assert rendered["y"] + rendered["height"] <= rendered["viewportHeight"] + 1, \
                        f"{label}: excede el viewport en vertical {rendered}"
                    page.emulate_media(reduced_motion="reduce")
                    static = spinner_style(page.locator("#boot-loading .spinner"))
                    text = boot.inner_text().strip()
                    page.emulate_media(reduced_motion="no-preference")
                    assert static["animation"] == "none", \
                        f"{label}: el spinner sigue girando con movimiento reducido (animation-name={static['animation']})"
                    assert static["width"] > 0 and static["height"] > 0, \
                        f"{label}: el indicador estático desaparece con movimiento reducido {static}"
                    assert text, f"{label}: sin texto junto al spinner con movimiento reducido"

                # An old API can still serve the new static files until restarted.
                owner.route("**/api/session", lambda route: route.fulfill(json={"authenticated": False, "csrf": None, "user": None}))
                owner.goto(url)
                expect(owner.locator("#notice")).to_contain_text("versión anterior")
                expect(owner.locator("#login button[type=submit]")).to_be_disabled()
                expect(owner.locator("#register button[type=submit]")).to_be_disabled()
                owner.unroute("**/api/session")
                # El arranque resuelve la sesión con una región de estado
                # accesible y sin destello del formulario de acceso.
                expect(owner.locator("#boot-loading")).to_have_count(1)
                expect(owner.locator("#boot-loading")).to_be_hidden()
                expect(owner.locator("#welcome")).to_be_visible()
                # http://127.0.0.1 es contexto local aceptado: no aparece el
                # aviso de origen no confiable (NFR-SVC-003).
                expect(owner.locator("#origin-warning")).to_be_hidden()

                register(owner, "owner")
                add_account(owner, "111", "Cuenta titular")
                register(viewer, "viewer")
                viewer.locator("#request-username").fill("owner")
                viewer.locator("#request-permission").select_option("manage")
                viewer.locator("#request-access button[type=submit]").click()
                expect(viewer.locator("#outgoing-requests")).to_contain_text("Pendiente de aprobación")
                owner.locator('[data-view="settings"]').click()
                expect(owner.locator("#incoming-requests")).to_contain_text("@viewer")
                owner.locator("#incoming-requests select").select_option("read")
                owner.get_by_role("button", name="Aprobar con este permiso").click()
                expect(owner.locator("#incoming-requests")).to_contain_text("Acceso autorizado")

                # Estado de carga accesible del panel: existe, se anuncia mientras
                # se consulta y se retira al terminar.
                expect(viewer.locator("#library-loading")).to_have_count(1)
                expect(viewer.locator("#library-loading")).to_be_hidden()
                expect(viewer.locator("#dashboard")).to_have_attribute("aria-busy", "false")

                # La petición se retiene en lugar de dormir en el enrutador:
                # un `time.sleep` ahí bloquea las aserciones de Playwright y
                # convierte esta comprobación en una carrera.
                pending_library = []
                viewer.route("**/api/library*", hold(pending_library))
                viewer.locator("#refresh").click()
                wait_held(viewer, pending_library, "GET library del refresco nunca llegó")
                expect(viewer.locator("#library-loading")).to_be_visible()
                expect(viewer.locator("#library-loading")).to_have_text("Cargando tu biblioteca…")
                expect(viewer.locator("#dashboard")).to_have_attribute("aria-busy", "true")
                release_held(pending_library)
                expect(viewer.locator("#library-loading")).to_be_hidden()
                expect(viewer.locator("#dashboard")).to_have_attribute("aria-busy", "false")
                viewer.unroute("**/api/library*")
                expect(viewer.locator("#linked-accounts")).to_contain_text("Cuenta titular")
                viewer.locator('[data-view="loans"]').click()
                expect(viewer.locator("#loan-list .book")).to_have_count(1)
                expect(viewer.locator("#loan-list")).to_contain_text("Autorización de solo lectura")
                expect(viewer.locator("#loan-list button")).to_have_count(0)

                owner.locator("#incoming-requests select").select_option("manage")
                owner.get_by_role("button", name="Guardar permiso").click()
                expect(owner.locator("#incoming-requests .badge")).to_have_text("Acceso autorizado")
                expect(owner.locator("#incoming-requests p").last).to_have_text("Gestión completa")
                viewer.locator("#refresh").click()
                expect(viewer.get_by_role("button", name="Renovar préstamo →")).to_be_visible()
                # Renovación con la respuesta retenida (móvil): mientras sigue
                # en vuelo el botón queda bloqueado con progreso accesible, un
                # segundo intento no envía otro POST y el aviso de éxito solo
                # llega después de refrescar y verificar el panel.
                pending_renew, renew_hits = [], []

                def hold_renew(route):
                    renew_hits.append(1)
                    pending_renew.append(route)

                viewer.route("**/api/renew*", hold_renew)
                viewer.get_by_role("button", name="Renovar préstamo →").click()
                wait_held(viewer, pending_renew, "POST renew del móvil nunca llegó al enrutador")
                renew_button = viewer.locator("#loan-list button")
                expect(renew_button).to_have_count(1)
                expect(renew_button).to_be_disabled()
                expect(renew_button).to_have_attribute("aria-busy", "true")
                expect(renew_button).to_have_text("Renovando…")
                expect(viewer.locator("#notice")).to_have_text("Renovando…")
                expect(viewer.locator("#notice")).not_to_contain_text("renovado")
                expect(viewer.locator("#loan-list")).to_contain_text("05/01/2030")
                renew_button.click(force=True)
                assert len(renew_hits) == 1, f"renovaciones enviadas: {len(renew_hits)}"
                release_held(pending_renew)
                expect(viewer.locator("#notice")).to_have_text("«Libro de 111» renovado. Devolución: 20/01/2030 · 15 días restantes.")
                expect(viewer.locator("#loan-list")).to_contain_text("20/01/2030")
                expect(viewer.locator("#loan-list")).to_contain_text("15 días restantes")
                expect(viewer.locator("#loan-list button")).to_have_count(0)
                viewer.unroute("**/api/renew*")
                assert len(renew_hits) == 1, f"POST de renovación totales: {len(renew_hits)}"
                viewer.reload()
                expect(viewer.locator("#loan-list")).to_contain_text("20/01/2030")
                expect(viewer.locator("#loan-list")).to_contain_text("15 días restantes")
                # Restauración de sesión: el estado de carga vuelve a su reposo.
                expect(viewer.locator("#library-loading")).to_be_hidden()
                expect(viewer.locator("#dashboard")).to_have_attribute("aria-busy", "false")

                # Un error del panel retira el estado de carga y avisa sin cerrar sesión.
                viewer.route("**/api/library*", lambda route: route.fulfill(
                    status=500, headers={"X-Biblio-API-Version": "6"},
                    body=json.dumps({"error": "No se pudo completar la operación"})))
                viewer.locator("#refresh").click()
                expect(viewer.locator("#library-loading")).to_be_hidden()
                expect(viewer.locator("#dashboard")).to_have_attribute("aria-busy", "false")
                expect(viewer.locator("#notice")).to_contain_text("No se pudo completar")
                expect(viewer.locator("#dashboard")).to_be_visible()
                viewer.unroute("**/api/library*")

                # Restauración de sesión: estado de carga accesible desde el
                # arranque, sin destello del formulario de acceso ni de un
                # panel vacío mientras se consultan los permisos.
                pending_session, pending_settings = [], []
                viewer.route("**/api/session*", hold(pending_session))
                viewer.route("**/api/settings*", hold(pending_settings))
                viewer.reload()
                expect(viewer.locator("#boot-loading")).to_have_count(1)
                expect(viewer.locator("#boot-loading")).to_be_visible()
                expect(viewer.locator("#boot-loading")).to_have_attribute("role", "status")
                expect(viewer.locator("#welcome")).to_be_hidden()
                # Móvil: el estado de arranque se renderiza y cae dentro del
                # viewport antes de que se resuelva la sesión retenida.
                assert_boot_rendered(viewer, "móvil")
                wait_held(viewer, pending_session, "GET session nunca llegó al enrutador")
                release_held(pending_session)
                expect(viewer.locator("#boot-loading")).to_be_hidden()
                expect(viewer.locator("#library-loading")).to_be_visible()
                expect(viewer.locator("#dashboard")).to_have_attribute("aria-busy", "true")
                expect(viewer.locator("#library-loading")).to_have_text("Cargando tu biblioteca…")
                # El spinner del panel también se dibuja y anima, no es un nodo vacío.
                panel_spin = spinner_style(viewer.locator("#library-loading .spinner"))
                assert panel_spin["display"] != "none", f"panel: display del spinner {panel_spin['display']}"
                assert panel_spin["animation"] == "spin", f"panel: animation-name {panel_spin['animation']}"
                assert panel_spin["width"] > 0 and panel_spin["height"] > 0, f"panel: spinner sin caja {panel_spin}"
                wait_held(viewer, pending_settings, "GET settings de la restauración nunca llegó")
                release_held(pending_settings)
                expect(viewer.locator("#library-loading")).to_be_hidden()
                expect(viewer.locator("#dashboard")).to_have_attribute("aria-busy", "false")
                expect(viewer.locator("#loan-list .book")).to_have_count(1)
                viewer.unroute("**/api/session*")
                viewer.unroute("**/api/settings*")

                add_account(viewer, "222", "Mi cuenta")
                viewer.locator('[data-view="loans"]').click()
                expect(viewer.locator("#loan-list .book")).to_have_count(2)
                settings = viewer_context.request.get(url + "/api/settings").json()
                own = next(a for a in settings["accounts"] if a["own"])
                shared = next(a for a in settings["accounts"] if not a["own"])
                assert PORTAL_PASSWORD not in json.dumps(settings)
                viewer.locator("#account-filter").select_option(own["id"])
                expect(viewer.locator("#loan-list .book")).to_have_count(1)
                expect(viewer.locator("#loan-list")).to_contain_text("Libro de 222")
                # Préstamo con portada atribuida a su cuenta y su registro: se
                # sirve desde la blob URL de la caché RAM, no como ruta cruda.
                expect(viewer.locator("#loan-list .book-cover img")).to_have_count(1)
                loan_cover = viewer.locator("#loan-list .book-cover img")
                expect(loan_cover).to_have_attribute("src", re.compile(r"^blob:"))
                loan_blob = loan_cover.get_attribute("src")
                assert loan_blob.startswith("blob:"), loan_blob

                viewer.locator('[data-view="reservations"]').click()
                expect(viewer.locator("#reservation-list .book")).to_have_count(1)
                reservation_cover = viewer.locator("#reservation-list .book-cover img")
                expect(reservation_cover).to_have_count(1)
                # Misma cuenta y mismo registro que el préstamo: la caché RAM
                # reutiliza la misma blob URL sin volver a descargarla.
                expect(reservation_cover).to_have_attribute("src", loan_blob)
                created_after_first_render = viewer.evaluate("window.__blobs.created.length")
                viewer.locator('[data-view="loans"]').click()
                expect(viewer.locator("#loan-list .book-cover img")).to_have_attribute("src", loan_blob)
                assert viewer.evaluate("window.__blobs.created.length") == created_after_first_render, \
                    "la caché creó una blob URL nueva al re-renderizar la misma portada"

                viewer.locator('[data-view="catalog"]').click()
                viewer.locator("#catalog-account").select_option(shared["id"])
                viewer.locator("#query").fill("libro")
                viewer.locator("#search button").click()
                # Portada servida por la propia app, con carga diferida y sin
                # ninguna URL ni token del OPAC en el DOM.
                expect(viewer.locator("#results .book")).to_have_count(1)
                cover = viewer.locator("#results .book-cover img")
                expect(cover).to_have_count(1)
                expect(cover.first).to_have_attribute("loading", "lazy")
                expect(cover.first).to_have_attribute("src", re.compile(r"^blob:"))
                shared_blob = cover.first.get_attribute("src")
                assert shared_blob != loan_blob, "cuentas distintas no comparten blob URL"
                assert "THREADTOKEN" not in viewer.content()
                assert "abnetopac" not in viewer.content()
                # El préstamo mantiene su portada, atribuida a su cuenta+registro.
                expect(viewer.locator("#loan-list .book-cover img")).to_have_count(1)
                expect(viewer.locator("#loan-list .book-cover img")).to_have_attribute("src", loan_blob)
                viewer.get_by_role("button", name="Ver ejemplares y reservar →").click()
                expect(viewer.locator(".detail-summary")).to_have_text("2 ejemplares en 2 bibliotecas · 1 disponible ahora")
                expect(viewer.locator("#detail-content img.detail-cover")).to_have_count(1)
                # The exact old shape must not be rendered as a fallback row.
                legacy_row = 'copiasRes_locCont"> B. Móstoles CENTRAL ALMUDENA GRANDES < a href="/biblio_publicas/cgi-bin/abnetopac/TEST_SESSION'
                viewer.route("**/api/reservable?*", lambda route: route.fulfill(
                    headers={"X-Biblio-API-Version": "6"},
                    json={"copies": [{"index": 1, "barcode": "999", "row": legacy_row}]}))
                viewer.get_by_role("button", name="Consultar ejemplares reservables").click()
                expect(viewer.locator("#notice")).to_contain_text("no contiene los datos de biblioteca")
                expect(viewer.locator("#detail-content")).not_to_contain_text("copiasRes_locCont")
                expect(viewer.locator("#detail-content")).not_to_contain_text("TEST_SESSION")
                expect(viewer.locator("#reservable-options button")).to_have_count(0)
                viewer.unroute("**/api/reservable?*")
                viewer.get_by_role("button", name="Consultar ejemplares reservables").click()
                expect(viewer.locator("#detail-content")).to_contain_text("Todos los ejemplares de esta ficha")
                expect(viewer.locator("#reservable-options")).to_contain_text("1 opción de reserva en 1 biblioteca")
                expect(viewer.locator("#reservable-options")).to_contain_text("Sede reservas")
                expect(viewer.locator("#reservable-options")).to_contain_text("JUE SWI ley")
                expect(viewer.locator("#reservable-options")).not_to_contain_text("copiasRes_")
                viewer.get_by_role("button", name="Reservar este ejemplar").click()
                expect(viewer.locator("#notice")).to_have_text("Reserva realizada para 111")

                # Nada de la portada se persiste en el navegador: ni
                # CacheStorage, ni localStorage, ni sessionStorage.
                persisted = viewer.evaluate("""() => ({
                    local: Object.keys(window.localStorage),
                    session: Object.keys(window.sessionStorage)})""")
                assert persisted["local"] == [], f"localStorage con datos: {persisted}"
                assert persisted["session"] == [], f"sessionStorage con datos: {persisted}"
                cached_requests = viewer.evaluate("""async () => {
                    const out = [];
                    for (const key of await window.caches.keys()) {
                        const cache = await window.caches.open(key);
                        for (const request of await cache.keys()) {
                            if (request.url.includes('/api/cover')) out.push(request.url);
                        }
                    }
                    return out;
                }""")
                assert cached_requests == [], f"portadas en CacheStorage: {cached_requests}"

                # Portada que falla (ficha todavía no cacheada): la imagen se
                # retira sola y queda el marcador.
                viewer.route("**/api/search?*", lambda route: route.fulfill(
                    headers={"X-Biblio-API-Version": "6"},
                    json={"total": 1, "page": 1, "records": [{
                        "record_id": "777", "title": "Un libro", "author": "",
                        "publication": "", "year": "", "language": "", "isbn": "",
                        "classification": "", "extent": "", "summary": "",
                        "subjects": [], "openurl": {}, "doc_type": "", "raw_marc": {},
                        "cover_url": f"/api/cover?account={shared['id']}&record=777"}]}))
                viewer.route("**/api/cover?*", lambda route: route.fulfill(
                    status=404, headers={"X-Biblio-API-Version": "6"}, body=""))
                viewer.locator("#query").fill("libro")
                viewer.locator("#search button").click()
                expect(viewer.locator("#results .book-cover img")).to_have_count(1)
                expect(viewer.locator("#results .book-cover img")).to_have_count(0)
                expect(viewer.locator("#results .book-cover")).to_contain_text("U")
                expect(viewer.locator("#results .book")).to_have_count(1)
                viewer.unroute("**/api/cover?*")
                viewer.unroute("**/api/search?*")

                # Una respuesta antigua con la URL del OPAC nunca se pinta.
                viewer.route("**/api/search?*", lambda route: route.fulfill(
                    headers={"X-Biblio-API-Version": "6"},
                    json={"total": 1, "page": 1, "records": [{
                        "record_id": "123", "title": "Un libro", "author": "",
                        "publication": "", "year": "", "language": "", "isbn": "",
                        "classification": "", "extent": "", "summary": "",
                        "subjects": [], "openurl": {}, "doc_type": "", "raw_marc": {},
                        "cover_url": "https://gestiona3.madrid.org/biblio_publicas/cgi-bin/abnetopac/THREADTOKEN99?ACC=299&MLKOB=1"}]}))
                viewer.locator("#search button").click()
                expect(viewer.locator("#results .book")).to_have_count(1)
                expect(viewer.locator("#results .book-cover img")).to_have_count(0)
                stale = viewer.content()
                assert "THREADTOKEN99" not in stale, "Token del OPAC en el DOM"
                assert "gestiona3.madrid.org" not in stale, "URL del proveedor en el DOM"
                viewer.unroute("**/api/search?*")

                # Invalidación por permiso: al retirar el acceso, la portada de
                # la cuenta que autorizaba ese permiso se revoca; la de la cuenta
                # propia se conserva.
                owner.get_by_role("button", name="Revocar acceso").click()
                expect(owner.locator("#incoming-requests")).to_contain_text("Acceso retirado")
                viewer.locator("#refresh").click()
                expect(viewer.locator("#linked-accounts .settings-card")).to_have_count(1)
                revoked = viewer.evaluate("window.__blobs.revoked")
                assert shared_blob in revoked, "la portada de la cuenta revocada no se revocó"
                assert loan_blob not in revoked, "la portada de la cuenta propia se revocó sin permiso cambiado"
                viewer.locator('[data-view="loans"]').click()
                expect(viewer.locator("#loan-list .book")).to_have_count(1)
                viewer.locator('[data-view="settings"]').click()
                assert viewer.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Horizontal overflow on mobile"

                # Escritorio: mismo catálogo y portada sin tokens del OPAC.
                owner.locator('[data-view="catalog"]').click()
                owner.locator("#catalog-account").select_option(index=0)
                owner.locator("#query").fill("libro")
                owner.locator("#search button").click()
                expect(owner.locator("#results .book-cover img")).to_have_count(1)
                expect(owner.locator("#results .book-cover img")).to_have_attribute(
                    "src", re.compile(r"^blob:"))
                assert "THREADTOKEN" not in owner.content()

                # Escritorio: renovación con la respuesta retenida. La cuenta
                # 111 ya renovó en el móvil (comparten el estado del portal
                # falso), así que el botón de escritorio es el de una segunda
                # biblioteca; se exige la misma guarda, progreso y aviso.
                add_account(owner, "333", "Biblioteca de escritorio")
                owner.locator('[data-view="loans"]').click()
                expect(owner.locator("#loan-list .book")).to_have_count(2)
                pending_owner_renew, owner_renew_hits = [], []

                def hold_owner_renew(route):
                    owner_renew_hits.append(1)
                    pending_owner_renew.append(route)

                owner.route("**/api/renew*", hold_owner_renew)
                expect(owner.get_by_role("button", name="Renovar préstamo →")).to_have_count(1)
                owner.get_by_role("button", name="Renovar préstamo →").click()
                wait_held(owner, pending_owner_renew, "POST renew del escritorio nunca llegó")
                owner_button = owner.locator("#loan-list button")
                expect(owner_button).to_have_count(1)
                expect(owner_button).to_be_disabled()
                expect(owner_button).to_have_attribute("aria-busy", "true")
                expect(owner_button).to_have_text("Renovando…")
                expect(owner.locator("#notice")).to_have_text("Renovando…")
                expect(owner.locator("#notice")).not_to_contain_text("renovado")
                expect(owner.locator("#loan-list")).to_contain_text("05/01/2030")
                owner_button.click(force=True)
                assert len(owner_renew_hits) == 1, f"renovaciones enviadas: {len(owner_renew_hits)}"
                release_held(pending_owner_renew)
                expect(owner.locator("#notice")).to_have_text("«Libro de 333» renovado. Devolución: 20/01/2030 · 15 días restantes.")
                expect(owner.locator("#loan-list")).to_contain_text("20/01/2030")
                expect(owner.locator("#loan-list button")).to_have_count(0)
                owner.unroute("**/api/renew*")
                assert len(owner_renew_hits) == 1, f"POST de renovación totales: {len(owner_renew_hits)}"

                # Escritorio: el mismo estado de arranque renderizado y dentro
                # del viewport, con la sesión retenida antes de resolverla.
                # `pagehide` revoca todas las blob URLs de la pestaña (ADR-014).
                owner.evaluate("window.dispatchEvent(new Event('pagehide'))")
                owner_revoked = owner.evaluate("window.__blobs.revoked")
                owner_missing = [blob for blob in owner.evaluate("window.__blobs.created")
                                 if blob not in owner_revoked]
                assert owner_missing == [], f"blob URLs sin revocar tras pagehide: {owner_missing}"
                pending_owner_session = []
                owner.route("**/api/session*", hold(pending_owner_session))
                owner.reload()
                assert_boot_rendered(owner, "escritorio")
                wait_held(owner, pending_owner_session, "GET session del escritorio nunca llegó")
                release_held(pending_owner_session)
                expect(owner.locator("#boot-loading")).to_be_hidden()
                expect(owner.locator("#dashboard")).to_be_visible()
                owner.unroute("**/api/session*")

                # Logout con una respuesta de panel en vuelo: esa respuesta es de
                # la sesión cerrada, no reanuncia la carga ni levanta el panel.
                pending_library = []
                viewer.route("**/api/library*", hold(pending_library))
                viewer.locator("#refresh").click()
                wait_held(viewer, pending_library, "GET library del logout nunca llegó")
                expect(viewer.locator("#library-loading")).to_be_visible()
                viewer.locator("#logout").click()
                expect(viewer.locator("#welcome")).to_be_visible()
                expect(viewer.locator("#library-loading")).to_be_hidden()
                expect(viewer.locator("#dashboard")).to_be_hidden()
                # Invalidación por logout: ninguna blob URL de la sesión cerrada
                # queda sin revocar (ADR-014).
                logout_revoked = viewer.evaluate("window.__blobs.revoked")
                logout_missing = [blob for blob in viewer.evaluate("window.__blobs.created")
                                  if blob not in logout_revoked]
                assert logout_missing == [], f"blob URLs sin revocar tras logout: {logout_missing}"
                release_held(pending_library)
                time.sleep(1.0)
                expect(viewer.locator("#library-loading")).to_be_hidden()
                expect(viewer.locator("#dashboard")).to_be_hidden()
                expect(viewer.locator("#notice")).not_to_contain_text("La sesión ha cambiado")
                viewer.unroute("**/api/library*")

                # Acceso con la fase de permisos retenida: el panel anuncia su
                # carga desde el login, sin presentar un dashboard vacío.
                pending_settings = []
                viewer.route("**/api/settings*", hold(pending_settings))
                viewer.locator("#username").fill("viewer")
                viewer.locator("#password").fill(APP_PASSWORD)
                viewer.locator("#login button[type=submit]").click()
                wait_held(viewer, pending_settings, "GET settings del login nunca llegó")
                expect(viewer.locator("#welcome")).to_be_hidden()
                expect(viewer.locator("#library-loading")).to_be_visible()
                expect(viewer.locator("#dashboard")).to_have_attribute("aria-busy", "true")
                expect(viewer.locator("#library-loading")).to_have_text("Cargando tu biblioteca…")
                release_held(pending_settings)
                expect(viewer.locator("#library-loading")).to_be_hidden()
                expect(viewer.locator("#dashboard")).to_have_attribute("aria-busy", "false")
                expect(viewer.locator("#loan-list .book")).to_have_count(1)
                viewer.unroute("**/api/settings*")

                # Una respuesta obsoleta de `settings` de la sesión cerrada no
                # reanuncia la carga ni publica su error en el aviso.
                pending_settings = []
                viewer.route("**/api/settings*", hold(pending_settings))
                viewer.locator("#refresh").click()
                wait_held(viewer, pending_settings, "GET settings del refresco nunca llegó")
                expect(viewer.locator("#library-loading")).to_be_visible()
                expect(viewer.locator("#dashboard")).to_have_attribute("aria-busy", "true")
                viewer.locator("#logout").click()
                expect(viewer.locator("#welcome")).to_be_visible()
                expect(viewer.locator("#library-loading")).to_be_hidden()
                expect(viewer.locator("#dashboard")).to_be_hidden()
                release_held(pending_settings)
                time.sleep(0.75)
                expect(viewer.locator("#library-loading")).to_be_hidden()
                expect(viewer.locator("#dashboard")).to_be_hidden()
                expect(viewer.locator("#notice")).not_to_contain_text("La sesión ha cambiado")
                viewer.unroute("**/api/settings*")

                # Identidad (FR-AUTH-002 / FR-AUTH-003): verificar el email
                # desde Configuración con el correo del servidor falso, entrar
                # con el email, cambiar la contraseña y recuperarla. El código
                # lo lee la prueba del SMTP falso, no se inventa en el cliente.
                viewer.locator("#show-register").click()
                viewer.locator("#register-name").fill("Identidad")
                viewer.locator("#register-username").fill("ident")
                viewer.locator("#register-password").fill(APP_PASSWORD)
                viewer.locator("#register button[type=submit]").click()
                expect(viewer.locator("#settings")).to_be_visible()
                expect(viewer.locator("#email-state")).to_contain_text("Añade un email verificado")
                viewer.locator("#email-input").fill("ident@ejemplo.test")
                viewer.locator("#email-form button[type=submit]").click()
                expect(viewer.locator("#email-verify-row")).to_be_visible()
                expect(viewer.locator("#email-state")).to_contain_text("Pendiente de verificar")
                viewer.locator("#email-token").fill(smtp.last_token())
                # Un email sin verificar no abre sesión; el username sí.
                viewer.locator("#logout").click()
                viewer.locator("#username").fill("ident@ejemplo.test")
                viewer.locator("#password").fill(APP_PASSWORD)
                viewer.locator("#login button[type=submit]").click()
                expect(viewer.locator("#welcome")).to_be_visible()
                expect(viewer.locator("#notice")).to_contain_text("incorrectos")
                viewer.locator("#username").fill("ident")
                viewer.locator("#password").fill(APP_PASSWORD)
                viewer.locator("#login button[type=submit]").click()
                expect(viewer.locator("#settings")).to_be_visible()
                # El pendiente no se persiste: se pide el código otra vez y se
                # verifica con el correo del servidor falso.
                viewer.locator("#email-input").fill("ident@ejemplo.test")
                viewer.locator("#email-form button[type=submit]").click()
                expect(viewer.locator("#email-verify-row")).to_be_visible()
                viewer.locator("#email-token").fill(smtp.last_token())
                viewer.locator("#email-verify").click()
                expect(viewer.locator("#email-state")).to_contain_text("Email verificado: ident@ejemplo.test")
                # El email verificado entra con la contraseña vigente.
                viewer.locator("#logout").click()
                viewer.locator("#username").fill("ident@ejemplo.test")
                viewer.locator("#password").fill(APP_PASSWORD)
                viewer.locator("#login button[type=submit]").click()
                expect(viewer.locator("#settings")).to_be_visible()
                # Cambiar la contraseña desde Configuración mantiene la sesión.
                viewer.locator("#current-password").fill(APP_PASSWORD)
                viewer.locator("#new-password").fill("nueva-identidad-77")
                viewer.locator("#password-form button[type=submit]").click()
                expect(viewer.locator("#notice")).to_contain_text("Contraseña actualizada")
                expect(viewer.locator("#settings")).to_be_visible()
                # El email verificado entra con la contraseña nueva.
                viewer.locator("#logout").click()
                viewer.locator("#username").fill("ident@ejemplo.test")
                viewer.locator("#password").fill("nueva-identidad-77")
                viewer.locator("#login button[type=submit]").click()
                expect(viewer.locator("#settings")).to_be_visible()
                # Recuperación con el código del correo falso.
                viewer.locator("#logout").click()
                viewer.locator("#show-recovery").click()
                expect(viewer.locator("#recovery")).to_be_visible()
                viewer.locator("#recovery-email").fill("ident@ejemplo.test")
                viewer.locator("#recovery-send").click()
                expect(viewer.locator("#recovery-reset")).to_be_visible()
                viewer.locator("#recovery-token").fill(smtp.last_token())
                viewer.locator("#recovery-password").fill("recuperada-identidad-88")
                viewer.locator("#recovery-confirm").click()
                expect(viewer.locator("#login")).to_be_visible()
                viewer.locator("#username").fill("ident")
                viewer.locator("#password").fill("recuperada-identidad-88")
                viewer.locator("#login button[type=submit]").click()
                expect(viewer.locator("#settings")).to_be_visible()
                expect(viewer.locator("#email-state")).to_contain_text("Email verificado")

                # Passkeys (FR-AUTH-004) con el autenticador virtual de
                # Chromium: registrar en Configuración exige reautenticación,
                # la passkey aparece listada y sirve para entrar sin contraseña.
                passkey_context = browser.new_context(viewport={"width": 1280, "height": 900})
                passkey_page = passkey_context.new_page()
                passkey_page.on("pageerror", lambda error: errors.append(str(error)))
                passkey_page.on("dialog", lambda dialog: dialog.accept())
                cdp = passkey_context.new_cdp_session(passkey_page)
                cdp.send("WebAuthn.enable", {})
                cdp.send("WebAuthn.addVirtualAuthenticator", {"options": {
                    "protocol": "ctap2", "transport": "internal", "hasResidentKey": True,
                    "hasUserVerification": True, "isUserVerified": True,
                    "automaticPresenceSimulation": True}})
                # Chromium exige un `rpId` con forma de dominio: la passkey se
                # prueba en `localhost` (misma instancia, otro host local).
                passkey_url = f"http://localhost:{server.server_port}"
                register(passkey_page, "passkeyuser", passkey_url)
                expect(passkey_page.locator("#passkey-add")).to_be_enabled()
                passkey_page.locator("#passkey-add").click()
                # El servidor pide reautenticación explícita (ventana corta).
                expect(passkey_page.locator("#reauth")).to_be_visible()
                expect(passkey_page.locator("#reauth-password")).to_be_focused()
                passkey_page.locator("#reauth-password").fill("contraseña-mala")
                passkey_page.locator("#reauth-form button[type=submit]").click()
                expect(passkey_page.locator("#reauth-error")).to_be_visible()
                passkey_page.locator("#reauth-password").fill(APP_PASSWORD)
                passkey_page.locator("#reauth-form button[type=submit]").click()
                expect(passkey_page.locator("#reauth")).to_be_hidden()
                expect(passkey_page.locator("#passkey-list")).to_contain_text("Passkey")
                expect(passkey_page.locator("#passkey-list")).to_contain_text("Borrar passkey")
                # Borrar exige reautenticación de nuevo: se cierra la ventana
                # de reautenticación (constante del servidor) para poder
                # observar el diálogo en un escenario que dura segundos.
                web_module.REAUTH_TTL = 0
                passkey_page.locator("#passkey-list button").click()
                expect(passkey_page.locator("#reauth")).to_be_visible()
                passkey_page.locator("#reauth-close").click()
                expect(passkey_page.locator("#passkey-list")).to_contain_text("Passkey")
                web_module.REAUTH_TTL = REAUTH_TTL
                # Login con passkey tras cerrar sesión, con la sesión nueva.
                passkey_page.locator("#logout").click()
                expect(passkey_page.locator("#welcome")).to_be_visible()
                expect(passkey_page.locator("#passkey-login-row")).to_be_visible()
                passkey_page.locator("#passkey-login").click()
                expect(passkey_page.locator("#dashboard")).to_be_visible()
                expect(passkey_page.locator("#my-identity")).to_contain_text("@passkeyuser")
                # La passkey sobrevive a la recarga y aparece en Configuración.
                passkey_page.reload()
                expect(passkey_page.locator("#passkey-list")).to_contain_text("Passkey")
                passkey_context.close()

                # Móvil emulado: alta y login con passkey en 390×844, con su
                # propio autenticador virtual (las passkeys no se sincronizan
                # entre contextos del navegador de prueba).
                mobile_passkey_context = browser.new_context(
                    viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
                mobile_passkey = mobile_passkey_context.new_page()
                mobile_passkey.on("pageerror", lambda error: errors.append(str(error)))
                mobile_passkey.on("dialog", lambda dialog: dialog.accept())
                mobile_cdp = mobile_passkey_context.new_cdp_session(mobile_passkey)
                mobile_cdp.send("WebAuthn.enable", {})
                mobile_cdp.send("WebAuthn.addVirtualAuthenticator", {"options": {
                    "protocol": "ctap2", "transport": "internal", "hasResidentKey": True,
                    "hasUserVerification": True, "isUserVerified": True,
                    "automaticPresenceSimulation": True}})
                register(mobile_passkey, "movilpass", passkey_url)
                mobile_passkey.locator("#passkey-add").click()
                expect(mobile_passkey.locator("#reauth")).to_be_visible()
                mobile_passkey.locator("#reauth-password").fill(APP_PASSWORD)
                mobile_passkey.locator("#reauth-form button[type=submit]").click()
                expect(mobile_passkey.locator("#passkey-list")).to_contain_text("Passkey")
                assert mobile_passkey.evaluate("document.documentElement.scrollWidth <= innerWidth")
                mobile_passkey.locator("#logout").click()
                expect(mobile_passkey.locator("#passkey-login-row")).to_be_visible()
                mobile_passkey.locator("#passkey-login").click()
                expect(mobile_passkey.locator("#dashboard")).to_be_visible()
                expect(mobile_passkey.locator("#my-identity")).to_contain_text("@movilpass")
                mobile_passkey_context.close()

                # Acceso con Google (FR-AUTH-005) contra el proveedor falso:
                # vincular con email verificado + reautenticación, y entrar con
                # la cuenta vinculada. El proveedor redirige al callback.
                google_context = browser.new_context(viewport={"width": 1280, "height": 900})
                google_page = google_context.new_page()
                google_page.on("pageerror", lambda error: errors.append(str(error)))
                google_page.on("dialog", lambda dialog: dialog.accept())
                register(google_page, "googleuser")
                expect(google_page.locator("#google-link")).to_be_visible()
                expect(google_page.locator("#google-state")).to_contain_text("Vincula tu cuenta de Google")
                google_page.locator("#email-input").fill("googleuser@ejemplo.test")
                google_page.locator("#email-form button[type=submit]").click()
                expect(google_page.locator("#email-verify-row")).to_be_visible()
                google_page.locator("#email-token").fill(smtp.last_token())
                google_page.locator("#email-verify").click()
                expect(google_page.locator("#email-state")).to_contain_text("Email verificado")
                google_page.locator("#google-link").click()
                expect(google_page.locator("#reauth")).to_be_visible()
                google_page.locator("#reauth-password").fill(APP_PASSWORD)
                google_page.locator("#reauth-form button[type=submit]").click()
                expect(google_page.locator("#notice")).to_contain_text("vinculada")
                expect(google_page.locator("#google-unlink")).to_be_visible()
                expect(google_page.locator("#google-link")).to_be_hidden()
                # Salir y volver a entrar con la cuenta de Google vinculada.
                google_page.locator("#logout").click()
                expect(google_page.locator("#google-login")).to_be_visible()
                expect(google_page.locator("#google-signup")).to_be_visible()
                google_page.locator("#google-login").click()
                expect(google_page.locator("#dashboard")).to_be_visible()
                expect(google_page.locator("#my-identity")).to_contain_text("@googleuser")
                expect(google_page.locator("#google-state")).to_contain_text("vinculada")
                google_context.close()

                # Móvil emulado: la entrada con Google también funciona.
                mobile_google_context = browser.new_context(
                    viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
                mobile_google = mobile_google_context.new_page()
                mobile_google.on("pageerror", lambda error: errors.append(str(error)))
                mobile_google.goto(url)
                expect(mobile_google.locator("#google-login")).to_be_visible()
                mobile_google.locator("#google-login").click()
                expect(mobile_google.locator("#dashboard")).to_be_visible()
                expect(mobile_google.locator("#my-identity")).to_contain_text("@googleuser")
                assert mobile_google.evaluate("document.documentElement.scrollWidth <= innerWidth")
                mobile_google_context.close()

                # Login CSRF de Google (TODO-SEC-004): el flujo queda atado al
                # navegador que lo inició. El proveedor falso devuelve el par
                # `code`+`state` a quien inicia; transportar ese callback al
                # navegador de otra persona —sin su cookie de enlace— no debe
                # abrir sesión. Primero el navegador legítimo completa.
                csrf_context = browser.new_context(viewport={"width": 1280, "height": 900})
                csrf_page = csrf_context.new_page()
                csrf_page.on("pageerror", lambda error: errors.append(str(error)))
                csrf_page.on("dialog", lambda dialog: dialog.accept())
                csrf_page.goto(url)
                expect(csrf_page.locator("#google-login")).to_be_visible()
                # La SPA navega al proveedor dentro de la misma tarea que
                # resuelve el `fetch`, así que el cuerpo de la respuesta deja de
                # estar disponible para el protocolo de red en cuanto ocurre la
                # redirección. Se retiene la petición (misma técnica que las
                # cargas retenidas de arriba): `fetch` la envía una sola vez, se
                # lee el cuerpo mientras el recurso vive y se responde al
                # navegador con ese mismo cuerpo (`fulfill`, sin duplicar la
                # petición en el servidor).
                captured = {}

                def capture_start(route):
                    response = route.fetch()
                    captured["response"] = response
                    route.fulfill(response=response)

                csrf_page.route("**/api/auth/google/start*", capture_start)
                csrf_page.locator("#google-login").click()
                for _ in range(120):
                    if "response" in captured:
                        break
                    csrf_page.wait_for_timeout(250)
                csrf_page.unroute("**/api/auth/google/start*", capture_start)
                assert "response" in captured, "no se capturó la respuesta de google/start"
                authorize_url = json.loads(
                    captured["response"].body().decode("utf-8"))["authorize_url"]
                # El proveedor falso responde al `authorize` con un 303 al
                # callback con `code`+`state`; para el navegador víctima se
                # arma esa URL sin tocar al proveedor ni a su cookie.
                parsed = urlsplit(authorize_url)
                hostile_callback = (f"{url.rstrip('/')}{GOOGLE_CALLBACK_PATH}"
                                    f"?{parsed.query}")
                # Dos navegadores distintos: uno conserva su cookie de enlace,
                # el otro no la tiene (contexto recién creado, sin cookies).
                victim_context = browser.new_context(viewport={"width": 1280, "height": 900})
                victim_page = victim_context.new_page()
                victim_page.on("pageerror", lambda error: errors.append(str(error)))
                victim_page.goto(url)
                expect(victim_page.locator("#login")).to_be_visible()
                # La víctima carga el callback ajeno: sin su cookie de enlace el
                # servidor rechaza y no abre sesión (no toca al proveedor).
                victim_page.goto(hostile_callback)
                expect(victim_page.locator("#login")).to_be_visible()
                # El navegador que inició el flujo sí completa con su cookie.
                csrf_page.goto(authorize_url)
                expect(csrf_page.locator("#dashboard")).to_be_visible()
                csrf_context.close()
                victim_context.close()

                # Origen no confiable (NFR-SVC-003): con `isSecureContext`
                # forzado a falso —como haría HTTP servido desde una IP de
                # red local— el aviso persistente aparece y el resto de la
                # aplicación sigue funcionando.
                insecure_context = browser.new_context(viewport={"width": 1280, "height": 900})
                insecure = insecure_context.new_page()
                insecure.on("pageerror", lambda error: errors.append(str(error)))
                insecure.add_init_script(
                    "Object.defineProperty(window, 'isSecureContext', "
                    "{get: () => false, configurable: true});")
                insecure.goto(url)
                expect(insecure.locator("#origin-warning")).to_be_visible()
                expect(insecure.locator("#origin-warning")).to_contain_text("passkeys")
                expect(insecure.locator("html")).to_have_attribute("data-secure-origin", "false")
                # Sin contexto seguro no hay controles de passkey que ofrecer;
                # el acceso con Google (OIDC) no depende del contexto del navegador.
                expect(insecure.locator("#passkey-login-row")).to_be_hidden()
                expect(insecure.locator("#welcome")).to_be_visible()
                insecure_context.close()

                assert not errors, errors
                browser.close()
                print("UI OK: registro, vinculación, solicitud, lectura, gestión, panel conjunto, "
                      "estado de carga accesible (arranque/restauración renderizado y dentro del "
                      "viewport en escritorio y móvil, con spinner estático bajo "
                      "prefers-reduced-motion; login, recarga, error y logout con respuesta "
                      "obsoleta en library y en settings), filtro, renovación con la respuesta "
                      "retenida en escritorio y móvil (botón bloqueado con aria-busy y progreso "
                      "accesible, un solo POST ante un segundo intento y aviso de éxito solo "
                      "tras el panel verificado), portadas "
                      "(catálogo, préstamo y reserva: cargada, rota y URL antigua) con caché RAM "
                      "por blob URL invalidada en logout, pagehide y cambio de permiso, sin "
                       "persistencia en CacheStorage/localStorage/sessionStorage, aviso de origen "
                       "no confiable, detalle, reserva y revocación; identidad con email verificado "
                       "desde Configuración, login con email verificado (y rechazo del sin verificar), "
                       "cambio de contraseña con la sesión viva y recuperación con el correo falso; "
                        "passkeys con autenticador virtual (reautenticación para añadir y borrar, "
                        "listado y login sin contraseña) y acceso con Google contra el proveedor "
                        "falso (vinculación con email verificado + reautenticación y entrada con la "
                        "cuenta vinculada, más login CSRF rechazado: el par code+state del navegador "
                        "que inició el flujo no abre sesión en otro navegador sin su cookie de "
                        "enlace, TODO-SEC-004); "
                       "sin tokens del OPAC en el "
                       "DOM, sin errores JS ni desbordamiento móvil.")
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
            smtp.shutdown()
            smtp.server_close()
            smtp_thread.join()
            oidc.stop()
            store.close()


if __name__ == "__main__":
    main()
