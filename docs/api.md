# Contrato HTTP — API v6

Implementación: [web.py](../biblio/web.py), [store.py](../biblio/store.py),
[mailer.py](../biblio/mailer.py), [passkeys.py](../biblio/passkeys.py),
[oidc.py](../biblio/oidc.py), [models.py](../biblio/models.py). Este es el API de **BiblioCM**, no un API público
de las bibliotecas. Base local de ejemplo: `http://127.0.0.1:8000/api/`.

La versión pasó de `2` a `3` al cambiar la semántica de `cover_url` (antes URL
del proveedor, ahora ruta de esta aplicación) y añadir `GET cover`. Pasó de `3`
a `4` al llevar esa misma `cover_url` a los DTO de panel (préstamos y reservas),
añadir `record_id` al préstamo y cambiar la semántica de `GET cover`, que ahora
puede descubrir bajo demanda la portada de una ficha desconocida. Pasó de `4` a
`5` al añadir las cinco rutas de identidad (email verificado, cambio y
recuperación de contraseña) y los campos `email`/`email_verified` del `user`
de `session`/`settings`; ver [ADR-017](decisions.md#adr-017--identidad-con-email-verificado-smtp-por-entorno-tokens-hasheados-y-api-v5).
Pasó de `5` a `6` al añadir las passkeys ([FR-AUTH-004](specification.md#fr-auth-004))
y el acceso opcional con Google ([FR-AUTH-005](specification.md#fr-auth-005)):
seis rutas nuevas, `passkeys`/`identities` en el `settings`, `google` en
`session` y el callback de Google como única respuesta del API que no es JSON
(303); ver [ADR-018](decisions.md#adr-018--passkeys-con-webauthn-y-google-oidc-con-joserfc).
Una UI `3` rechaza un servidor `4` y viceversa, que es el caso de proceso antiguo con
archivos nuevos descrito en [incidents](incidents.md). El cambio es aditivo para
los campos ya existentes: una UI `5` frente a un servidor `6` sigue funcionando
y solo omite passkeys/Google, pero el gate de versión obliga a reiniciar
juntos backend y archivos.

## Reglas comunes

- JSON UTF-8; respuesta de éxito actual **200**, incluido registro/creación.
  La única excepción es `GET auth/google/callback`, que responde **303** con
  `Location` a `/?google=…` (navegación del navegador, no una llamada del API).
- `X-Biblio-API-Version: 6` (string), `Cache-Control: no-store`, `nosniff`.
  `GET cover` también responde `no-store`: sus bytes son privados y no se
  guardan en la caché persistente del navegador.
- Fechas ISO `YYYY-MM-DD`; datetimes ISO sin garantía de zona/offset; opcionales `null`.
- IDs BiblioCM de usuario/carné/link: strings opacos, nunca carné o índice de lista.
- IDs OPAC `record`, `barcode`, `reservation` son strings de dígitos en estos endpoints.
- POST: `Content-Type: application/json` y objeto, hasta 8192 bytes.
- Salvo register/login, POST autenticado exige `X-CSRF-Token` de session/login/register.
- Cookie `biblio_session`, Path=/, HttpOnly, SameSite=Strict; Secure con `--secure`.
- Origin se comprueba si está presente, contra el origen canónico del pedido
  (esquema configurado + Host canónico); un Host no canónico no puede igualar
  Origin y responde 403. Sin Origin no hay esa comprobación. No hay CORS.
- Solo lectura autoriza consultas, nunca `renew`, `reserve` o `cancel`.
- Mensajes son texto informativo, no una clave estable para lógica de cliente.
- Si el cliente se desconecta mientras se escribe la respuesta, el servidor
  cierra esa conexión sin emitir otro estado en ella: nunca hay un `502` detrás
  de un `200` empezado (por ejemplo el de `GET cover`). Con el cliente
  conectado, los errores siguen el envelope de la sección
  [Errores](#errores). Las operaciones sin relación no esperan entre sí
  (NFR-SVC-002).
- Cambiar nombres/tipos/semántica pública requiere revisar versión backend + frontend
  y regresiones. Incrementar caché SW es otra operación, no cambia la versión API.

## Catálogo de endpoints

Todas las rutas de la tabla llevan prefijo `/api/`.

| Método / ruta | Acceso | Entrada | Respuesta 200 |
|---|---|---|---|
| GET `version` | Público | — | `{api_version:"6"}` |
| GET `session` | Público | Cookie opcional | `{authenticated,csrf,user,api_version,google}`; `google` es `{enabled}` según la configuración del servidor |
| POST `register` | Público | `{username,name,password}` | `{authenticated:true,csrf,user}` + cookie nueva |
| POST `login` | Público | `{username,password}` | Mismo envelope de autenticación + cookie nueva; `username` admite también un email **verificado** |
| POST `logout` | Sesión + CSRF | `{}` | `{ok:true}` + cookie expirada |
| POST `auth/email/request` | Sesión + CSRF | `{email}` | `{ok:true,message}` idéntico exista o no el email en otra cuenta **y** haya o no fallo de entrega (503 solo sin SMTP configurado) |
| POST `auth/email/verify` | Público (límite propio) | `{token}` | `{verified:true,user}` |
| POST `auth/password/change` | Sesión + CSRF (límite propio) | `{current_password,password}` | `{ok:true,message}`; cierra las demás sesiones |
| POST `auth/password/recovery/request` | Público (límite propio) | `{email}` | `{ok:true,message}` idéntico exista o no el email verificado, con o sin incidencia de correo; 503 sin SMTP |
| POST `auth/password/recovery/reset` | Público (límite propio) | `{token,password}` | `{ok:true,message}`; cierra todas las sesiones del usuario |
| POST `auth/reauth` | Sesión + CSRF (límite propio) | `{password}` | `{ok:true,expires_in}`; abre la ventana de reautenticación (300 s). Contraseña mala → **403** (nunca 401: no cierra la sesión) |
| POST `auth/passkeys/login/options` | Público (límite propio) | `{}` | `{publicKey}` con challenge de un solo uso; respuesta uniforme, sin enumerar usuarios ni `allowCredentials` |
| POST `auth/passkeys/login` | Público (límite propio) | `{credential}` | Mismo envelope de autenticación + cookie nueva (sesión rotada, reautenticada) |
| POST `auth/passkeys/register/options` | Sesión + CSRF + reautenticación (límite propio) | `{}` | `{publicKey}` con `residentKey`/`userVerification` obligatorios y las passkeys existentes en `excludeCredentials` |
| POST `auth/passkeys/register` | Sesión + CSRF + reautenticación (límite propio) | `{credential,label?}` | `{ok,passkey,message}`; credencial repetida → 409 |
| POST `auth/passkeys/delete` | Sesión + CSRF + reautenticación (límite propio) | `{id}` | `{ok,message}`; id ajeno o inexistente → 403 |
| POST `auth/google/start` | Público (login/signup) o sesión + CSRF + reautenticación + email verificado (link) | `{mode}` con `login`/`signup`/`link` | `{authorize_url}` + cookie de enlace `biblio_oidc` del flujo; sin configuración → 503 |
| GET `auth/google/callback` | Público (límite propio) + cookie de enlace del flujo | Query del proveedor (`code`,`state` o `error`) | **303** a `/?google=…`; retira siempre la cookie de enlace y en `login`/`signup` exitosos emite cookie de sesión |
| POST `auth/google/unlink` | Sesión + CSRF + reautenticación (límite propio) | `{}` | `{ok,message}`; sin vínculo → 404 |
| GET `settings` | Sesión | — | `{user,accounts,incoming,outgoing,passkeys,identities}` |
| POST `accounts/add` | Sesión + CSRF | `{label,card,password}` | `{account,message}` |
| POST `accounts/update` | Dueño + CSRF | `{account,label,password}` | `{account,message}` |
| POST `accounts/delete` | Dueño + CSRF | `{account}` | `{message}` |
| POST `links/request` | Sesión + CSRF | `{username,permission}` | `{id,message}` |
| POST `links/decide` | Participante autorizado + CSRF | `{id,action,permission?}` | `{message}` |
| GET `library` | Sesión | — | `{user,accounts,loans,reservations}` |
| GET `search` | Cuenta accesible | Query `account,q,page?` | `{total,records,page}` |
| GET `cover` | Cuenta accesible (read) | Query `account,record` | imagen (`image/png`, `image/jpeg`, …) |
| GET `copies` | Cuenta accesible | Query `account,record` | `{copies}` con DTO Copy |
| GET `reservable` | Cuenta accesible | Query `account,record` | `{copies}` con DTO Reservable |
| POST `renew` | Manage + CSRF | `{account,barcode}` | DTO RenewResult |
| POST `reserve` | Manage + CSRF | `{account,record,index,barcode?}` | `{message}` |
| POST `cancel` | Manage + CSRF | `{account,reservation}` | `{message}` |

## Validaciones específicas

- Registro: username lowercase único, regex `[a-z0-9][a-z0-9_.-]{2,39}`,
  name no vacío ≤80, password 10–200. Login admite password no vacío ≤200.
- El `user` de `session`/`settings` incluye `email` (o `null`) y
  `email_verified` (booleano); nunca sale en DTOs de otros usuarios.
- Identidad: `email` lowercase ≤254 con forma `local@dominio.tld`; los códigos
  de verificación caducan a las 24 h y los de recuperación a la hora, son de un
  solo uso y en la base de datos solo vive su SHA-256. Un fallo de entrega
  retira el código y responde el **mismo** 200 genérico que un envío
  satisfactorio: la respuesta no distingue si el email existe (la incidencia
  del proveedor no puede ser un oráculo de enumeración); sin
  `BIBLIO_SMTP_HOST` los endpoints de correo responden 503 global. El cambio
  exige la contraseña actual y una distinta, y verifica y escribe en la misma
  sección crítica del store; el reset fija la nueva y cierra todas las sesiones
  del usuario.
- Rate limit: 20 intentos cada 5 minutos por IP **y ruta**, con cubetas
  separadas para registro/login (`auth`), verificación (`verify`), solicitud de
  código (`email`), recuperación (`recovery`), cambio (`change`), reauth
  (`reauth`), passkeys (`passkey` autenticadas y `passkey_login` públicas) y
  Google (`oidc`, compartida por start/callback/unlink).
- Passkeys: el RP ID y el origen esperado se derivan del origen **canónico del
  pedido** (esquema `--secure` + Host parseado de forma estricta) validado
  contra la lista de confianza del servidor: local por defecto
  (`localhost`/`127.0.0.1`, cualquier puerto, http y https) y público solo si
  está en `BIBLIO_TRUSTED_ORIGINS` (solo https no locales, coincidencia exacta
  de origen). Un Host arbitrario —incluso sobre TLS— recibe **403** y un Host
  no canónico (userinfo, ruta, query, fragmento, control o puerto inválido)
  **400**, ambos antes de mirar el cuerpo (NFR-SVC-003). Los retos viven 5
  minutos, se guardan como SHA-256 y se consumen **una sola vez** (también en
  login); la verificación de `Origin`, RP ID, firma, UV y contador es de la
  librería `webauthn`, contra la clave pública guardada de esa credencial, y un
  contador que no avanza se rechaza.
  `label` es opcional (≤40, default `Passkey`); máximo 10 passkeys por cuenta.
- Reautenticación: la ventana (`expires_in`, 300 s) se abre con
  `auth/reauth` (contraseña) o con una passkey recién usada; añadir/borrar
  passkeys y vincular/desvincular Google la exigen, y fuera de ella responden
  **403** con `code:"reauth_required"`.
- Google: `state` y `nonce` de un solo uso con caducidad de 10 minutos, PKCE
  (S256) y verificación del token ID (RS256 contra el JWKS por descubrimiento
  OIDC; `iss`, `aud`, `exp`/`iat`, `nonce`, `azp` con varias audiencias). El
  estado se consume antes de tocar el proveedor, así que un fallo no deja
  transacción viva ni sesión abierta. Identidad: par `(issuer, sub)`; `link`
  exige email verificado y reautenticación, y una cuenta Google solo puede
  pertenecer a un usuario por instancia. `signup` crea una cuenta nueva con el
  email certificado por el proveedor y alias determinista; si el email ya existe
  responde `/?google=exists` sin crear ni fusionar nada. El `redirect_uri` se
  selecciona solo desde un origen de confianza del servidor (la misma lista
  `BIBLIO_TRUSTED_ORIGINS` de las passkeys): con `BIBLIO_GOOGLE_REDIRECT_URI`
  la URI debe ser canónica, apuntar a `/api/auth/google/callback` y su origen
  debe estar en la lista (incorrecta → 503); sin ella se deriva del origen
  canónico del pedido, y un Host hostil recibe **403** en `start` —nunca elige
  el callback—. Sin configuración, `start`/`callback` responden 503 y
  `session.google.enabled` es `false`.
  Destinos del callback: `signed`, `linked`, `exists`, `not-linked`, `denied`,
  `error`.
- Login CSRF de Google ([ADR-019](decisions.md#adr-019--el-flujo-google-se-liga-al-navegador-y-a-su-sesión-viva)):
  `start` emite la cookie de enlace `biblio_oidc` (valor aleatorio de 32 bytes,
  `HttpOnly`, `SameSite=Lax`, `Path=/api/auth/google`, `Max-Age=600` y `Secure`
  con `--secure`); el servidor guarda **solo su SHA-256** en el detalle cifrado
  del estado y lo compara en tiempo constante **antes** de canjear el `code`,
  crear sesión o escribir un vínculo. El callback sin esa cookie —o con una
  ajena, reutilizada o caducada— responde `/?google=error` sin ninguna llamada
  al proveedor y **sin consumir el estado**, así que el navegador que inició el
  flujo aún puede completarlo. El enlace nunca viaja en la query. En `link`, el
  estado guarda además el SHA-256 del token de la sesión que inició el flujo: si
  esa sesión ya no está viva para el mismo usuario con email verificado (p. ej.
  un logout pendiente), el callback responde `error` y no vincula nada. La
  escritura del vínculo ocurre en un **gate atómico respecto al logout**: la
  comprobación de sesión y la escritura se serializan con el propio lock que usa
  el logout (y el titular se revalida dentro de la transacción que escribe), de
  modo que un logout no puede intercalarse entre ambas; si llega durante el
  gate, se ordena después (la sesión seguía viva al escribir) y solo cierra la
  sesión, sin desvincular. La cookie de sesión global no cambia
  (`SameSite=Strict`) y el callback no la lee.
- Vincular: label no vacío ≤80, card no vacío ≤100 (no se restringe a dígitos
  en este endpoint), password no vacío ≤200. Se valida en el portal.
- Update no acepta cambiar card: reutiliza el guardado y verifica la nueva clave.
- Solicitud: username no vacío ≤40 y permission `read`/`manage`.
- Decisión: `approve`, `reject`, `revoke`, `permission`. Permission obligatorio
  para approve/permission; solo el owner puede ejecutar esas decisiones.
- Catálogo: q no vacío ≤300, page default 1, entero 1–1000.
- Portada: `record` son dígitos y `account` se autoriza con permiso de lectura
  **antes** de mirar la portada **y antes** de servirla desde la memoria de
  bytes. Si la caché en memoria no conoce esa
  (cuenta, ficha) — nunca se buscó, la entrada caducó o el servidor se reinició
  —, el servidor abre la ficha del registro **una sola vez** para descubrir la
  URL y la memoriza; también memoriza la ausencia, para no repetir la petición
  en cada render. Sin registro y sin portada en la ficha → 404. El motor
  revalida esquema, origen, puerto y CGI, y rechaza userinfo/puertos malformados,
  caracteres de control, dot segments y separadores percent-codificados en
  **todas** las capas de decodificación de la ruta, con profundidad acotada: si
  la normalización no estabiliza dentro del tope, se rechaza. También aplican
  límite de tamaño (1,5 MB) y de tipos: solo se sirven tipos `image/*` de una
  lista cerrada (sin SVG); cualquier incumplimiento o fallo del portal → 502.
  La respuesta no incluye la URL del proveedor ni su token. El panel no lanza
  esas fichas por su cuenta: la descubierta solo ocurre cuando el navegador
  pide una portada concreta, con carga diferida.
- Reserva: index entero real >0; boolean no válido. Barcode opcional en API,
  pero la UI lo envía para proteger selección si cambia el orden del asistente.
- Account opaco no vacío ≤100 en la autorización. Un ID ajeno devuelve 403.

## DTO User y Account

```json
{
  "user": {"id": "user-example", "username": "persona", "name": "Persona de ejemplo",
           "email": null, "email_verified": false},
  "account": {
    "id": "account-example", "owner_id": "user-example", "label": "Principal",
    "username": "persona", "name": "Persona de ejemplo",
    "permission": "manage", "own": true
  }
}
```

Este bloque muestra formas de DTO, no una respuesta adicional. El `user` lleva
`email` (string o `null`) y `email_verified` (booleano) desde la API `5`; ese
bloque solo aparece para el propio usuario, nunca en DTOs de terceros. En
`settings`, las cuentas propias añaden `masked_card` y el usuario añade
`passkeys` e `identities`: la primera es una lista de `{id,label,created_at}`
(del propio usuario, nunca ajena; `id` es el identificador de la credencial en
base64url) y la segunda de `{provider,created_at}` (hoy solo `google`), sin
`sub` ni email del proveedor. En `library`, cada cuenta
puede añadir `reader` o `error`. El `account` anidado de préstamos/reservas
contiene metadatos básicos, no la contraseña ni el objeto cliente.

DTO Reader: `card`, `name`, `suspended`, `expired`, `card_expires` (date/null).
`card` puede ser completo en el panel autorizado; el enmascaramiento de settings
no significa que todo el API enmascare los carnés.

## DTO Loan

| Campo | Tipo |
|---|---|
| `barcode`, `title`, `library`, `branch_address`, `branch_code`, `signature` | string |
| `record_id` | string con el `TITN` del enlace de ficha del préstamo; vacío si el portal no lo da |
| `cover_url` | string: `/api/cover?account=…&record=…` cuando `record_id` es numérico, si no vacío |
| `due` | datetime ISO |
| `due_date`, `renewal_available_from` | date; segundo nullable |
| `days_left`, `renewals_used`, `renewals_max`, `renew_window_days`, `pending_holds` | integer |
| `renewal_state` | string del enum RenewalState |
| `clean_title`, `author` | string derivado |
| `overdue`, `due_soon` | boolean derivado |
| `account` | metadatos Account; añadido por la agregación web |

Enum declarado: `renovable`, `renovable_desde`, `limite_alcanzado`, `no_renovable`,
`prestado_con_retraso`, `lector_caducado`, `lector_suspendido`, `desconocido`.
El derivador actual no usa todas las variantes de bloqueo; ver [backend](backend.md).

Un barcode repetido en cuentas distintas no es un préstamo único. No agrupar ni
enviar operaciones usando solo el título/barcode sin su Account.

La portada se atribuye con **cuenta + `record_id`**, nunca con el título ni solo
con el barcode. Si el HTML del préstamo no trae el enlace de ficha, `record_id`
y `cover_url` vienen vacíos y la UI conserva su marcador de letra.

## DTO Reservation

`reservation_id`, `title`, `record_id`, `state`, `signature`, `branch`, `branch_code`
son strings; `expires` date/null, `created` datetime/null; `account` añadido en el
panel. `state` es texto del portal, no el enum de links ni RenewalState.
`cover_url` es `/api/cover?account=…&record=…` cuando `record_id` es numérico,
vacío en caso contrario: la atribución es cuenta + registro, nunca el título.

## DTO Link (settings)

`id`, `owner_id`, `requester_id`, `permission`, `status`, `owner_username`,
`owner_name`, `requester_username`, `requester_name`.

Permission: `read`/`manage`. Status: `pending`/`approved`/`rejected`/`revoked`.
`incoming` son relaciones donde la sesión es owner; `outgoing` donde es requester.
No hay created_at/updated_at ni histórico de estados en este contrato.

## DTO MarcRecord (search)

Strings: `record_id`, `title`, `author`, `publication`, `year`, `language`, `isbn`,
`classification`, `extent`, `summary`, `cover_url`, `doc_type`.
`subjects`: lista de strings. `openurl`: dict string/string.
`raw_marc`: dict string/lista de strings. `extent` ayuda a distinguir
soporte/edición; `subjects`, `language`, `classification`, `doc_type`,
`openurl` y `raw_marc` se devuelven aunque la UI no los pinte todavía
(TODO-CAT-003).

`cover_url` es relativa a esta aplicación: `/api/cover?account=…&record=…`, o
cadena vacía cuando no hay portada utilizable. Se emite también cuando el portal
salta directamente a la ficha con un único resultado: esa ficha trae su portada
y se lee con la misma regla que la de la lista, resolviéndola contra la última
respuesta. La URL real del proveedor, con el
token del hilo, se conserva solo en memoria del servidor y nunca sale en la
respuesta. Además, cualquier valor del DTO que contenga la ruta de sesión del
OPAC (`/abnetopac/<token>`) se sustituye por cadena vacía antes de serializar,
también en `openurl` y `raw_marc`. La UI solo pinta `cover_url` si coincide con
esa forma; no cargar portadas desde otro origen. Queda verificar en el portal
real el resto de representaciones: TODO-SEC-001.

`total` es el total informado por el portal, no el tamaño de `records`. La UI
actual no calcula un último número de página fiable a partir del total.

## DTO Copy y Reservable

**Copy** (`copies`): `barcode`, `signature`, `library`, `branch`, `location`,
`copy_type`, `availability`, `support` (strings), `expected` date/null y
`available_now` boolean. Solo igualdad textual normalizada con «Disponible»
significa disponible ahora. Los recuentos son de esa ficha concreta.

**Reservable** (`reservable`):

```json
{
  "copies": [{
    "index": 3, "barcode": "9000000003",
    "library": "Red municipal de ejemplo", "branch": "Sucursal de ejemplo",
    "location": "Sala infantil", "signature": "JUE SWI ejemplo",
    "copy_type": "Juegos de consola",
    "availability": "Disponible después de 20/10/2026"
  }]
}
```

No enviar `row`, sequence, period ni price. Los índices pueden no ser consecutivos;
no renumerarlos. Biblioteca/sucursal debe estar presente; de lo contrario el
servidor rechaza el resultado con 502. El formulario interno del motor sí tiene
otros campos para enviar la operación, y la CLI usa una descripción `row` limpia.

## DTO RenewResult

```json
{
  "ok": true,
  "message": "Título renovado: fecha anterior → fecha confirmada",
  "previous_due": "2026-10-05", "new_due": "2026-10-20",
  "renewals_used": 1, "renewals_max": 1
}
```

El cuerpo no tiene «días de prórroga» ni «días restantes». La UI vuelve a consultar
`library` y usa `due_date`/`days_left` de la tarjeta actualizada. No parsear message
para calcular fechas. El POST de renovación no se repite durante la comprobación.

## Respuesta de portada (`GET cover`)

No es JSON: devuelve los bytes de la imagen con `Content-Type: image/*`,
`X-Biblio-API-Version`, `X-Content-Type-Options: nosniff`,
`Referrer-Policy: no-referrer`, `Cache-Control: no-store` y
`Content-Security-Policy: default-src 'none'; sandbox`. La URL de la petición
no contiene tokens y el service worker no intercepta esta ruta.

Si la portada no estaba en la caché en memoria, el servidor la descubre abriendo
`?TITN=<record>` una sola vez para esa (cuenta, ficha) y TTL; el resultado —
también el negativo — queda en la misma caché, así que un render siguiente no
repite la petición al portal. La descubierta ocurre después de autorizar la
cuenta y solo responde con bytes de imagen validados.

Los bytes validados se memorizan también en memoria (mismo TTL, máximo 40
entradas y 8 MB en total) porque la respuesta es `no-store`: así un render
siguiente se sirve del servidor sin volver a descargar la imagen del portal.
La memoria **no** sustituye la autorización: `store.access` se ejecuta siempre
**antes** de mirarla, de modo que una sesión sin permiso, un tercero ajeno o una
concesión revocada reciben 403 aunque los bytes estén memorizados, y ninguna
petición denegada llega al portal. La forma, los estados y las cabeceras de esta
respuesta no cambian: por eso la versión sigue siendo `4`.

## Errores

Envelope: `{"error":"mensaje legible"}` con el header de versión. Opcionalmente
el cuerpo añade `"code"`, el **único** campo estable para la lógica de cliente
(hoy solo `reauth_required`); los mensajes siguen sin ser claves. El orden de
validación influye: una sesión ausente puede devolver 401 antes de llegar a una
ruta desconocida; no asumir que toda entrada incorrecta devuelve 400.

| Status | Uso actual |
|---|---|
| 400 | JSON/campos/rangos inválidos, auto-solicitud, decisión desconocida, passkey/reto inválido o caducado |
| 401 | Login web o passkey incorrecto, sesión ausente/cerrada/caducada |
| 403 | Origin/CSRF, cuenta no autorizada, permiso insuficiente, decisión ajena, reautenticación requerida (`code:"reauth_required"`), WebAuthn o start de Google en origen no confiable/no listado |
| 404 | Recurso estático/ruta desconocida, username solicitado inexistente, ficha sin portada utilizable, Google sin vincular |
| 409 | Username/carné/passkey/identidad Google duplicados, transición de link inválida, operación OPAC rechazada/no confirmada, sesión con login/signup de Google abierto |
| 413 | Cuerpo POST demasiado grande |
| 415 | POST que no declara JSON |
| 422 | AuthError del carné/OPAC en una operación individual |
| 429 | Intentos de login/registro/identidad por IP agotados temporalmente |
| 502 | Fallo no traducido del motor/transporte, reservables sin datos estructurados, portada de tipo no permitido o proveedor OIDC sin respuesta |
| 503 | Capacidad de sesiones activas agotada, correo sin configurar o acceso con Google sin configurar |

`library` representa fallos de una cuenta mediante `accounts[].error` y mantiene
200 con resultados parciales; no convertirlos en un logout global. No hay códigos
de error de máquina más detallados ni ID de correlación por petición.

## Respuesta de redirección (`GET auth/google/callback`)

No es JSON: responde **303** con `Location: /?google=<resultado>`,
`Cache-Control: no-store` y longitud cero. **Toda** respuesta retira la cookie
de enlace `biblio_oidc` (al completar y en cada error); en un login/signup
exitoso añade además la cookie `biblio_session` nueva (misma cookie que el
login por contraseña). La cookie se guarda en cualquier respuesta y se envía en
las peticiones posteriores del propio origen, que es donde la app consulta la
sesión. Los posibles valores de `google` son `signed`, `linked`, `exists`,
`not-linked`, `denied` y `error`; la UI los traduce a mensaje y limpia la URL
sin exponer el `state`, que ya se consumió (o que quedó intacto si el rechazo
fue por enlace de navegador incorrecto).

## Ejemplo de autenticación (pseudoflujo)

1. GET session → si no está autenticado, POST login con usuario BiblioCM.
2. El navegador conserva la cookie HttpOnly; guardar `csrf` en memoria de UI.
3. GET settings → obtener `account.id` accesible.
4. GET search/copies con ese ID. POST solo con permiso y CSRF actuales.
5. Logout elimina sesión/cookie. Reiniciar el servidor exige otro login.

No documentar cookies reales ni usar la clave OPAC para el login de este API.
