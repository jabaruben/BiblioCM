"""Portadas: la URL con token se resuelve en el servidor y solo se descarga
en el origen/CGI del OPAC. Sin red externa: los servidores son locales."""
import http.server
import threading
import unittest
import urllib.parse
from pathlib import Path

from biblio import parser
from biblio.client import AbsysClient, is_portal_url, record_from_document_page
from biblio.http import Http, HttpError, Response, origin

FIXTURE = Path(__file__).with_name("fixtures") / "search_results.html"
DOCUMENT_FIXTURE = Path(__file__).with_name("fixtures") / "document_page.html"
COPIES_FIXTURE = Path(__file__).with_name("fixtures") / "record_copies.html"
BASE = "https://example.test/biblio_publicas/"
COVER_RELATIVE = "/biblio_publicas/cgi-bin/abnetopac/THREADTOKEN02?ACC=299&MLKOB=1553619074343"
COVER_ABSOLUTE = "https://example.test/biblio_publicas/cgi-bin/abnetopac/THREADTOKEN02?ACC=299&MLKOB=1553619074343"
DOCUMENT_COVER_RELATIVE = "/biblio_publicas/cgi-bin/abnetopac/THREADTOKEN05?ACC=294&DOC=1&MLKOB=1522445965151"
DOCUMENT_URL = BASE + "cgi-bin/abnetopac/THREADTOKEN05/NT44"
SEARCH_URL = BASE + "cgi-bin/abnetopac/THREADTOKEN02/NT15"
HOME_HTML = (
    '<html><body><form id="abnformSearch" method="post" '
    'action="/biblio_publicas/cgi-bin/abnetopac/THREADTOKEN01/NT3">'
    '<input type="hidden" name="ACC" value="131"/><input name="xsqf01"/>'
    "</form></body></html>"
)


class FakeHttp:
    """Devuelve la portada del fixture y registra las descargas de imagen."""

    def __init__(self):
        self.gets, self.posts, self.images = [], [], []

    def get(self, url, follow_refresh=True):
        self.gets.append(url)
        return Response(url, HOME_HTML)

    def post(self, url, fields, follow_refresh=False):
        self.posts.append((url, dict(fields)))
        return Response(SEARCH_URL, FIXTURE.read_text(encoding="utf-8"))

    def get_image(self, url, allowed_origin, max_bytes=None):
        self.images.append((url, allowed_origin))
        return b"png-de-ejemplo", "image/png"


class ImageHandler(http.server.BaseHTTPRequestHandler):
    body = b"\x89PNG\r\n\x1a\nportada-de-ejemplo"
    content_type = "image/png"
    redirect_to = None
    hits = 0

    def log_message(self, *args):
        pass

    def do_GET(self):
        cls = type(self)
        cls.hits += 1
        if cls.redirect_to and self.path == "/cover.png":
            self.send_response(302)
            self.send_header("Location", cls.redirect_to)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", cls.content_type)
        self.send_header("Content-Length", str(len(cls.body)))
        self.end_headers()
        self.wfile.write(cls.body)


class LocalServer:
    def __init__(self, handler):
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.httpd.server_address
        self.origin = f"http://{host}:{port}"

    def url(self, path):
        return self.origin + path

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)


def handler(name, **attributes):
    return type(name, (ImageHandler,), attributes)


class SearchResolvesTheCoverUrl(unittest.TestCase):
    def setUp(self):
        self.http = FakeHttp()
        self.client = AbsysClient("fake", "fake", base_url=BASE, http=self.http)
        self.client._base = BASE + "cgi-bin/abnetopac/THREADTOKEN01/NT3"

    def test_relative_cover_becomes_absolute_with_the_thread_token(self):
        total, records = self.client.search("libro")
        self.assertEqual(total, 1029)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].cover_url, COVER_ABSOLUTE)

    def test_records_without_cover_keep_an_empty_url(self):
        _, records = self.client.search("sin portada")
        self.assertEqual(records[1].cover_url, "")

    def test_parser_keeps_the_relative_value(self):
        # La resolución es responsabilidad del cliente, no del parser.
        _, records = parser.parse_search_results(FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(records[0].cover_url, COVER_RELATIVE)

    def test_the_cover_is_not_replaced_by_an_earlier_image(self):
        """Un icono dentro de la tarjeta no debe pasar por ser la portada."""
        html = (
            '<html><body><p>1029 resultados</p><ol class="c-docs">'
            '<li class="c-docs_unit"><div class="c-docs_info">'
            '<img src="/biblio_publicas/css/icono.gif" alt="">'
            '<span class="c-docs_author">Autora, Una</span>'
            '<span class="c-docs_title">Título de prueba</span>'
            '<p class="c-docs_marc dn"><span class="js-TITN">123</span></p>'
            "</div>"
            '<div class="c-docs_img"><span class="c-docs_imgPreLoad">'
            '<img loading="lazy" alt="Cubierta - 1" '
            'src="/biblio_publicas/cgi-bin/abnetopac/THREADTOKEN02?ACC=299&amp;MLKOB=1553619074343">'
            "</span></div></li></ol></body></html>"
        )
        _, records = parser.parse_search_results(html)
        self.assertIn("MLKOB=1553619074343", records[0].cover_url)


class DocumentPageCover(unittest.TestCase):
    """Con un único resultado el portal salta a la ficha, que también trae portada."""

    def test_record_page_cover_is_read_with_the_same_rule(self):
        record = record_from_document_page(DOCUMENT_FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(record.cover_url, DOCUMENT_COVER_RELATIVE)
        self.assertEqual(record.record_id, "288993")

    def test_record_page_without_cover_keeps_an_empty_url(self):
        record = record_from_document_page(COPIES_FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(record.cover_url, "")


class RecordCoverDiscovery(unittest.TestCase):
    """El cliente puede descubrir la portada abriendo la ficha del registro."""

    def client_for(self, html):
        gets = []

        class Http:
            def get(inner_self, url, follow_refresh=True):
                gets.append(url)
                return Response(url, html)

        client = AbsysClient("fake", "fake", base_url=BASE, http=Http())
        client._base = BASE + "cgi-bin/abnetopac/THREADTOKEN05/NT44"
        return client, gets

    def test_cover_url_is_resolved_against_the_record_response(self):
        client, gets = self.client_for(DOCUMENT_FIXTURE.read_text(encoding="utf-8"))
        discovered = client.record_cover_url("288993")
        self.assertEqual(discovered, urllib.parse.urljoin(DOCUMENT_URL, DOCUMENT_COVER_RELATIVE))
        self.assertTrue(is_portal_url(discovered, BASE))
        self.assertEqual(len(gets), 1, "una sola apertura de ficha por descubrimiento")

    def test_record_page_without_cover_reports_nothing(self):
        client, _ = self.client_for(COPIES_FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(client.record_cover_url("288993"), "")

    def test_foreign_cover_on_the_record_page_is_refused(self):
        html = DOCUMENT_FIXTURE.read_text(encoding="utf-8").replace(
            "/biblio_publicas/cgi-bin/abnetopac/THREADTOKEN05?ACC=294&amp;DOC=1&amp;MLKOB=1522445965151",
            "https://evil.example/portada.png")
        client, _ = self.client_for(html)
        self.assertEqual(client.record_cover_url("288993"), "")


class CoverUrlValidation(unittest.TestCase):
    def setUp(self):
        self.http = FakeHttp()
        self.client = AbsysClient("fake", "fake", base_url=BASE, http=self.http)

    def cover(self, url):
        return self.client.cover(url)

    def test_registered_cover_is_fetched_only_on_the_portal_origin(self):
        data, content_type = self.cover(COVER_ABSOLUTE)
        self.assertEqual((data, content_type), (b"png-de-ejemplo", "image/png"))
        self.assertEqual(self.http.images, [(COVER_ABSOLUTE, "https://example.test")])

    def test_relative_cover_path_is_resolved_against_the_portal(self):
        self.cover(COVER_RELATIVE)
        self.assertEqual(self.http.images[0][0], COVER_ABSOLUTE)

    def test_foreign_origin_is_rejected_without_any_request(self):
        for url in (
            "https://evil.example/biblio_publicas/cgi-bin/abnetopac/TOK?ACC=299",
            "javascript:alert(1)",
            "http://127.0.0.1:1/biblio_publicas/cgi-bin/abnetopac/TOK?ACC=299",
        ):
            with self.subTest(url=url), self.assertRaises(HttpError):
                self.cover(url)
        self.assertEqual(self.http.images, [])

    def test_path_outside_the_opac_cgi_is_rejected(self):
        for url in (
            "https://example.test/biblio_publicas/portada.png",
            "https://example.test/biblio_publicas/cgi-bin/abnetopacEVIL/TOK?ACC=299",
        ):
            with self.subTest(url=url), self.assertRaises(HttpError):
                self.cover(url)
        self.assertEqual(self.http.images, [])

    def test_empty_url_is_rejected(self):
        with self.assertRaises(HttpError):
            self.cover("")
        self.assertEqual(self.http.images, [])

    def test_traversal_and_encoded_traversal_are_rejected_without_any_request(self):
        cgi = "https://example.test/biblio_publicas/cgi-bin/abnetopac"
        for url in (
            cgi + "/TOK/../portadas/x.png",            # dot segment en crudo
            cgi + "/TOK/./x.png",
            cgi + "/TOK/%2e%2e/portadas/x.png",        # dot segment codificado
            cgi + "/TOK/%2E%2E%2Fportadas%2Fx.png",    # separador y dots codificados
            cgi + "/TOK/%252e%252e/x.png",             # doble codificación
            cgi + "/TOK/..%5cx.png",                   # backslash codificado
            cgi + "/TOK/%2f%2e%2e/x.png",              # slash codificado
            cgi + "/TOK/..\\..\\x.png",                # backslash en crudo
            cgi + "/TOK/%0d%0aLocation:%20x.png",      # control codificado
        ):
            with self.subTest(url=url), self.assertRaises(HttpError):
                self.cover(url)
        self.assertEqual(self.http.images, [], "una URL con traversal no debe llegar a la descarga")

    def test_deeply_encoded_traversal_is_rejected_without_any_request(self):
        # Regresión exacta de la revisión: la codificación anidada tarda más de
        # cuatro capas en convertirse en `../`, y antes pasaba la validación.
        url = ("https://example.test/biblio_publicas/cgi-bin/abnetopac/"
               "%252525252e%252525252e%252525252fadmin")
        self.assertFalse(is_portal_url(url, BASE), "esta URL debe rechazarse")
        with self.assertRaises(HttpError):
            self.cover(url)
        self.assertEqual(self.http.images, [], "no debe llegar a la descarga")

    def test_encoding_depth_beyond_the_limit_is_rejected(self):
        # Sin dot segments en ninguna capa: solo se rechaza porque la
        # normalización no estabiliza dentro del tope de profundidad.
        deep = BASE + "cgi-bin/abnetopac/" + "%25" + "25" * 12
        self.assertFalse(is_portal_url(deep, BASE))
        with self.assertRaises(HttpError):
            self.cover(deep)
        self.assertEqual(self.http.images, [])

    def test_malformed_authority_is_rejected_without_any_request(self):
        for url in (
            "https://persona@example.test/biblio_publicas/cgi-bin/abnetopac/TOK?ACC=299",
            "https://example.test:99999/biblio_publicas/cgi-bin/abnetopac/TOK?ACC=299",
            "https://example.test:abc/biblio_publicas/cgi-bin/abnetopac/TOK?ACC=299",
            "https://example.test\\@evil.example/biblio_publicas/cgi-bin/abnetopac/TOK?ACC=299",
            "https://example.test/biblio_publicas/cgi-bin/abnetopac/TOK%00.png?ACC=299",
            "https://example.test/biblio_publicas/cgi-bin/abnetopac/TOK?ACC=299\r\nX:1",
        ):
            with self.subTest(url=url), self.assertRaises(HttpError):
                self.cover(url)
        self.assertEqual(self.http.images, [])

    def test_is_portal_url_only_accepts_http_on_the_portal_cgi(self):
        self.assertTrue(is_portal_url(COVER_ABSOLUTE, BASE))
        self.assertTrue(is_portal_url(BASE + "cgi-bin/abnetopac?ACC=299", BASE))
        self.assertFalse(is_portal_url("ftp://example.test/cgi-bin/abnetopac/TOK", BASE))
        self.assertFalse(is_portal_url("https://example.test/otro?ACC=299", BASE))
        self.assertFalse(is_portal_url(COVER_ABSOLUTE, "https://otro.test/biblio_publicas/"))


class HttpImageDownload(unittest.TestCase):
    """Servidores locales: comprueba límites del proxy sin tocar el OPAC."""

    def setUp(self):
        self.servers = []

    def tearDown(self):
        for server in self.servers:
            server.close()

    def serve(self, **attributes):
        server = LocalServer(handler(f"Handler{len(self.servers)}", **attributes))
        self.servers.append(server)
        return server

    def test_returns_bytes_and_content_type(self):
        server = self.serve()
        data, content_type = Http(base_delay=0).get_image(server.url("/cover.png"), server.origin)
        self.assertEqual(data, ImageHandler.body)
        self.assertEqual(content_type, "image/png")

    def test_same_origin_redirect_is_followed(self):
        server = self.serve(redirect_to="/real.png")
        data, _ = Http(base_delay=0).get_image(server.url("/cover.png"), server.origin)
        self.assertEqual(data, ImageHandler.body)
        self.assertEqual(server.httpd.RequestHandlerClass.hits, 2)

    def test_cross_origin_redirect_never_contacts_the_target(self):
        target = self.serve(body=b"interno", content_type="image/png")
        source = self.serve(redirect_to=target.url("/secret.png"))
        with self.assertRaises(HttpError):
            Http(base_delay=0).get_image(source.url("/cover.png"), source.origin)
        self.assertEqual(target.httpd.RequestHandlerClass.hits, 0)

    def test_non_image_content_type_is_rejected(self):
        server = self.serve(content_type="text/html", body=b"<html>sesion</html>")
        with self.assertRaises(HttpError):
            Http(base_delay=0).get_image(server.url("/cover.png"), server.origin)

    def test_oversized_body_is_rejected(self):
        server = self.serve(body=b"x" * 64)
        with self.assertRaises(HttpError):
            Http(base_delay=0).get_image(server.url("/cover.png"), server.origin, max_bytes=16)

    def test_url_outside_allowed_origin_is_rejected_before_requesting(self):
        server = self.serve()
        with self.assertRaises(HttpError):
            Http(base_delay=0).get_image(server.url("/cover.png"), "https://other.example")
        self.assertEqual(server.httpd.RequestHandlerClass.hits, 0)

    def test_traversal_path_is_rejected_before_requesting(self):
        server = self.serve()
        for path in (
            "/biblio_publicas/cgi-bin/abnetopac/../secret.png",
            "/biblio_publicas/cgi-bin/abnetopac/%2e%2e/secret.png",
            "/biblio_publicas/cgi-bin/abnetopac/%2E%2E%2Fsecret.png",
        ):
            with self.subTest(path=path), self.assertRaises(HttpError):
                Http(base_delay=0).get_image(server.url(path), server.origin)
        self.assertEqual(server.httpd.RequestHandlerClass.hits, 0,
                         "una ruta con traversal no debe llegar al servidor")

    def test_redirect_to_traversal_path_is_not_followed(self):
        server = self.serve(redirect_to="/biblio_publicas/abnetopac/../../secret.png")
        with self.assertRaises(HttpError):
            Http(base_delay=0).get_image(server.url("/cover.png"), server.origin)
        self.assertEqual(server.httpd.RequestHandlerClass.hits, 1,
                         "solo la petición inicial: la redirección no se sigue")

    def test_deeply_encoded_traversal_is_rejected_before_requesting(self):
        server = self.serve()
        path = ("/biblio_publicas/cgi-bin/abnetopac/"
                "%252525252e%252525252e%252525252fadmin")
        with self.assertRaises(HttpError):
            Http(base_delay=0).get_image(server.url(path), server.origin)
        self.assertEqual(server.httpd.RequestHandlerClass.hits, 0,
                         "la codificación profunda no debe llegar al servidor")

    def test_origin_helper(self):
        self.assertEqual(origin("https://Example.test/a?b=1"), "https://example.test")
        self.assertEqual(origin("https://example.test:443/a"), "https://example.test")
        self.assertEqual(origin("https://example.test:8443/a"), "https://example.test:8443")
        self.assertEqual(origin("/relativa"), "")
        self.assertEqual(origin("ftp://example.test/a"), "")
        # Autoridades malformadas no producen un origen comparable.
        self.assertEqual(origin("https://persona@example.test/a"), "")
        self.assertEqual(origin("https://example.test:99999/a"), "")
        self.assertEqual(origin("https://example.test/a\r\nX:1"), "")


if __name__ == "__main__":
    unittest.main()
