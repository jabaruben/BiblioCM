# Backend y dominio

Arquitectura: [architecture.md](architecture.md). Contrato público: [api.md](api.md).
Estado verificable: [status.md](status.md). El protocolo externo tiene su propia
[referencia](absys-opac-protocol.md), distinta de la API de nuestra aplicación.

## Motor OPAC

### Transporte — `biblio/http.py`

- `Http`: urllib, sin cookie jar; `Response` expone `url`, `text`, `status`.
- Ritmo por instancia: un segundo entre peticiones por defecto; timeout 30 s.
- `get_image(url, allowed_origin)` descarga portadas en binario: ignora el proxy
  del entorno, comprueba el origen antes de cada redirección (y también la
  Location en crudo), rechaza rutas con dot segments, separadores codificados o
  caracteres de control, limita el tamaño (1,5 MB) y exige `image/*`. No sigue
  meta-refresh ni decodifica texto.
- `origin()` devuelve el origen normalizado y vacío ante userinfo, puerto
  malformado, backslash o caracteres de control; `path_layers()` aplica la
  decodificación percent capa a capa con un tope (`MAX_PATH_DECODINGS`) y
  devuelve `None` si no estabiliza, y `has_unsafe_path()` comprueba **todas**
  esas capas (dot segments, separadores codificados, controles) antes de usar
  la ruta, de modo que un `..` que aparece en la capa 5 también se rechaza.
- Descomprime gzip/deflate y decodifica usando charset, con fallback Latin-1.
- GET sigue meta-refresh, hasta cinco saltos. POST **no** lo sigue por defecto.
- HTTPError se convierte en `Response` con status y cuerpo; otros errores de
  transporte pueden propagarse. No existe política general de retries/backoff.
- `_last_request` pertenece a cada cliente HTTP, no a un limitador global distribuido.

### Parser — `biblio/parser.py` y `biblio/dom.py`

Funciones de parseo no hacen red ni guardan estado. El DOM mínimo soporta
`by_id`, clases, atributos, padres y texto. No ejecutar el JavaScript del proveedor
ni usar recortes arbitrarios de HTML para interpretar un formulario.

Entradas principales:
- `parse_reader`: datos de lector, tolerando nombre en uno o varios spans.
- `parse_loans`: `varJSONpr` + marcado de retraso; acepta `today` para pruebas y
  lee `record_id` del `href?TITN=` del título (vacío si el portal no lo enlaza).
- `derive_renewal_state`: bloqueos → límite → ventana por fecha → renovable.
- `parse_reservations`: HTML de `lector_RE`, no un supuesto JSON de reservas.
- `parse_search_results`: resultados, MARC y OpenURL.
- `cover_src`: portada de una tarjeta de lista o de una ficha — imagen
  «Cubierta…», después imagen del enlace `MLKOB=`, después `c-docs_img`; no el
  primer `<img>` de la tarjeta.
- `parse_copies`: todos los accordions y filas `data-disp`, deduplicados por barcode.
- `parse_reservable_copies`: filas del formulario `abnformRes`, índice original,
  campos internos y descripción limpia. La API filtra los campos internos.
- `renewal_form`, `form_fields`, `link_with_acc`, `varjson`: navegación/formularios.

Reglas actuales de renovación:
1. Sobrepaso marcado en el HTML, lector suspendido o caducado → `no_renovable`.
2. Usadas ≥ máximo → `limite_alcanzado`.
3. Ventana ≤ 0 → `renovable` en el derivador; el envío sigue requiriendo formulario real.
4. Hoy < devolución − ventana → `renovable_desde` con fecha de umbral.
5. Resto → `renovable`.

El enum contiene estados adicionales para hints/representación, pero el derivador
actual colapsa los bloqueos del punto 1 en `no_renovable`. Días restantes:
`due_date - today`, usando fecha local del servidor. Cambiar zona horaria/reglas de
calendario requiere especificación y pruebas de borde.

### Cliente — `biblio/client.py`

Una instancia representa un carné. `_base` guarda el hilo OPAC y `_acc` los
códigos descubiertos en el HTML. Hay fallbacks de ACC en el código; no todos los
códigos proceden siempre de `varJSONmain`.

| Método | Resultado / comportamiento |
|---|---|
| `login()` | Invitado → formulario → nuevo hilo autenticado y lector válido |
| `logout()` | Cierra el hilo del portal; distinto del logout de la web |
| `my_library(today=None)` | `Library(reader, loans, reservations)` |
| `search(query, page=1, subcat='/')` | `(total, list[MarcRecord])`, reconstruye la búsqueda por llamada y resuelve `cover_url` contra la última respuesta |
| `record(record_id)` | Response de ficha; no es un endpoint separado de la API web |
| `record_cover_url(record_id)` | URL absoluta de portada de la ficha (una sola apertura), o `""` si no tiene o apunta fuera del portal |
| `copies(record_id)` | Lista de `Copy` de esa ficha |
| `cover(cover_url)` | `(bytes, content_type)` de una portada registrada; revalida origen y CGI |
| `reservable_copies(record_id)` | Lista de dicts del asistente, con índice y datos internos |
| `renew(barcode, today=None)` | `RenewResult` tras nueva autenticación y verificación |
| `reserve(record_id, copy_index, barcode=None)` | Mensaje tras comprobar reserva nueva |
| `cancel_reservation(id)` | Mensaje tras verificar ausencia del ID |
| `copy_detail(signature, barcode)` | Response específica de ejemplar; no expuesta en API web |

`_auth_get` puede recuperar una sesión caducada con login y una nueva lectura.
Esto no autoriza a repetir mutaciones automáticamente. En renovación, exigir fecha
posterior y aumento del contador; en reserva, ID nuevo y mismo registro; en
anulación, desaparición del ID. No inferir éxito de textos de plantilla.

Errores de dominio: `AuthError`, `SessionExpired` (subclase), `OperationRefused`.
La traducción a HTTP se documenta en `api.md`.

## Persistencia web — `biblio/store.py`

SQLite por defecto en `.biblio-data/biblio.sqlite3`, relativo al directorio de
arranque. `foreign_keys=ON`, `secure_delete=ON`, conexión compartida entre hilos
protegida por RLock. El esquema se versiona con `PRAGMA user_version` y lo migra
`Store._migrate` (v1 el 2026-10-10, [ADR-017](decisions.md#adr-017--identidad-con-email-verificado-smtp-por-entorno-tokens-hasheados-y-api-v5);
v2 el mismo día con passkeys/OIDC, [ADR-018](decisions.md#adr-018--passkeys-con-webauthn-y-google-oidc-con-joserfc)).

### Esquema actual (user_version = 2)

| Tabla | Columnas y restricciones |
|---|---|
| `users` | `id` PK opaco, `username` UNIQUE, `name`, `salt` BLOB, `password_hash` BLOB, `email` TEXT (único entre no nulos), `email_verified_at` TEXT |
| `accounts` | `id` PK, `owner_id` FK users, `label`, `card_digest` UNIQUE, `credentials` BLOB |
| `links` | `id` PK, `owner_id` FK, `requester_id` FK, `permission`, `status`; pareja UNIQUE y owner ≠ requester |
| `identity_tokens` | `token_hash` PK (SHA-256 del código), `user_id` FK (CASCADE), `purpose` (`email_verify`/`password_reset`), `detail` (email pendiente), `expires_at`, `created_at` |
| `passkeys` | `credential_id` PK (base64url), `user_id` FK (CASCADE), `public_key` BLOB (COSE), `sign_count`, `transports` (JSON), `label`, `created_at` |
| `auth_challenges` | `challenge_hash` PK (SHA-256), `purpose` (`webauthn_register`/`webauthn_login`/`oidc`), `user_id` FK nullable, `detail` BLOB (Fernet en OIDC), `expires_at`, `created_at` |
| `identities` | `id` PK, `user_id` FK (CASCADE), `provider`, `issuer`, `sub`, `email`, `created_at`; UNIQUE `(issuer,sub)` y UNIQUE `(user_id,provider)` |

`card_digest` es SHA-256 del carné normalizado por el endpoint, usado para unicidad;
no es un hash de contraseña. `credentials` es Fernet de JSON `{card,password}`.
Passwords BiblioCM: scrypt con sal de 16 bytes, N=16384, r=8, p=1, dklen=32;
comparación mediante `compare_digest`. El login acepta username o email
**verificado**; un email sin verificar da el mismo 401 genérico.

### Migración de esquema

`_migrate` añade columnas, tablas e índices sin tocar identificadores, vínculos,
carnés ni credenciales cifradas. Como el módulo `sqlite3` no abre transacción
implícita para DDL, la migración usa `BEGIN`/`COMMIT`/`ROLLBACK` explícitos:
un fallo revierte todo (incluido `user_version`), cierra la conexión y arranca
con error en lugar de dejar la base a medias. Un fichero v0 recorre v0→v1→v2
en **una** transacción; un fichero v1 solo ejecuta el paso v2. Las pruebas
migran solo fixtures temporales (v0→v2, v1→v2, base reciente y rollback de
ambos pasos); migrar una base real exige respaldo previo y sigue en
[TODO-DATA-001](../TODO.md) el marco completo.

### Retos de un solo uso (passkeys y OIDC)

`put_challenge` guarda un reto/transacción con caducidad (5 minutos para
WebAuthn, 10 para el `state` OIDC) **solo como SHA-256**; `take_challenge` lo
consume borrando la fila en la misma transacción, así que un segundo uso —o uno
caducado— devuelve `None` sin importar el propósito. `peek_challenge` (solo
lectura, sin borrar) permite al callback OIDC comprobar el enlace de navegador
**antes** de consumir nada: un intento hostil no arruina el flujo legítimo
(TODO-SEC-004). El detalle de una transacción OIDC (nonce, verificador PKCE,
redirect, modo, digest del enlace de navegador y —en `link`— digest del token
de la sesión que lo inició) se cifra con la Fernet del servidor: ni el nonce,
ni el verificador, ni el enlace, ni el token se guardan en claro.

### Passkeys (FR-AUTH-004)

[passkeys.py](../biblio/passkeys.py) traduce tipos y errores de la librería
`webauthn`; toda la verificación (origen, RP ID, firma, UP/UV y contador) es de
la librería contra la clave pública guardada. El RP ID/origen salen del origen
**canónico del pedido** (esquema + Host parseado de forma estricta por
[origins.py](../biblio/origins.py)) validado contra la lista de confianza del
servidor: local por defecto, público solo con `BIBLIO_TRUSTED_ORIGINS`; un Host
arbitrario queda fuera (403) incluso sobre TLS (NFR-SVC-003, TODO-SEC-003). Se
registran credenciales **descubribles** con UV obligatoria; el login no lleva
identificador ni `allowCredentials` (sin enumeración) y rota el token de sesión
como el login por contraseña, marcando la sesión como reautenticada.
`Store.add_passkey` impone el tope de 10 por cuenta y unicidad del
credential_id; `set_sign_count` solo avanza (la librería ya rechaza
retrocesos); `delete_passkey` borra solo passkeys del propio usuario.

### Google OIDC (FR-AUTH-005)

[oidc.py](../biblio/oidc.py) implementa el flujo de código con `joserfc`:
configuración opt-in por entorno (`BIBLIO_GOOGLE_*`), descubrimiento OIDC
perezoso con caché por proceso, endpoints aceptados solo en HTTPS (o bucle, para
el proveedor falso de pruebas), intercambio del `code` con PKCE y verificación
del token ID (RS256 contra el JWKS; `iss`, `aud`, `exp`/`iat`, `nonce` y `azp`
con varias audiencias). La identidad es `(issuer, sub)` en `identities`; el
email del token nunca encuentra ni crea cuentas. El alta con Google genera una
contraseña aleatoria que nadie conoce (fijable después por recuperación) y un
alias determinista derivado de la parte local del email, con sufijo del `sub`
si el alias está ocupado.

El flujo completo está **atado al navegador que lo inició** (login CSRF,
[ADR-019](decisions.md#adr-019--el-flujo-google-se-liga-al-navegador-y-a-su-sesión-viva),
TODO-SEC-004): `google_start` emite la cookie `biblio_oidc` (`HttpOnly`,
`SameSite=Lax`, ruta `/api/auth/google`, TTL del `state`, `Secure` con
`--secure`) y guarda en el estado solo su SHA-256; `google_callback` la compara
en tiempo constante con `peek_challenge`/`take_challenge` **antes** de canjear
el `code` con el proveedor, abrir sesión o llamar al gate del vínculo. Sin cookie
o con una ajena la respuesta es `/?google=error`, sin llamada al proveedor y
sin consumir el estado; toda respuesta de callback retira la cookie.

La escritura del vínculo (`link`) ocurre en un **gate final atómico respecto al
logout** (`Handler.store_link_with_live_session`): retiene `server.lock` —el
mismo lock que usa el logout y `close_user_sessions` para retirar sesiones—
entre la comprobación de la sesión que inició el flujo y la llamada a
`store.link_identity(..., require_verified=True)`, que revalida existencia y
email verificado **dentro de la misma transacción** que escribe, bajo
`store.lock`. Así un logout no puede intercalarse en la ventana
comprobación→escritura: o se ordena antes (y no se escribe nada) o después (la
sesión seguía viva al escribir; el vínculo queda y el logout solo cierra la
sesión, sin desvincular). El orden de locks es `server.lock` → `store.lock`,
ya usado por `link_session_live`/`open_session`; el store nunca toca locks del
servidor ni de sesión, así que no hay ciclo, y la E/I con el proveedor ocurre
siempre **fuera** de estos locks. La comprobación previa al canje sigue existiendo
para no llamar al proveedor de más, pero la autoridad es el gate. En modo
`link` el estado guarda el SHA-256 del token de la sesión que inició el flujo,
y `link_session_live` lo exige —antes del canje y otra vez en el gate— que esa
sesión siga viva para el mismo usuario con email verificado: un logout pendiente
invalida la vinculación. La cookie de sesión global sigue siendo
`SameSite=Strict` y el callback no la lee (no viajaría en la vuelta del
proveedor).

### Códigos de un solo uso y correo

`email_verification_token`/`reset_token` generan el código con `secrets`, guardan
solo su SHA-256 y retiran los anteriores del mismo usuario/purpose; la caducidad
es de 24 h (verificación) y 1 h (recuperación) y consumir borra la fila en la
misma transacción. Si el SMTP falla, el código se retira antes de responder 502.
El envío vive en [mailer.py](../biblio/mailer.py) y se configura solo por
entorno (`BIBLIO_SMTP_*`, ver [operations.md](operations.md)); sin host no hay
envío y la app lo anuncia al arrancar.

Clave: parámetro interno `key`, después `BIBLIO_SECRET_KEY`, después `secret.key`
en el directorio de SQLite. Se genera de forma exclusiva solo para una base nueva;
al abrir, se comprueba el descifrado de las credenciales existentes. Permisos
POSIX solicitados al crear la clave: 0600; en Windows se deben gestionar ACL del
directorio mediante el sistema operativo. No existe rotación automatizada.

### Autorizaciones

```text
sin solicitud ──request──> pending ──approve──> approved
                            │                   │
                            reject              permission (read/manage)
                            ▼                   │
                         rejected               revoke
                            │                   ▼
                         request             revoked
                            └────> pending <────request
```

Un `revoke` también cierra una petición pendiente. Solo el titular aprueba,
rechaza o cambia permisos. Ambos participantes pueden retirar su relación dentro
de los estados permitidos. Se reutiliza el ID al volver a solicitar; el estado
anterior se sobrescribe, no hay histórico de transiciones ni timestamps.

`accessible_accounts` une carnés propios con `links.approved` donde el dueño
directo coincide con el titular. No recorre un grafo de autorizaciones.
`access` comprueba lectura/gestión; `require_owner` exige dueño directo para claves
y desvinculación. `credentials` es una función interna: sus llamadores HTTP deben
autorizar antes de descifrar.

## Servidor web — `biblio/web.py`

`ThreadingHTTPServer` sirve una whitelist de assets y JSON. No sirve SQLite ni
archivos arbitrarios. En Windows usa `SO_EXCLUSIVEADDRUSE` y desactiva reutilización
para impedir instancias simultáneas sobre la misma dirección/puerto.
La comparación de `Origin` y la selección del origen WebAuthn/callback Google
usan el origen canónico del pedido (`origins.canonical_origin`, Host estricto),
nunca el Host crudo; la lista de confianza (`BIBLIO_TRUSTED_ORIGINS`, default
solo local) vive en `AppServer.trusted_origins` y solo afecta a passkeys y
Google (TODO-SEC-003).

Sesiones en RAM: token aleatorio, user_id, CSRF, expires, lock y (desde la API
`6`) `reauth_at`, la marca de la última reautenticación explícita: la abren
`auth/reauth` (contraseña verificada) y el login con passkey, y es lo que
exigen añadir/borrar passkeys y vincular/desvincular Google durante 300 s
(`REAUTH_TTL`). **Sin esa clave no hay reautenticación**: `require_reauth`
rechaza la sesión con `403`/`reauth_required` con cualquier valor del reloj
monotónico, en lugar de comparar contra `0`, que haría válida una sesión sin
marca en un host recién arrancado cuyo `time.monotonic()` no llega aún a
`REAUTH_TTL` (TODO-SEC-005). TTL deslizante 3600 s; hasta 100 sesiones según el control de
alta. Registrar usuario y reservar
capacidad de sesión no son una transacción única: esta arista tiene trabajo pendiente
en TODO-TEST-001, con un caso de capacidad y estado persistido.
Logout solo elimina la sesión web; no conserva un cliente OPAC al que cerrar sesión.
Los retos WebAuthn y las transacciones OIDC no viven en la sesión: viven en
`auth_challenges` con su propia caducidad y su consumo de un solo uso. Lo único
que enlaza sesión y flujo OIDC es el **digest** del token guardado en el estado
`link`: se comprueba contra las sesiones vivas del servidor, nunca con la cookie
de sesión (que `SameSite=Strict` no envía en la vuelta del proveedor), así que
cerrar sesión mientras un `link` está pendiente lo invalida (TODO-SEC-004).

El lock de la sesión cubre solo la validación de la petición y el registro de la
operación en curso; después la E/I con el portal ocurre sin retenerlo. Los
permisos no se cachean en la cookie ni en el frontend: cada operación vuelve a
consultarlos en el store, y cada método de `Store` toma su lock para su propio
acceso a SQLite.

### Concurrencia: puertas de usuario y de cuenta (NFR-SVC-002, ADR-013)

`AppServer` mantiene dos colecciones de `OperationGate`: una por identificador
de **usuario** y otra por identificador de **cuenta** (espacios separados, una
puerta por clave vista, en RAM y con la misma vida que el proceso). Prioridad
de escritores en ambas. Las operaciones autenticadas entran en **compartido**
en su puerta de usuario y, cuando trabajan con una cuenta, también en
**compartido** en la de esa cuenta; los cambios entran en **exclusivo**:

- un `links/decide` entra en exclusivo sobre la puerta del `requester_id` del
  enlace (se lee con `Store.link_requester`, antes de entrar), así que una
  revocación o bajada espera a que termine la operación en curso del titular
  del permiso y se aplica antes de las siguientes peticiones (FR-LINK-002),
  incluida la autorización que se repite antes de descifrar;
- un `accounts/delete` o `accounts/update` entra en exclusivo sobre la puerta
  de **su cuenta**. Autorizar, descifrar y operar con el portal ocurren dentro
  de esa puerta, así que la desvinculación o la rotación de credenciales
  esperan a las operaciones en curso de esa cuenta —de cualquier usuario— y,
  cuando se aplican, no queda ninguna acción de portal posterior ni ninguna
  foto de credenciales anterior en vuelo; las peticiones siguientes vuelven a
  autorizar y descifrar (403/404 sin construir cliente);
- una operación lenta (renovación, portada, panel) no bloquea otra ruta del
  mismo usuario, otras cuentas ni las peticiones de otros usuarios: el lock
  global del store ya no acompaña la red, solo cada consulta SQLite. `library`
  toma las cuentas **una cada vez**, nunca dos a la vez.

Las claves de puerta de cuenta se recortan igual que `store.text`, de modo que
un id enviado con espacios delimita la misma puerta que el id limpio. Orden de
adquisición: lock de sesión → puerta de usuario → puerta de cuenta → lock del
store; nadie espera por una puerta mientras sostiene otra más alta ni mientras
sostiene el lock del store, así que no hay ciclo, y ninguna ruta adquiere dos
puertas de cuenta a la vez.

Antes de existir la puerta de cuenta, una desvinculación podía intercalar con
una operación ya autorizada: la foto de credenciales permitía terminar (incluso
una renovación) **después** de borrar o rotar. Eso no se corrige revalidando al
terminar —la acción ya se habría enviado—, sino impidiendo la intercalación.

### Respuestas y desconexiones

`respond`, `respond_image` y la entrega de estáticos envuelven la escritura: una
`OSError` de socket (cliente que se ha desconectado) marca la conexión
(`client_gone`), fija `close_connection` y **no** se reintenta. `error_response`
nunca emite una segunda respuesta si la primera ya empezó, de modo que no hay
un `502` detrás de un `200` de portada incompleto ni una excepción que salga
del hilo hacia `socketserver.handle_error`. Solo cuenta el socket como
desconexión: con el cliente conectado, los errores reales siguen traduciéndose
a 400/403/409/422/502.

`CoverRegistry` guarda, solo en memoria, la URL de portada que descubrió cada
búsqueda de una cuenta o cada apertura de ficha bajo demanda (TTL 600 s, máximo
200 entradas) **y**, una vez validados, sus propios bytes
(`put_image`/`get_image`, TTL 600 s, máximo 40 entradas y 8 MB en total).
`GET /api/cover` autoriza lectura **antes** de mirar esa memoria; solo si no
está, pide la URL al motor y, si tampoco la conoce, la descubre abriendo
`?TITN=` **una sola vez** para esa (cuenta, ficha), memorizando también la
ausencia (entrada con URL vacía). El motor vuelve a comprobar con
`is_portal_url` el origen, el CGI y que la ruta no admita traversal ni
autoridades malformadas; los bytes solo se memorizan después de superar tipo y
tamaño. Si la URL registrada cambia, los bytes memorizados se descartan. Las
portadas no se persisten ni viajan al navegador sin autorización.

La memoria de bytes existe porque el navegador recibe la imagen con
`Cache-Control: no-store`: sin ella, cada render volvía a descargarla del
portal. Medido el 2026-10-08 con cliente falso y latencia artificial de 0,3 s
por petición al portal (sin portal real): antes del arreglo, 3 `GET cover` de
la misma ficha producían **3 descargas** y la repetición costaba **0,302 s**;
después, **1 descarga** y la repetición se sirve de memoria en **0,001 s**
(frente a 0,603 s de la primera: descubrimiento + descarga). Serializar el
payload real de `/api/library` (1568 bytes) cuesta ~8 µs, unas 37.000 veces
menos que una descarga: la latencia no está en la serialización.

Como cualquier otra consulta al portal, la descarga ocurría bajo el lock global
del store (medido el 2026-10-08: `/api/settings` esperó 0,297 s mientras se
descargaba una ficha desconocida; ver TODO-PERF-001 y [ADR-012](decisions.md)).
Desde NFR-SVC-002 y [ADR-013](decisions.md) la descarga se hace sin retener ese
lock, solo bajo la puerta compartida del usuario, así que una portada nueva ya
no serializa el resto del API; su latencia solo espera a las peticiones de esa
misma puerta y a la propia descarga. Si el portal devuelve
un tipo fuera de `image/*`, una URL caducada o un error, la API responde 502 y
la interfaz conserva el marcador de letra; esos bytes fallidos nunca se memorizan.

## CLI — `biblio/accounts.py`, `biblio/cli.py`

Registro por defecto `~/.config/biblio/accounts.json`: solo `id`, `card`, `label`.
Password: primero valor en memoria, luego `BIBLIO_PWD_<ID>`, luego getpass si se
permite. Para el nombre de variable, upper-case y sustitución de `-` por `_`.

La CLI conoce alias/carnés, no usuarios web ni links. `prestamos` recorre cuentas;
búsqueda, renovación y reservas toman la primera cuenta seleccionada. El uso
exacto y diferencias de consola están en [operations.md](operations.md).

## Incidencias aún abiertas

El fallback de ficha única usa `h1` y puede dar «Documento» como título;
la navegación envía DOC=page aunque el href del fixture usan offsets 11/21;
`wait` está definido dos veces y el segundo referencia `time` sin importar;
la ayuda de credenciales menciona `--password-stdin`, que no existe. Las URLs
de portada/MARC ya se sanean en el API (ver [api](api.md)); queda verificar en
el portal real el resto de representaciones, en TODO-SEC-001. No son
correcciones hechas en esta documentación: ver [TODO.md](../TODO.md).
