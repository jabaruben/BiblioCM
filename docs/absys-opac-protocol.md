# Protocolo del OPAC de las Bibliotecas de la Comunidad de Madrid

Notas de ingeniería obtenidas inspeccionando el portal real (`gestiona3.madrid.org/biblio_publicas`).
El sistema es un **AbsysNet mOpac** (Baratz / Servicios de Teledocumentación S.A.U.).
No existe API pública: todo es HTML renderizado por CGI.

> Referencia del **proveedor externo** e inspecciones históricas, no contrato de
> nuestro servidor. Arquitectura vigente: [architecture.md](architecture.md);
> API BiblioCM: [api.md](api.md); implementación/evidencia: [status.md](status.md).
> Inventarios y políticas observados pueden cambiar. Los ejemplos de lector
> están anonimizados; no guardar tokens ni credenciales reales en estas notas.

## 1. Modelo de sesión

- Cada visita al OPAC crea un **hilo de sesión nuevo**, identificado por un token en el *path*:
  `https://gestiona3.madrid.org/biblio_publicas/cgi-bin/abnetopac/<TOKEN>/NT<n>`
- El sufijo `NT<n>` es un contador que **incremental en cada navegación** (`NT1` → `NT21` → `NT41` → `NT48`).
- El token **cambia en cada petición**: nunca se debe hardcodear una URL.
  **Regla de oro: usar siempre el `href`/`action` del último HTML descargado.**
- Única cookie: `ROUTEID` (stickiness del balanceador). No hay sesión por cookie.
- Caducidad: `window.setTimeout(..., 292000)` → **la sesión muere a los ~292 s (~5 min)** de inactividad.
  El cliente debe re-autenticarse de forma transparente (guarda la contraseña).

Consecuencia útil: **cada cuenta puede tener su propio hilo de sesión sin interferir con las demás**.
Esto hace trivially escalable el modo multicuenta.

## 2. Autenticación

### 2.1 Login

1. `GET https://gestiona3.madrid.org/biblio_publicas/` → redirige a `abnetopac/<TOKEN>?ACC=101`
2. Extraer del HTML el formulario `#abnopid` y sus campos ocultos.
3. `POST` al `action` del formulario:

| Campo | Valor |
|---|---|
| `leid` | nº de carné |
| `lepass` | contraseña |
| `FBC` | contador de formulario (ej. `316`) |
| `NAC` | contador (ej. `317`) |
| `ACC` | `201` |

- **No hay CAPTCHA** en el login (verificado: credenciales erróneas → solo "La contraseña es incorrecta").
- **Respuesta**: en un login correcto el servidor **minta un token de sesión autenticado distinto**
  del hilo invitado. El área de usuario vive en el token nuevo.
  Hay que descubrir ese token leyendo los `href`/`action` de la página devuelta (p. ej. el enlace
  del nombre del lector apunta al `ACC=210` ya con el token autenticado).
- Errores: texto `La contraseña es incorrecta`, `Error en los campos:`.

### 2.2 Logout

`GET <cgi>?ACC=301`

## 3. Área de usuario — "Mi biblioteca"

`GET <cgi>?ACC=210`  (usar el token autenticado)

### 3.1 Datos del lector

Bloque `<p id="varJSONlector" class="dn">` con spans de **forma variable**:

- El carné aparece **dos veces** (con y sin relleno de ceros).
- El nombre puede venir en **un** span (`PERSONA DE PRUEBA APELLIDO`) o en **dos**
  (`PERSONA` + `DE PRUEBA APELLIDO`). → **Nunca parsear posicionalmente.**
- Siguen dos flags `true`/`false`: suspendido, caducado.
- Opcionalmente, la fecha de caducidad del carné (`dd/MM/yyyy HH:mm`).

Ejemplos anonimizados con la misma estructura:

```
A: 111111111 | 111111111 | PERSONA DE PRUEBA APELLIDO | false | false | 17/11/2033 23:59
B: 22222222  | 022222222 | PERSONA | DE PRUEBA APELLIDO | false | false
```

Clasificar cada span por su forma (dígitos / `true|false` / fecha / resto = nombre) es
robusto para las dos variantes. Con un parser posicional, el caso de nombre partido
desplaza los flags y devuelve el nombre truncado.

### 3.2 Préstamos — sección `#lector_PR`

Cada préstamo es un `<li>` dentro de `#lector_PR .lector_box` que contiene un bloque
**JSON legible por máquina**: `<p class="varJSONpr dn">`.

| Clave | Significado | Ejemplo |
|---|---|---|
| `prbarc` | código de barras del ejemplar | `9000000021` |
| `tititu` | título + autor | `El libro del otoño /` |
| `address` | dirección de la sucursal | `Plaza del Perú, 13 28891 ...` |
| `description` | nombre de la biblioteca | `Biblioteca Municipal María Moliner` |
| `xsresv` | nº de reservas pendientes | `0` |
| `prnren` | renovaciones ya hechas | `0` |
| `ppdrnm` | máximo de renovaciones | `1` |
| `ppdrna` | días antes de la devolución para poder renovar | `5` |
| `prfdev` | **fecha de devolución** `dd/MM/yyyy HH:mm` | `12/10/2026 23:59` |
| `ppdrnw` | avisos de proximity | `1` |

Atributos `data-*` del `<li>`:
`data-prbarc`, `data-prppsq` (secuencia), `data-ppdrnwfake`, `data-ppdrnmfake`,
`data-ppdrnpfake`, `data-ppdrnafake`, y `data-su` (código de sucursal, ej. `BMVEL1`)
en el botón/`<a>` de la biblioteca.

Estado de renovación: **NO viene en el HTML.** El span
`<span id="lector_renovMen<prbarc>" class="lector_renovMen js-lector_renovMen ns-dn">`
llega **vacío**; el texto lo inyecta el JavaScript del portal en tiempo de
ejecución. Hay que derivarlo de `varJSONpr` (ver sección 3.2.1).

Retraso: se marca con un `<span class="cr">` **dentro** de
`.js-lectorPresta_xsfdev`, tal como hace el JS del portal:

```js
a.find(".js-lectorPresta_xsfdev .cr").length ? sobrePresta = true : sobrePresta = false
```

⚠️ El span `.js-lectorPresta_xsfdev` en sí está en **todos** los préstamos
(contiene "Fecha de devolución: ..."). Usar su presencia como marca de retraso
hace que todo salga como retrasado.

### 3.2.1 Derivar el estado de renovación (reproduciendo el JS del portal)

Máquina de estados extraída de `js/modules/mylibrary.min.js`:

```
si hay sobrepaso OR lector suspendido OR lector caducado  -> No se puede renovar
si no, si  prnren >= ppdrnm                                -> Límite de renovaciones
si no, si  hoy <  devolucion - ppdrna días                 -> Renovable a partir de <fecha>
si no                                                  -> Renovable
```

Prioridades strictly en ese orden: **el sobrepaso siempre gana**, aunque el texto
diga otra cosa.

**Detalle fino del umbral:** el JS hace `setDate(getDate() - (ppdrna - 1))`, pero el
comportamiento real es `- ppdrna`.

> ✅ **Validado 9/9 contra el texto que renderiza el portal** (lector con JS ejecutado),
> el 02/10/2026. Devoluciones 05/10 → "Renovable"; 12/10 → "desde 7/10"; 23/10 → "desde 18/10";
> 26/10 → "desde 21/10"; 03/11 → "desde 29/10". Todos con `ppdrna=5`.
> Ni un solo caso de borde fallado, así que la regla es `- ppdrna` y no `- ppdrna - 1`.
> Hay un día de desfase en el código minificado que no se corresponde con su comportamiento.

### 3.3 Renovación  ✅ verificada en vivo

**No** es un POST con el código de barras como nombre de campo. Cada préstamo
renovable lleva su **propio formulario**, y el campo se llama `CP<código>`:

```html
<form action="<cgi>" method="post" id="abnRenov9000000002"
      class="js-evn-lectorPresta-renov" data-cobarc="9000000002">
  <input type="hidden" name="ACC" value="228"/>
  <input type="hidden" name="CP9000000002" value="1"/>
  <button type="submit">Renovar 15 días</button>
</form>
```

- `ACC` = `228` (leído de `varJSONmain#renov`).
- El nombre del campo es **`CP` + el código de barras**.
- El botón indica la prórroga: "Renovar 15 días".

> ⚠️ **Error que costó una prueba fallida:** el módulo JS del *flujo AJAX* (el de
> "Ver renovables (N)" con selección múltiple) sí hace `dato[codigo] = 1`, pero
> el formulario normal por préstamo usa `CP<codigo>`. Mandar `9000000002=1`
> devuelve `Error en los campos:` sin más.
>
> **Por eso hay que leer el formulario del HTML**, no construir el payload a mano.

**El formulario solo existe si la renovación está disponible.** Si no hay
`form[data-cobarc]`, no se puede renovar: no hay que waste un intento.

> ⚠️ **No confiar en el mensaje del servidor.** La respuesta incluye el diccionario
> de mensajes del portal en `varJSONmain`, que contiene las cadenas
> "Ejemplar renovado", "Reserva eliminada", etc. Buscar el texto de éxito en el
> documento entero produce un **falso positivo** sobre un fallo.
>
> La implementación actual adopta la respuesta real del POST, abre un acceso nuevo
> y confirma fecha posterior y aumento del contador. La UI comunica los datos del
> panel actualizado, sin repetir la renovación para comprobarla.
> Verificado: renovar «Las sombras de la mente» movió la devolución de 05/10/2026
> a 20/10/2026 y el contador de renovaciones pasó de 0/1 a 1/1.

#### El aviso "Tiene préstamos sobrepasados" engaña

El banner `#lector_resum .lector_sobrePresta` **siempre está en el HTML**, pero con
clases `js-dn ns-dn` (oculto). El JavaScript lo muestra cuando procede. Comprobar
su presencia da un falso positivo: hay que comprobar `.js-lectorPresta_xsfdev .cr`
dentro de cada préstamo, o directamente si el formulario de renovación existe.

### 3.4 Reservas — sección `#lector_RE`

- Listado en la misma página `ACC=210`.
- **La sección solo se renderiza si hay reservas.** Con 0 reservas el `#lector_RE` **no existe**
  en el HTML (verificado). Hay que tratarlo como lista vacía, no como error.
- Cada reserva es un `<li>` en `#lector_RE .lector_box`:

| Dónde | Contenido |
|---|---|
| `a[href*="TITN="]` | título y `TITN` del registro |
| `.c-alert--content` | `Estado: Reservada` |
| `p` con `.t-we--500` | fecha de caducidad de la reserva (`dd/MM/yyyy`) |
| `[data-su]` + `<span>` | sucursal (código y nombre) |
| `.lector_boxDataInfoTxt` | fecha de creación, signatura, tipo de ejemplar |
| `button.js-evn-myLibrary-delRes[data-di]` | **ID de la reserva** |
| `a[href*="ACC=238"]` | enlace de anulación equivalente |

> ⚠️ **Las reservas NO tienen bloque JSON.** El `varJSONlectorReserv` existe en el HTML pero
> **viene vacío** (verificado con una reserva real). A diferencia de los préstamos,
> hay que parsear el HTML renderizado usando las etiquetas estables de arriba.

**Anular reserva**  ✅ verificado en vivo (creada y anulada una reserva real):

```
POST <cgi>
  ACC=238
  DI=<data-di>
```

Respuesta: fragmento HTML con `#lector_RE` regenerado; si queda vacía, la sección desaparece.
Tras anular, `ACC=210` vuelve a no incluir `#lector_RE` y el resumen muestra solo los préstamos.

### 3.5 Otras acciones (códigos ACC de `varJSONmain`)

| ACC | id en varJSON | Acción |
|---|---|---|
| 228 | `renov` | renovar un ejemplar |
| 238 | `delres` | anular reserva |
| 239 | `delrec` | eliminar recurso |
| 248 | `lecprehis` | activar/desactivar histórico de préstamos |
| 234 | `deldsi` | eliminar búsqueda guardada |
| 231 | `dellkl` | eliminar enlace |
| 237 | `delpet` | eliminar petición |
| 259 | `checkddocserie` | marcar serie |
| 306 | `modemail` | activar/desactivar avisos por email |
| 301 | — | cerrar sesión |
| 210 | — | Mi biblioteca |
| 300 | — | Ayuda |

### 3.6 reCAPTCHA

`varJSONmain` puede traer `captcha` (`0`/`1`) y `xcapkw` (site key de Google reCAPTCHA).
Se exige para acciones sensibles (p. ej. "Recibir resguardo por correo-e", ACC=351) y hay un
`TCAPT` en el POST. **La renovación y la anulación de reserva no lo requieren.**

## 4. Catálogo

### 4.1 Búsqueda

Formulario `#abnformSearch` → `POST` a su propio `action` con:

| Campo | Valor |
|---|---|
| `ACC` | `131` |
| `START` | `1` |
| `FORM` | `1` |
| `xmismo` | `on` |
| `FORM_DIGITAL` | `9` |
| `xsface` | `on` |
| `subcat` | `/` = todas las bibliotecas, o `<código>` para filtrar |
| `xsqf01` | la consulta |

- La búsqueda es **por tokens con AND**: `cien anos de soledad` exige los 3 términos.
  Si solo hay 1 coincidencia, el servidor salta **directamente a la ficha** (`ACC=165`),
  no a una lista. Hay que manejar ambos casos.
- Paginación observada: página 1 DOC=1, página 2 DOC=11, página 3 DOC=21.
  DOC es un offset/documento inicial según los href, no el número de página UI.
  Seguir el enlace del último HTML. El cliente actual envía DOC=page y tiene
  pendiente la corrección TODO-CAT-002.

### 4.2 Estructura de un resultado

`ol.c-docs > li.c-docs_unit` (10 por página). Campos:

| Selector | Contenido |
|---|---|
| `.c-docs_author` | autor principal |
| `.c-docs_title` | título |
| `.c-docs_data` | `Lugar : editorial, año`, géneros, edición, ISBN |
| `.c-docs_img img[src]` | portada → `?ACC=299&MLKOB=<n>` |
| `p.c-docs_marc` | **registro MARC completo** (ver abajo) |
| `span.Z3988` | **OpenURL / Z39.88-2004** (`url_ver`, `rft.*`) |

El **`c-docs_marc` es oro**: trae el registro MARC ya parseado en spans con prefijo `js-`:
`js-ld06`/`js-ld07` (leaders), `js-T008`, `js-TITN`, `js-LENG`, `js-FEPU`, `js-T1XX` (autor),
`js-T245` (título), `js-T260a/b/c` (publicación), `js-T300a` (páginas), `js-T080` (CDU),
`js-T520` (resumen), `js-T586` (nota), `js-T651`/`js-T655` (materias), `js-MATE` (materias combinadas),
`js-T856u` (URL externa, p. ej. eBiblio), `js-T020a` (ISBN), `js-AUTZ` (ids de autoridad).

→ **No hace falta llamar a la ficha para mostrar un resultado de búsqueda.**

### 4.3 Disponibilidad

**No viene en la lista de resultados.** El marcador aparece vacío
(`<li class="mmxResults js-mmxResults" data-xsndoc="1" data-xsdisp="coverNodis">`),
la lista solo enseña la portada.

Para verla hay que abrir la ficha (`?TITN=<id>`). Ahí sí vienen **todas** las
filas de ejemplares en el HTML, agrupadas:

```
div.copias_accordion            <- hay VARIOS en la página, uno por bloque
  div.c-accordion_item
    p.c-accordion_h             -> "Sucursal: <nombre de la biblioteca>"
    section > table > tr[data-disp]
      td .icm_locSign           -> "Sala adultos"
      td a[data-bc][data-sign]  -> código de barras y signatura
      td (2ª)                   -> tipo de ejemplar ("Prestable. Libros")
      td (3ª)                   -> soporte ("Libro", "CD", "DVD")
      td.copias_tableDisp       -> disponibilidad
```

- `tr[data-disp]` es la fuente de verdad: `"Disponible"` o
  `"Disponible después de 24/10/2026"`.
- ⚠️ **Ojo al contar disponibilidad:** `"Disponible después de X"` **no** está
  disponible hoy. Comparar por igualdad, no por `startswith("Disponible")`.
- Cada celda lleva un `span.copias_label` con el nombre de la columna (visible
  solo en móvil) que hay que excluir al leer el valor.
- Verificado: 79 disponibles de 231 ejemplares, coincidente con el
  "Ver disponibles (79)" que muestra el propio portal.

Ficha de un ejemplar concreto: `GET <cgi>?ACC=143&SIGN=<signatura>&BC=<código>`.

### 4.4 Facetas disponibles en los resultados

Autor, Título, Materia, Año, Idioma, Tipo de documento.
Permiten refinar sin rehacer la búsqueda.

### 4.5 Ficha de documento

`GET <cgi>?TITN=<id>` (el id está en `js-TITN` del resultado)

- `bodyJSON` con los flags de la interfaz (`carrlimit`, `numejepag`, `ODAPreview`, `mmxResults`, ...).
- Botón **Reservar** → `GET <cgi>?ACC=193` (sin parámetros: el servidor guarda el documento
  Actual en el estado de la sesión, por eso el orden de llamadas importa).

### 4.3 Solicitar reserva

1. `GET <cgi>?TITN=<id>` y luego `GET <cgi>?ACC=193` → asistente "Solicitar reserva".
   - `abnformResMos`: filtro por biblioteca (`ACC=193`, `sucursmospre=<código>`).
   - `abnformRes`: tabla de ejemplares elegibles con `ACC=194`. Campos indexados por ejemplar:

   | Campo | Ejemplo |
   |---|---|
   | `xcheck_<n>` | `1` |
   | `rebarc_<n>` | `9000000003` |
   | `ppnseq_<n>` | `596` |
   | `pprper_<n>` | `180` |
   | `pprprc_<n>` | `-1` |
   | `EMAIL` | `on` |
   | `NCOP` | nº de ejemplares marcados |

2. `POST` al `action` del propio formulario (que es otro hilo distinto, `/NT70`) con
   **solo los campos del ejemplar elegido** + `ACC=194`. `NCOP` = número de ejemplares marcados.

> Con un título muy prestado (135 ejemplares) el formulario pesa mucho. Hay que **recortar los
> campos a los del ejemplar que se reserva**, no reenviar el formulario entero.

Solo se admiten reservas de ejemplares **prestados o con reserva activa**.
`carrlimit=2` → máximo 2 reservas simultáneas.

Cada fila de la tabla muestra: biblioteca/sucursal, localización/signatura, tipo de ejemplar,
disponibilidad (`Disponible después de dd/mm/aaaa`, `Nº de reservas: N`) y su casilla "Solicitar".

En el motor actual se parsea la fila completa de `abnformRes`, excluyendo
`copiasRes_label`; no se recorta el HTML alrededor del barcode. Los índices pueden
tener huecos. La web envía barcode para reencontrar el índice al volver a abrir el
asistente y confirma una nueva reserva de ese registro tras el POST. La API de
la aplicación expone campos estructurados, no el texto `row` interno del CLI.

### 4.4 Ficha de ejemplar

`GET <cgi>?ACC=143&SIGN=<signatura>&BC=<código de barras>` → estado de ese ejemplar
(disponible, fecha de devolución esperada, "Disponible después de dd/mm/aaaa").

## 5. Cookies y CORS (decisivo para elegir arquitectura)

### 5.1 La sesión funciona SIN cookies

Verificado ejecutando el flujo completo (login →|mi biblioteca → 9 préstamos) con un
`CookieJar` vacío y sin enviar ninguna cookie: **funciona**. La sesión viaja íntegramente en
el token de la URL.

El servidor sí emite cookies (`srv_id`, `ROUTEID`, y varias `TS*` de F5 ASM con
`HttpOnly; Secure; SameSite=Strict`), pero **no son necesarias** para operar.
Consecuencia: el motor es HTTP puro, sin gestión de cookies, y por tanto trivialmente
portable a cualquier lenguaje/plataforma.

### 5.2 Sin CORS para peticiones directas desde el navegador

```
GET https://gestiona3.madrid.org/biblio_publicas/cgi-bin/abnetopac?ACC=101
  con Origin: https://example.com

HTTP/1.1 200 OK
Content-Type: text/html; charset=iso-8859-1
(no hay Access-Control-Allow-Origin)
```

**Implicación directa:** una webapp que llame al OPAC desde el navegador **no puede funcionar**.
No es cuestión de configurarlo. Esto descarta:

- Webapp pública (HTML+JS) que consulte el OPAC directamente → **imposible**.
- WebView en Android haciendo `fetch()` al OPAC → **bloqueado por CORS** (salvo hacks como
  `shouldInterceptRequest`, que son frágiles).

La aplicación implementada resuelve esta restricción con una **API Python del
mismo origen que la UI**. El backend hace HTTP al OPAC fuera del navegador. Puede
ejecutarse localmente en un ordenador o detrás de HTTPS accesible desde teléfonos;
no requiere ejecutar Python en el propio iPhone. Las credenciales se guardan
cifradas en ese servidor, no exclusivamente en el dispositivo móvil. La ausencia
de CORS del proveedor no impide una PWA con backend propio.
Arquitectura vigente y límites de despliegue en [architecture.md](architecture.md).

## 6. Descubrimiento del `cgi`

Cada página contiene `<p id="varJSONmain" class="dn">` con spans `id` que son la clave del valor:

```html
<span id="cgi">/biblio_publicas/cgi-bin/abnetopac/<TOKEN>/NT41</span>
<span id="renov">228</span>
<span id="delres">238</span>
...
```

`#cgi` es el endpoint base al que se POSTea. Leer acciones/códigos del último HTML
cuando están disponibles. El cliente actual también contiene constantes/fallbacks
de ACC; no todos sus códigos se descubren dinámicamente. Los tokens de sesión no
deben reconstruirse a partir de ejemplos históricos.

## 7. Notas de robustez para el cliente

- Charset: el OPAC sirve **`iso-8859-1`**. Hay que decodificar Latin-1, no UTF-8.
- La entrada `https://gestiona3.madrid.org/biblio_publicas/` es una **cadena de `meta refresh`**
  (3 saltos hasta `abnetopac/<token>?ACC=101`), no redirecciones HTTP. Hay que seguirlos a mano.
- Parsear por **clases CSS y `data-*` estables** (`#lector_PR .varJSONpr`, `data-prbarc`),
  nunca por posición ni por texto libre.
- Re-login automático al detectar `Sesión expirada` o `timeout.htm`.
- No mezclar hilos de cuentas. Recuperar lecturas tras caducidad; la verificación
  de renovación abre expresamente un acceso nuevo. La API crea un cliente por
  operación/cuenta y no conserva un pool de sesiones OPAC.
- Ritmo: requests con ~1 s de separación; nada de concurrencia agresiva.

## 8. Estado de verificación

Inspecciones históricas del **portal**, no tabla de funcionalidades implementadas
en nuestra UI. Por ejemplo, el proveedor tiene facetas, pero nuestro API/frontend
no las expone todavía. Estado de producto y evidencia reciente: [status.md](status.md).

| Pieza | Estado |
|---|---|
| Login sin captcha | ✅ verificado |
| Sesión sin cookies (solo URL) | ✅ verificado |
| Lectura de préstamos (9/9) | ✅ verificado |
| Umbrales de renovación derivados | ✅ **validados 9/9 contra el portal** (leído con el JS ejecutado) |
| Multicuenta (hilos independientes) | ✅ **verificado con 2 tarjetas reales** en una sola ejecución |
| Endpoint de renovación (`CP<código>`) | ✅ **verificado en vivo**: 05/10 → 20/10, 0/1 → 1/1 |
| Renovación con éxito | ✅ **verificada en vivo** |
| Listado de reservas (`#lector_RE`) | ✅ verificado con una reserva real |
| Anular reserva (`ACC=238&DI=`) | ✅ **verificado en vivo**: creada y anulada |
| Crear reserva (`ACC=193` → `194`) | ✅ **verificado en vivo** |
| Búsqueda + MARC + OpenURL + facetas | ✅ verificado end-to-end |
| Disponibilidad de ejemplares | ✅ 79 de 231, coincide con el "Ver disponibles (79)" del portal |
