# Backlog editable de BiblioCM

Única lista de tareas y estados. Base revisada: **2026-10-05**.
Requisitos: [especificación](docs/specification.md). Funcionalidades existentes:
[estado y evidencia](docs/status.md). Proceso: [SDD/TDD](docs/testing.md).

## Reglas de edición

- Mantener IDs estables; no reutilizar el ID de una tarea cerrada para otro trabajo.
- Estados: `proposed`, `pending`, `in_progress`, `blocked`, `done`, `cancelled`.
- `proposed`: mejora que necesita decidir alcance; no es una instrucción para implementarla.
- `pending`: tarea aceptada/lista para comenzar. `blocked`: indicar bloqueo y siguiente acción.
- Al empezar, asignar responsable y actualizar fecha. Un agente mantiene una tarea
  activa, salvo que un trabajo paralelo se haya encargado explícitamente.
- `done` requiere aceptación y evidencia de comprobaciones realizadas; no basta con escribir código.
- Editar estado en índice **y** ficha, y actualizar `docs/status.md` si cambia el producto.
- Prioridad P1: defecto/aceptación importante; P2: calidad/evolución necesaria;
  P3: mejora posterior. No constituye autorización de publicar/desplegar ni migrar datos reales.

## Índice

| ID | Estado | Prioridad | Trabajo |
|---|---|---|---|
| TODO-DOC-001 | done | P1 | Base documental SDD/TDD y continuidad |
| TODO-BASE-001 | done | P1 | Identidad web, carnés cifrados, permisos y panel conjunto |
| TODO-REN-001 | done | P1 | Confirmación de renovación consistente con recarga |
| TODO-RES-001 | done | P1 | Reservables estructurados y copia elegida |
| TODO-SVC-001 | done | P1 | Versión API y puerto exclusivo en Windows |
| TODO-SEC-001 | in_progress | P1 | Evitar tokens OPAC en URLs de DTOs bibliográficos |
| TODO-CAT-001 | pending | P1 | Título real al saltar a ficha única |
| TODO-CORE-001 | pending | P2 | Helper wait duplicado/inválido |
| TODO-CLI-001 | pending | P2 | Entradas vacías y ayuda de credenciales de CLI |
| TODO-TEST-001 | pending | P2 | Cobertura faltante y test ISBN no descubierto |
| TODO-UI-001 | pending | P1 | Reproducir/resolver respuestas de panel y detalle fuera de orden |
| TODO-UI-002 | done | P1 | Feedback de carga accesible en arranque, acceso y refresco |
| TODO-DATA-001 | pending | P1 | Versionar esquema y probar migración/restauración |
| TODO-PLAT-001 | pending | P1 | Instalación/offline en Android e iPhone reales |
| TODO-A11Y-001 | pending | P2 | Verificación accesible de formularios y diálogo |
| TODO-CAT-002 | pending | P1 | Navegar enlaces/offsets de páginas y detectar el final |
| TODO-TEST-002 | pending | P2 | Cobertura de navegador faltante (reservas, sesión y fallos) |
| TODO-UX-001 | done | P3 | Portadas bibliográficas reales |
| TODO-UX-003 | done | P1 | Estado de carga del panel y portadas en préstamos/reservas |
| TODO-CAT-005 | done | P1 | Caché RAM de portada en el navegador con revocación |
| TODO-AUTH-001 | done | P2 | Cambio/recuperación de contraseña BiblioCM |
| TODO-AUTH-002 | done | P1 | Email verificado con username como alias |
| TODO-AUTH-003 | done | P2 | Passkeys WebAuthn con librería mantenida |
| TODO-AUTH-004 | done | P3 | Acceso con Google (OIDC) opcional |
| TODO-LINK-001 | proposed | P2 | Compartición granular por carné |
| TODO-OPS-001 | proposed | P2 | Despliegue HTTPS reproducible |
| TODO-OPS-002 | done | P2 | Aviso de origen no local e instrucciones HTTPS (mkcert) |
| TODO-OPS-003 | done | P2 | Guía HTTPS local válida (Caddy multiline y nombre DNS de red) |
| TODO-CI-001 | in_progress | P2 | Automatización de comprobaciones en CI |
| TODO-PUB-001 | done | P1 | Licencia MIT, SECURITY.md y documentación de publicación |
| TODO-PUB-002 | done | P1 | Candidato público limpio, allowlist del escaneo y auditoría aislada |
| TODO-PRIV-001 | done | P1 | Identidad de lector e identificadores de préstamo/reserva sintéticos y reglas del escaneo |
| TODO-SEC-002 | done | P1 | Escaneo de secretos previo a publicar |
| TODO-SEC-003 | done | P1 | Orígenes de confianza para passkeys y Google |
| TODO-SEC-004 | done | P1 | Vínculo del flujo Google al navegador y a la sesión |
| TODO-SEC-005 | done | P1 | Rechazo de reautenticación sin marca con reloj monotónico joven |
| TODO-NOTIFY-001 | proposed | P3 | Recordatorios/notificaciones |
| TODO-CAT-003 | proposed | P3 | Metadatos MARC que la UI no muestra |
| TODO-CAT-004 | proposed | P3 | Facetas y disponibilidad por resultado |
| TODO-UX-002 | proposed | P3 | Metadatos de panel sin mostrar |
| TODO-PERF-001 | done | P3 | Medir y evolucionar latencia/concurrencia |
| TODO-SVC-002 | done | P1 | Desconexión del cliente y peticiones sin bloqueo global |
| TODO-API-001 | proposed | P3 | Contrato OpenAPI verificable |

## Fichas de tareas

### TODO-DOC-001 — Base documental SDD/TDD

**Estado:** `done`
**Prioridad:** P1
**Tipo:** documentación
**Responsable:** agente de documentación
**Actualizado:** 2026-10-05
**Requisitos:** NFR-DEV-001.

Aceptación: arquitectura/back/frontend/contrato descritos; implementación separada
de evidencia; backlog con plantilla/estados; entrada para agentes; enlaces/IDs/estados
validados; README sin credenciales reales ni planes obsoletos presentados como actuales.
Evidencia: revisión 2026-10-05. `python scripts/check_docs.py --tests` validó 15 documentos,
16 requisitos, 23 tareas, 147 enlaces y el recuento de 137 tests; el flag solo cuenta
tests. `python -m unittest discover -s tests -t .` ejecutó 137 tests con resultado OK.
Se validaron `--help` de CLI/servidor y de los scripts de navegador/diagnóstico.
Revisión de código y fixtures localizó gaps registrados en TODO-SEC-001,
TODO-CAT-001/002, TODO-CORE-001, TODO-CLI-001, TODO-TEST-001 y TODO-UI-001.

### TODO-BASE-001 — Identidad, vinculación y vista conjunta

**Estado:** `done`
**Prioridad:** P1
**Tipo:** funcionalidad base
**Responsable:** implementación inicial
**Actualizado:** 2026-10-05
**Requisitos:** FR-AUTH-001, FR-ACC-001, FR-LINK-001, FR-LINK-002, FR-PANEL-001.

Aceptación alcanzada para el MVP: usuarios propios, múltiples carnés, cifrado,
solicitudes/aprobación, read/manage, revocación y atribución por cuenta.
Evidencia: WebTests de [test_web.py](tests/test_web.py) y escenarios de
[navegador](scripts/check_web_browser.py). Recovery y permisos por carné no forman parte de este cierre.

### TODO-REN-001 — Fecha definitiva de renovación

**Estado:** `done`
**Prioridad:** P1
**Tipo:** regresión
**Responsable:** corrección de renovación
**Actualizado:** 2026-10-05
**Requisitos:** FR-RENEW-001.

Aceptación: adoptar POST, verificar desde login nuevo, exigir avance date/counter,
una única mutación, aviso/card/recarga coherentes.
Evidencia: 9 RenewalClientTests, test HTTP de recarga y navegador. Caso intermedio
12/10 frente a final 20/10 simulado; préstamos reales consultados sin renovar otra vez.

### TODO-RES-001 — Listado y selección de reservables

**Estado:** `done`
**Prioridad:** P1
**Tipo:** regresión
**Responsable:** corrección de reservables
**Actualizado:** 2026-10-05
**Requisitos:** FR-COPY-001, FR-RES-001.

Aceptación: filas completas, metadata pública sin row/URL, índices con huecos,
barcode reencontrado y reserva nueva verificada; todas las copias permanecen visibles.
Evidencia: [test_reservable.py](tests/test_reservable.py), WebTests, navegador y
consulta real Z-A por API. Creación de reservas verificada con simulación, no nueva reserva real.

### TODO-SVC-001 — Instancia y contrato coherentes

**Estado:** `done`
**Prioridad:** P1
**Tipo:** regresión operativa
**Responsable:** corrección del servidor
**Actualizado:** 2026-10-05
**Requisitos:** NFR-SVC-001.

Aceptación: versión API consultable/header, UI rechaza respuestas antiguas,
segundo bind en misma dirección falla en Windows y primer servidor sigue usable.
Evidencia: WebTests de versión/bind, navegador con respuesta antigua y verificación
HTTP local. Historia de duplicados en [incidents.md](docs/incidents.md).

### TODO-SEC-001 — URLs de sesión en datos bibliográficos

**Estado:** `in_progress`
**Prioridad:** P1
**Tipo:** contrato/privacidad detectado por inspección
**Responsable:** implementador de portadas
**Actualizado:** 2026-10-05
**Requisitos:** NFR-SEC-001, FR-CAT-001.

Origen: `parse_search_results` copia img.src a cover_url y la API serializa
MarcRecord sin sanitización de URLs. El fixture search_results ya contiene
un token ficticio en esa ruta. La UI no cargaba portadas, pero el campo existía
en JSON.
Alcance cerrado en esta sesión: el DTO de búsqueda entrega `cover_url` como ruta
de esta aplicación (`/api/cover?…`), la URL del proveedor solo vive en el
servidor, y cualquier valor de `cover_url`/`openurl`/`raw_marc` que contenga la
ruta de sesión del OPAC se retira antes de serializar; la portada se sirve con
autorización `read`, validación de origen/CGI/tipo/tamaño y cabeceras sin
referrer/caché del SW.
RED 2026-10-05: `python -m unittest tests.test_web.WebTests.test_search_cover_is_served_by_the_app_without_opac_tokens tests.test_web.WebTests.test_provider_urls_in_openurl_and_marc_are_dropped tests.test_web.WebTests.test_foreign_cover_urls_are_never_published tests.test_web.WebTests.test_cover_endpoint_serves_the_registered_image`
→ 9 fallos (URL con `THREADTOKEN02` publicada, `openurl`/`raw_marc` sin sanear,
404 en `/api/cover`); `python -m unittest tests.test_covers` → ImportError de
`is_portal_url`.
GREEN: mismos comandos en verde tras `without_opac_tokens`, `CoverRegistry`,
`GET /api/cover`, `is_portal_url` e `Http.get_image`; suite completa
`python -m unittest discover -s tests -t .` → 160 tests OK; navegador sin tokens
en el DOM.
Corrección tras revisión independiente 2026-10-05 (dos incumplimientos):
1. La portada se servía con `Cache-Control: private, max-age=1800`, contra la
   regla común `no-store` del API y contra no persistir datos privados en la
   caché del navegador. RED:
   `python -m unittest tests.test_web.WebTests.test_cover_endpoint_serves_the_registered_image`
   → `'private, max-age=1800' != 'no-store'`. GREEN: `respond_image` responde
   `no-store`; se mantiene la exclusión del service worker.
2. `is_portal_url` comparaba prefijo y origen sin canonicalizar la ruta:
   `/abnetopac/../…`, `%2e%2e`, `%2E%2E%2F`, doble codificación, backslash y
   `%0d%0a` pasaban la validación y llegaban a la descarga (misma autoridad,
   otra ruta del host). RED: `python -m unittest tests.test_covers` → 20 fallos
   con `hits=3` en el servidor local (sí hubo petición) y `images` no vacío.
   GREEN: `origin()` descarta userinfo, puerto malformado, backslash y
   caracteres de control; `has_unsafe_path()` examina la ruta en crudo y en
   varias capas de decodificación; `get_image`, `is_portal_url` y el handler de
   redirecciones los aplican (este último sobre la Location en crudo, porque
   `urljoin` normaliza los `..`).
Verificación tras la corrección (base de 164 tests en ese momento):
`python -m unittest discover -s tests -t .` → OK; `python scripts/check_docs.py --tests` → Docs OK;
`node --check` de app.js y sw.js → 0; `python scripts/check_web_browser.py
--channel msedge` → OK.
Segunda corrección (sonda adversarial de la revisión, 2026-10-05): la codificación
anidada `/abnetopac/%252525252e%252525252e%252525252fadmin` tardaba más de
cuatro capas en convertirse en `../` y `is_portal_url` devolvía `True`.
RED: `python -m unittest
tests.test_covers.CoverUrlValidation.test_deeply_encoded_traversal_is_rejected_without_any_request
tests.test_covers.CoverUrlValidation.test_encoding_depth_beyond_the_limit_is_rejected
tests.test_covers.HttpImageDownload.test_deeply_encoded_traversal_is_rejected_before_requesting`
→ 3 fallos (URL aceptada y servidor local alcanzado, `hits=1`).
GREEN: `path_layers()` recorre todas las capas de decodificación y devuelve
`None` si no estabiliza dentro de `MAX_PATH_DECODINGS`; `has_unsafe_path()`
comprueba cada capa (dot segments, `%2f`/`%5c`, controles) y el rechazo ocurre
antes de cualquier petición. Verificación final: `python -m unittest discover
-s tests -t .` → 167 tests OK; `check_docs.py --tests` → Docs OK; `node --check`
→ 0; navegador → OK.
Aceptación pendiente (no cerrar sin ello): revisar en el portal real que ningún
otro DTO/endpoint devuelve URLs con token; si cambia la representación de una
URL, mantener contrato y versión revisados (API, UI y caché SW). No usar tokens
reales como datos de prueba.

### TODO-CAT-001 — Ficha única con título bibliográfico

**Estado:** `pending`
**Prioridad:** P1
**Tipo:** bug detectado por inspección
**Responsable:** sin asignar
**Actualizado:** 2026-10-05
**Requisitos:** FR-CAT-001.

Origen: `record_from_document_page` usa `_first_span_text(h1)` y el detector
requiere h1 «Documento»; puede devolver ese rótulo como título.
Aceptación: fixture con h1 genérico y MARC real ficticio; RED que exige título/ID
bibliográficos; lista de un resultado correcta sin romper listas normales.
Prueba pendiente: cliente search con salto a ficha; no está cubierta por SearchResultsTest.

### TODO-CORE-001 — Una definición válida de wait

**Estado:** `pending`
**Prioridad:** P2
**Tipo:** bug detectado por inspección
**Responsable:** sin asignar
**Actualizado:** 2026-10-05
**Requisitos:** NFR-DEV-001.

Origen: helper duplicado al final de client.py; segunda definición referencia time
sin import global. No es el throttle usado por Http.
Aceptación: aclarar uso, conservar/eliminar API interna según referencias; si se
mantiene, test con sleep simulado sin espera real y sin NameError; una sola definición.
Evidencia pendiente: reproducción dirigida antes de editar, no refactor del transporte entero.

### TODO-CLI-001 — Errores y opciones de CLI coherentes

**Estado:** `pending`
**Prioridad:** P2
**Tipo:** bug/cobertura
**Responsable:** sin asignar
**Actualizado:** 2026-10-05
**Requisitos:** FR-CLI-001.

Origen: mensaje anuncia `--password-stdin` inexistente; búsqueda/reservas usan
primera cuenta de selección sin guarda de registro vacío; faltan validaciones
tempranas de parámetros por acción de reserva.
Aceptación: tests con registro temporal vacío y inputs inválidos, salida/código
legibles sin IndexError ni llamadas al portal; ayuda sin opciones inexistentes.
No implementar una nueva forma de login ni tocar el registro real para obtener verde.

### TODO-TEST-001 — Cobertura que falta en motor/CLI

**Estado:** `pending`
**Prioridad:** P2
**Tipo:** pruebas
**Responsable:** sin asignar
**Actualizado:** 2026-10-05
**Requisitos:** FR-CLI-001, FR-CAT-001, FR-RES-002, FR-AUTH-001, NFR-DEV-001.

Aceptación: descubrir la prueba ISBN suelta (el limpiador ya existe en parser),
comprobar el caso de ficha única y añadir FakeHttp para login/logout/caducidad/anulación;
tests de charset, compresión, meta-refresh, timeout y throttle sin red ni sleeps reales.
Cubrir también límite de sesiones y atomicidad: el registro actual persiste el
usuario antes de comprobar capacidad, por lo que puede responder 503 tras crearlo.
Dividir en subtareas si no cabe una sesión. No convertir funciones no descubiertas
en «cobertura» ni relajar expectativas para pasar. Dependencia parcial: TODO-CLI-001.

### TODO-UI-001 — Respuestas async de panel/detalle

**Estado:** `pending`
**Prioridad:** P1
**Tipo:** investigación/regresión
**Responsable:** sin asignar
**Actualizado:** 2026-10-05
**Requisitos:** FR-PANEL-001, FR-CAT-001, FR-COPY-001.

Origen por inspección: hay generación de sesión/búsqueda, pero no guard independiente
de respuestas library ni de aperturas sucesivas de detalle dentro de una búsqueda.
Aceptación: respuestas demoradas/reordenadas en navegador; un snapshot anterior
no sobrescribe uno nuevo y datos de ficha A no se presentan bajo título B.
Registrar primero si se reproduce; corregir localmente sin cambiar permisos ni framework.

### TODO-UI-002 — Feedback de carga accesible en arranque, acceso y refresco

**Estado:** `done`
**Prioridad:** P1
**Tipo:** funcionalidad UI / accesibilidad
**Responsable:** ORCA-implementer MiMo
**Actualizado:** 2026-10-08
**Requisitos:** FR-PANEL-001, FR-AUTH-001, NFR-DEV-001.

Origen (inspección 2026-10-08 de `index.html`, `app.js` y
[check_web_browser.py](scripts/check_web_browser.py)): `#library-loading` solo
se enciende al entrar en `loadLibrary()`, que va **después** de `loadSettings()`.
Por tanto (a) mientras se resuelve `GET session` se ve el formulario de acceso
sin ninguna señal accesible, aunque haya sesión; (b) en login, restauración y
«Actualizar» el dashboard queda visible y vacío con `aria-busy="false"` durante
toda la consulta de `settings`; (c) el indicador es una línea `muted` sin
spinner; y (d) si `settings` responde después de cerrar sesión, `api()` lanza
«La sesión ha cambiado.» y `busy()` lo publica en el aviso persistente.
Aceptación:
- Región `#boot-loading` (`role="status"`, `aria-live="polite"`, spinner +
  texto) visible mientras se resuelve `GET session` y oculta al resolver, tanto
  en éxito como en error; mientras tanto `#welcome` permanece oculto, sin
  destello del formulario de acceso.
- `#library-loading` (spinner + texto) visible con `aria-busy="true"` desde que
  empieza el ciclo `settings` + `library` de login, restauración y
  «Actualizar», no solo durante `library`.
- Retirada en éxito, error y cierre de sesión. Las cargas se adjudican con un
  token: solo la fase más reciente puede retirar el estado y una sesión
  cerrada lo invalida, de modo que una respuesta vieja no lo reanuncia.
- Una respuesta obsoleta de `settings` de una sesión cerrada no repuebla el
  panel ni publica «La sesión ha cambiado.» en el aviso.
- Si el panel nunca se resuelve (error de `session`, de `settings` o de
  `library` en el arranque), se vuelve al acceso en lugar de dejar un
  dashboard vacío.
RED previsto: escenario de navegador (ver Evidencia al cerrar).
Verificación al cerrar: `python scripts/check_docs.py --tests`,
`python -m unittest discover -s tests -t .`, `node --check` de app.js y sw.js y
`python scripts/check_web_browser.py --channel msedge`.
Dependencias: ninguna; no cierra TODO-UI-001 (respuestas de panel/detalle fuera
de orden, hoy también pendientes en búsqueda) ni TODO-TEST-002.

Evidencia: RED 2026-10-08 (baseline, antes de tocar `app.js`/`index.html`):
1. `python scripts/check_web_browser.py --channel msedge` → `AssertionError:
   Locator expected to have count '1' / Actual value: 0` en
   `expect(owner.locator("#boot-loading")).to_have_count(1)`.
2. Sondas temporales con el mismo escenario y las aserciones nuevas retiradas
   una a una (los ficheros de sonda se borraron al terminar):
   - restauración con `GET session`/`GET settings` retenidos →
     `AssertionError: Locator expected to be visible / Actual value: hidden`
     en `#library-loading` durante la fase `settings`;
   - refresco con `GET settings` retenido → idéntico fallo;
   - soltando esa respuesta tras cerrar sesión →
     `AssertionError: Locator expected not to contain text 'La sesión ha
     cambiado'`.
3. Medición adicional del enrutador: un `time.sleep` de 3 s en el enrutador
   retrasó una aserción con `timeout=500` hasta 3,54 s; por eso los escenarios
   retienen la petición en lugar de dormirla.
Evidencia: GREEN 2026-10-08:
`python scripts/check_docs.py --tests` → Docs OK: 16 documentos, 16 requisitos,
29 tareas, 186 enlaces y 182 tests; `python -m unittest discover
-s tests -t .` → 182 tests OK; `node --check` de app.js y sw.js → 0;
`python scripts/check_web_browser.py --channel msedge` → OK en dos ejecuciones
seguidas, con escritorio 1280×900 y móvil emulado 390×844 y sin errores JS.
Límites: no se verificó con el portal real ni en dispositivos físicos (siguen
TODO-SEC-001 y TODO-PLAT-001); el acceso no se destalla porque `#welcome` nace
`hidden` en el HTML, de modo que una carga del documento sin `app.js` mostraría
el `noscript` y no el formulario.

Revisión independiente (2026-10-08), misma tarea:
- Defecto: `@media(prefers-reduced-motion:reduce){.spinner{animation-duration:
  2.4s}}` **seguía animando** (más lento), y la cobertura de navegador solo
  comprobaba recuento/visibilidad del nodo, no renderizado, presencia en el
  viewport ni la CSS de movimiento reducido.
- RED auténtica sobre el árbol vigente (sin simular comportamiento antiguo):
  `python scripts/check_web_browser.py --channel msedge` → exit 1,
  `AssertionError: móvil: el spinner sigue girando con movimiento reducido
  (animation-name=spin)` en `assert_boot_rendered`. Las comprobaciones de
  `display: flex`, `animation-name: spin` con caja dibujada y containment en el
  viewport **ya eran verdes en ese mismo árbol**: cobertura adicional, no un
  fallo, y así se registra.
- Arreglo: `@media(prefers-reduced-motion:reduce){.spinner{animation:none}}`;
  la regla base (`spin .8s linear infinite`) no cambia, así que con movimiento
  normal el spinner sigue girando.
- Cobertura añadida: `assert_boot_rendered` lee `display` calculado,
  `animation-name`/`animation-duration` y la caja del spinner, exige que el
  bloque completo caiga dentro de `innerWidth`/`innerHeight` y que con
  `page.emulate_media(reduced_motion="reduce")` la rotación pase a `none` sin
  perder anillo ni texto; se ejecuta en **escritorio (owner) y móvil (viewer)
  antes de soltar la sesión retenida**. El spinner de `#library-loading` se
  comprueba igual mientras el panel anuncia la carga.
- Verificación: `python scripts/check_web_browser.py --channel msedge` → exit 0;
  `python scripts/check_docs.py --tests` → Docs OK; `python -m unittest discover
  -s tests -t .` → 182 tests OK; `node --check` de app.js y sw.js → 0.
  El shell sigue en `bibliocm-shell-v9`: el cambio de `styles.css` pertenece al
  mismo conjunto sin publicar que introdujo `v9`, así que no hay una `v9`
  antigua en circulación.

### TODO-DATA-001 — Evolución y recuperación de SQLite

**Estado:** `pending`
**Prioridad:** P1
**Tipo:** persistencia
**Responsable:** sin asignar
**Actualizado:** 2026-10-05
**Requisitos:** NFR-DATA-001.

Origen: el baseline nació con `CREATE TABLE IF NOT EXISTS` sin número de
esquema; el 2026-10-10 la identidad añadió `PRAGMA user_version` (=1) y
`Store._migrate` para la migración v0→v1 de email/tokens, con rollback
atómico sobre fixtures temporales ([TODO-AUTH-002](#todo-auth-002--email-verificado-con-username-como-alias),
[ADR-017](docs/decisions.md#adr-017--identidad-con-email-verificado-smtp-por-entorno-tokens-hasheados-y-api-v5)).
Queda abierto el marco completo: transiciones más allá de identidad,
herramienta de respaldo/restauración y reapertura probada.
Aceptación: especificar versiones y transiciones siguientes; tests de BD
antigua→nueva, reapertura, fallo/rollback y restauración con par clave/BD; no
perder credenciales/links.
Trabajar con copias/fakes y plan de migración, sin modificar datos reales durante la prueba.
Rotación de clave necesita subespecificación; no generar una clave nueva para la BD existente.

### TODO-PLAT-001 — PWA en dispositivos reales

**Estado:** `pending`
**Prioridad:** P1
**Tipo:** validación
**Responsable:** sin asignar
**Actualizado:** 2026-10-05
**Requisitos:** FR-PWA-001.

Aceptación: origen HTTPS de prueba, Android/Chrome e iPhone/Safari identificados;
instalar, abrir standalone, login, diálogo/scroll, online→offline→online, actualización
de shell y logout sin datos privados cacheados; registrar dispositivos/versiones/evidencia.
Si no hay dispositivos/origen, cambiar a blocked con recursos necesarios. Móvil
emulado en Edge no cierra esta tarea. No requiere publicar en App Store/Play Store.

### TODO-A11Y-001 — Accesibilidad verificable

**Estado:** `pending`
**Prioridad:** P2
**Tipo:** calidad UI
**Responsable:** sin asignar
**Actualizado:** 2026-10-05
**Requisitos:** FR-PWA-001.

Aceptación: recorrer formularios y secciones por teclado; abrir/cerrar diálogo,
gestionar foco, mensajes de error/status, zoom y contraste; añadir regresión de
navegador donde corresponda. Registrar lector de pantalla/manual si se verifica.
No afirmar cumplimiento WCAG completo con un test de viewport sin overflow.

### TODO-CAT-002 — Enlaces de páginas y fin de resultados

**Estado:** `pending`
**Prioridad:** P1
**Tipo:** UX/cobertura
**Responsable:** sin asignar
**Actualizado:** 2026-10-05
**Requisitos:** FR-CAT-001.

Origen: cliente usa DOC=page, pero el fixture de paginación muestra página 2
con DOC=11 y página 3 con DOC=21. Además siguiente se desactiva solo al recibir
página vacía. Tests actuales prueban routing fake, no esa navegación del cliente.
Aceptación: RED de navegación que exija los href del último HTML, con offsets
observados sin tratar DOC como número de página ni asumir un page-size eterno;
tests de primera/última/vacía/error, volver atrás sin estado incoherente y fixture
de enlaces/páginas del portal. No multiplicar consultas reales para una prueba unitaria.

### TODO-TEST-002 — Cobertura de navegador que falta

**Estado:** `pending`
**Prioridad:** P2
**Tipo:** pruebas
**Responsable:** sin asignar
**Actualizado:** 2026-10-05
**Requisitos:** FR-AUTH-001, FR-ACC-001, FR-PANEL-001, FR-RENEW-001, FR-RES-002.

Origen: auditoría de capacidades 2026-10-05 de
[check_web_browser.py](scripts/check_web_browser.py) frente al API. El escenario
cubre registro, vinculación, concesiones, panel conjunto, filtro, renovación,
catálogo/detalle, reservables y revocación en escritorio y móvil emulado; no
cubre logout en UI, pantalla y anulación de reservas, un 401 en uso que debe
volver al acceso, fallo parcial de una cuenta (`accounts[].error`), renovación
rechazada (409), resultados/ejemplares vacíos ni los botones de paginación.
Aceptación: escenarios reproducibles con fakes, servidor y BD temporales que
recorran esos caminos sin errores JS ni desbordamiento; no afirmar pruebas
dispositivos ni usar el portal real para cerrarla.
RED previsto: añadir esos escenarios al script de navegador (logout, listado y
anulación de reservas, 401 en uso, fallo parcial de una cuenta, renovación
rechazada, resultados/ejemplares vacíos y paginación); hoy no existen, así que
el primer paso es ejecutarlos y anotar qué falla en el código actual antes de
corregir. Si un escenario ya pasa, se registra como cobertura nueva y no se
fuerza un fallo artificial.
Verificación al cerrar: comando del script, resultado y lista de escenarios.
Dependencias: ninguna; no sustituye a TODO-UI-001 (respuestas fuera de orden).

### TODO-UX-001 — Portadas bibliográficas reales

**Estado:** `done`
**Prioridad:** P3
**Tipo:** funcionalidad/seguridad de UI
**Responsable:** implementador de portadas
**Actualizado:** 2026-10-05
**Requisitos:** FR-CAT-001, FR-PWA-001, NFR-SEC-001.

Alcance decidido por petición de la persona usuaria: pintar portadas del catálogo
usando los metadatos ya disponibles, sin abrir la ficha ni emitir peticiones
masivas, y sin compartir tokens OPAC. Comparte trabajo con TODO-SEC-001.
Aceptación: la API entrega `cover_url` como ruta de esta misma aplicación
(`/api/cover?account=…&record=…`) y nunca la URL del proveedor; el servidor
resuelve la URL con token del último HTML, comprueba origen, CGI, tamaño y tipo
de imagen, y devuelve bytes con `nosniff`, `Cache-Control: no-store`, sin
referrer y sin caché del service worker; la UI pinta solo esa ruta con
`loading="lazy"`, mantiene el marcador actual cuando no hay portada, retira la
imagen si falla y no escribe tokens ni URLs ajenas en el DOM; accesible (texto
alternativo vacío porque el título ya está en la tarjeta) y estable en
escritorio y móvil emulado.
Evidencia: RED 2026-10-05 con
`python -m unittest tests.test_web.WebTests.test_search_cover_is_served_by_the_app_without_opac_tokens`
(devolvía la URL con `THREADTOKEN02`) y
`python -m unittest tests.test_web.WebTests.test_cover_endpoint_serves_the_registered_image`
(404: el endpoint no existía); `python -m unittest tests.test_covers` no
importaba `is_portal_url`.
Corrección tras revisión independiente (2026-10-05): la cabecera de portada
pasó de `private, max-age=1800` a `no-store` y se cerró el traversal de ruta en
`is_portal_url`/`get_image`; RED/GREEN en TODO-SEC-001.
GREEN y verificación 2026-10-05:
`python -m unittest discover -s tests -t .` → 167 tests OK;
`python scripts/check_docs.py --tests` → Docs OK (16 documentos, 16 requisitos,
27 tareas, 177 enlaces, 167 tests); `node --check biblio/static/app.js` y
`node --check biblio/static/sw.js` → 0; `python scripts/check_web_browser.py
--channel msedge` → OK con portada cargada, rota (marcador recuperado) y URL de
proveedor sin pintar, en móvil emulado y escritorio, sin errores JS.
Límite: no se afirma funcionamiento con el portal real ni en dispositivos
físicos (sigue TODO-PLAT-001); al ser `no-store`, cada render nuevo vuelve a
pedir la portada al servidor, dentro del ritmo de una petición por segundo.

### TODO-UX-003 — Estado de carga del panel y portadas en préstamos/reservas

**Estado:** `done`
**Prioridad:** P1
**Tipo:** funcionalidad/UI + diagnóstico de portadas
**Responsable:** implementador de panel y portadas
**Actualizado:** 2026-10-07
**Requisitos:** FR-PANEL-001, FR-CAT-001, FR-PWA-001, NFR-SEC-001.

Origen (inspección de código, fixtures y snapshot de portal guardado en
`.playwright-mcp/`, directorio ignorado):
1. No existe estado de carga del panel. `loadLibrary()` no anuncia nada mientras
   consulta `GET library`, así que tras login, restauración de sesión y
   «Actualizar» el panel aparece vacío sin señal accesible; y si la petición
   falla, si se cierra sesión con la respuesta en vuelo o si esa respuesta
   pertenece a una sesión anterior, no hay estado que retirar ni regla que lo
   impida reaparecer.
2. Portadas de catálogo ausentes: (a) con un único resultado el portal salta a
   la ficha (`h1 «Documento»`) y `record_from_document_page` no lee la portada
   que esa ficha sí trae (`<img alt="Cubierta">` dentro de un enlace
   `…?ACC=294&DOC=1&MLKOB=…`, observado en el snapshot real de 2026-10-02), así
   que `cover_url` queda vacía; (b) `GET /api/cover` solo servía lo que una
   búsqueda hubiera registrado hacía menos de 600 s (máx. 200 entradas, se vacía
   al reiniciar), y al no encontrarlo devolvía 404, que la UI interpreta como
   «sin portada» y borra la imagen; (c) en la lista, la portada se tomaba como
   *primer* `<img>` de la tarjeta, no como la imagen de portada.
3. Préstamos y reservas no pintan portada: el DTO de préstamo ni siquiera lleva
   identidad bibliográfica (`record_id` aparece en el `href?TITN=` del título),
   y ningún DTO de panel lleva `cover_url`.

Aceptación:
- `#library-loading` existe con `role="status"`/`aria-live`, se anuncia durante
  la carga del panel (login, restauración con recarga y «Actualizar») y queda
  retirado al terminar: éxito, error, cierre de sesión y respuestas obsoletas de
  otra sesión no lo dejan visible ni lo vuelven a mostrar; `#dashboard` lleva
  `aria-busy` solo mientras carga.
- `Loan` expone `record_id` leído del enlace de ficha (vacío si el portal no lo
  da; nunca se deduce del título) y la API entrega `cover_url` como
  `/api/cover?account=…&record=…` en préstamos y reservas cuando `record_id` es
  numérico, sin tokens ni URL del proveedor.
- La portada de la ficha única se lee con la misma regla que la de la lista y se
  resuelve contra la última respuesta del cliente.
- `GET /api/cover` descubre bajo demanda la portada de una ficha desconocida
  abriendo `?TITN=` **una sola vez** por cuenta/registro y TTL, y recuerda
  también la ausencia para no repetir la petición; sigue autorizando lectura
  antes de tocar el registro, revalidando origen/CGI/tipo/tamaño y sin emitir
  token. El panel no lanza peticiones de ficha por su cuenta (sin prefetch
  masivo): solo el navegador pide la portada de lo que pinta, con
  `loading="lazy"`.
- La UI pinta la portada de préstamo/reserva con la misma regla `COVER_URL`,
  marcador de letra de respaldo, retiro en error y `alt=""`.
- API `4` y shell `bibliocm-shell-v8` revisados juntos (contrato + assets).

RED previsto/observado: ver «Evidencia» al cerrar.
Verificación al cerrar: `python scripts/check_docs.py --tests`,
`python -m unittest discover -s tests -t .`, `node --check` de app.js y sw.js y
`python scripts/check_web_browser.py --channel msedge` (escritorio y móvil
emulado), con recuento de tests actualizado en `docs/status.md`.
Dependencias: ninguna; comparte TODO-UX-001/TODO-SEC-001 (mecanismo de portada)
y no cierra TODO-CAT-001 (título de la ficha única) ni TODO-TEST-002.

Evidencia: 2026-10-07. RED de motor/API:
`python -m unittest tests.test_parser.LoansTest.test_identidad_bibliografica_del_prestamo
tests.test_parser.LoansTest.test_prestamo_sin_enlace_de_ficha_no_inventa_un_registro
tests.test_covers.SearchResolvesTheCoverUrl.test_the_cover_is_not_replaced_by_an_earlier_image
tests.test_covers.DocumentPageCover tests.test_covers.RecordCoverDiscovery`
→ 8 tests, `FAILED (failures=2, errors=5)`: `Loan` sin `record_id` (los dos tests
de préstamo fallan con `AttributeError`/TypeError dentro del cliente falso),
`cover_url` de la ficha única vacía y el icono de la tarjeta tomado como portada
(`/biblio_publicas/css/icono.gif` en lugar de `…?MLKOB=…`), `record_cover_url`
inexistente.
`python -m unittest tests.test_web.WebTests.test_library_dto_attributes_covers_by_account_and_record
tests.test_web.WebTests.test_cover_is_discovered_from_the_record_page_when_it_is_not_registered
tests.test_web.WebTests.test_a_record_without_cover_is_remembered_instead_of_refetched
tests.test_web.WebTests.test_api_version_is_available_before_login_and_on_errors`
→ 5 tests, `FAILED (failures=3, errors=1)`: `loans` vacío por `record_id`
desconocido, `404` en el descubrimiento, ausencia no memorizada y API aún `3`.

RED de navegador (mismo escenario, comportamiento previo simulado quitando el
anuncio y el `cover_url`): `expect(viewer.locator("#library-loading")).to_be_visible()`
→ `AssertionError: Locator expected to be visible … unexpected value "hidden"`;
`expect(viewer.locator("#loan-list .book-cover img")).to_have_count(1)` →
`unexpected value "0"`.

Causa de las omisiones de portada del catálogo (diagnóstico 2026-10-07, con
snapshot real de portal en `.playwright-mcp/`): la ficha única sí trae portada
`<img alt="Cubierta">` dentro de `…?ACC=294&DOC=1&MLKOB=…` y no se leía;
`GET cover` solo servía lo registrado en los últimos 600 s y devolvía 404 que la
UI borraba; la lista tomaba el primer `<img>` de la tarjeta; y los préstamos no
traían identidad bibliográfica.

GREEN 2026-10-07:
`python -m unittest discover -s tests -t .` → **179 tests OK** (base previa 167);
`python scripts/check_docs.py --tests` → **Docs OK: 16 documentos, 16 requisitos,
28 tareas, 180 enlaces; 179 tests**;
`node --check biblio/static/app.js` y `node --check biblio/static/sw.js` → **0**;
`python scripts/check_web_browser.py --channel msedge` → **OK** con escritorio
1280×900 y móvil emulado 390×844, sin errores JS ni desbordamiento: estado de
carga en recarga/error/logout con respuesta en vuelo, portada de catálogo,
préstamo y reserva servidas, rota con marcador recuperado y URL de proveedor sin
pintar.

Límites: no se verificó con el portal real ni en dispositivos físicos (siguen
TODO-SEC-001 y TODO-PLAT-001); cada portada desconocida cuesta una apertura de
ficha memorizada (TTL 600 s, máx. 200 entradas), y las fichas que el portal no
ilustra siguen sin portada; el título de la ficha única sigue en TODO-CAT-001 y
la ausencia de logout/401/anulación en el escenario sigue en TODO-TEST-002.

### TODO-PERF-001 — Latencia y concurrencia

**Estado:** `done`
**Prioridad:** P3
**Tipo:** arquitectura/rendimiento
**Responsable:** ORCA-implementer MiMo
**Actualizado:** 2026-10-08
**Requisitos:** NFR-SVC-001, FR-CAT-001, NFR-SEC-001.

Alcance acordado el 2026-10-08 por la petición de la persona usuaria: medir la
latencia de `GET cover` y la latencia que impone serializar sus descargas, y
optimizar solo lo que la medición evidencie. Origen por inspección: la descarga
de portada ocurre bajo el lock global del store, así que mientras trae una
imagen todas las demás peticiones autenticadas esperan; solo se memoriza la URL
del proveedor, no los bytes, y como el navegador la recibe con `no-store`, cada
render vuelve a pedir la portada y el servidor vuelve a descargarla del portal.
Aceptación:
- Evidencia antes/después con contadores de peticiones al portal y con latencia
  medida usando un cliente falso con latencia artificial (sin portal real): el
  mismo `GET cover` repetido pasa de N descargas a 1, y la segunda respuesta se
  sirve de memoria sin pagar la latencia del portal.
- Evidencia de serialización: mientras una descarga de portada está en vuelo,
  otra petición autenticada espera; una respuesta servida desde memoria no
  espera. Se mide también la serialización JSON del payload real para poder
  afirmar que no es el cuello de botella.
- Caché de bytes acotada (entradas y tamaño) con el mismo TTL que la URL,
  solo en memoria, nunca persistida, y **siempre** después de autorizar lectura
  de la cuenta: una concesión revocada, un tercero ajeno o una sesión sin
  permiso reciben 403 aunque los bytes estén memorizados, sin llegar al portal.
- No se mueve E/I fuera del lock ni se altera la autorización, la revocación,
  la fecha definitiva de renovación ni el ritmo del portal: sin evidencia de
  semántica de concurrencia demostrada, el lock se conserva tal cual.
- Sin cachear sesiones ni credenciales viejas para eliminar la comprobación
  fresca.
RED previsto: ver Evidencia al cerrar.
Verificación al cerrar: `python scripts/check_docs.py --tests`,
`python -m unittest discover -s tests -t .`, `node --check` de app.js y sw.js y
`python scripts/check_web_browser.py --channel msedge`.
Dependencias: ninguna. No autoriza a publicar, desplegar ni migrar datos.

Evidencia: RED 2026-10-08 (baseline, cliente falso con latencia artificial de
0,3 s por petición, sin portal real):
1. `python -m unittest tests.test_web.WebTests.test_repeated_cover_requests_hit_the_portal_only_once
   tests.test_web.WebTests.test_cover_download_serializes_other_requests_until_it_is_cached
   tests.test_web.WebTests.test_cover_memory_cache_is_never_served_without_read_authorization`
   → `FAILED (failures=2)`: `descargas redundantes al portal: 3` y
   `la portada memorizada sigue pagando el portal: 0.302s`.
2. El tercer test (autorización sobre la memoria) ya era verde en el baseline:
   es la guarda que debía seguirlo siendo después del arreglo.
Ajuste de una expectativa, no un debilitamiento:
`test_cover_rejects_non_image_content_types` pedía 200 y después 502 **para la
misma ficha**; con la memoria de bytes esa segunda respuesta ya no vuelve al
portal. Se conservan ambas partes usando una ficha distinta (`record=777`) para
el 502 y se comprueba además que el fallo no se memoriza (dos 502 seguidos); el
camino 200 sigue cubierto por `test_cover_endpoint_serves_the_registered_image`.
Evidencia: GREEN 2026-10-08:
`python -m unittest discover -s tests -t .` → **182 tests OK**;
`python scripts/check_docs.py --tests` → Docs OK: 16 documentos, 16 requisitos,
29 tareas, 186 enlaces y 182 tests; `node --check` de app.js y
sw.js → 0; `python scripts/check_web_browser.py --channel msedge` → OK en dos
ejecuciones seguidas.
Medición antes/después con el mismo harness (latencia artificial 0,3 s):
`GET cover` repetido de **3 descargas / 0,302 s** → **1 descarga / 0,001 s** de
memoria (la primera petición cuesta 0,603 s: descubrimiento + descarga);
serialización JSON del payload real de `library` (1568 bytes) **~8 µs**, unas
37.000 veces menos que una descarga; una portada nueva en vuelo sigue
serializando el resto del API (**0,297 s de espera** en `/api/settings`).
Decisión registrada en [ADR-012](docs/decisions.md).
Límites: no se midió contra el portal real ni con carga concurrente real; el
lock del store **no se movió**, así que la primera petición de cada portada
nueva sigue bloqueando el resto del API durante su latencia. Sacar la E/I de ese
lock exige demostrar la semántica de concurrencia con revocación y operaciones,
que sigue sin probarse; esa es la acción siguiente si la latencia agregada
llega a importar.
Sustitución 2026-10-09: la prueba
`test_cover_download_serializes_other_requests_until_it_is_cached` recogía el
comportamiento de espera y fue reescrita por
[TODO-SVC-002](#todo-svc-002--desconexión-del-cliente-y-peticiones-sin-bloqueo-global)
(`test_slow_cover_download_does_not_block_unrelated_requests`); la medición de
descargas/latencia de arriba se conserva como evidencia histórica de ese cierre.

### TODO-SVC-002 — Desconexión del cliente y peticiones sin bloqueo global

**Estado:** `done`
**Prioridad:** P1
**Tipo:** bug/concurrencia detectados por inspección
**Responsable:** ORCA-implementer MiMo
**Actualizado:** 2026-10-09
**Requisitos:** NFR-SVC-002, FR-LINK-002, NFR-SEC-001, NFR-SVC-001, FR-RENEW-001.

Origen por inspección de `biblio/web.py` (2026-10-09), dos defectos:
1. *Desconexión:* `respond`/`respond_image` escriben cabeceras y cuerpo sin
   proteger el socket. Si el cliente se desconecta al escribir la portada, la
   `OSError` llega al `except Exception` de `api()`, que intenta un **segundo**
   `respond(502)` sobre una conexión que ya envió un `200`; ese segundo
   intento vuelve a fallar y la excepción sale del handler hacia
   `socketserver.handle_error` (traceback en stderr por petición desconectada).
2. *Bloqueo:* `dispatch` envuelve toda la operación en `store.lock` y en
   `session["lock"]`, de modo que una renovación o una descarga de portada
   lentas bloquean peticiones sin relación (medido en TODO-PERF-001:
   `/api/settings` esperó 0,297 s). El lock global existía para que la
   revocación esperase a la operación en curso (FR-LINK-002), así que
   sustituirlo exige conservar esa semántica de forma explícita.

Aceptación (NFR-SVC-002): fallo de escritura de cabecera/cuerpo ⇒ una sola
respuesta intentada, conexión cerrada, sin excepción fuera del handler y sin
segundo 502 tras un 200 de portada; con cliente conectado los errores reales
siguen dando 400/403/409/422/502; una operación lenta de portal no bloquea
otra ruta del mismo usuario ni las peticiones de otro usuario; la revocación y
la bajada de permiso esperan a la operación en curso del titular del permiso y
se aplican antes de las siguientes; autorización antes de descifrar y `read`
sin mutación intactos.
RED previsto: pruebas con Event/barrera para concurrencia y con `wfile` falso
para fallos de escritura/cabecera (ver Evidencia al cerrar).
Verificación al cerrar: `python scripts/check_docs.py --tests`,
`python -m unittest discover -s tests -t .`, `node --check` de app.js y sw.js.
Dependencias: ninguna; no cierra TODO-PERF-001 (medición histórica) ni
TODO-SEC-001.

Evidencia: RED 2026-10-09 (baseline, antes de tocar `web.py`/`store.py`):
1. `python -m unittest tests.test_web.WebTests.test_disconnect_while_writing_an_image_is_not_answered_twice tests.test_web.WebTests.test_header_write_failure_closes_without_a_second_response`
   → `FAILED (failures=1, errors=1)`: `Lists differ: [200, 502] != [200]` (la
   misma conexión recibió `HTTP/1.1 200 OK` de portada y después
   `HTTP/1.1 502 Bad Gateway`) y `BrokenPipeError` propagándose fuera de `api()`
   por el `except Exception` que intentaba el 502.
2. Reproducción local real:
   `python -m unittest tests.test_web.WebTests.test_client_reset_during_a_cover_response_leaves_the_server_usable`
   → FAIL: el cliente cierra con RST (`SO_LINGER=0`) mientras la descarga
   estaba retenida y stderr recibe `ConnectionResetError [WinError 10054]` al
   escribir las cabeceras del 200 **y otra** al intentar el 502, con traceback
   de `socketserver.handle_error`.
3. Concurrencia:
   `python -m unittest tests.test_web.WebTests.test_slow_cover_download_does_not_block_unrelated_requests tests.test_web.WebTests.test_slow_renew_does_not_block_unrelated_requests tests.test_web.WebTests.test_slow_operation_of_one_user_does_not_block_another_user`
   → 3 fallos: `/api/settings esperó a la descarga de otra ruta`,
   `/api/settings esperó a la renovación en curso` y `/api/settings de otro
   usuario esperó la operación de otro`.
4. Ya verdes en el baseline (guardas, no RED): los dos tests de espera de
   revocación/bajada (el lock global daba esa orden) y
   `test_real_errors_keep_their_status_for_a_connected_client`.

GREEN 2026-10-09:
- Mismos 9 tests dirigidos → `OK` (7,4 s): escritura/cabecera con `wfile`
  falso, errores reales con cliente conectado, RST real, portada y renovación
  sin bloquear otra ruta ni a otro usuario, y espera de revocación/bajada.
- Mutación sobre el arreglo (prueba de que las guardas protegen FR-LINK-002):
  con `exclusive=False` en `links/decide`, los dos tests de espera fallan con
  `la acción «revoke»/«permission» no esperó a la operación en curso`;
  revertido a `exclusive=target is not None`.
- `python -m unittest discover -s tests -t .` → **190 tests OK** (base 182;
  `tests.test_web` pasa de 45 a 53).
- `python scripts/check_docs.py --tests` → Docs OK: 16 documentos,
  17 requisitos, 30 tareas, 203 enlaces y 190 tests; `node --check` de app.js y
  sw.js → 0.
- Ajuste de expectativa, no debilitamiento: la prueba
  `test_cover_download_serializes_other_requests_until_it_is_cached` codificaba
  el bloqueo que NFR-SVC-002 ahora prohíbe; se reescribió como
  `test_slow_cover_download_does_not_block_unrelated_requests` conservando la
  comprobación de descarga única y de servicio desde memoria.
Revisión independiente (2026-10-09), misma tarea — corrección aceptada:
- Defecto: con solo la puerta de usuario, una operación que ya había pasado
  `store.access` y descifrado credenciales podía terminar **después** de que el
  titular ejecutara `accounts/delete` o `accounts/update` —incluso una
  renovación, que muta el portal—, y la línea de límites de esta ficha afirmaba
  sin prueba que eso «fallaba cerrado»: con la foto ya tomada no falla, termina.
- RED auténtico sobre el árbol vigente:
  `python -m unittest tests.test_web.WebTests.test_account_delete_waits_for_the_operation_in_course tests.test_web.WebTests.test_account_update_waits_and_later_operations_use_the_new_credentials`
  → `FAILED (failures=2)`: `accounts/delete no esperó a la operación en curso
  de esa cuenta` y `accounts/update no esperó…`, ambos con la renovación aún
  retenida. Tercer caso de la misma carrera encontrado al inspeccionar la
  normalización de claves:
  `python -m unittest tests.test_web.WebTests.test_delete_waits_for_an_operation_started_with_a_padded_account_id`
  → `delete con id limpio no esperó a la operación con id con espacios` (la
  clave de puerta sin recortar no coincidía con la de `store.text`).
- Arreglo: segunda colección de puertas (`account_gate`) con clave de cuenta
  recortada igual que `store.text`; autorizar, descifrar y operar con el portal
  ocurren dentro de la puerta compartida de esa cuenta (cover, search, copies,
  reservable, renew, reserve, cancel y `library` una cuenta cada vez), y
  `accounts/delete`/`accounts/update` entran en **exclusivo** sobre ella.
  Orden de adquisición sesión → puerta de usuario → puerta de cuenta → store;
  ninguna ruta mantiene dos puertas de cuenta a la vez, así que no hay ciclo.
- Verificación: los 4 tests de puerta de cuenta → `OK`;
  `python -m unittest discover -s tests -t .` → **194 tests OK** (base 182);
  mutación con la puerta de cuenta desactivada → delete/update vuelven a
  fallar con el mismo mensaje mientras el test de otra cuenta sigue en verde;
  `python scripts/check_docs.py --tests` → Docs OK; `node --check` de app.js y
  sw.js → 0. La guarda `test_slow_operation_on_one_account_does_not_block_another_account`
  (cuenta A retenida, cuenta B responde) ya era verde antes y después: la
  puerta es por cuenta y no reintroduce bloqueo global.

Límites: sin carga real, sin portal real y sin escenario de navegador (el
cambio es de servidor/API y no altera contrato ni assets: matriz de
[testing](docs/testing.md)); las puertas viven en RAM, una por clave vista, y
no se borran al desvincular porque podría haber hilos esperando; una operación
ya autorizada puede terminar tras un logout, aunque una petición posterior con
la sesión cerrada sigue dando 401; `library` conserva la puerta de una cuenta
mientras consulta su portal, de modo que las cuentas de un mismo panel se
consultan secuencialmente (como antes, pero ya no bloquean al resto del API).

Ampliación de aceptación (2026-10-09): renovación con progreso accesible
([FR-RENEW-001](docs/specification.md#fr-renew-001)).
Aceptación: mientras el POST de renovación sigue en vuelo, el botón queda
`disabled` (sin doble clic) con `aria-busy="true"` y texto «Renovando…», y esa
misma frase se anuncia en `#notice` (`role="status"`); un segundo intento del
usuario no envía otro POST, la operación sigue siendo un único envío, no hay
retries ni timeout propio que inventar (si la conexión cae, se informa del
error y la mutación no se reintenta); el aviso de éxito solo se publica
después de refrescar el panel y encontrar el mismo ejemplar de la misma cuenta.
Sin cambio de contrato: la API sigue en `4`; el shell sube de
`bibliocm-shell-v9` a `bibliocm-shell-v10` por tocar `app.js`/`sw.js`.
RED 2026-10-09 (escenario nuevo con `app.js` sin cambios):
`python scripts/check_web_browser.py --channel msedge` → exit 1,
`AssertionError: Locator expected to have attribute 'true' / Actual value:
None` sobre `#loan-list button` con la renovación retenida, resuelto a
`<button disabled type="button">Renovar préstamo →</button>`: la guarda de
doble clic (`disabled` de `busy`) **ya existía y se verificó**, pero no había
progreso accesible mientras esperaba.
GREEN 2026-10-09: `node --check` de app.js y sw.js → 0;
`python scripts/check_web_browser.py --channel msedge` → exit 0 con la
renovación retenida en **móvil y escritorio** (botón bloqueado + `aria-busy` +
«Renovando…» + aviso en la región viva; `len(hits)==1` tras un segundo intento
con `click(force=True)`; «… renovado …» y la fecha nueva solo después de soltar
la respuesta y refrescar el panel) y sin errores JS;
`python scripts/check_docs.py --tests` → Docs OK; suite unittest → 194 tests OK.
Archivos: [app.js](biblio/static/app.js) (`busy`, `action` con
`data-pending-text` y la llamada de renovación), [sw.js](biblio/static/sw.js)
(cache `v10`) y [check_web_browser.py](scripts/check_web_browser.py)
(bloques retenidos de móvil y escritorio).

### TODO-AUTH-001 — Recovery y cambio de contraseña de app

**Estado:** `done`
**Prioridad:** P2
**Tipo:** producto
**Responsable:** ORCA-implementer MiMo
**Actualizado:** 2026-10-10
**Requisitos:** [FR-AUTH-003](docs/specification.md#fr-auth-003), [NFR-SEC-002](docs/specification.md#nfr-sec-002).

Aprobado el 2026-10-10 por la persona usuaria; alcance fijado en la
especificación y decidido en [ADR-015](docs/decisions.md#adr-015--email-verificado-passkeys-y-oidc-con-librerías-mantenidas-y-tokens-hasheados)
y [ADR-017](docs/decisions.md#adr-017--identidad-con-email-verificado-smtp-por-entorno-tokens-hasheados-y-api-v5).
Decisión de identidad de recuperación ya tomada: el email verificado
([TODO-AUTH-002](#todo-auth-002--email-verificado-con-username-como-alias)).
Aceptación: cambio con contraseña actual y nueva distinta, invalidando las
demás sesiones y sin tocar clave Fernet ni credenciales OPAC; recovery por email
con respuesta genérica sin enumeración, token de un solo uso, caducidad y hash
en base de datos, que al usarse fija la contraseña y cierra todas las sesiones;
CSRF + JSON + Origin y rate limit propio en ambas rutas.
Verificación al cerrar: `python scripts/check_docs.py --tests`,
`python -m unittest discover -s tests -t .`, `node --check` de app.js y sw.js y
`python scripts/check_web_browser.py --channel msedge`.
Dependencias: [TODO-AUTH-002](#todo-auth-002--email-verificado-con-username-como-alias)
implementado en la misma sesión; el esquema se migró con rollback atómico sobre
fixtures temporales ([TODO-DATA-001](#todo-data-001--evolución-y-recuperación-de-sqlite)
sigue abierto para el marco completo). No se debilitaron las puertas de
[ADR-013](docs/decisions.md#adr-013--puerta-de-operaciones-ei-fuera-del-lock-global-y-escrituras-protegidas).

Evidencia: RED 2026-10-10 (baseline, antes de tocar `store.py`/`web.py`):
`python -m unittest tests.test_identity` → `ImportError: cannot import name
'mailer' from 'biblio'` (el módulo ni las rutas existían).
GREEN 2026-10-10:
- `Store.change_password` (contraseña actual + nueva distinta + sal nueva) y
  `Store.reset_token`/`reset_password` (código de un solo uso con caducidad de
  1 h, hash SHA-256 en `identity_tokens`, consumo que borra la fila);
  `AppServer.close_user_sessions` cierra las demás sesiones en el cambio y
  todas en el reset, sin tocar Fernet, carnés ni vínculos (verificado abriendo
  la BD con una `Store` nueva y descifrando credenciales).
- Rutas `auth/password/change` (sesión + CSRF + límite «change») y
  `auth/password/recovery/request`/`reset` (públicas con límite «recovery»;
  respuesta idéntica exista o no el email; 503 global sin SMTP para no crear
  un oráculo; 502 con el código retirado si el envío falla).
- UI: `#recovery` en dos pasos y `#password-form` en Configuración.
- `python -m unittest tests.test_identity.PasswordChangeTests tests.test_identity.RecoveryTests`
  → 9 tests OK; suite completa → **232 tests OK**; navegador con el flujo
  completo de cambio y recuperación sobre el correo falso → exit 0.
Límites: sin 2FA; el SMTP real no se probó (solo el falso local); recovery
exige email verificado previo; una operación ya autorizada puede terminar tras
el cierre de sesión (petición posterior da 401), como en el logout normal.

Corrección tras revisión independiente (2026-10-10, INC-006):
- *Oráculo de enumeración durante fallo de correo*: el `502` de
  `auth/password/recovery/request` solo aparecía cuando el email existía
  verificado (el inexistente devolvía 200). RED:
  `python -m unittest tests.test_identity.RecoveryTests.test_delivery_failure_is_not_an_oracle_for_recovery`
  → `AssertionError: 502 != 200`. GREEN: el fallo de entrega retira el código y
  responde el mismo 200 genérico; la prueba exige además que no quede ningún
  token vivo.
- *Carrera cambio/reset*: `change_password` verificaba bajo el lock y escribía
  después de soltarlo. RED:
  `python -m unittest tests.test_identity.PasswordMutationRaceTests.test_concurrent_changes_cannot_both_verify_the_old_password`
  → `AssertionError: 2 != 1` (ambos cambios verificaron contra la contraseña
  vieja). GREEN: verificación y escritura en la misma sección crítica; exactamente
  un cambio gana y el login coincide con el ganador. También cobertura de
  cambio+reset concurrentes dejando una sola contraseña coherente.
- Verificación: `tests.test_identity` → 29 tests OK; suite completa → **236
  tests OK**; `check_docs.py --tests` → Docs OK; `node --check` → 0;
  navegador → exit 0 (los flujos sanos no cambian de respuesta). El rate limit
  por ruta y el cierre de sesiones quedan intactos y cubiertos.

### TODO-CAT-005 — Caché RAM de portada en el navegador con revocación

**Estado:** `done`
**Prioridad:** P1
**Tipo:** funcionalidad/UI + privacidad
**Responsable:** ORCA-implementer MiMo
**Actualizado:** 2026-10-10
**Requisitos:** [FR-CAT-001](docs/specification.md#fr-cat-001),
[NFR-SEC-001](docs/specification.md#nfr-sec-001).

Origen: cada render de portada volvía a pedir `GET /api/cover` (la respuesta
lleva `Cache-Control: no-store`, decisión de [ADR-010](docs/decisions.md#adr-010--portadas-servidas-por-la-propia-aplicación)),
de modo que cambiar de vista o refrescar el panel re-descargaba imágenes ya
mostradas. Aceptación: las portadas servidas se memorizan en el navegador como
blob URL en un Map de memoria, con tope de 60 entradas y expulsión FIFO; toda
entrada se invalida con `URL.revokeObjectURL` al cerrar sesión, al recargar o
cerrar la pestaña y cuando cambia o desaparece el permiso o la cuenta que
autoriza esa portada; nada se persiste (ni CacheStorage, ni localStorage, ni
IndexedDB) y el service worker sigue sin interceptar `/api/cover`.
RED previsto: escenario de navegador (ver Evidencia).
Verificación al cerrar: `python scripts/check_docs.py --tests`,
`python -m unittest discover -s tests -t .`, `node --check` de app.js y sw.js y
`python scripts/check_web_browser.py --channel msedge`.
Dependencias: ninguna; no cierra [TODO-UX-001](#todo-ux-001--portadas-bibliográficas-reales)
ni [TODO-SEC-001](#todo-sec-001--urls-de-sesión-en-datos-bibliográficos).

Evidencia: RED 2026-10-10 (baseline, antes de tocar `app.js`/`web.py`):
1. `python scripts/check_web_browser.py --channel msedge` → exit 1,
   `AssertionError: Locator expected to have count '1' / Actual value: 0` sobre
   `#loan-list .book-cover img`.
2. Causa encontrada con una sonda de navegador (fetch manual de la portada):
   `GET /api/cover` respondía **200** con `image/png` y 69 bytes, pero el
   navegador bloqueaba la imagen con
   `Content Security Policy directive: "img-src 'self'"` y la petición del blob
   terminaba con `failure=csp`. El fallo no era del servidor ni de la caché: el
   CSP del shell no admitía blob URLs.
3. RED de API sobre el árbol vigente:
   `python -m unittest tests.test_web.WebTests.test_static_assets_and_traversal`
   → FAIL: `'self' != 'self' blob:` al extraer el directorio `img-src`.
GREEN 2026-10-10:
- `coverCache`/`coverPending`/`coverFetch`/`revokeCovers` en
  [app.js](biblio/static/app.js): blob URL por ruta, tope 60 con expulsión FIFO,
  una sola petición por ruta pendiente, descarga con `credentials:'same-origin'`
  y `cache:'no-store'`, y `revokeObjectURL` en cada invalidación. Una descarga
  en vuelo pertenece a la generación de la caché: si se invalida antes de
  resolver, su blob se revoca y no se guarda.
- Invalidación en los tres puntos exigidos: `showSession(false)` (logout),
  `pagehide` (recarga/cierre) y `syncAccounts` cuando cambia o desaparece el
  permiso o la cuenta de esa portada.
- CSP del shell en [web.py](biblio/web.py): `img-src 'self'` →
  `img-src 'self' blob:`, con test que extrae el directorio y exige exactamente
  `'self' blob:` (sin `data:`, sin orígenes ajenos). Decisión registrada en
  [ADR-014](docs/decisions.md#adr-014--caché-de-portada-en-ram-del-navegador-con-invalidación-por-blob-url)
  y sustitución parcial anotada en
  [ADR-010](docs/decisions.md#adr-010--portadas-servidas-por-la-propia-aplicación).
- Shell `bibliocm-shell-v10` → `v11` en [sw.js](biblio/static/sw.js); la API
  **sigue en `4`** (rutas, DTOs y estados sin cambio).
- Escenario de navegador ampliado: instrumentación de `createObjectURL`/
  `revokeObjectURL` por `add_init_script` (sin hooks de depuración en app.js),
  aserción de que la portada de reserva reutiliza la blob URL del préstamo, de
  que re-renderizar no crea otra, de que nada se persiste en
  CacheStorage/localStorage/sessionStorage, de revocación tras `pagehide`, tras
  logout y al retirar el acceso (la portada de la cuenta revocada se revoca y la
  de la propia cuenta no), y de portada rota en una ficha **todavía no
  cacheada** (la ruta ya cacheada sirve desde memoria, que es el comportamiento
  deseado).
- `python -m unittest discover -s tests -t .` → **207 tests OK** (base 194;
  `tests.test_release_scan` añade 13);
  `python scripts/check_docs.py --tests` → Docs OK; `node --check` de app.js y
  sw.js → 0; `python scripts/check_web_browser.py --channel msedge` → exit 0.
Límites: el portal real no se probó con la caché (sigue TODO-SEC-001); la
revocación al cerrar la pestaña se verifica disparando `pagehide` de forma
sintética, porque una descarga real no es observable desde el propio documento
(las blob URLs mueren con él de todos modos); el aviso de origen no confiable se
probó forzando `isSecureContext`, no con un host de red local real.

### TODO-AUTH-002 — Email verificado con username como alias

**Estado:** `done`
**Prioridad:** P1
**Tipo:** producto/identidad
**Responsable:** ORCA-implementer MiMo
**Actualizado:** 2026-10-10
**Requisitos:** [FR-AUTH-002](docs/specification.md#fr-auth-002),
[NFR-SEC-002](docs/specification.md#nfr-sec-002).

Aprobado el 2026-10-10 por la persona usuaria; alcance fijado en la
especificación y decidido en [ADR-015](docs/decisions.md#adr-015--email-verificado-passkeys-y-oidc-con-librerías-mantenidas-y-tokens-hasheados)
y [ADR-017](docs/decisions.md#adr-017--identidad-con-email-verificado-smtp-por-entorno-tokens-hasheados-y-api-v5).
El username sigue siendo el alias público de las solicitudes; el email se
normaliza a minúsculas, es único y se verifica con token de un solo uso,
caducidad (24 h) y hash almacenado, con respuestas sin enumeración. El login
acepta username (transición legada) o email **verificado**; un email sin
verificar nunca abre sesión y ningún email se hereda ni se deduce de otra
fuente.
Aceptación: SMTP configurable por entorno, con servidor falso en pruebas y
ninguna prueba enviando correo real; rate limit sobre verificación y login por
email; un fallo de envío no altera la cuenta.
Verificación al cerrar: `python scripts/check_docs.py --tests`,
`python -m unittest discover -s tests -t .`, `node --check` de app.js y sw.js y
`python scripts/check_web_browser.py --channel msedge`.
Dependencias: migración v0→v1 incluida en esta tarea sobre fixtures temporales
con rollback atómico; el marco completo sigue en
[TODO-DATA-001](#todo-data-001--evolución-y-recuperación-de-sqlite).

Evidencia: RED 2026-10-10: `python -m unittest tests.test_identity` →
`ImportError` (sin `biblio/mailer.py`); con el módulo pero sin las rutas, las
peticiones devolvían 404 y el registro fallaba con 502 (`INSERT INTO users`
sin lista de columnas tras añadir las de email).
GREEN 2026-10-10:
- Migración v0→v1 con `BEGIN` explícito (el DDL de sqlite3 no es transaccional
  implícito: medido, sin BEGIN un `ALTER` quedaba aplicado tras un fallo),
  añadiendo `users.email`/`email_verified_at`, `identity_tokens` e índices; la
  prueba de rollback deja `user_version` en 0 con IDs, vínculos, carnés y
  credenciales Fernet intactos, y la conexión cerrada (en Windows deja el
  fichero libre para corregir el obstáculo).
- `email_verification_token`/`verify_email`/`login` por email verificado;
  códigos hasheados (SHA-256), un solo uso, con caducidad, retirados si el
  envío falla; email ocupado por otra cuenta = éxito silencioso sin correo ni
  token; login con email sin verificar = mismo 401 genérico.
- SMTP falso local en las pruebas (`FakeSmtpServer` en
  [test_identity.py](tests/test_identity.py), puerto efímero en 127.0.0.1, sin
  AUTH ni STARTTLS) y `biblio/mailer.py` con configuración `BIBLIO_SMTP_*`; sin
  host la app anuncia que no enviará correo.
- API `4` → `5` y shell `v11` → `v12` por los assets de la UI; ninguna ruta
  antigua cambia de forma.
- `python -m unittest tests.test_identity.EmailVerificationTests` → 11 tests
  OK; suite completa → **232 tests OK**; navegador verificando desde
  Configuración, rechazando el login con email sin verificar, entrando con el
  verificado y con el alias username → exit 0.
Límites: SMTP real no probado; el pendiente no se persiste (tras recargar se
pide otro código); sin notificaciones cuando un tercero reclama un email; el
portal real no está involucrado en ningún paso.

Corrección tras revisión independiente (2026-10-10, INC-006): el fallo de
entrega de `auth/email/request` devolvía 502 solo cuando el email estaba libre
(uno ocupado por otra cuenta seguía en 200), lo que convertía una incidencia
del SMTP en un oráculo. RED:
`python -m unittest tests.test_identity.EmailVerificationTests.test_delivery_failure_is_not_an_oracle_for_email_request`
→ `AssertionError: 200 != 502`. GREEN: misma respuesta genérica en los dos
casos con el código retirado; la prueba de «fallo deja sin código vivo» se
ajustó al 200 uniforme (el contenido sustantivo, ningún token utilizable, se
conserva). `tests.test_identity` → 29 OK; suite → 236 OK.

### TODO-AUTH-003 — Passkeys WebAuthn con librería mantenida

**Estado:** `done`
**Prioridad:** P2
**Tipo:** producto/identidad
**Responsable:** ORCA-implementer MiMo
**Actualizado:** 2026-10-10
**Requisitos:** [FR-AUTH-004](docs/specification.md#fr-auth-004),
[NFR-SEC-002](docs/specification.md#nfr-sec-002),
[NFR-SVC-003](docs/specification.md#nfr-svc-003).

Aprobado el 2026-10-10 por la persona usuaria; alcance fijado en la
especificación y decidido en [ADR-015](docs/decisions.md#adr-015--email-verificado-passkeys-y-oidc-con-librerías-mantenidas-y-tokens-hasheados) y
[ADR-018](docs/decisions.md#adr-018--passkeys-con-webauthn-y-google-oidc-con-joserfc).
Excepción de dependencias acotada: `webauthn>=2.2.0` en `pyproject.toml`
(instalado y probado con **3.0.1**); no se implementa criptografía WebAuthn a
mano. Challenge de un solo uso con caducidad (5 min) guardado como SHA-256,
verificación de `Origin`/RP ID/UV/firma/contador por la librería, reautenticación
explícita para añadir o borrar una passkey y rechazo del servidor en origen no
confiable.
Aceptación: autenticación con passkey que crea una sesión BiblioCM normal con
rotación de token y los mismos permisos que el login por contraseña; pruebas
negativas de origin equivocado, challenge reutilizado/expirado, payload malformado
y passkey de otro usuario; contraseña siempre disponible como reserva.
Verificación al cerrar: `python scripts/check_docs.py --tests`,
`python -m unittest discover -s tests -t .`, `node --check` de app.js y sw.js y
`python scripts/check_web_browser.py --channel msedge`.
Dependencias: [TODO-AUTH-002](#todo-auth-002--email-verificado-con-username-como-alias)
ya implementado; migración v1→v2 incluida en esta tarea sobre fixtures temporales.

Evidencia: 2026-10-10.
- **Esquema v2** ([store.py](biblio/store.py)): tablas `passkeys`,
  `auth_challenges` e `identities` añadidas en la misma transacción con `BEGIN`
  explícito; migraciones probadas sobre fixtures temporales en
  [SchemaMigrationTests](tests/test_identity.py): v0→v2, v1→v2, base reciente,
  reapertura sin migrar dos veces y rollback atómico de cada paso dejando
  `user_version` en el valor anterior con IDs, vínculos, carnés y crypto intactos.
- **Servidor** ([web.py](biblio/web.py), [passkeys.py](biblio/passkeys.py)):
  `auth/passkeys/login/options` (público, sin enumerar), `auth/passkeys/login`
  (rota el token), `auth/passkeys/register/options`, `auth/passkeys/register`,
  `auth/passkeys/delete` (sesión + CSRF + reautenticación) y `auth/reauth`;
  `settings` añade `passkeys` y `session` añade `google`. El RP ID/origen se
  derivan del Host y del esquema; HTTP solo es confiable en `localhost` y
  `127.0.0.1`, y cualquier otro host HTTP recibe 403 antes de mirar el cuerpo.
- **UI** ([index.html](biblio/static/index.html), [app.js](biblio/static/app.js)):
  filas de login con passkey, panel de passkeys en Configuración y diálogo de
  reautenticación (`code:"reauth_required"`); traducción de base64url a
  `ArrayBuffer` para `navigator.credentials.create/get`. Shell `v12` → `v13` y
  API `5` → `6`.
- **Pruebas** (21 en [test_passkeys.py](tests/test_passkeys.py) con el
  autenticador sintético de [webauthn_fake.py](tests/webauthn_fake.py), que
  construye attestation/assertion reales verificadas por la librería):
  registro/login, reautenticación y su caducidad, challenge de un solo uso y
  caducado, origen ajeno, payload malformado, reto de otro usuario, firma/UV/
  contador, credencial ajena, excludeCredentials, no enumeración y login
  concurrente con un único reto (exactamente un 200 entre cuatro hilos).
- **Navegador** (escenario nuevo en [check_web_browser.py](scripts/check_web_browser.py)):
  autenticador virtual de Chromium en `http://localhost:8000` —Chromium rechaza
  un RP ID con forma de IP, y la UI lo explica—: alta con reautenticación
  (incluido un password incorrecto que se queda en el diálogo), listado, borrado
  rechazado sin reauth y login sin contraseña, en escritorio **y** móvil
  emulado, recargando la página y sin errores JS.
- **Guardas verificadas por mutación** (RED auténtico sobre el árbol verde):
  sin `require_reauth` en `register/options` → `test_management_requires_fresh_reauthentication`
  falla (200 != 403); sin el chequeo de `purpose` en `take_challenge` →
  `test_a_registration_challenge_cannot_log_in` falla (200 != 401, un reto de
  registro abría sesión); con el origen de passkeys siempre confiable →
  `test_server_rejects_webauthn_on_a_non_local_http_origin` falla.
- Fallos reales encontrados y corregidos durante el desarrollo: `excludeCredentials`
  como dicts planos rompía `options_to_json` (502); el navegador exige
  `ArrayBuffer` en `challenge`/`user.id`/`id` (error de tipo en `create`); el
  diálogo de reauth no se cerraba tras confirmar; y `rp.id=127.0.0.1` lo rechaza
  Chromium («This is an invalid domain»), de ahí el uso de `localhost` y el
  aviso para IPs.
- Comprobaciones de cierre: `python -m unittest discover -s tests -t .` → **290
  tests OK**; `python scripts/check_docs.py --tests` → Docs OK; `node --check`
  de app.js y sw.js → 0; `python scripts/check_web_browser.py --channel msedge`
  → OK; `python scripts/release_scan.py` → 0 hallazgos; `pip-audit` sin
  vulnerabilidades conocidas para `cryptography==50.0.2`, `webauthn==3.0.1` y
  `joserfc==1.7.5`.
Límites: sin hardware real ni Safari/Firefox (solo Chromium con autenticador
virtual); el portal OPAC no interviene; la CI no se ha ejecutado en el proveedor
([TODO-CI-001](#todo-ci-001--automatizar-checks)); las passkeys de una cuenta
creada con Google requieren antes fijar contraseña por recuperación (reseñado en
[operations.md](docs/operations.md)).

### TODO-AUTH-004 — Acceso con Google (OIDC) opcional

**Estado:** `done`
**Prioridad:** P3
**Tipo:** producto/identidad
**Responsable:** ORCA-implementer MiMo
**Actualizado:** 2026-10-10
**Requisitos:** [FR-AUTH-005](docs/specification.md#fr-auth-005),
[NFR-SEC-002](docs/specification.md#nfr-sec-002).

Aprobado el 2026-10-10 por la persona usuaria; alcance fijado en la
especificación y decidido en [ADR-015](docs/decisions.md#adr-015--email-verificado-passkeys-y-oidc-con-librerías-mantenidas-y-tokens-hasheados) y
[ADR-018](docs/decisions.md#adr-018--passkeys-con-webauthn-y-google-oidc-con-joserfc).
Opt-in por entorno (`BIBLIO_GOOGLE_*`); sin configuración no hay botón, no hay
callback y el servidor responde 503. Flujo de código con `state`/`nonce` de un
solo uso (10 min), PKCE S256 y token ID verificado con `joserfc>=1.6`
(instalado y probado con **1.7.5**): firma RS256 contra el JWKS por
descubrimiento OIDC, `iss`, `aud`, `exp`/`iat`, `nonce` y `azp` con varias
audiencias. La identidad es el par `(issuer, sub)`; el email del token no crea
ni encuentra cuentas. Vincular/desvincular exige sesión, reautenticación y (para
vincular) email verificado; el alta con Google es un modo explícito con email
certificado por el proveedor, contraseña aleatoria y alias determinista.
Aceptación: una cuenta Google vinculada a un único usuario por instancia;
desvincular no borra la cuenta ni sus carnés; fallo del proveedor o del callback
no deja sesión abierta ni token sin consumir.
Verificación al cerrar: `python scripts/check_docs.py --tests`,
`python -m unittest discover -s tests -t .`, `node --check` de app.js y sw.js y
`python scripts/check_web_browser.py --channel msedge`.
Dependencias: [TODO-AUTH-002](#todo-auth-002--email-verificado-con-username-como-alias)
y la migración v1→v2 de [TODO-AUTH-003](#todo-auth-003--passkeys-webauthn-con-librería-mantenida);
las credenciales OAuth de Google las crea la persona (trámite humano en la
consola de Google Cloud, sin APIs de pago y sin promesa de coste: ver fuentes
fechadas en [operations.md](docs/operations.md)) y nunca se versionan ni se usan
en CI.

Evidencia: 2026-10-10.
- **Servidor** ([oidc.py](biblio/oidc.py), [web.py](biblio/web.py)):
  `auth/google/start` (login/signup público, link con sesión+CSRF+reauth+email
  verificado), `auth/google/callback` (única respuesta del API que no es JSON:
  303 a `/?google=…`, con cookie en login/signup exitosos) y
  `auth/google/unlink`. El `state` se consume **antes** de tocar al proveedor;
  el detalle (nonce, verificador PKCE, redirect y modo) se cifra con la Fernet
  del servidor y en la BD solo vive el SHA-256 del estado.
- **Pruebas** (29 en [test_oidc.py](tests/test_oidc.py) contra el proveedor OIDC
  falso local de [fake_oidc.py](tests/fake_oidc.py): discovery + JWKS + token
  RS256 firmado con una clave generada en la prueba): opt-in (sin configuración
  503 en start/callback/unlink y `session.google.enabled=false`), parámetros de
  autorización (state/nonce/PKCE/redirect), estado de un solo uso y caducado,
  fallo de proveedor sin sesión, verificación unitaria del token (firma ajena,
  issuer, audiencia, nonce, expirado y token malformado), vincular con email
  verificado + reautenticación, login con la cuenta vinculada, **sin merge por
  email** (una cuenta local con el mismo email no recibe sesión ni identidad),
  alta con alias determinista y sufijo del `sub` cuando el alias está ocupado,
  rechazo del alta si el email ya existe, unicidad de la cuenta Google,
  desvinculación que conserva cuenta/carnés, CSRF y rate limit.
- **UI**: botones `#google-login`/`#google-signup` en el acceso (solo con
  `session.google.enabled`), `#google-link`/`#google-unlink` en Configuración
  con reautenticación, y traducción de `/?google=…` a aviso limpiando la URL.
- **Navegador**: vinculación completa (email verificado con el SMTP falso +
  reautenticación + vuelta del proveedor) y entrada con Google, en escritorio y
  en móvil emulado, contra el proveedor falso; sin errores JS.
- Comprobaciones de cierre: las mismas que en
  [TODO-AUTH-003](#todo-auth-003--passkeys-webauthn-con-librería-mantenida)
  (290 tests OK, Docs OK, node 0, navegador OK, release_scan 0, pip-audit sin
  hallazgos).
Límites: Google real y credenciales OAuth de la persona no se probaron (ni se
versionan); el proveedor falso cubre el contrato, no el comportamiento de
Google; sin `access_type=offline` ni refresh tokens (no hace falta para sesión
BiblioCM); la cuenta creada con Google queda con una contraseña aleatoria
desconocida, fijable con la recuperación por su email verificado.

### TODO-OPS-002 — Aviso de origen no local e instrucciones HTTPS (mkcert)

**Estado:** `done`
**Prioridad:** P2
**Tipo:** UI/operación
**Responsable:** ORCA-implementer MiMo
**Actualizado:** 2026-10-10
**Requisitos:** [NFR-SVC-003](docs/specification.md#nfr-svc-003).

Origen: sobre HTTP servido desde una dirección que el navegador no considera
local, la UI no advertía de nada y el usuario no podía distinguir ese contexto
de `http://127.0.0.1`. Aceptación: la UI detecta `window.isSecureContext` y,
cuando el origen no es de confiable, muestra un aviso persistente
`#origin-warning` que explica el alcance del riesgo (tráfico sin cifrar y
passkeys deshabilitadas) y orienta a `http://127.0.0.1` y a la guía mkcert; el
resto de la aplicación sigue funcionando; `127.0.0.1` y `localhost` no muestran
el aviso. El servidor expone el estado con `data-secure-origin` en `<html>`.
Añadida en [operations.md](docs/operations.md#https-local-con-mkcert-recomendado-para-móvil)
la instrucción de mkcert + proxy TLS con `--secure`, sin instalar certificados,
sin abrir puertos y sin publicar servicios; el binding default sigue siendo
`127.0.0.1`.
RED previsto: escenario de navegador (ver Evidencia).
Verificación al cerrar: `python scripts/check_docs.py --tests`,
`python -m unittest discover -s tests -t .`, `node --check` de app.js y sw.js y
`python scripts/check_web_browser.py --channel msedge`.
Dependencias: ninguna para el aviso. La desactivación **servidor** de passkeys
queda para [TODO-AUTH-003](#todo-auth-003--passkeys-webauthn-con-librería-mantenida):
hoy no existe ninguna operación WebAuthn que rechazar, y la UI no tiene botón de
passkey que desactivar; el aviso ya lo comunica. No se afirma HTTPS ni passkeys
funcionando en un dispositivo real (sigue
[TODO-PLAT-001](#todo-plat-001--pwa-en-dispositivos-reales)).

Evidencia: RED 2026-10-10 (baseline, `app.js` sin el aviso):
1. `python scripts/check_web_browser.py --channel msedge` → exit 1 con la
   aserción nueva `expect(owner.locator("#origin-warning")).to_be_hidden()`
   fallando por `Actual value: hidden`… en realidad el elemento no existía en el
   HTML, así que el locator devolvía 0 nodos (`to_have_count` 0 frente a 1).
2. Tras añadir el elemento y la rama de `app.js`, la rama «no confiable» se
   reprodujo con un contexto de navegador que fuerza
   `Object.defineProperty(window,'isSecureContext',{get:()=>false})` vía
   `add_init_script`: `#origin-warning` visible y `data-secure-origin="false"`.
GREEN 2026-10-10: `#origin-warning` en
[index.html](biblio/static/index.html) (`role="status"`, `aria-live="polite"`,
`hidden` por defecto), rama `if (!secureOrigin)` en
[app.js](biblio/static/app.js) que lo muestra y fija
`document.documentElement.dataset.secureOrigin`, regla `.origin-warning` en
[styles.css](biblio/static/styles.css) y guía mkcert en
[operations.md](docs/operations.md). `python scripts/check_web_browser.py --channel msedge`
→ exit 0 con el aviso oculto en `http://127.0.0.1` y visible en el contexto
forzado; `python -m unittest discover -s tests -t .` → 207 tests OK;
`python scripts/check_docs.py --tests` → Docs OK; `node --check` → 0.
Límites: el aviso se verificó forzando `isSecureContext`, no sirviendo la app
desde una IP de red local real; mkcert no se ejecutó (instala una CA local, que
queda fuera de una prueba automatizada) y el proxy TLS de ejemplo no se probó;
el rechazo servidor de WebAuthn en origen no confiable queda pendiente en
[TODO-AUTH-003](#todo-auth-003--passkeys-webauthn-con-librería-mantenida).

### TODO-PUB-001 — Licencia MIT, SECURITY.md y documentación de publicación

**Estado:** `done`
**Prioridad:** P1
**Tipo:** publicación/documentación
**Responsable:** ORCA-implementer MiMo
**Actualizado:** 2026-10-10
**Requisitos:** [NFR-DEV-001](docs/specification.md#nfr-dev-001).

Origen: el usuario aprobó publicar el repositorio y la base no tenía licencia,
canal de aviso de seguridad ni sección de colaboración. Adecuación registrada en
[ADR-016](docs/decisions.md#adr-016--publicación-preparada-licencia-mit-securitymd-ci-de-solo-lectura-y-escaneo-de-secretos).
Aceptación: `LICENSE` con MIT (titular «jabaruben/BiblioCM», el sugerido por la
persona usuaria, sin inventar
personas), `SECURITY.md` con canal privado de notificación (advisories del
hosting, nunca un issue público con datos), alcance y fuera de alcance, sin
inventar direcciones de correo; README con sección de licencia/colaboración y
el escaneo de publicación en las comprobaciones.
Verificación al cerrar (2026-10-10): `python scripts/check_docs.py --tests` →
Docs OK (207 tests, sin enlaces ni anclas rotos); `python scripts/release_scan.py`
→ 0 hallazgos sobre el set publicable; `python -m unittest discover -s tests -t .`
→ 207 OK. Revisión de que ningún ejemplo del README ni de SECURITY.md contiene
credenciales, tokens ni URLs internas, y de que SECURITY.md no inventa
direcciones de correo (canal privado del hosting).
Dependencias: ninguna; no autoriza a publicar el repositorio (eso sigue siendo
una acción de la persona). No se creó remota, no se hizo commit y no se publicó
nada.

Evidencia: `LICENSE` (MIT, «jabaruben/BiblioCM»), `SECURITY.md` (canal
privado de notificación, alcance y fuera de alcance, sin direcciones de correo
inventadas) y secciones de licencia/colaboración en el README. Comandos de
cierre ejecutados el 2026-10-10: `check_docs.py --tests` → Docs OK;
`release_scan.py` → 0 hallazgos; suite unittest → 207 OK. Límite: la CI solo
existe como fichero ([TODO-CI-001](#todo-ci-001--automatizar-checks)); no se
publicó ni se ejecutó en ningún proveedor.

### TODO-SEC-002 — Escaneo de secretos previo a publicar

**Estado:** `done`
**Prioridad:** P1
**Tipo:** infraestructura de seguridad
**Responsable:** ORCA-implementer MiMo
**Actualizado:** 2026-10-10
**Requisitos:** [NFR-SEC-001](docs/specification.md#nfr-sec-001),
[NFR-DEV-001](docs/specification.md#nfr-dev-001).

Origen: publicar sin una barrera automática depende de la memoria de quien
publique. Decisión en
[ADR-016](docs/decisions.md#adr-016--publicación-preparada-licencia-mit-securitymd-ci-de-solo-lectura-y-escaneo-de-secretos).
Aceptación: `scripts/release_scan.py` recorre los ficheros que Git publicaría
(`git ls-files --cached --others --exclude-standard`), aplica reglas de material
privado (claves privadas, tokens Fernet, tokens de proveedores conocidos, JWT,
rutas de sesión OPAC de alta entropía y ficheros de datos/claves que no deberían
versionarse) y reporta **solo regla + ruta + línea**, nunca el contenido; código
de salida 0 limpio, 1 con hallazgos, 2 error; los temporales de `.gitignore` no
se escanean.
RED previsto: ver Evidencia.
Verificación al cerrar: `python -m unittest tests.test_release_scan`,
`python scripts/release_scan.py` y `python -m unittest discover -s tests -t .`.
Dependencias: ninguna.

Evidencia: RED 2026-10-10:
`python -m unittest tests.test_release_scan` → `ImportError: cannot import name
'release_scan' from 'scripts'` (el módulo no existía).
GREEN 2026-10-10:
- [release_scan.py](scripts/release_scan.py) con reglas de contenido y de
  nombre, umbral de entropía calibrado contra los tokens ficticios de los
  fixtures (`THREADTOKEN02` y similares, ≤13 caracteres, no se marcan) y
  reporte `HALLAZGO <regla> <ruta>:<línea>` sin contenido.
- [test_release_scan.py](tests/test_release_scan.py) → **13 tests OK**, con
  constructores de secretos por concatenación para que el propio fichero de
  tests no se marque al escanear el repositorio, prueba de que el reporte no
  contiene ni el valor ni sus primeros 16 caracteres, prueba de que una BD
  ignorada no entra en el set publicable, y prueba de que el set publicable del
  proyecto real está limpio y no vacío.
- `python scripts/release_scan.py` → `release-scan: 60 ficheros, 0 hallazgos`,
  exit 0.
- `python -m unittest discover -s tests -t .` → 207 tests OK.
Límites: es un guardia previo a publicar, no una auditoría de seguridad; no
detecta lógica malintencionada ni material fuera de las reglas; el umbral de
entropía puede dejar pasar un token muy corto y marcar un ejemplo legítimo muy
largo, y eso se revisa al ejecutarlo, no se «arregla» relajando la regla.

### TODO-SEC-003 — Orígenes de confianza para passkeys y Google

**Estado:** `done`
**Prioridad:** P1
**Tipo:** seguridad
**Responsable:** ORCA-implementer MiMo
**Actualizado:** 2026-10-10
**Requisitos:** [NFR-SVC-003](docs/specification.md#nfr-svc-003),
[FR-AUTH-004](docs/specification.md#fr-auth-004),
[FR-AUTH-005](docs/specification.md#fr-auth-005).

Origen: revisión del paquete passkeys/Google recién implementado: `rp_context`
aceptaba cualquier Host sobre TLS (el RP ID/origen WebAuthn salían del Host del
pedido) y `google_redirect_uri` derivaba el callback OIDC del Host cuando no
había `BIBLIO_GOOGLE_REDIRECT_URI`, de modo que un Host hostil elegía el origen
esperado y la URI de retorno del proveedor.
Aceptación: existen orígenes de confianza con default solo local
(`localhost`/`127.0.0.1`, cualquier puerto válido, http y https); el origen
público exige `BIBLIO_TRUSTED_ORIGINS` canónico (sin userinfo/ruta/query/
fragmento/control, puerto estricto); WebAuthn deriva RP ID/origen solo de un
origen de confianza y rechaza el resto (403 incluso sobre TLS); el callback
Google se configura o deriva del origen de confianza del pedido, nunca de un
Host arbitrario; URI configurada no canónica o con origen no confiable → 503.
RED previsto: ver Evidencia.
Verificación al cerrar: `python -m unittest tests.test_passkeys tests.test_oidc`
y la suite completa; docs con `check_docs.py --tests`.
Dependencias: ninguna.

Evidencia: 2026-10-10. Fail-before por inspección (el worktree no tiene
historial Git: todo está untracked, no se puede re-ejecutar el código previo):
`rp_context` tenía `trusted = scheme == "https" or hostname in LOCAL_HOSTNAMES`
(aceptaba `Host: evil.example` sobre TLS) y `google_redirect_uri` devolvía
`f"{scheme}://{Host}/api/auth/google/callback"`. GREEN tras la corrección:
- [origins.py](biblio/origins.py): origen canónico estricto (sin userinfo/ruta/
  query/fragmento/control, puerto 1–65535, puertos por defecto normalizados) y
  `TrustedOrigins` con default solo local y coincidencia exacta por origen.
- [passkeys.py](biblio/passkeys.py) `rp_context(host, secure, trusted)`:
  400 con Host no canónico, 403 si el origen no está en la lista (antes
  cualquier TLS valía); [web.py](biblio/web.py): comparación de `Origin` contra
  el origen canónico, y el callback Google exige origen de confiable en todos
  los casos (Host hostil → 403; `BIBLIO_GOOGLE_REDIRECT_URI` no canónico, con
  ruta distinta o con origen no listado → 503). Arranque con
  `BIBLIO_TRUSTED_ORIGINS` inválido → exit 1 antes de enlazar (probado).
- RED intermedio real: con el redirect configurado, `start` con Host hostil
  devolvía 200 (`test_configured_https_callback_is_used_only_on_listed_origins`
  falló `200 != 403`); se corrigió exigiendo también el origen de confianza del
  pedido antes de usar la URI configurada.
- `python -m unittest tests.test_passkeys` → **31 tests OK** (10 nuevos:
  parsing canónico, Host hostil sobre TLS, local TLS, origen listado exacto,
  Origin==Host hostil, Host malformado, flujo passkeys sobre origen HTTPS
  configurado).
- `python -m unittest tests.test_oidc` → **34 tests OK** (5 nuevos: Host hostil
  no elige callback, derivación local, callback configurado solo en origen
  listado, https local sin lista extra y configuraciones inválidas → 503).
- `python -m unittest discover -s tests -t .` → **305 tests OK**.
- `python scripts/check_docs.py --tests` → Docs OK, 305 tests contados;
  `python scripts/release_scan.py` → 0 hallazgos; `node --check` app.js/sw.js →
  0.
Límites: no se ejecutó mkcert ni un proxy TLS real ni un despliegue con dominio
público; el escenario de navegador no se repitió porque la UI no cambia (las
rutas locales siguen en el default de confianza). La comprobación fail-before no
se re-ejecutó contra el código previo (sin historial en este worktree); queda la
inspección citada. El resto de rutas del API siguen accesibles desde cualquier
Host (la lista solo cubre passkeys y Google): el rechazo de DNS rebinding para
el panel completo sigue fuera de alcance.

Evidencia documental 2026-10-10 (misma fecha, sin cambios de código): una
revisión independiente del paquete señaló que las afirmaciones de coste en
[operations.md](docs/operations.md) no tenían fuentes fechadas. Corrección: nueva
sección «Fuentes externas y salvedades (consulta: 2026-10-10)» con las URLs
oficiales de OpenID Connect de Google, nivel gratuito de Google Cloud, mkcert,
Mailpit y precios de Tailscale, cada una con la salvedad de que la comprobación
fue solo un HEAD 200 el 2026-10-10 (accesibilidad ese día, no contenido, precio
ni condiciones). Se corrigieron el titular «opt-in y gratuito», el «trámite
humano y gratuito», el «gratuito y local» de mkcert/proxy/Mailpit y el «cuenta
gratuita» de Tailscale sin retirar la guía de instalación; Brevo y Resend
quedan marcados explícitamente como proveedores de correo sin verificar y no
usados. Verificación: `python scripts/check_docs.py --tests` → Docs OK, sin
enlaces ni anclas rotos. Límites: ninguna URL de tercero se re-valida en CI y
los precios/condiciones externos pueden cambiar sin relación con este
repositorio. Las tareas `done` de este paquete (TODO-AUTH-003,
TODO-AUTH-004, TODO-OPS-002, TODO-SEC-003) se cierran sin reabrirlas: esto es
corrección de sourcing documental, no un defecto de comportamiento.

### TODO-CI-001 — Automatizar checks

**Estado:** `in_progress`
**Prioridad:** P2
**Tipo:** infraestructura de desarrollo
**Responsable:** ORCA-implementer MiMo
**Actualizado:** 2026-10-10
**Requisitos:** evolución de [NFR-DEV-001](docs/specification.md#nfr-dev-001).

Decisión de alcance en [ADR-016](docs/decisions.md#adr-016--publicación-preparada-licencia-mit-securitymd-ci-de-solo-lectura-y-escaneo-de-secretos):
proveedor GitHub Actions, matriz Python 3.11/3.13 sobre ubuntu-latest y
windows-latest, permisos `contents: read`, sin secretos, sin deploy y sin
publicación automática. Los pasos son `pip install -e .`,
`check_docs.py --tests`, la suite unittest, `node --check` de `app.js`/`sw.js` y
`release_scan.py`.
Aceptación: la ejecución real en el proveedor debe verse fallando con asserts
activos y sin portal, claves ni cuentas reales; mientras no se ejecute allí, la
tarea no es `done`.
RED previsto: no aplica todavía (no hay ejecución del proveedor).
Verificación pendiente: abrir el primer push/PR y comprobar que los cinco pasos
corren y que un fallo de aserción se ve en rojo.
Dependencias: ninguna técnica; el bloqueo es que la primera ejecución ocurre
cuando la persona publique o haga push. El escenario de navegador se queda
fuera de la CI por ahora (exige instalar un navegador en el runner): es una
decisión futura, no un fallo.

Evidencia parcial 2026-10-10: creado
[.github/workflows/ci.yml](.github/workflows/ci.yml) con la matriz, permisos
de solo lectura y los cinco pasos; validado con `yaml.safe_load` y con una
revisión de que no referencia `secrets.*`, ni `gh release`, ni `twine`, ni
`git push`. Los cinco comandos pasan en local (ver Evidencia de
[TODO-SEC-002](#todo-sec-002--escaneo-de-secretos-previo-a-publicar) y
[TODO-CAT-005](#todo-cat-005--caché-ram-de-portada-en-el-navegador-con-revocación)),
pero **eso no es una ejecución de CI**: la tarea sigue `in_progress` hasta que
el proveedor la ejecute.

### TODO-SEC-004 — Vínculo del flujo Google al navegador y a la sesión

**Estado:** `done`
**Prioridad:** P1
**Tipo:** seguridad
**Responsable:** ORCA-implementer MiMo
**Actualizado:** 2026-10-10
**Requisitos:** [FR-AUTH-005](docs/specification.md#fr-auth-005),
[NFR-SEC-001](docs/specification.md#nfr-sec-001),
[NFR-SEC-002](docs/specification.md#nfr-sec-002).

Origen: revisión de `google_start`/`google_callback` en [web.py](biblio/web.py).
El `state` solo vivía en la BD: nada lo ligaba al navegador que inició el flujo
(login CSRF de OAuth: el par `code`+`state` conseguido en el navegador del
atacante se puede completar en el de la víctima, que abre sesión del atacante).
Además el modo `link` guardaba el `user_id` en el reto, así que un **logout
mientras el flujo estaba pendiente no impedía** que el callback escribiera el
vínculo en una sesión ya cerrada (y el gate no volvía a mirar email verificado).
Aceptación: (1) `start` emite una cookie de enlace por flujo con valor aleatorio
criptográfico, `HttpOnly`, `SameSite=Lax`, `Secure` sobre HTTPS, ruta
`/api/auth/google` y TTL igual al del `state`; el servidor guarda **solo el
digest** junto al estado y lo compara en tiempo constante **antes** de
intercambiar el `code` con el proveedor y antes de crear sesión o vínculo.
(2) Sin cookie, con cookie ajena, transferida a otro navegador, reutilizada tras
completar o caducada → rechazo sin ninguna llamada al proveedor; en esos casos el
estado legítimo **no** se consume, así que el navegador original aún puede
completar. (3) La cookie se retira al completar y en cada error. (4) `link`
exige en el gate final del store que la sesión que inició el flujo siga abierta
para el mismo usuario y que el usuario siga existiendo con email verificado.
(5) La cookie de sesión global sigue con `SameSite=Strict`. Sin secretos, valores
ni digests en respuestas, `Location` o logs.
RED previsto: ver Evidencia.
Verificación al cerrar: `python -m unittest tests.test_oidc`,
`python -m unittest discover -s tests -t .`, `python scripts/check_docs.py --tests`
y `node --check` de app.js y sw.js.
Dependencias: ninguna; amplía el alcance aprobado de
[TODO-AUTH-004](#todo-auth-004--acceso-con-google-oidc-opcional).

Evidencia: 2026-10-10. Fail-before por inspección del código previo (el worktree
no tiene historial Git, todo untracked, así que no se puede re-ejecutar): en
`google_start` solo se hacía `store.put_challenge(...)` con el `state` y el
detalle, **sin ninguna cookie ni valor de enlace por navegador**; en
`google_callback` el primer contacto con el flujo era
`take_challenge(...)` seguido de `provider.exchange_code(...)` —sin comparar
nada propio del navegador— y el modo `link` hacía `store.link_identity(user_id,
...)` con el `user_id` rescatado del reto, **sin** volver a comprobar que la
sesión siguiera viva ni que el email siguiera verificado. Nada impedía por tanto
completar en la víctima un `code`+`state` conseguido en el atacante (login CSRF)
ni vincular tras un logout con el flujo pendiente.

RED 2026-10-10: como el worktree no tiene historial Git no se puede re-ejecutar
el código previo, y tampoco se conserva un commit intermedio con el test en rojo
sobre el árbol definitivo. La evidencia RED se apoya en dos cosas y no se
presenta como más: (a) el **fail-before por inspección** de arriba, y (b) la
ejecución real de las 13 pruebas nuevas contra el servidor **sin** la
corrección, durante la construcción, cuyos fallos fueron exactamente los
síntomas de arriba, no fallos de implementación:
`python -m unittest tests.test_oidc.GoogleBindingTests` → **FAIL (10 fallos,
2 errores)**, entre ellos `test_the_original_browser_completes_and_the_cookie_is_cleared`
→ `AssertionError: '' is not true` (ninguna cookie de enlace emitida),
`test_a_wrong_binding_cookie_is_rejected_before_the_provider` →
`'/?google=signed' != '/?google=error'` (callback con cookie ajena **abría
sesión**), `test_logout_while_the_link_is_pending_blocks_the_link` →
`'/?google=linked' != '/?google=error'` (el vínculo se escribía tras el logout) y
`test_peek_challenge_reads_the_state_without_consuming_it` → `AttributeError`
(método inexistente). Verificado al cerrar que sobre el árbol definitivo ese
mismo comando ya no reproduce ese rojo: `python -m unittest
tests.test_oidc.GoogleBindingTests` → **13 OK**; quien quiera el rojo debe
quitar la corrección de `google_callback`, que es justamente lo que el test
detecta.

GREEN 2026-10-10:
- [biblio/web.py](biblio/web.py): constantes `OIDC_BINDING_COOKIE`/`OIDC_BINDING_PATH`;
  `binding_cookie`/`clear_binding_cookie` (valor `secrets.token_urlsafe(32)`,
  `HttpOnly`, `SameSite=Lax`, `Path=/api/auth/google`, `Max-Age` = TTL del
  `state`, `Secure` solo con `--secure`); `binding_value` lee la cookie;
  `binding_matches` compara el SHA-256 del valor con el guardado mediante
  `secrets.compare_digest` y `google_callback` lo exige **antes** de
  `store.take_challenge` y de `provider.exchange_code`, con `store.peek_challenge`
  (nuevo, de solo lectura) de modo que un intento hostil **no consume el
  estado** y el navegador original aún puede completar; el modo `link` guarda
  además el SHA-256 del token de la sesión (`google_start`) y
  `link_session_live` lo exige —sesión viva, mismo usuario, email verificado—
  antes del canje **y** otra vez en el gate final junto a `store.link_identity`.
  Toda respuesta del callback retira la cookie (`clear_binding_cookie`); la cookie
  de sesión global sigue con `SameSite=Strict` y el callback no la lee. Sin
  secretos ni digests en `Location`, cuerpo o logs.
- [biblio/store.py](biblio/store.py): `peek_challenge(purpose, raw)` de solo
  lectura, que valida propósito y caducidad sin retirar la fila; el consumo de
  un solo uso sigue siendo `take_challenge`.
- **Pruebas** (13 nuevas en
  [GoogleBindingTests](tests/test_oidc.py), 48 en la suite OIDC): dos contextos
  de navegador (el original completa con su cookie; el atacante con el par
  `code`+`state` transferido **no**), sin cookie / cookie ajena / transferida /
  reutilizada tras completar / caducada → `/?google=error` con
  `self.assertEqual(self.provider.seen, [], ...)` (**ninguna llamada al
  proveedor**) y sin consumir el estado, `link` rechazado con logout pendiente,
  con la sesión rotada y con el email desverificado, `Secure` presente en el
  cookie sobre HTTPS, y `assert_not_in(...)` del valor del enlace en
  `authorize_url`, `Location` y salidas. Se ajustaron 6 aserciones previas de
  `assertNotIn("Set-Cookie", headers)` a `assert_no_session(headers)` porque la
  cookie de enlace se retira ahora en **todos** los caminos: cambio de
  expectativa exigido por la aceptación, no un debilitamiento.
- **Navegador**: `python scripts/check_web_browser.py --channel msedge` →
  **exit 0** (2026-10-10), incluyendo el escenario Google (vinculación con email
  verificado + reautenticación, logout y entrada con la cuenta vinculada en
  escritorio y móvil emulado) **y el paso nuevo de login CSRF en dos contextos**:
  se retiene la respuesta de `auth/google/start` (patrón de carga retenida del
  propio script), el navegador que inició el flujo completa, y el par
  `code`+`state` cargado en un segundo navegador **sin** su cookie de enlace
  rechaza y se queda en la pantalla de acceso. Playwright no estaba instalado en
  el Python del entorno: se instaló **solo para esta ejecución** con
  `pip install --target %TEMP%\opencode\pwin playwright` (fuera del repo, sin
  tocar `pyproject.toml` ni el entorno global) y se ejecutó con
  `PYTHONPATH` apuntando a esa carpeta; el navegador fue el Edge del sistema
  (`--channel msedge`), sin descargar navegadores ni abrir puertos.
- Comprobaciones de cierre 2026-10-10: `python -m unittest tests.test_oidc` →
  **48 OK**; `python -m unittest discover -s tests -t .` → **329 OK**;
  `python scripts/check_docs.py --tests` → Docs OK; `node --check` de app.js y
  sw.js → 0.
Límites: sin historial Git no se pudo re-ejecutar el código previo para el
fail-before automatizado; el fail-before es por inspección del diff y el RED
anterior es un retroceso de la corrección sobre los tests ya escritos. No se
probó con Google real ni con credenciales de la persona. No se cambió la versión
de API (`6`): la forma de las respuestas JSON no cambia y la cookie la gestiona
el navegador; una UI antigua contra un servidor nuevo sigue funcionando.

**Corrección por revisión independiente (2026-10-10, mismo día):** la revisión
señaló que el gate final comprobaba `link_session_live()` y después llamaba a
`store.link_identity()` **sin lock compartido**: un logout que entrara en esa
ventana retiraba la sesión y el INSERT se escribía igual, contra la aceptación
«logout mientras pendiente invalida la vinculación». Corrección:
- [biblio/web.py](biblio/web.py): nuevo `Handler.store_link_with_live_session`
  que retiene `server.lock` —el mismo que usan el logout y
  `close_user_sessions` para retirar sesiones— entre la comprobación de la
  sesión que inició el flujo y la escritura, haciendo ambas indivisibles
  respecto al logout. La E/I con el proveedor ocurre **antes** del lock. Orden
  de locks `server.lock` → `store.lock` (ya usado por `link_session_live` y
  `open_session`); el store nunca toka locks del servidor ni de sesión y ninguna
  ruta toma `server.lock` y después una puerta de operación: sin ciclos, sin
  deadlock. Un logout que llega durante el gate se ordena **detrás** (la sesión
  seguía viva al escribir; el vínculo queda y el logout solo cierra la sesión,
  misma semántica que una operación ya autorizada tras logout, NFR-SVC-002).
- [biblio/store.py](biblio/store.py): `link_identity(..., require_verified=True)`
  revalida existencia y `email_verified_at` **dentro de la misma transacción**
  que escribe el vínculo, bajo `store.lock`; el titular ya no válido recibe 401
  y no se escribe fila.
- **RED determinista** (2026-10-10): con el lock retirado del gate (copia
  temporal del gate anterior), `python -m unittest
  tests.test_oidc.GoogleBindingTests.test_the_final_link_gate_is_indivisible_with_respect_to_logout`
  → **FAIL**: `AssertionError: True is not false: el logout pudo obtener
  server.lock dentro del gate` — el logout se colaba en la ventana. GREEN al
  restaurar el lock: 15 tests de `GoogleBindingTests` OK. La prueba fuerza el
  logout lanzándolo desde la propia comprobación final (bajo el lock) y mide,
  desde ese hilo, si `server.lock` estaba contendido; además comprueba que el
  resultado es el orden documentado (`linked` con la sesión viva, logout
  detrás, sin desvincular) y añade prueba de unidad del gate del store
  (`require_verified` → 401 sin escribir).
- `python -m unittest tests.test_oidc` → **50 OK** (48 → 50); recuento global
  329 → 331.
Límites de la corrección: la indivisibilidad cubre el logout de esta instancia
(las sesiones viven en RAM del proceso); no convierte el vínculo en transacción
con la sesión de otro proceso porque no hay despliegue distribuido. El orden
«logout durante el gate → se ordena detrás» es deliberado y está documentado.

### TODO-SEC-005 — Rechazo de reautenticación sin marca con reloj monotónico joven

**Estado:** `done`
**Prioridad:** P1
**Tipo:** seguridad
**Responsable:** ORCA-implementer MiMo
**Actualizado:** 2026-10-10
**Requisitos:** [FR-AUTH-004](docs/specification.md#fr-auth-004),
[FR-AUTH-005](docs/specification.md#fr-auth-005),
[NFR-SEC-002](docs/specification.md#nfr-sec-002).

Origen: evidencia externa de CI sobre el commit `969e247` (Ubuntu Python 3.11):
`tests.test_passkeys.PasskeyFlowTests.test_management_requires_fresh_reauthentication`
falló en la línea 179 con `403 != 200`, mientras Windows 3.11/3.13 y Ubuntu 3.13
pasaron (3 pasan / 1 falla; el siguiente push quedó por verificar). Causa
identificada por inspección y reproducida en local: `require_reauth` usa
`session.get("reauth_at", 0)`, de modo que una sesión que **nunca** reautenticó
se compara contra el instante `0` del reloj monotónico. En un host cuyo
`time.monotonic()` aún no llega a `REAUTH_TTL` (300 s: VM/contenedor recién
arrancado, típico en CI) `monotonic - 0 <= 300` y el servidor respondía **200**
en lugar de `403` para `auth/passkeys/register/options`; el mismo helper gatea
`auth/passkeys/register`/`delete` y `auth/google/start` (modo `link`) y
`auth/google/unlink`, así que la ventana de reautenticación dependía de la
antigüedad del host.
Aceptación: (1) una sesión sin `reauth_at` o con la marca caducada recibe
siempre `403` `code:"reauth_required"`, con cualquier valor de
`time.monotonic()`; (2) una reautenticación fresca sigue abriendo la ventana
con el mismo reloj joven; (3) sin tocar la caducidad deslizante de sesión
(`TTL`), la ventana `REAUTH_TTL` ni la selección de sesión por token; (4) la
prueba de CI y cualquier aserción previa se conservan: sin debilitar, eliminar
ni saltar.
RED previsto: ver Evidencia.
Verificación al cerrar: `python -m unittest tests.test_passkeys` (repetido),
`python -m unittest discover -s tests -t .`, `python scripts/check_docs.py
--tests` y `node --check` de app.js y sw.js.
Dependencias: ninguna; sin dependencias nuevas, sin tocar store, BD ni portal.

Evidencia: 2026-10-10. **Adjudicación: defecto de producto (seguridad), no de
la prueba.** La prueba de CI pide el `403` que exige el invariante y el fallo
solo aparece cuando `time.monotonic() < REAUTH_TTL`; no se tocó, debilitó ni
saltó ninguna aserción. Fail-before reproducible en local sin esperar la
uptime de la máquina: `python -m unittest
tests.test_passkeys.PasskeyFlowTests.test_management_without_reauth_is_rejected_on_a_young_monotonic_clock`
→ **FAIL (exit 1)**, `AssertionError: 200 != 403` en `assertEqual(code, 403)`
antes de la corrección (la prueba fija el reloj de `biblio.web` a
`REAUTH_TTL - 1`; una reproducción independiente con `time.monotonic()` = 42 s
devolvió también `200` en `auth/passkeys/register/options`), y **OK** después.
Evidencia externa de CI sobre `969e247`: Ubuntu 3.11 falló en la línea 179
(`403 != 200`) y Windows 3.11/3.13 y Ubuntu 3.13 pasaron (**3 pasan / 1
falla**; aquí la suite local pasaba porque el monotónico del equipo supera
`REAUTH_TTL`); el siguiente push quedó por verificar.
GREEN (2026-10-10): [biblio/web.py](biblio/web.py) — `require_reauth` toma
`session.get("reauth_at")` y exige que la marca exista y sea numérica antes de
compararla con `time.monotonic() - REAUTH_TTL`; sin marca (o no numérica) →
`403` `code:"reauth_required"` con cualquier valor del reloj. Sin cambio de
contrato (el `403`/`reauth_required` ya estaba documentado en
[api.md](docs/api.md)), sin tocar store, BD, portal ni UI, y sin dependencias
nuevas.
Pruebas: 1 nueva en [tests/test_passkeys.py](tests/test_passkeys.py)
(`test_management_without_reauth_is_rejected_on_a_young_monotonic_clock`, que
además exige que el rechazo no emita reto de registro y que una reautenticación
fresca sí habilita con el mismo reloj joven); recuento 343 → **344**.
Comprobaciones de cierre: `python -m unittest tests.test_passkeys` → **32 OK**
en tres ejecuciones seguidas; cinco pruebas de reautenticación (la de CI, la
nueva, caducidad, borrado y login con passkey) → **OK** en cinco
ejecuciones seguidas; `python -m unittest tests.test_oidc` → **50 OK** (mismo
helper para el vínculo de Google); `python -m unittest discover -s tests -t .`
→ **344 OK** (167,3 s); `python scripts/check_docs.py --tests` → **Docs OK** (16
documentos, 23 requisitos, 43 tareas, 472 enlaces, 344 tests); `node --check`
de `app.js` y `sw.js` → **0**. Límites: la CI externa no se re-ejecutó desde
aquí; sin navegador (la UI no cambia) ni portal real.

### TODO-PUB-002 — Candidato público limpio, allowlist del escaneo y auditoría aislada

**Estado:** `done`
**Prioridad:** P1
**Tipo:** publicación/infraestructura
**Responsable:** ORCA-implementer MiMo
**Actualizado:** 2026-10-10
**Requisitos:** [NFR-DEV-001](docs/specification.md#nfr-dev-001),
[NFR-SEC-001](docs/specification.md#nfr-sec-001).

Origen: la revisión de publicación solo comprobaba el set publicable **dentro**
del repositorio de trabajo, donde conviven `.biblio-data/`,
`docs/HANDOFF-SOL.md` (con datos personales) y temporales `.biblio-test-*`: nada
comprobaba que un **candidato limpio** —solo lo que Git publicaría— siga
funcionando, ni que el escáner tuviera una política de rutas explícita.
Aceptación: script de exportación que copia exactamente el set publicable a un
directorio temporal, verifica que no lleva ningún fichero ignorado (nunca
`.biblio-data` ni el HANDOFF legado) y ejecuta sobre ese candidato el checker de
documentación, la importación del paquete, la sintaxis JS y la suite; el escáner
de publicación aplica además una lista de rutas permitidas y exclusiones
explícitas; revisión manual acotada de fuentes/fixtures que deja constancia de
que las expresiones regulares no son una prueba de privacidad; auditoría de
dependencias **aislada y limitada a las dependencias declaradas**, sin
actualizaciones y separando los avisos del entorno global.
RED previsto: ver Evidencia.
Verificación al cerrar: `python scripts/release_export.py --run-tests`,
`python -m unittest tests.test_release_scan tests.test_release_export`,
`python scripts/release_scan.py` y `python scripts/check_docs.py --tests`.
Dependencias: ninguna. **No autoriza a publicar, hacer push ni desplegar.**

Evidencia: 2026-10-10. RED por ausencia, igual que en
[TODO-SEC-002](#todo-sec-002--escaneo-de-secretos-previo-a-publicar): antes de la
tarea `python -m unittest tests.test_release_export` → `ModuleNotFoundError: No
module named 'tests.test_release_export'` (el script y su prueba no existían), y
el escáner no tenía ninguna política de rutas. GREEN:
- [release_export.py](scripts/release_export.py): exporta **exactamente** el set
  publicable (`git ls-files --cached --others --exclude-standard`) a un
  directorio (temporal del sistema por defecto; se **rechaza** un destino dentro
  del repositorio), verifica ausencia de ignorados/prohibidos
  (`.biblio-data/`, `.biblio-test-*`, `*.sqlite3`, `docs/HANDOFF*`, `.env`,
  claves, `__pycache__`), que el conjunto exportado es exactamente el listado, y
  aplica el escáner con su lista de rutas permitidas sobre el candidato. Después
  ejecuta **dentro** del candidato `check_docs.py --tests`, la importación del
  paquete y `node --check` de app.js/sw.js, y con `--run-tests` la suite
  completa; sin Node el paso queda `NOT_RUN`, nunca un pase. Sale 0/1/2 y borra
  el candidato salvo `--keep`.
- [test_release_export.py](tests/test_release_export.py) → **4 tests OK**: la
  exportación de un repo sintético con material ignorado copia solo lo público,
  el material plantado a mano en el destino se señala, el destino dentro del
  repo se rechaza y el candidato real del proyecto pasa con el HANDOFF y la BD
  locales ausentes.
- [release_scan.py](scripts/release_scan.py): lista de rutas permitidas de
  primer nivel (`ALLOWED_TOP_LEVEL`, hallazgo `path-not-allowlisted`), regla de
  nombre `private-handoff` (ficheros `HANDOFF*.md` aunque se trackeen) y
  exclusiones explícitas comentadas (tamaño y binarios, que sí pasan las reglas
  de nombre). `--no-allowlist` documentado para escanear solo contenido.
  [test_release_scan.py](tests/test_release_scan.py) → **19 tests OK** (6 nuevos:
  handoff trackeado, rutas fuera de dentro/de la lista, proyecto dentro de
  política y ausencia de ignorados en el set). Las 4 pruebas que inspeccionan el
  repo vivo con git se omiten (**skip**, no fallo) dentro de un candidato: allí
  no hay `.git` y su cobertura la aporta la exportación.
- **Candidato limpio real**: `python scripts/release_export.py --run-tests` →
  exit 0 sobre 73 ficheros: `PASS ausencia-ignorados`, `PASS conjunto-exacto`,
  `PASS release-scan (0 hallazgos)`, `PASS check-docs`, `PASS import-paquete`,
  `PASS node-app.js`, `PASS node-sw.js` y `PASS suite-unittest (OK, 5 skips
  justificados)`. El candidato no contiene `docs/HANDOFF-SOL.md`,
  `.biblio-data/` ni ningún `*.sqlite3`.
- **Auditoría de dependencias aislada** (2026-10-10): venv temporal en
  `%TEMP%\opencode\biblio-audit-venv` (fuera del repo) con **solo** las
  dependencias declaradas resueltas — `cryptography 50.0.2`, `webauthn 3.0.1`,
  `joserfc 1.7.5` + transitivas (`cbor2`, `cffi`, `pyasn1`, `pyOpenSSL`,
  `pycparser`) —; desinstalado el `pip` de arranque del venv y
  `python -m pip_audit --path <site-packages>` → **«No known vulnerabilities
  found»**, exit 0. El `pip` 24.2 del propio venv tenía 12 avisos
  (PYSEC-2026-…) y el escaneo del **entorno global** (119 paquetes) reporta 22
  avisos en 6 paquetes (`aiohttp`, `anyio`, `litellm`, `multidict`, `urllib3`,
  `virtualenv`): **ninguno** es dependencia del paquete; son herramientas del
  entorno y quedan separados. La auditoría consultó el servicio de avisos
  (OSV, vía pip-audit) el 2026-10-10. **Sin ninguna actualización**: no se
  tocaron `pyproject.toml`, el lock ni el entorno global.
- **Revisión manual acotada de privacidad** del candidato (73 ficheros de texto
  y assets generados): barrido de patrones (emails, DNI/NIE, teléfonos, IBAN,
  números tipo tarjeta, IPs, direcciones) → solo IPs de bucle (`127.0.0.1`),
  dominios de documentación (`.test`/`ejemplo.test`), identificadores de
  ficha del catálogo público (p. ej. `1553619074343`) y nombres de autoría
  bibliográfica pública en fixtures (p. ej. «Rafael Alberti» como autor de un
  título). Los campos de lector de los fixtures son sintéticos
  (`lenlec=12345678`, `nombre=PERSONA DE PRUEBA APELLIDO`) y los tokens OPAC
  son placeholders `THREADTOKEN0x`. `docs/absys-opac-protocol.md` declara sus
  ejemplos anonimizados y no se halló ningún token, credencial o dato de
  persona real. **Una expresión regular y una revisión manual acotada no son
  una prueba de privacidad**: no pueden demostrar la ausencia de todo dato
  personal ni reconocer formatos desconocidos; es una barrera más, no una
  certificación.
- Metadatos MIT en [pyproject.toml](pyproject.toml) (`license = {text = "MIT"}`,
  `readme = "README.md"`), alineados con el `LICENSE` existente. **No** se creó
  `CONTRIBUTING.md`: la revisión de README/SECURITY/docs no promete ese fichero
  (el README dirige a [testing.md](docs/testing.md)), así que crearlo sería
  alcance inventado.
- Comprobaciones de cierre: `python -m unittest tests.test_release_scan
  tests.test_release_export` → 23 OK; `python -m unittest discover -s tests
  -t .` → **329 OK**; `python scripts/check_docs.py --tests` → Docs OK;
  `python scripts/release_scan.py` → 73 ficheros, 0 hallazgos.
Límites: la auditoría depende de la base de avisos del servicio el día de la
consulta; la revisión de privacidad es acotada y manual; el candidato se validó
en Windows sobre el set publicable actual. Nada de esto publica, hace push,
despliega ni toca servicios remotos más allá de la consulta de avisos.

### TODO-PRIV-001 — Identidad de lector e identificadores de préstamo/reserva sintéticos y reglas del escaneo

**Estado:** `done`
**Prioridad:** P1
**Tipo:** privacidad/publicación
**Responsable:** ORCA-implementer MiMo
**Actualizado:** 2026-10-10
**Requisitos:** [NFR-DEV-001](docs/specification.md#nfr-dev-001),
[NFR-SEC-001](docs/specification.md#nfr-sec-001).

Origen: gate final de privacidad del candidato público (73 ficheros). El fixture
`tests/fixtures/my_library_renovable.html` conservaba identidad real de lector
—carné OPAC con y sin relleno de ceros, más nombre y apellidos en los marcadores
`lenlec`/`nombre`/`apellidos`— junto con el historial de préstamos de esa misma
página, y varias pruebas esperaban esos literales. La afirmación de
`TODO-PUB-002` de que «los campos de lector de los fixtures son sintéticos» era
cierta para `my_library_loans.html` y **falsa** para `my_library_renovable.html`.
El resto de candidatos se revisó con una búsqueda de la identidad y de sus
historiales ligados (fixtures, pruebas esperadas, fuentes, scripts y docs).

Aceptación:
- Ningún fichero del set publicable repite esa identidad ni los códigos de
  ejemplar de su historial de préstamo; los sustitutos son sintéticos y evidentes
  y conservan las relaciones que el parser explota: carné repetido con y sin
  relleno de ceros, nombre partido en dos spans que se une en el mismo valor,
  campo `CP<código>` derivado del código del préstamo e ids `lector_box…`,
  `abnRenov…` y `data-prbarc` coherentes entre sí.
- **Ampliación (revisión):** también son sintéticos el resto de identificadores
  privados de préstamo/reserva del candidato —los códigos de ejemplar de
  `my_library_loans.html` con sus `data-prppsq`, el `data-di`/`DI=` de la reserva
  de `my_library_with_reservation.html`, y los ejemplos `abnRenov…`/`CP…`/
  `data-cobarc…` de `biblio/parser.py` y `docs/absys-opac-protocol.md`—, con todas
  sus referencias derivadas actualizadas a la vez y las pruebas que las fijaban
  apuntando a los sintéticos. Los identificadores de ficha del catálogo
  (`TITN`, `data-bc`, `rebarc_`) se mantienen: son inventario público, no
  historial personal.
- Las pruebas que fijaban esos literales esperan ahora los sintéticos, sin
  debilitar aserciones ni cambiar el comportamiento del parser.
- `scripts/release_scan.py` añade la regla semántica `opac-reader-identity`:
  cualquier marcador `lenlec`/`nombre`/`apellidos` cuyo valor no esté en la lista
  de valores sintéticos se señala; los valores de los fixtures sintéticos pasan.
  RED reproducible en ambas direcciones antes del arreglo. La ampliación añade
  `opac-loan-identifier` con el mismo patrón para los identificadores de
  préstamo/reserva y su lista permitida.
- El reporte sigue siendo **solo regla, ruta y línea**, nunca el dato hallado, y
  la documentación declara explícitamente que la regla **no** es un detector de
  datos personales arbitrarios.
- Correcciones documentales del gate: README con el contrato **v6** y un arranque
  que describa con exactitud lo que pide el alta y el papel del email;
  [operations.md](docs/operations.md) distingue el escenario mkcert + passkeys de
  red local de los redirect que Google realmente acepta, y aclara que una dirección
  IP puede llevar un certificado válido sin ser por eso un RP ID de passkey
  aceptable.

RED previsto/observado: ver Evidencia.
Verificación al cerrar: `python scripts/check_docs.py --tests`,
`python -m unittest discover -s tests -t .`, `node --check` de app.js y sw.js,
`python scripts/release_scan.py` y `python scripts/release_export.py --run-tests`.
Dependencias: ninguna. **No autoriza a publicar, hacer push ni desplegar.**

Evidencia: **primera entrega** (2026-10-10, **histórica**: sus recuentos de
337 tests y 447 enlaces corresponden a ese corte intermedio, **no** al cierre
de la tarea; la evidencia final enmendada está al final de la ficha). SPEC previa:
criterios añadidos a
[NFR-DEV-001](docs/specification.md#nfr-dev-001) y esta ficha, antes de tocar
pruebas ni código.
RED 1 (regla inexistente), `python -m unittest tests.test_release_scan` →
exit 1, `FAILED (failures=3)` sobre 25 tests:
`AssertionError: 'opac-reader-identity' not found in []`,
`Lists differ: [] != ['opac-reader-identity', 'opac-reader-identity']` y
`AssertionError: 0 != 1 : un hallazgo debe dar código de salida 1`.
RED 2 (regla implementada, fixture aún sin sanear), mismos comandos → 3 fallos:
`test_publishable_set_has_only_synthetic_reader_fields` con **4 hallazgos**
`opac-reader-identity:tests/fixtures/my_library_renovable.html:19`, `:20`, `:21`
y `:22` (los dos carnés y los dos nombres) y
`test_project_publishable_set_is_clean` con los mismos 4; el tercer fallo era un
error propio del test (el valor sintético rellenado se construía con 10 dígitos
en lugar de 9) y se corrigió en el test, **no** en la lista permitida.
GREEN: fixture y expectativas sanitizadas →
`python -m unittest tests.test_release_scan` → 25 OK;
`python -m unittest tests.test_parser tests.test_renewal` → 89 OK.
Comprobaciones de cierre de esa primera entrega (**históricas**, hoy
superadas):
- `python scripts/check_docs.py --tests` → exit 0, Docs OK: 16 documentos,
  23 requisitos, 42 tareas, 447 enlaces y 337 tests.
- `python -m unittest discover -s tests -t .` → exit 0, **337 tests OK**
  (168,6 s; base previa 331).
- `node --check biblio/static/app.js` y `node --check biblio/static/sw.js` → 0.
- `python scripts/release_scan.py` → exit 0, **73 ficheros, 0 hallazgos**.
- `python scripts/release_export.py --run-tests` → exit 0: `PASS
  ausencia-ignorados`, `PASS conjunto-exacto`, `PASS release-scan`,
  `PASS check-docs`, `PASS import-paquete`, `PASS node-app.js`,
  `PASS node-sw.js` y `PASS suite-unittest (OK, skipped=6)`.
- `python scripts/check_web_browser.py --channel msedge` → exit 0 (se ejecutó
  porque cambió un fichero de `biblio/`, aunque solo un comentario de docstring:
  sin errores JS ni desbordamiento móvil).
- Búsqueda final en el set publicable de la identidad, sus apellidos y sus
  códigos de préstamo: **0 coincidencias** (solo queda el titular de la licencia
  `jabaruben/BiblioCM`, atribución pública preexistente).
Límites de la primera entrega: la regla `opac-reader-identity` solo cubre los
marcadores `lenlec`/`nombre`/`apellidos` y no detecta datos personales
arbitrarios; `.playwright-mcp/` se consultó solo para localizar originales y
**no** se modificó, igual que `.biblio-data/`; el único cambio en `biblio/` fue
un comentario de docstring (sin comportamiento nuevo), y el escenario de
navegador se ejecutó aun así → exit 0. Observación abierta para decisión, sin
tocar: `scan_main` de `release_scan.py` no aplica la lista de rutas permitidas y
su cabecera menciona un `--no-allowlist` inexistente; la aplican
`release_export.py` y las pruebas, así que la validación del candidato queda
cubierta (pertenece al alcance de `TODO-PUB-002`).

**Ampliación tras revisión (2026-10-10):** un bloque de lector sintético no
bastaba: los códigos de ejemplar de las filas de préstamo y el id de la reserva
son historiales personales reales y seguían en fixtures, en un docstring del
parser y en el protocolo. Alcance nuevo, misma ficha:
- `tests/fixtures/my_library_renovable.html`: sus dos códigos → `9000000011` y
  `9000000012`, con todas las referencias derivadas (`lector_box…`,
  `lector_renovMen…`, `abnRenov…`, `data-cobarc`, `data-prbarc`, `CP<código>`)
  actualizadas a la vez.
- `tests/fixtures/my_library_loans.html`: sus tres códigos → `9000000021`,
  `9000000022` y `9000000023`, y `data-prppsq` → `9001`.
- `tests/fixtures/my_library_with_reservation.html`: `data-di` y `DI=` de la
  reserva → `9000001`.
- Ejemplos de fuente/docs: el formulario de renovación de `biblio/parser.py` y
  de [docs/absys-opac-protocol.md](docs/absys-opac-protocol.md) → `9000000002`;
  la tabla `prbarc` → `9000000021`; el ejemplo `rebarc_` → `9000000003`
  (coherente con `reservable_copies.html`).
- Las pruebas que fijaban esos valores apuntan ahora a los sintéticos, con las
  mismas aserciones y sin reducir ningún recuento de comportamiento.

RED 2026-10-10 (regla nueva): `python -m unittest tests.test_release_scan` →
exit 1 con **4 fallos** antes de implementar `opac-loan-identifier`
(`'opac-loan-identifier' not found in []`, listas vacías frente a los hallazgos
esperados de barcode, reserva y referencias derivadas, y `0 != 1` en el
reporte). Con la regla y **sin** sanitizar → **28 hallazgos** en
`biblio/parser.py:74-77`, `docs/absys-opac-protocol.md:147-150`,
`tests/fixtures/my_library_loans.html`, `my_library_renovable.html`,
`my_library_with_reservation.html` y `tests/test_parser.py:429-430` (RED que
reproduce la fuga; el reporte solo da regla, ruta y línea). GREEN: sanitizado →
verde.
Comprobaciones de cierre de la ampliación:
- `python -m unittest tests.test_release_scan` → exit 0, **31 tests OK**.
- `python -m unittest tests.test_parser tests.test_renewal` → exit 0, **89 OK**.
- `python -m unittest discover -s tests -t .` → exit 0, **343 tests OK** (166,8 s).
- `python scripts/check_docs.py --tests` → exit 0, Docs OK: 16 documentos,
  23 requisitos, 42 tareas, 462 enlaces y **343 tests**.
- `python scripts/release_scan.py` → exit 0, **73 ficheros, 0 hallazgos**.
- `python scripts/release_export.py --run-tests` → exit 0 (ocho PASS,
  `suite-unittest OK (skipped=7)` por no haber `.git` en el candidato) y
  `python scripts/check_web_browser.py --channel msedge` → exit 0, repetido tras
  la ampliación.
- Búsqueda explícita de los 16 valores originales/relacionados (identidad,
  carnés y códigos ligados) sobre el set publicable → **0 coincidencias** en 73
  ficheros; `rg -i` de los nombres solo encuentra el titular de la licencia
  `jabaruben/BiblioCM`.
Límites: las dos reglas cubren solo esos marcadores y no detectan datos
personales arbitrarios; los identificadores de ficha del catálogo (`TITN`,
`data-bc`, `rebarc_` de `record_copies.html`) y los títulos/signaturas se
conservan por ser inventario y datos bibliográficos públicos, no historial de
una cuenta.

**Evidencia final enmendada (cierre de la tarea, 2026-10-10):** sustituye a los
recuentos de la primera entrega marcados arriba como históricos. Totales
definitivos: **343 tests** —no 337, que fue el corte intermedio—; el escáner de
publicación aplica **dos reglas semánticas** (`opac-reader-identity` y
`opac-loan-identifier`) además de sus reglas de material privado, la lista de
rutas permitidas y las exclusiones sobre **73 ficheros**, con **0 hallazgos**.
Última pasada completa:
- `python -m unittest discover -s tests -t .` → exit 0, **343 tests OK**;
- `python -m unittest tests.test_release_scan tests.test_parser tests.test_renewal`
  → exit 0, **120 tests OK**;
- `python scripts/check_docs.py --tests` → exit 0, Docs OK con 16 documentos,
  23 requisitos, 42 tareas, **462 enlaces** y 343 tests;
- `python scripts/release_scan.py` → exit 0, **73 ficheros, 0 hallazgos**;
- `python scripts/release_export.py --run-tests` → exit 0 (ocho PASS,
  `suite-unittest OK (skipped=7)`);
- `node --check` de `biblio/static/app.js` y `biblio/static/sw.js` → 0;
- `python scripts/check_web_browser.py --channel msedge` → exit 0.
Tarea cerrada en `done`: aceptación cumplida y verificada. El cierre **no**
autoriza a publicar, hacer push ni desplegar.

### TODO-OPS-003 — Guía HTTPS local válida (Caddy multiline y nombre DNS de red)

**Estado:** `done`
**Prioridad:** P2
**Tipo:** operación/docs
**Responsable:** ORCA-implementer MiMo
**Actualizado:** 2026-10-10
**Requisitos:** [NFR-SVC-003](docs/specification.md#nfr-svc-003).

Origen: [operations.md](docs/operations.md) mostraba el `Caddyfile` de ejemplo en
**una sola línea** con sintaxis de PowerShell (`$env:USERPROFILE\...`) dentro del
fichero de Caddy: no es un `Caddyfile` válido y nunca se pudo probar. Además
proponía `127.0.0.1:8443` como sitio, inservible para passkeys desde el móvil
(Chromium rechaza un RP ID con forma de IP) y no explicaba cómo resuelve el
teléfono el nombre ni en qué dispositivo confía.
Aceptación: muestra canónica **multiline** correcta (`{$USERPROFILE}` de Caddy),
nombre DNS **estable de red local** (no IP) como RP ID/passkey, certificado
mkcert emitido para ese nombre + `BIBLIO_TRUSTED_ORIGINS` y
`BIBLIO_GOOGLE_REDIRECT_URI` coincidentes, prerrequisitos explícitos de
resolución en el teléfono y de confianza en la CA local de mkcert en el
teléfono, sin exigir dominio público de pago; `caddy validate` se ejecuta si
`caddy` está instalado y, si no, se declara como no ejecutado.
RED previsto: no aplica (solo documentación).
Verificación al cerrar: `python scripts/check_docs.py --tests`, revisión de los
comandos y `caddy validate` si `caddy` existe en el PATH.
Dependencias: ninguna.

Evidencia: 2026-10-10. Solo documental: sin cambios de producto ni de API.
- [operations.md](docs/operations.md#https-local-con-mkcert-recomendado-para-móvil)
  reescrito: la línea única del `Caddyfile` con sintaxis de PowerShell se
  sustituyó por la muestra canónica **multiline**
  (`biblio.lan:8443 { tls "{$USERPROFILE}/…" … reverse_proxy 127.0.0.1:8000 }`,
  con la variable `{$USERPROFILE}` que expansiona Caddy, no `$env:`), prerrequisitos
  numerados (nombre DNS estable de red —no IP—, resolución del nombre desde el
  teléfono, mkcert y proxy instalados), certificado mkcert emitido para
  `biblio.lan localhost 127.0.0.1`, `BIBLIO_TRUSTED_ORIGINS` y
  `BIBLIO_GOOGLE_REDIRECT_URI` coincidentes con ese nombre, y el paso de
  confianza de la CA local de mkcert **en el teléfono** (`mkcert -CAROOT` →
  instalar `rootCA.pem`), con la aclaración de que no hace falta ningún dominio
  público de pago. Se conservó el aviso de ficheros privados
  (`cert.pem`/`key.pem`/`rootCA.pem`) ignorados por el `.gitignore`.
- `caddy` **no** está instalado en esta máquina (`Get-Command caddy` → vacío) y
  `mkcert` tampoco: `caddy validate` y la instalación de la CA quedan como
  **NOT_RUN declarado**, no como pase; la guía lo dice explícitamente. El
  contenido del Caddyfile de muestra se revisó manualmente contra la sintaxis
  documentada de Caddy (sitio con llaves, directivas en líneas propias,
  placeholders `{$VAR}`), sin ejecutarlo.
- `python scripts/check_docs.py --tests` → Docs OK (enlaces y anclas de la
  sección nueva válidos).

## Propuestas: decidir antes de implementar

### TODO-LINK-001 — Permisos por carné individual

**Estado:** `proposed`
**Prioridad:** P2
**Tipo:** producto/datos
**Responsable:** sin asignar
**Actualizado:** 2026-10-05
**Requisitos:** cambio propuesto de FR-LINK-001 / FR-LINK-002.

Decidir política de nuevas cuentas y compatibilidad con las concesiones de titular
completo actuales. Requiere ADR, esquema/migración y aceptación por usuario; no
reducir ni ampliar silenciosamente autorizaciones existentes mediante un refactor.

### TODO-OPS-001 — Hosting HTTPS reproducible

**Estado:** `proposed`
**Prioridad:** P2
**Tipo:** operación
**Responsable:** sin asignar
**Actualizado:** 2026-10-05
**Requisitos:** evolución de NFR-SVC-001 / FR-PWA-001.

Decidir destino de despliegue, proxy/Host, almacenamiento/clave, proceso único y
gestión de sesiones/limits. Aceptación futura: configuración reproducible, rollback,
backup probado y comprobación móvil. No hay proveedor ni publicación aprobada en este backlog.

### TODO-NOTIFY-001 — Recordatorios

**Estado:** `proposed`
**Prioridad:** P3
**Tipo:** producto
**Responsable:** sin asignar
**Actualizado:** 2026-10-05
**Requisitos:** nueva especificación pendiente; no implementado en FR-PWA-001.

Decidir canal, opt-in, horario, permisos de cuentas compartidas y tratamiento de
errores de credenciales. No hay scheduler/push; documentar alcance antes de elegir
workers/dependencias. No incluye renovación automática por defecto.

### TODO-CAT-003 — Metadatos MARC que la UI no muestra

**Estado:** `proposed`
**Prioridad:** P3
**Tipo:** producto/UI
**Responsable:** sin asignar
**Actualizado:** 2026-10-05
**Requisitos:** extensión propuesta de FR-CAT-001.

Origen: auditoría de capacidades 2026-10-05. El DTO de búsqueda ya devuelve
`subjects`, `language`, `classification`, `doc_type`, `openurl` y `raw_marc`, y
la UI solo pinta título, autor, publicación, año, soporte, resumen e ISBN.
Decidir qué campos aportan valor y en qué superficie (lista o detalle) antes de
tocar la UI. Aceptación por acordar: usar campos ya presentes, sin cambio de
contrato y sin romper el render actual ni la paginación.
RED previsto: contingente a la aceptación y a la especificación; una vez
acordados los campos y la superficie, prueba que exija esos datos visibles ahí.
No se escribe hoy: el alcance sigue sin aprobar, así que una prueba ahora
inventaría comportamiento.
Dependencias: decisión de producto (salir de `proposed` y extender FR-CAT-001
antes de codificar); los campos ya están en el DTO, así que sin cambio de
contrato; relación con TODO-CAT-004 para no repetir decisiones de catálogo.

### TODO-CAT-004 — Facetas y disponibilidad por resultado

**Estado:** `proposed`
**Prioridad:** P3
**Tipo:** producto/motor
**Responsable:** sin asignar
**Actualizado:** 2026-10-05
**Requisitos:** extensión propuesta de FR-CAT-001.

Origen: el portal ofrece facetas (autor, título, materia, año, idioma, tipo) y la
lista de resultados no trae disponibilidad; nuestro motor/API/UI no las usan
([protocolo](docs/absys-opac-protocol.md) §4.4 y §4.3). Exige decidir el contrato
con el OPAC siguiendo href del último HTML, el alcance API/UI y el coste de
peticiones. Aceptación por acordar: sin romper la navegación actual
(TODO-CAT-002) ni convertir una búsqueda en scraping masivo; «disponible después
de X» no cuenta como disponible ahora.
RED previsto: contingente a la aceptación y a la especificación; después de
definir el contrato, prueba con fixture de facetas que exija seguir los href del
último HTML (sin tratar DOC como número de página) y que la disponibilidad del
listado no se lea como «disponible ahora». No se escribe hoy: el alcance sigue
sin aprobar, así que una prueba ahora fijaría un contrato que no está decidido.
Dependencias: decisión de producto y de contrato con el OPAC, con especificación
previa de FR-CAT-001; alineación con TODO-CAT-002 para no duplicar la
navegación por páginas; coste de peticiones pendiente de decidir. Ninguna otra
tarea del backlog la bloquea.

### TODO-UX-002 — Metadatos de panel sin mostrar

**Estado:** `proposed`
**Prioridad:** P3
**Tipo:** producto/UI
**Responsable:** sin asignar
**Actualizado:** 2026-10-05
**Requisitos:** extensión propuesta de FR-PANEL-001 / FR-RES-002.

Origen: auditoría de capacidades 2026-10-05. La API ya entrega `signature`,
`branch_address` y `branch_code` en préstamos; `signature`, `created` y
`record_id` en reservas; `card_expires` en el lector. La UI muestra fecha, días,
estado, biblioteca, expiración de reserva y avisos de lector.
Decidir qué metadatos ayudan (p. ej. signatura para localizar el libro en sala o
enlace de la reserva a su ficha) antes de modificar tarjetas. Aceptación por
acordar: conservar atribución por cuenta, orden por urgencia y legibilidad móvil.
RED previsto: contingente a la aceptación y a la especificación; una vez
decididos los metadatos y dónde se muestran, prueba de navegador que exija esos
datos en la tarjeta correspondiente. No se escribe hoy: el alcance sigue sin
aprobar, así que una prueba ahora elegiría campos por cuenta propia.
Dependencias: decisión de producto y extensión de FR-PANEL-001 / FR-RES-002
antes de codificar; los campos ya existen en el API, así que sin cambio de
contrato; no depende de otras tareas del backlog.

### TODO-API-001 — OpenAPI con verificación de DTOs

**Estado:** `proposed`
**Prioridad:** P3
**Tipo:** contrato/herramientas
**Responsable:** sin asignar
**Actualizado:** 2026-10-05
**Requisitos:** evolución de NFR-DEV-001 / NFR-SVC-001.

Fuente actual: contrato Markdown en docs/api.md. Decidir generación o fichero
canónico OpenAPI; probar DTO/status/header frente al servidor y evitar dos contratos
que diverjan. No existe Swagger/runtime OpenAPI actualmente.

## Plantilla para nuevas tareas

Copiar fuera de este bloque, asignar ID numérico único y añadir fila al índice:

```markdown
### TODO-AREA-NNN — Título específico

**Estado:** `proposed`
**Prioridad:** P2
**Tipo:** bug / funcionalidad / prueba / docs / operación
**Responsable:** sin asignar
**Actualizado:** YYYY-MM-DD
**Requisitos:** ID existente o propuesta de nueva especificación.

Origen/evidencia: síntoma observado o deducción por inspección; ficheros afectados.
Aceptación: resultado concreto comprobable.
RED previsto/observado: test y motivo del fallo.
Verificación al cerrar: comandos, resultado, alcance y omisiones.
Dependencias/bloqueo: tarea o decisión y siguiente acción.
```
