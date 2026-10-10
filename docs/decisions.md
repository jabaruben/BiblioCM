# Decisiones de arquitectura — ADR

Estado de estas decisiones: **aceptadas para la base actual**. Evolucionarlas
requiere describir alternativa, impacto en requisitos/datos y pruebas. Las
mejoras de [TODO.md](../TODO.md) no cambian estas decisiones por sí mismas.

## ADR-001 — PWA con backend Python

Contexto: disponer de web, Android e iPhone aprovechando el motor existente.
Decisión: HTML/CSS/JS nativos y PWA, servidos junto a un adaptador Python HTTP.
Consecuencia: una UI sin build Node y un solo motor del protocolo; la instalación
móvil necesita HTTPS y soporte del navegador. No se entrega código nativo ni
notificaciones. Comentarios antiguos de código sobre portar a Kotlin son
antecedentes, no instrucciones vigentes de producto.

## ADR-002 — Identidad BiblioCM independiente del OPAC

Contexto: un acceso único y solicitudes de autorización sin compartir claves.
Decisión: username/password propios en SQLite; vincular carnés después del registro.
Consecuencia: login web no acepta carné/clave del portal, y compartir permisos es
una función nuestra, no una delegación ofrecida por el proveedor. Recovery/email
no existen todavía.

## ADR-003 — Credenciales OPAC cifradas recuperables por el servidor

Contexto: consultar cuentas autorizadas sin que su titular esté conectado.
Decisión aceptada por la persona usuaria: Fernet con clave del servidor; password
BiblioCM con scrypt y sal. La clave es independiente de la contraseña de usuario.
Consecuencia: se pueden reautenticar carnés; se necesita respaldar/proteger la
clave y no sustituirla silenciosamente. El cifrado no evita que un servidor con
acceso a la clave descifre credenciales. No sustituirlo por hashes de password
OPAC, porque el motor necesita presentar esa clave al proveedor.

## ADR-004 — Concesión por titular, dos niveles, no transitiva

Contexto: ver todo junto y permitir aprobación de otro usuario.
Decisión: `read` o `manage` sobre todos los carnés directos del titular, incluidos
los futuros. Una concesión recibida no se puede redistribuir.
Consecuencia: consultas SQL simples y una política explícita en UI. Permisos
granulares por carné cambiarían producto y esquema: son propuesta, no refactor local.

## ADR-005 — Una instancia, locks y autorización en cada operación

Contexto: impedir que un permiso cacheado permita actuar tras revocarlo.
Decisión: sesiones en RAM, locks de sesión y store, permisos consultados antes
de descifrar/operar; red bajo lock del store.
Consecuencia: revocación espera a operación en curso, pero puede aumentar latencia;
no hay coordinación distribuida. Windows usa binding exclusivo para impedir
dos servidores sobre la misma dirección/puerto, tras una incidencia real.
Sustitución parcial: desde [ADR-013](#adr-013--puerta-de-operaciones-ei-fuera-del-lock-global-y-escrituras-protegidas)
la E/I con el portal ya no va bajo el lock global del store; ahora espera en
la puerta de operaciones del usuario. La autorización en cada operación y la
espera de la revocación se conservan.

## ADR-006 — Portal como fuente de verdad de las mutaciones

Contexto: los HTML contienen mensajes de éxito como plantillas y los hilos de
sesión pueden producir lecturas que no coinciden con una recarga nueva.
Decisión: verificar estado posterior. Renovación adopta POST y abre acceso fresco;
reserva exige ID nuevo del registro; anulación exige desaparición del ID.
Consecuencia: más lecturas y latencia, pero no anuncios de éxito basados solo en
textos. No eliminar el login fresco para «optimizar» sin preservar la regresión.
Nunca reenviar una mutación como parte de un retry de comprobación.

## ADR-007 — Reservables estructurados y selección por barcode

Contexto: texto roto por recortes HTML y posible cambio de índices del asistente.
Decisión: parsear fila completa; conservar índice original; la web envía barcode
para reencontrar la copia. La API actual excluye `row` y la UI no tiene fallback HTML.
Consecuencia: una respuesta incompatible es error explícito. Todos los ejemplares
y los reservables siguen separados, sin prometer que disponible ⇒ reservable.

## ADR-008 — Solo shell público offline

Contexto: instalación PWA sin conservar datos de cuentas en el dispositivo.
Decisión: whitelist de assets; red primero y caché de instalación como fallback.
Consecuencia: la UI abre offline, los datos/operaciones requieren servidor/portal.
Cambios en assets requieren revisar cache SW; no añadir API al precache para
resolver una experiencia offline sin especificación nueva.

## ADR-009 — Contratos y evidencia en documentos con dueño

Contexto: continuidad entre modelos y evolución sin depender del historial del chat.
Decisión: requisitos con IDs, contrato API, mapa de pruebas/estado y un único TODO;
validación local de enlaces/IDs/estados y proceso SDD/TDD para nuevos cambios.
Consecuencia: docs actuales deben actualizarse junto al comportamiento, y las
propuestas no se presentan como funcionalidades entregadas. README es puerta de
entrada; no duplicar en él todo el contrato técnico.

## ADR-010 — Portadas servidas por la propia aplicación

Contexto: pintar portadas del catálogo (TODO-UX-001) sin exponer el token de
sesión del OPAC que el HTML del proveedor incluye en `img.src`.
Decisión: el servidor registra la URL real en memoria al responder una
búsqueda, la reescribe en el DTO como `/api/cover?account=…&record=…` y la
descarga él mismo comprobando origen, CGI, tipo y tamaño; redirecciones fuera
del origen se rechazan antes de seguirlas. La UI solo pinta esa ruta con carga
diferida y la retira si falla; el service worker no la intercepta y la respuesta
de portada lleva `Cache-Control: no-store`,
`default-src 'none'; sandbox` y `Referrer-Policy: no-referrer`.
Consecuencia: el navegador nunca ve una URL del proveedor, no se abre un proxy
arbitrario y el shell sigue sin abrir `img-src` a ningún dominio ajeno. La
portada depende de que la
búsqueda siga registrada en el servidor (TTL de 600 s) y de que el portal
responda; al no persistirse, un reinicio vuelve al marcador de letra. La API
pasó de `2` a `3` por el cambio de semántica de `cover_url` y el asset de
shell de `v6` a `v7`.
Sustitución parcial (2026-10-10, [ADR-014](#adr-014--caché-de-portada-en-ram-del-navegador-con-invalidación-por-blob-url)):
`img-src` pasó de `'self'` a `'self' blob:` para admitir la caché de blob URL
del navegador; el origen del DOM sigue cerrado a dominios ajenos.
Alternativas descartadas: mostrar la URL del proveedor en el DOM (token en DOM,
caché y respuestas), abrir `img-src` al dominio del portal (permite referir el
origen de la persona usuaria y amplía la CSP), reconstruir la URL sin token (no
verificado contra el portal) y descargar todas las portadas al buscar (masivo y
contra el ritmo del OPAC).

## ADR-011 — Portadas del panel y descubrimiento bajo demanda

Contexto: (a) el panel no anunciaba su carga; (b) faltaban portadas en el
catálogo porque la ficha única a la que salta el portal con un resultado nunca
se leía y porque `GET cover` solo servía lo registrado hacía menos de 600 s,
devolviendo 404 que la UI interpretaba como «sin portada»; (c) los préstamos no
traían identidad bibliográfica y ni préstamos ni reservas pedían portada.
Decisión: `Loan.record_id` se lee del `href?TITN=` del título (vacío si no
existe, nunca deducido del título) y la API entrega `cover_url` en préstamos y
reservas; `GET cover` descubre bajo demanda la portada de una ficha desconocida
abriendo `?TITN=` una sola vez por (cuenta, ficha) y TTL, memorizando también la
ausencia; la regla de «¿cuál es la portada?» es única (`cover_src`: imagen
«Cubierta…», enlace `MLKOB=`, contenedor `c-docs_img`) y se aplica a lista y
ficha. El estado de carga del panel es una región `role="status"` más
`aria-busy`, retirada por la carga más reciente y por `showSession(false)`, de
modo que una respuesta de una sesión cerrada no la reanuncia.
Consecuencia: API `3` → `4` y shell `bibliocm-shell-v7` → `v8`, revisados
juntos; la descubierta añade una lectura de ficha por portada nueva (bajo
`loading="lazy"`, sin prefetch del panel), y las fichas sin portada se
recuerdan durante el TTL en lugar de repetir la apertura.
Alternativas descartadas: emitir la URL del proveedor (token en DOM/caché),
prefetch de todas las fichas del panel (scraping masivo contra el ritmo del
OPAC), deducir el registro del título (atribución ambigua) y guardar portadas
en disco (datos privados fuera de memoria).

## ADR-012 — Memoria de bytes de portada sin tocar el lock

Contexto (medición del 2026-10-08, con cliente falso y latencia artificial de
0,3 s por petición, sin portal real): `GET /api/cover` solo memorizaba la URL
del proveedor, no los bytes, y el navegador la recibe con `Cache-Control:
no-store`, así que **cada render volvía a descargar la imagen del portal**:
tres peticiones de la misma ficha producían tres descargas y la repetición
costaba 0,302 s. Además esa descarga ocurre bajo el lock global del store, de
modo que mientras dura, el resto del API autenticado espera (medido: 0,297 s de
espera en `/api/settings`). Serializar el payload real de `/api/library`
(1568 bytes) cuesta ~8 µs, así que la serialización JSON no es el cuello de
botella.
Decisión: `CoverRegistry` memoriza también los **bytes ya validados**, con el
mismo TTL (600 s) y con tope de 40 entradas y 8 MB en total, solo en memoria y
nunca persistidos. La autorización de lectura se ejecuta **siempre antes** de
mirar esa memoria, de modo que una concesión revocada, un tercero ajeno o una
sesión sin permiso reciben 403 aunque los bytes estén ahí y ninguna petición
denegada llegue al portal. Si la URL registrada para esa (cuenta, ficha) cambia,
los bytes se descartan. Los tipos no permitidos siguen respondiendo 502 y no se
memorizan. El lock del store **no se mueve**: la descarga de una portada nueva
sigue serializando el resto del API, porque alterarlo exigiría demostrar la
semántica de concurrencia con revocación y operaciones, que no está probada
(NFR-SVC-001, FR-LINK-002). Sustitución 2026-10-09: esa semántica quedó
demostrada en [ADR-013](#adr-013--puerta-de-operaciones-ei-fuera-del-lock-global-y-escrituras-protegidas)
con la puerta de operaciones (NFR-SVC-002), y la descarga ya no serializa el
resto del API; la memoria de bytes y su autorización previa no cambian.
Consecuencia: dos `GET cover` de la misma ficha pasan de 2 descargas a 1
(0,603 s la primera, 0,001 s la repetición); API **`4` sin cambio** porque
forma, estados y cabeceras no varían, y shell `bibliocm-shell-v8` → `v9` por los
assets de la UI. Una portada nueva del portal sigue costando su latencia
completa bajo el lock.
Alternativas descartadas: servir la portada desde la caché HTTP del navegador
(los bytes son privados y `no-store` es una decisión anterior ya aceptada),
mover la descarga fuera del lock (sin semántica de concurrencia demostrada),
compartir los bytes entre cuentas (rompería la separación por cuenta) y
persistirlos en disco (datos privados fuera de memoria).

## ADR-013 — Puerta de operaciones, E/I fuera del lock global y escrituras protegidas

Contexto: (a) la medición de [ADR-012](#adr-012--memoria-de-bytes-de-portada-sin-tocar-el-lock)
mostró que una portada nueva serializa el resto del API (0,297 s de espera en
`/api/settings`) porque `dispatch` retenía `store.lock` **y** `session["lock"]`
durante toda la E/I con el portal; (b) la inspección del 2026-10-09 encontró
que una desconexión del cliente al escribir una portada convertía la `OSError`
en un **segundo** intento de respuesta (`502` tras un `200` ya empezado) y en
una excepción que salía del handler hacia `socketserver.handle_error`
(reproducido en local con un RST: `ConnectionResetError 10054` dos veces y
traceback en stderr). FR-LINK-002 exige que una operación en curso termine
antes de aplicar la revocación, que era lo que el lock global garantizaba.
(c) La revisión independiente del mismo día encontró el hueco equivalente en
las cuentas: con solo la puerta de usuario, una operación que ya había pasado
`store.access` y había descifrado credenciales podía seguir —incluso una
renovación, que muta el portal— mientras el titular borraba la cuenta o rotaba
su contraseña, y la documentación afirmaba sin prueba que eso «fallaba
cerrado»: con la foto ya tomada no falla, termina.

Decisión:
1. **Puerta por usuario (`OperationGate`)**: toda operación autenticada entra
   en modo compartido sobre la puerta del usuario que la ejecuta; un
   `links/decide` entra en modo **exclusivo** sobre la puerta del
   `requester_id` del enlace (el titular del permiso que cambia, no quien
   decide), con prioridad de escritores. El lock de la sesión solo cubre la
   validación y el registro de la operación; el lock global del store solo
   cubre cada acceso a SQLite (los métodos de `Store` ya lo tomaban). La
   autorización se consulta en el servidor antes de descifrar y antes de
   operar, en cada petición.
2. **Puerta por cuenta**: segunda colección de puertas, con clave de espacio
   propio (identificador de cuenta, recortado igual que `store.text`, de modo
   que un id con espacios delimita la misma puerta que el limpio). Autorizar,
   descifrar y operar con el portal ocurren dentro de la puerta compartida de
   esa cuenta —`library` recorre las cuentas una cada vez— y
   `accounts/delete`/`accounts/update` entran en **exclusivo** sobre ella:
   desvincular o rotar credenciales espera a las operaciones en curso de esa
   cuenta, de cualquier usuario, y al aplicarse no queda ninguna acción de
   portal posterior ni ninguna credencial obsoleta en vuelo. Orden de
   adquisición: sesión → puerta de usuario → puerta de cuenta → store; ninguna
   ruta mantiene dos puertas de cuenta a la vez.
3. **Escrituras protegidas**: `respond`/`respond_image`/estáticos envuelven la
   escritura y una `OSError` de socket marca la conexión como desconectada y la
   cierra (`close_connection`); `error_response` no emite nunca una segunda
   respuesta si la primera empezó. Solo el socket cuenta como desconexión:
   los errores reales siguen dando 400/403/409/422/502 con el cliente
   conectado.

Consecuencia: una revocación o bajada espera a la operación en curso de ese
usuario, y una desvinculación o rotación espera a la de su cuenta, aplicándose
en cada caso antes de las peticiones siguientes (probado con Event/barrera y
verificado por mutación: sin la exclusiva correspondiente, los cuatro tests
fallan); las peticiones sin relación dejan de serializarse entre sí, pero una
cuenta sí serializa con su propia desvinculación/rotación; una operación ya
autorizada puede terminar tras un logout (una petición posterior con la sesión
cerrada sigue dando 401). Las puertas viven en RAM, una por clave vista, y no
se borran al desvincular porque podría haber hilos esperando. API **`4`** y
shell `bibliocm-shell-v9` sin cambio: forma, estados y cabeceras no varían.
(Al cerrar la misma tarea se añadió el progreso accesible de la renovación
[FR-RENEW-001], que cambia solo `app.js`: el shell sube a
`bibliocm-shell-v10` —operación de assets, distinta de la versión API— y la
API sigue en `4`.)
Sustituye en lo tocante a «red bajo lock del store» la consecuencia de
[ADR-005](#adr-005--una-instancia-locks-y-autorización-en-cada-operación) y
la alternativa descartada de mover la E/I de [ADR-012](#adr-012--memoria-de-bytes-de-portada-sin-tocar-el-lock).
Alternativas descartadas: mantener el lock global (bloqueo medido y documentado),
un lock por conexión (no cubre revocaciones entre sesiones), reintentar la
respuesta tras el fallo de escritura (concatena estados en una conexión rota),
reconstruir la respuesta desde cero sin marca de estado (permitiría un segundo
estado después de un `200`), revalidar la cuenta al terminar la operación (ya
habría enviado la mutación al portal) y una sola puerta global por cuenta o
por proceso (volvería a serializar a usuarios y cuentas sin relación).

## ADR-014 — Caché de portada en RAM del navegador con invalidación por blob URL

Contexto: cada render de portada vuelve a pedir `GET /api/cover` (la respuesta
lleva `Cache-Control: no-store`, decisión anterior de [ADR-010](#adr-010--portadas-servidas-por-la-propia-aplicación)),
así que cambiar de vista o refrescar el panel re-descarga imágenes que ya se
mostraron. La memoria de bytes de [ADR-012](#adr-012--memoria-de-bytes-de-portada-sin-tocar-el-lock)
evita ir al portal, pero no evita la petición HTTP local ni el re-render.
Decisión: `app.js` memoriza las portadas ya servidas como **blob URL** en un
Map de memoria, con clave la ruta `/api/cover?account=…&record=…` y tope de 60
entradas con expulsión FIFO. Las imágenes se pintan desde la blob URL; si la
petición falla se conserva el marcador de inicial. Toda entrada se invalida con
`URL.revokeObjectURL` al cerrar sesión (`showSession(false)`), al recargar o
cerrar la página (`pagehide`) y cuando `syncAccounts` detecta que cambió o
desapareció el permiso o la cuenta que autoriza esa portada. Nada se persiste:
ni CacheStorage, ni localStorage, ni IndexedDB, y el service worker sigue sin
interceptar `/api/cover`.
Consecuencia: API **`4` sin cambio** (rutas, DTOs y estados idénticos) y shell
`bibliocm-shell-v10` → `v11` por assets de UI. El CSP del shell pasa
`img-src 'self'` → `img-src 'self' blob:` para admitir las blob URL creadas por
este mismo documento; el DOM no se abre a ningún origen ajeno y
`default-src`/`connect-src` no cambian. La caché es por pestaña y
no sobrevive a un recorte de memoria del navegador; la autorización del
servidor no cambia, se sigue ejecutando en cada petición de portada.
Alternativas descartadas: servir desde la caché HTTP del navegador (los bytes
son privados y `no-store` ya se decidió), caché persistente en el dispositivo
(datos privados fuera de RAM, contra la frontera de datos del proyecto) y
quitar `no-store` del servidor (afectaría a todas las respuestas del API).

## ADR-015 — Email verificado, passkeys y OIDC con librerías mantenidas y tokens hasheados

Contexto: el usuario aprueba login con email verificado conservando el username
como alias ([FR-AUTH-002](specification.md#fr-auth-002)), recuperación/cambio de
contraseña ([FR-AUTH-003](specification.md#fr-auth-003)), passkeys WebAuthn
([FR-AUTH-004](specification.md#fr-auth-004)) y acceso opcional con Google vía
OIDC ([FR-AUTH-005](specification.md#fr-auth-005)), con
[NFR-SEC-002](specification.md#nfr-sec-002) como higiene común.
Decisión:
1. **Excepción de dependencias, acotada**: para WebAuthn y OIDC se usarán
   librerías Python mantenidas (candidatas: `webauthn` y `authlib`), porque
   implementar a mano el registro/verificación WebAuthn o la verificación de
   tokens OIDC sería criptografía casera. Es una excepción explícita al criterio
   de stdlib-only de la base actual; se fija en `pyproject.toml` con versión
   mínima y se justifica en esta ADR. El resto del proyecto no adquiere
   dependencias nuevas por esta decisión.
2. **Tokens de un solo uso, hasheados y caducados**: email de verificación,
   recovery, state/nonce OIDC y challenges WebAuthn se generan con
   `secrets`, se guardan como hash (SHA-256/HMAC) con caducidad y se invalidan
   al consumirse. Nada de tokens en claro en SQLite.
3. **Sin enumeración y con rate limit**: solicitudes de verificación/recovery
   responden igual exista o no la cuenta; límites por IP y ruta junto al
   existente de registro/login.
4. **Vinculación explícita con reautenticación**: el email del proveedor OIDC
   no crea ni encuentra cuentas de forma implícita; vincular o desvincular
   exige sesión autenticada y reautenticación. El username sigue siendo el
   alias público; los usuarios legados sin email conservan su login.
5. **Migraciones con fixtures temporales**: los cambios de esquema se prueban
   sobre BD temporales preservando IDs, vínculos, carnés y credenciales
   cifradas, con rollback atómico; sin migrar datos reales. No se debilitan las
   puertas de operación de [ADR-013](#adr-013--puerta-de-operaciones-ei-fuera-del-lock-global-y-escrituras-protegidas).
Consecuencia: pendiente de implementar en [TODO-AUTH-001](../TODO.md),
[TODO-AUTH-002](../TODO.md), [TODO-AUTH-003](../TODO.md) y
[TODO-AUTH-004](../TODO.md); hasta entonces la base sigue siendo login con
username/contraseña y sin envíos de correo. SMTP configurable por entorno con
servidor falso en pruebas; ninguna prueba envía correo real.
Alternativas descartadas: criptografía/WebAuthn/OIDC a medida, «login con el
mismo email sin verificar», mapeo automático email↔cuenta (inventaría
identidades) y recordar tokens en claro.

## ADR-016 — Publicación preparada: licencia MIT, SECURITY.md, CI de solo lectura y escaneo de secretos

Contexto: el usuario aprueba publicar el repositorio y quiere una superficie de
publicación segura sin depender de la memoria de quien publique.
Decisión:
1. **Licencia MIT** en `LICENSE` (titular: «jabaruben/BiblioCM», el sugerido
   por la persona usuaria, sin inventar
   personas) y sección de licencia/colaboración en el README.
2. **`SECURITY.md`** con canal privado de notificación (advisories del hosting,
   nunca un issue público con datos), alcance y fuera de alcance; sin inventar
   direcciones de correo.
3. **CI de solo lectura** en `.github/workflows/ci.yml`: checkout, Python
   3.11/3.13, `pip install -e .`, `check_docs.py --tests`, suite unittest,
   `node --check` de `app.js`/`sw.js` y el escaneo de publicación. Permisos
   `contents: read`; sin secretos, sin deploy y sin publicación automática.
4. **Escaneo de secretos** con `scripts/release_scan.py`: recorre los ficheros
   que Git publicaría (según `.gitignore`), aplica reglas de material privado
   (claves privadas, Fernet, tokens de proveedores conocidos, JWT, rutas de
    sesión del OPAC de alta entropía, ficheros de datos/claves que no deberían
    versionarse) y reporta **solo regla + ruta + línea**, nunca contenido. Es un
    guardia previo a publicar, no una auditoría de seguridad completa.
    Ampliación 2026-10-10 ([TODO-PRIV-001](../TODO.md)): regla semántica
    `opac-reader-identity` que señala los marcadores de identidad de lector del
    OPAC (`lenlec`, `nombre`, `apellidos`) cuando su valor no está en la lista de
    valores sintéticos declarados, y regla `opac-loan-identifier` con el mismo
    patrón para los identificadores de préstamo/reserva (`data-prbarc`,
    `data-cobarc`, `data-prppsq`, `data-di`, `prbarc`, `CP<código>`,
    `lector_box…`, `abnRenov…`, `lector_renovMen…`, `DI=`) frente a
    `SYNTHETIC_LOAN_IDS`, que cubre también las referencias derivadas de un
    fixture. El alcance se declara acotado: **no** son detectores de datos
    personales arbitrarios, no cubren los identificadores de ficha del catálogo
    (`TITN`, `data-bc`, `rebarc_`) y siguen complementando (y no sustituyendo) la
    revisión manual.
Consecuencia: publicar el repositorio no instala confianza de CA, no abre
puertos ni migra datos; la ejecución real de la CI y la primera publicación
siguen siendo acciones de la persona. El escaneo no sustituye una revisión
humana ni detecta lógica malintencionada.
Alternativas descartadas: escaneo con servicio en la nube que sube el código
(privacidad), publicar sin licencia (uso no autorizado) y commit hooks locales
como única barrera (no viajan con el repo).

## ADR-017 — Identidad con email verificado: SMTP por entorno, tokens hasheados y API v5

Contexto: [TODO-AUTH-002](../TODO.md) y [TODO-AUTH-001](../TODO.md) llevan a la
práctica [FR-AUTH-002](specification.md#fr-auth-002),
[FR-AUTH-003](specification.md#fr-auth-003) y la parte aplicable de
[NFR-SEC-002](specification.md#nfr-sec-002); el marco general lo fija
[ADR-015](#adr-015--email-verificado-passkeys-y-oidc-con-librerías-mantenidas-y-tokens-hasheados).
Decisión:
1. **SMTP solo por entorno** (`BIBLIO_SMTP_HOST` y compañía, ver
   [operations.md](operations.md)): sin host no hay envío y los endpoints de
   correo responden 503 **global** —previo a mirar si el email existe— para que
   la ausencia de configuración no se convierta en un oráculo de enumeración.
   Las pruebas usan un servidor SMTP falso local (puerto efímero en 127.0.0.1,
   sin AUTH ni STARTTLS anunciados); ningún test habla con un proveedor real.
2. **Tabla `identity_tokens`**: SHA-256 del código, propósito
   (`email_verify` con el email pendiente en `detail`, `password_reset`),
   caducidad (24 h / 1 h) y consumo que borra la fila en la misma transacción.
   Pedir un código nuevo retira los anteriores del mismo usuario/purpose; si el
   envío falla, el código se retira antes de responder 502. El claro solo viaja
   por el correo.
3. **Anti-enumeración**: la verificación de recovery responde igual exista o no
   el email (y solo envía si existe verificado); «añadir un email que ya es de
   otra cuenta» es un éxito silencioso sin envío ni token. El login por email
   exige `email_verified_at`; un email sin verificar recibe el mismo 401
   genérico que una contraseña mala, y el username legado entra igual que
   siempre.
4. **Cierre de sesiones al rotar credenciales**: el cambio conserva la sesión
   que lo ejecuta y cierra las demás; el reset de recuperación cierra todas.
   No se tocan puertas de operación, cifrado Fernet ni carnés.
5. **Migración v0→v1 en una transacción con BEGIN explícito**: el módulo
   `sqlite3` no abre transacción implícita para DDL, así que sin BEGIN manual
   un `ALTER` quedaría aplicado aunque el resto fallara (medido en la prueba de
   rollback). Solo se añaden columnas/tabla/índices; IDs, vínculos, carnés y
   credenciales cifradas no se tocan, y un fallo deja `user_version` en 0 con
   los datos intactos y la conexión cerrada (en Windows una conexión abierta
   dejaría el fichero bloqueado). Ejecutado sobre fixtures temporales; migrar
   una base real exige respaldo ([TODO-DATA-001](../TODO.md) sigue abierto para
   el marco completo).
6. **API `4` → `5` y shell `v11` → `v12`**: se añaden cinco rutas de identidad
   (`auth/email/request`, `auth/email/verify`,
   `auth/password/recovery/request`, `auth/password/recovery/reset`,
   `auth/password/change`) y los campos `email`/`email_verified` del usuario.
   Nada existente cambia de forma; el bump sigue la convención de
   [ADR-011](#adr-011--portadas-del-panel-y-descubrimiento-bajo-demanda) y la
   UI rechaza un servidor antiguo con su aviso habitual.
7. **Alcance deliberado**: passkeys ([TODO-AUTH-003](../TODO.md)) y OIDC
   ([TODO-AUTH-004](../TODO.md)) quedaban **pendientes** en esta ADR, con sus
   pasos concretos y sin añadir dependencias sin usarlas; hoy están
   implementados y decididos en [ADR-018](#adr-018--passkeys-con-webauthn-y-google-oidc-con-joserfc).
Consecuencia: usuarios existentes siguen entrando por username; el email se
añade encima sin migrar identidades ni inventar mapeos. El correo depende de un
proveedor configurado por la persona operadora, no del proyecto.
Corrección tras revisión independiente (2026-10-10): (a) el fallo de entrega
**no** puede responder 502 solo cuando el email existe y 200 cuando no —eso
convertía una incidencia del SMTP en un oráculo de enumeración—; ahora
`auth/email/request` y `auth/password/recovery/request` retiran el código y
responden el mismo 200 genérico que un envío satisfactorio, y el detalle del
fallo queda en el servidor (regresión en
[test_identity.py](../tests/test_identity.py) con el proveedor falso bloqueado);
(b) `change_password` verificaba la contraseña actual bajo el lock y escribía
después de soltarlo, de modo que dos cambios concurrentes —o un cambio y un
reset— podían ambos verificar contra la contraseña vieja y pisarse (reproducido
con dos hilos y barrera: los dos reportaban éxito); ahora verifica y escribe en
la misma sección crítica (lock + transacción). Ambas correcciones conservan el
rate limit por ruta y el cierre de sesiones.
Alternativas descartadas: correo fijo de un proveedor embebido (secretos en el
repo), guardar los tokens en claro (un volcado de la BD los revelaría todos),
responder 404/409 distintos según exista el email (oráculo de enumeración),
devolver 502 en el fallo de entrega (oráculo durante la incidencia, corregido)
y migrar la base en varios pasos sin transacción (riesgo de base a medias).

## ADR-018 — Passkeys con `webauthn` y Google OIDC con `joserfc`

Contexto: [TODO-AUTH-003](../TODO.md) y [TODO-AUTH-004](../TODO.md) llevan a la
práctica [FR-AUTH-004](specification.md#fr-auth-004),
[FR-AUTH-005](specification.md#fr-auth-005) y la parte aplicable de
[NFR-SEC-002](specification.md#nfr-sec-002) y
[NFR-SVC-003](specification.md#nfr-svc-003), dentro de la excepción de
dependencias de [ADR-015](#adr-015--email-verificado-passkeys-y-oidc-con-librerías-mantenidas-y-tokens-hasheados).
Decisión:
1. **Librerías fijadas**: `webauthn>=2.2.0` para registro/verificación WebAuthn
   (instalado y probado con 3.0.1) y `joserfc>=1.6` para el token ID OIDC
   (instalado y probado con 1.7.5). Para OIDC se eligió `joserfc` y no
   `authlib`: en su 1.8.0 `authlib` deprecó su propio módulo `authlib.jose`
   (único componente que aquí haría falta) en favor de `joserfc`, que es
   además el motor JOSE que authlib delega; el flujo de código se implementa
   con la stdlib, así que authlib no aportaría nada más. Verificado por
   inspección el 2026-10-10 (`from authlib.jose import jwt` emite
   `AuthlibDeprecationWarning`).
2. **Esquema v2 con `auth_challenges`, `passkeys` e `identities`**: los retos
   WebAuthn y las transacciones OIDC (`state`/`nonce`/verificador PKCE) viven en
   `auth_challenges` solo como SHA-256; el detalle de OIDC va cifrado con la
   Fernet del servidor, nunca en claro. Migración v1→v2 añadiendo tablas e
   índices en la misma transacción con `BEGIN` explícito de
   [ADR-017](#adr-017--identidad-con-email-verificado-smtp-por-entorno-tokens-hasheados-y-api-v5),
   probada sobre fixtures temporales (v0→v2, v1→v2, reciente y rollback).
3. **Passkeys descubribles con UV obligatoria**: `resident_key=REQUIRED` y
   `user_verification=REQUIRED`, reto de 5 minutos de un solo uso y login sin
   `allowCredentials` para no enumerar usuarios. La ventana de reautenticación
   (`REAUTH_TTL`, 300 s) se abre con la contraseña (`POST auth/reauth`) o con
   una passkey recién usada; es lo que exigen añadir/borrar passkeys y
   vincular/desvincular Google. `code: reauth_required` en el error es el único
   campo estable del envelope.
4. **Origen no confiable rechazado en servidor**: el RP ID/origen se derivan del
   Host del pedido (nunca del body); HTTP solo se considera confiable en
   `localhost`/`127.0.0.1`, y cualquier otro host HTTP recibe 403 antes de mirar
   el cuerpo. Chromium exige además un RP ID con forma de dominio, por lo que la
   UI desactiva las passkeys sobre una IP literal y explica el motivo.
5. **Google OIDC por código con PKCE**: `state` y `nonce` de un solo uso con
   caducidad (10 min), verificación del token ID (RS256 contra el JWKS por
   descubrimiento OIDC, `iss`, `aud`, `exp`/`iat`, `nonce` y `azp` cuando hay
   varias audiencias), endpoints aceptados solo en HTTPS (o bucle para el
   proveedor falso de pruebas) y redirección 303 a `/?google=…` cuyo resultado
   publica la UI. Identidad: `(issuer, sub)`. El callback consume el estado
   **antes** de tocar el proveedor, así que un fallo no deja transacción viva.
6. **Sin merge por email, alta explícita**: el login con Google solo sirve para
   un `(issuer, sub)` ya vinculado; el alta con Google es un modo aparte
   (`signup`) que exige email verificado por el proveedor, genera una contraseña
   aleatoria que nadie conoce (fijable después por recuperación) y deriva el
   alias de forma determinista, rechazando el alta si el email ya existe.
7. **API `5` → `6` y shell `v12` → `v13`**: rutas nuevas de passkeys y Google,
   `passkeys`/`identities` en `settings`, `google` en `session` y el callback
   como única respuesta del API que no es JSON (303). Nada existente cambia de
   forma.
Consecuencia: quien quiera passkeys u OIDC debe instalar las dos dependencias
(añadidas a `pyproject.toml`, las instala `pip install -e .` y la CI); quien no
las use no configura nada y no ve botones. Google requiere credenciales OAuth
creadas por la persona (trámite humano en la consola de Google Cloud, sin APIs
de pago y sin promesa de coste, ver fuentes fechadas en
[operations](operations.md)) y nunca se versionan.
Alternativas descartadas: WebAuthn/OIDC a medida (criptografía casera),
`authlib.jose` deprecado, login con el email del token (merge implícito),
guardar el verificador PKCE o el nonce en claro, fijar el `rp.id` a `127.0.0.1`
(Chromium lo rechaza) y depender de una sesión de navegador sin reautenticación
para gestionar passkeys o identidades externas.

## ADR-019 — El flujo Google se liga al navegador y a su sesión viva

Contexto: revisión de seguridad del 2026-10-10 sobre el flujo de
[ADR-018](#adr-018--passkeys-con-webauthn-y-google-oidc-con-joserfc)
([TODO-SEC-004](../TODO.md), [FR-AUTH-005](specification.md#fr-auth-005),
[NFR-SEC-001](specification.md#nfr-sec-001),
[NFR-SEC-002](specification.md#nfr-sec-002)): el `state` solo vivía en la BD,
sin nada que lo ligara al navegador que lo inició, así que un par
`code`+`state` conseguido en el navegador del atacante podía completarse en el
de la víctima (login CSRF de OAuth: la víctima quedaría con la sesión del
atacante); y el modo `link` guardaba el `user_id` en el reto, de modo que un
logout mientras el flujo estaba pendiente no impedía escribir el vínculo.
Decisión:
1. **Cookie de enlace por flujo** (`biblio_oidc`): `google_start` genera 32
   bytes aleatorios criptográficos y los emite como cookie `HttpOnly`,
   `SameSite=Lax`, con la ruta del propio flujo (`/api/auth/google`), la misma
   caducidad que el `state` (10 min) y `Secure` cuando el servidor trabaja con
   `--secure`. En la base solo vive su SHA-256, en el mismo detalle cifrado que
   `nonce`/PKCE; el callback lo compara en tiempo constante (`compare_digest`)
   **antes** de canjear el `code`, abrir sesión o escribir un vínculo.
2. **Estado no consumido en un intento hostil**: el callback lee el reto con
   `peek_challenge` (nuevo, de solo lectura), y solo lo consume con
   `take_challenge` cuando el enlace casa. Así un callback copiado a otro
   navegador se rechaza sin ninguna llamada al proveedor **y** sin arruinar el
   flujo del navegador que sí lo inició; el consumo de un solo uso se conserva
   para los intentos legítimos.
3. **`SameSite=Lax`, no `Strict`**: la vuelta desde el proveedor es una
   navegación superior cruzada y una cookie `Strict` no viajaría. La cookie de
   sesión global sigue siendo `SameSite=Strict` y el callback **no** la lee.
4. **La vinculación exige su sesión viva, de forma atómica**: en modo `link` el
   estado guarda el SHA-256 del token de la sesión que inició el flujo (nunca el
   token). Antes de canjear el code el callback comprueba que esa sesión siga
   abierta para el mismo usuario con email verificado, para no tocar al proveedor
   de más. La **autoridad** es el gate final
   (`Handler.store_link_with_live_session`), que retiene `server.lock` —el mismo
   que usa el logout para retirar la sesión— entre esa comprobación y
   `link_identity(..., require_verified=True)`, el cual revalida existencia y
   email verificado dentro de la propia transacción que escribe. Un logout no
   puede intercalarse en la ventana comprobación→escritura: o se ordena antes
   (no se escribe nada) o después (la sesión seguía viva al escribir; el vínculo
   queda y el logout solo cierra la sesión). Corregido el 2026-10-10 tras una
   revisión independiente que señaló la ventana entre comprobación y escritura.
   Orden de locks `server.lock` → `store.lock`, sin ciclo y sin retener locks
   sobre la E/I con el proveedor.
Consecuencia: la cookie de enlace viaja solo entre `start` y el callback del
mismo navegador; quien tenga dos pestañas iniciando flujos a la vez conserva el
enlace del último `start` y el flujo anterior debe repetirse. La UI no cambia
(una cookie gestionada por el navegador), la API JSON no cambia de forma y la
versión sigue siendo `6`; lo que sí cambia es que el callback exige esa cookie.
Alternativas descartadas: dejar el enlace solo en la query del callback (legible
y transferible, el propio defecto), atar el flujo a la cookie de sesión
(`SameSite=Strict`, no viajaría en la vuelta del proveedor), exigir
reautenticación también en el callback (rompería flujos legítimos de más de
5 minutos) y confiar solo en el `state` (es exactamente lo que el atacante
obtiene en su propio navegador).

## Cómo proponer otra ADR

Añadir ID nuevo, fecha, contexto, decisión propuesta/aceptada, alternativas e
impacto en requisitos, persistencia y pruebas. No reescribir retrospectivamente
una decisión aceptada como si hubiera sido otra; enlazar su sustitución.
