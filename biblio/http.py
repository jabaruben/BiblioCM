"""Capa HTTP: el OPAC habla latin-1, encadena meta-refresh y no envía cookies
que nos interesen. Esta capa centraliza las tres cosas.
"""

from __future__ import annotations

import gzip
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib

DEFAULT_BASE_DELAY = 1.0
DEFAULT_TIMEOUT = 30
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
MAX_IMAGE_BYTES = 1_500_000


class HttpError(RuntimeError):
    pass


# Carácter de control y backslash: nunca deben viajar en una URL que vamos a
# pedir (inyección de cabecera, separador alternativo en algunos servidores).
_CONTROL_OR_BACKSLASH = re.compile(r"[\x00-\x1f\x7f\\]")
# Segmentos `.` y `..` como segmentos completos de la ruta.
_DOT_SEGMENT = re.compile(r"(?:^|/)\.{1,2}(?:/|$)")
# Separadores percent-codificados: esconden un cambio de ruta para el servidor.
_ENCODED_SEPARATOR = re.compile(r"%(?:2f|5c)", re.IGNORECASE)
# Profundidad máxima de decodificación. La capa de codificación la decide quien
# envía la URL, así que si no estabiliza dentro de este tope se rechaza: no se
# normaliza recursivamente sin límite (CPU) ni se acepta una ruta "a medias".
MAX_PATH_DECODINGS = 6


def has_unsafe_url_chars(url: str) -> bool:
    """True si la cadena contiene backslash o caracteres de control.

    `urlsplit` elimina tabuladores y saltos de línea por su cuenta, así que hay
    que mirar la cadena original antes de que nada la normalice.
    """
    return bool(_CONTROL_OR_BACKSLASH.search(url))


def path_layers(path: str) -> list[str] | None:
    """Capas de decodificación percent de la ruta, o `None` si no estabiliza.

    Devuelve `[ruta en crudo, capa 1, …]` terminando en el valor estable, o
    `None` cuando todavía cambiaba al agotar `MAX_PATH_DECODINGS`. El número de
    iteraciones está acotado, así que el coste es lineal y acotado.
    """
    layers = [path]
    value = path
    for _ in range(MAX_PATH_DECODINGS):
        nxt = urllib.parse.unquote(value)
        if nxt == value:
            return layers
        layers.append(nxt)
        value = nxt
    return None


def decoded_path(path: str) -> str:
    """Última capa estabilizada de la ruta; cadena vacía si no llega a ella."""
    layers = path_layers(path)
    return layers[-1] if layers else ""


def has_unsafe_path(url: str) -> bool:
    """True si la ruta permite salir del destino previsto.

    Se comprueba **cada capa** de decodificación (no solo la cruda y la final):
    así un `..` o un `%2f` que aparecen después de varias capas también se ven.
    Si la ruta no estabiliza dentro de `MAX_PATH_DECODINGS` se considera
    insegura, igual que si contiene dot segments, separadores percent-codificados,
    backslashes o caracteres de control.
    """
    try:
        path = urllib.parse.urlsplit(url).path
    except ValueError:
        return True
    layers = path_layers(path)
    if layers is None:
        return True
    for layer in layers:
        if _CONTROL_OR_BACKSLASH.search(layer) or _DOT_SEGMENT.search(layer):
            return True
        if _ENCODED_SEPARATOR.search(layer):
            return True
    return False


def origin(url: str) -> str:
    """`https://host[:puerto]` normalizado; cadena vacía si la URL no es válida.

    Se descartan userinfo, puertos malformados o fuera de rango, backslashes y
    caracteres de control, para que la comparación de orígenes no se pueda
    confundir con una autoridad distinta a la permitida.
    """
    if has_unsafe_url_chars(url):
        return ""
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return ""
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https") or not parts.netloc:
        return ""
    if parts.username is not None or parts.password is not None:
        return ""
    try:
        port = parts.port
    except ValueError:
        return ""
    host = parts.hostname
    if not host:
        return ""
    default = 443 if scheme == "https" else 80
    netloc = host.lower() + (f":{port}" if port and port != default else "")
    return f"{scheme}://{netloc}"


class _SameOriginRedirect(urllib.request.HTTPRedirectHandler):
    """Solo sigue redirecciones dentro del origen permitido y sin traversal.

    Sin esta guarda, una redirección del portal llevaría la petición a
    cualquier destino (SSRF) o a otra ruta del mismo host. Se comprueba antes
    de seguir cada salto.
    """

    def __init__(self, allowed_origin: str):
        self.allowed_origin = allowed_origin

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # `http_error_302` ya normalizó la Location con urljoin: los `..` se
        # pierden ahí, así que se comprueba el header en crudo.
        raw = headers.get("location") or headers.get("uri") or newurl
        target = urllib.parse.urljoin(req.full_url, newurl)
        if (has_unsafe_url_chars(raw) or has_unsafe_path(raw)
                or has_unsafe_path(target) or origin(target) != self.allowed_origin):
            raise HttpError(f"redirección no permitida hacia {self.allowed_origin}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


# El OPAC responde con <meta http-equiv="Refresh" content="0; URL=..."> en lugar de
# un 302. Hay que seguirlos a mano.
_META_REFRESH = re.compile(
    r"""http-equiv\s*=\s*["']?refresh["']?[^>]*content\s*=\s*["'][^"']*url\s*=\s*([^"';]+)""",
    re.IGNORECASE,
)


class Response:
    __slots__ = ("url", "text", "status")

    def __init__(self, url: str, text: str, status: int = 200):
        self.url = url
        self.text = text
        self.status = status

    def __repr__(self) -> str:
        return f"<Response {self.status} {self.url}>"


class Http:
    """Cliente HTTP sin estado de cookies.

    Verificado: la sesión del OPAC viaja en el token de la URL, no en cookies,
    así que no hace falta mantener un cookie jar. Eso es justo lo que hace que
    el motor sea trivialmente portable.
    """

    def __init__(
        self,
        base_delay: float = DEFAULT_BASE_DELAY,
        timeout: int = DEFAULT_TIMEOUT,
        user_agent: str = USER_AGENT,
        max_refresh_hops: int = 5,
    ):
        self.base_delay = base_delay
        self.timeout = timeout
        self.user_agent = user_agent
        self.max_refresh_hops = max_refresh_hops
        self._last_request = 0.0
        # Sin opener con cookie jar a propósito: ver nota de clase.
        self._opener = urllib.request.build_opener()

    # -- interno ---------------------------------------------------------
    def _throttle(self) -> None:
        if self.base_delay <= 0:
            return
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.base_delay:
            time.sleep(self.base_delay - elapsed)

    def _decode(self, raw: bytes, headers) -> str:
        charset = None
        ctype = headers.get("Content-Type", "")
        if "charset=" in ctype:
            charset = ctype.split("charset=", 1)[1].split(";")[0].strip().lower()
        if charset in ("iso-8859-1", "latin-1", "latin1", "windows-1252", None, ""):
            return raw.decode("iso-8859-1", "replace")
        try:
            return raw.decode(charset)
        except LookupError:
            return raw.decode("iso-8859-1", "replace")

    def _send(self, request: urllib.request.Request) -> Response:
        self._throttle()
        self._last_request = time.monotonic()
        try:
            with self._opener.open(request, timeout=self.timeout) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                elif resp.headers.get("Content-Encoding") == "deflate":
                    raw = zlib.decompress(raw, -zlib.MAX_WBITS)
                return Response(resp.geturl(), self._decode(raw, resp.headers), resp.status)
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            return Response(exc.geturl(), self._decode(raw, exc.headers), exc.code)

    def _resolve(self, url: str, base: str | None) -> str:
        return urllib.parse.urljoin(base, url) if base else url

    # -- público ---------------------------------------------------------
    def next_meta_refresh(self, html: str, current_url: str) -> str | None:
        match = _META_REFRESH.search(html)
        if not match:
            return None
        return self._resolve(match.group(1).strip(), current_url)

    def get(self, url: str, follow_refresh: bool = True) -> Response:
        """GET siguiendo la cadena de meta-refresh (máx. `max_refresh_hops`)."""
        response = self.get_once(url)
        hops = 0
        while follow_refresh and hops < self.max_refresh_hops:
            nxt = self.next_meta_refresh(response.text, response.url)
            if nxt is None:
                break
            response = self.get_once(nxt)
            hops += 1
        return response

    def get_once(self, url: str) -> Response:
        request = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        return self._send(request)

    def get_image(
        self,
        url: str,
        allowed_origin: str,
        max_bytes: int = MAX_IMAGE_BYTES,
    ) -> tuple[bytes, str]:
        """Descarga binaria acotada a un origen y a un tamaño.

        A diferencia de `get`, no decodifica texto ni sigue meta-refresh: aquí
        solo interesan los bytes de una portada. Cualquier redirección fuera de
        `allowed_origin` se rechaza antes de seguirla, la petición ignora el
        proxy del entorno y el cuerpo no puede superar `max_bytes`. Devuelve
        `(bytes, content_type)` o lanza `HttpError`.
        """
        if origin(url) != allowed_origin or has_unsafe_path(url):
            raise HttpError(f"URL no permitida para descargar (origen {allowed_origin})")
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            _SameOriginRedirect(allowed_origin),
        )
        request = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        self._throttle()
        self._last_request = time.monotonic()
        try:
            with opener.open(request, timeout=self.timeout) as response:
                data = response.read(max_bytes + 1)
                if len(data) > max_bytes:
                    raise HttpError("imagen demasiado grande")
                if origin(response.geturl()) != allowed_origin:
                    raise HttpError(f"respuesta redirigida fuera de {allowed_origin}")
                content_type = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
                if not content_type.startswith("image/"):
                    raise HttpError(f"contenido que no es imagen: {content_type or 'sin tipo'}")
                return data, content_type
        except urllib.error.HTTPError as exc:
            raise HttpError(f"no se pudo descargar la imagen ({exc.code})") from None
        except urllib.error.URLError as exc:
            raise HttpError(f"no se pudo conectar para la imagen: {exc.reason}") from None
        except OSError as exc:
            raise HttpError(f"error leyendo la imagen: {exc}") from None

    def post(
        self,
        url: str,
        fields: dict[str, str] | list[tuple[str, str]],
        follow_refresh: bool = False,
    ) -> Response:
        data = urllib.parse.urlencode(fields).encode("ascii")
        request = urllib.request.Request(
            url,
            data=data,
            headers={
                "User-Agent": self.user_agent,
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        response = self._send(request)
        if follow_refresh:
            hops = 0
            while hops < self.max_refresh_hops:
                nxt = self.next_meta_refresh(response.text, response.url)
                if nxt is None:
                    break
                response = self.get_once(nxt)
                hops += 1
        return response

    def absolute(self, href: str, base_url: str) -> str:
        return self._resolve(href, base_url)