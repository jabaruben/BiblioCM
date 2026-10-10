# Arquitectura

Para el contrato de producto ver [especificación](specification.md). Para el
contrato de transporte ver [API](api.md). Decisiones: [ADRs](decisions.md).

## Vista del sistema actual

```text
Navegador / PWA Android-iPhone
  index.html + styles.css + app.js + sw.js
       │ HTTP JSON mismo origen + cookie BiblioCM + CSRF
       ▼
biblio.web.AppServer / Handler
       ├── biblio.store.Store ── SQLite + clave Fernet
       └── biblio.client.AbsysClient (nuevo por operación/carné)
                    │
                    ├── biblio.parser + biblio.dom ── modelos de dominio
                    └── biblio.http.Http ── OPAC externo CGI/HTML

biblio.cli ── biblio.accounts.Registry ── AbsysClient ── mismo motor OPAC
```

Es un proceso Python con servidor HTTP de biblioteca estándar y archivos
estáticos, no un servicio REST del proveedor ni un cliente que acceda al portal
directamente desde el navegador. No hay React, bundler, servidor Node, app Kotlin,
Swift, job scheduler ni worker de notificaciones.

## Mapa de ficheros y responsabilidad

| Fichero | Responsabilidad | Dependencias relevantes |
|---|---|---|
| [models.py](../biblio/models.py) | Dataclasses, estados y propiedades de dominio | stdlib |
| [dom.py](../biblio/dom.py) | Árbol mínimo HTML y búsqueda por atributos/clases | HTMLParser |
| [parser.py](../biblio/parser.py) | HTML → datos, reglas derivadas, formularios | dom, models |
| [http.py](../biblio/http.py) | HTTP, encoding, compresión, meta-refresh y ritmo | urllib |
| [client.py](../biblio/client.py) | Sesión OPAC y orquestación de operaciones | http, parser, models |
| [accounts.py](../biblio/accounts.py) | Registro de la CLI y obtención de passwords | JSON, entorno, getpass |
| [cli.py](../biblio/cli.py) | Comandos y salida de terminal | accounts, client |
| [store.py](../biblio/store.py) | Identidad web, cifrado, códigos de un solo uso, retos y concesiones | SQLite, cryptography |
| [mailer.py](../biblio/mailer.py) | Correo de verificación/recuperación por SMTP del entorno | smtplib |
| [origins.py](../biblio/origins.py) | Origen canónico y lista de orígenes de confianza (passkeys/Google) | store |
| [passkeys.py](../biblio/passkeys.py) | Ceremonias WebAuthn y contexto de origen/RP ID | webauthn, origins |
| [oidc.py](../biblio/oidc.py) | Configuración, descubrimiento y verificación del token de Google | joserfc, urllib, origins |
| [web.py](../biblio/web.py) | API, sesiones web, permisos y archivos estáticos | store, client, mailer, passkeys, oidc, origins |
| [app.js](../biblio/static/app.js) | Estado UI, renderizado y peticiones | API del navegador |
| [index.html](../biblio/static/index.html) | Estructura y formularios | app.js, styles.css |
| [styles.css](../biblio/static/styles.css) | Layout y estilos responsive | CSS nativo |
| [sw.js](../biblio/static/sw.js) | Caché del shell público | CacheStorage |
| [manifest](../biblio/static/manifest.webmanifest) | Metadatos e iconos PWA | Navegador |

`pyproject.toml` empaqueta `biblio/static/*` y publica `biblio` y `biblio-web`.
Python mínimo: 3.11. Dependencias de la aplicación web: `cryptography>=44` y,
como excepción acotada ([ADR-015](decisions.md#adr-015--email-verificado-passkeys-y-oidc-con-librerías-mantenidas-y-tokens-hasheados),
[ADR-018](decisions.md#adr-018--passkeys-con-webauthn-y-google-oidc-con-joserfc)),
`webauthn>=2.2.0` y `joserfc>=1.6` para no escribir WebAuthn ni verificación de
token OIDC a medida; Playwright es opcional de verificación. Node solo se usa
opcionalmente para comprobar sintaxis, no para ejecutar o construir el frontend.

## Tres identidades que nunca deben confundirse

1. **Usuario web:** ID opaco, username, hash de contraseña y (desde 2026-10-10)
   email verificado opcional en SQLite.
2. **Carné:** ID opaco de vinculación, owner BiblioCM y credenciales OPAC cifradas.
3. **Sesión OPAC:** token en URL mantenido por una instancia de `AbsysClient`.

La cookie `biblio_session` no es una cookie del portal. Login BiblioCM no llama
al OPAC; vincular un carnés sí valida sus credenciales en el portal.
La CLI tiene un cuarto identificador local (alias de `accounts.json`), sin
relación automática con usernames, usuarios SQLite o autorizaciones.

El email verificado es un alias de acceso del usuario BiblioCM, no un carné ni
una identidad del portal: solo abre sesión si `email_verified_at` está fijo, y
el username legado sigue funcionando igual ([FR-AUTH-002](specification.md#fr-auth-002),
[ADR-017](decisions.md#adr-017--identidad-con-email-verificado-smtp-por-entorno-tokens-hasheados-y-api-v5)).
Los códigos de verificación/recuperación viven como hash en `identity_tokens` y
salen por el correo que envía [mailer.py](../biblio/mailer.py) con la
configuración SMTP del entorno; el proyecto no trae proveedor.
Una **identidad externa** (hasta ahora solo Google, `(issuer, sub)` en
`identities`) y una **passkey** (`credential_id` + clave pública en `passkeys`)
son factores anclados al usuario BiblioCM: se añaden de forma explícita con
reautenticación, no encuentran ni crean cuentas por sí solos y se pueden quitar
sin borrar la cuenta ni sus carnés.

## Flujo de lectura del panel

1. Cookie → sesión en memoria → `user_id`.
2. Bajo `Store.lock`, SQL calcula carnés propios y concesiones aprobadas actuales.
3. Por cada carné, autorizar, descifrar credenciales y construir un cliente nuevo.
4. `my_library()` autentica al OPAC y parsea lector/préstamos/reservas.
5. Un error se añade a ese carné, conservando los demás resultados.
6. JSON agregado: cada préstamo/reserva incluye su metadato `account`.
7. UI filtra, ordena y calcula contadores sobre la selección; no suma prórrogas locales.

Los préstamos/reservas no se persisten en SQLite. El portal es su fuente de
estado actual. Las sesiones OPAC tampoco se almacenan en la sesión BiblioCM.

## Flujo de autorización y mutación

1. Validar sesión, Origin/JSON/CSRF y campos de la petición.
2. Entrar en el lock de la sesión, comprobar que sigue vigente en memoria y
   registrar la operación en la puerta de su usuario (compartido; exclusivo
   sobre el `requester_id` cuando la ruta es `links/decide`).
3. Consultar la concesión actual bajo el lock del store (`manage` si mutación);
   cada método del store toma ese lock solo para su propio acceso a SQLite.
4. Entrar en la puerta de la cuenta con la que se va a trabajar (compartido;
   exclusivo para `accounts/delete`/`accounts/update` de esa cuenta), construir
   el cliente y ejecutar una única operación del portal **sin retener** el lock
   de la sesión ni el global del store. `library` recorre las cuentas una
   cada vez.
5. Verificar el resultado en el estado del portal antes de anunciar éxito.

Las puertas ([ADR-013](decisions.md), NFR-SVC-002) mantienen lo que antes
garantizaba el lock global: una revocación o bajada espera a que termine la
operación en curso del titular del permiso, y una desvinculación o rotación de
credenciales espera a las operaciones en curso de esa cuenta —de cualquier
usuario— antes de aplicarse, de modo que no hay acción de portal posterior a la
desvinculación ni con credenciales obsoletas. Una operación lenta no bloquea
otras rutas, cuentas ni usuarios. Los locks son de **este proceso**: no hay
garantía de coordinación entre varios procesos/servidores compartiendo SQLite.

## Flujos especialmente sensibles

- **Renovar:** formulario real → un POST → adoptar respuesta → login nuevo →
  comprobar fecha/counter → UI recarga panel → aviso desde ese mismo snapshot.
- **Reservar:** snapshot de reservas previas → ficha → asistente → reencontrar
  barcode/índice → un POST de una copia → nueva reserva de ese registro.
- **Anular:** comprobar ID en la cuenta → POST → comprobar ausencia del ID.
- **Compartir:** permiso sobre usuario titular → todos sus carnés directos;
  nunca propagar concesiones que el titular recibió de terceros.
- **Passkey:** reto de un solo uso emitido por el servidor → ceremonia en el
  navegador → verificación con la librería contra la clave pública guardada →
  sesión rotada. Añadir/borrar exige reautenticación (contraseña o passkey
  reciente), y el servidor rechaza la ceremonia fuera de un origen confiable.
- **Google:** `start` con `state`/`nonce`/PKCE de un solo uso → autorización en
  el proveedor → `callback` que consume el estado **antes** de tocar al proveedor
  → token ID verificado contra el JWKS → vincular a la cuenta del estado o
  abrir sesión solo si ese `(issuer, sub)` ya estaba vinculado. El alta es un
  modo aparte con email certificado; nunca hay fusión por email.

## Fronteras de datos

- Se envían al navegador datos de lector, préstamos, reservas y metadatos de
  cuentas accesibles. En `library`, el lector puede incluir el carné completo;
  `settings` enmascara el carné de vinculaciones propias.
- No se envían passwords OPAC, hashes/sales, clave Fernet ni campos internos de
  envío del asistente como sequence/period/price. Tampoco salen la clave pública
  de una passkey en listados distintos a los suyos, el nonce ni el verificador
  PKCE de Google: los retos viven como SHA-256 y el detalle OIDC cifrado con
  Fernet ([ADR-018](decisions.md#adr-018--passkeys-con-webauthn-y-google-oidc-con-joserfc)).
- Los metadatos MARC de búsqueda son datos bibliográficos del portal y sí se
  devuelven; no equivalen a compartir un formulario de autenticación.
- Las URLs bibliográficas salen saneadas: `cover_url` se reescribe como ruta de
  esta aplicación (`/api/cover`) y cualquier valor con la ruta de sesión del
  OPAC se retira del DTO de catálogo. La URL real solo vive en memoria del
  servidor, mientras la portada siga registrada o sea reciente; ver
  [ADR-010](decisions.md), [ADR-011](decisions.md) y TODO-SEC-001 para el resto
  de representaciones.
- El endpoint de portadas no es un proxy abierto: solo sirve imágenes de una
  cuenta que se autoriza de nuevo, con origen, CGI, tipo y tamaño comprobados,
  sin seguir redirecciones fuera del origen y sin cachear en el service worker.
  Si la caché no conoce la ficha, la descubre abriéndola una sola vez y
  memorizando también la ausencia; el panel no abre fichas por su cuenta. Los
  bytes ya validados se memorizan también en memoria con tope de entradas y de
  tamaño, y la autorización de lectura se ejecuta **antes** de mirarlos: una
  concesión revocada o un tercero ajeno reciben 403 aunque estén memorizados.
  Memorizarlos sin mover el lock del store es la decisión de
  [ADR-012](decisions.md).
- La UI crea texto con `textContent`. El API de reservables excluye el antiguo
  fragmento `row`; el CLI aún usa una descripción limpia `row` generada por el parser.
- La caché PWA está limitada por whitelist a recursos estáticos del mismo origen.

## Límites de diseño actuales

Una instancia y un SQLite; sesiones/rate limit en RAM; peticiones síncronas por
cuenta; sin colas, escalado, migraciones, observabilidad persistente ni sincronización
offline de datos privados. Los trabajos para evolucionar estos límites están en
[TODO.md](../TODO.md); no introducir otro framework para un cambio local sin una
decisión explícita de arquitectura.
