# Frontend y PWA

Fuentes: [index.html](../biblio/static/index.html), [app.js](../biblio/static/app.js),
[styles.css](../biblio/static/styles.css), [sw.js](../biblio/static/sw.js) y
[manifest](../biblio/static/manifest.webmanifest). Contrato: [api.md](api.md).

## Tecnología y navegación

HTML, CSS y JavaScript nativos, sin compilación ni framework. Un documento con
secciones ocultables; no hay router SPA, URLs por pantalla ni deep links.
La UI está en español. `node()` crea elementos y asigna `textContent`, no HTML
remoto. Portadas: catálogo, préstamos y reservas pintan la imagen que trae
`cover_url` sobre la inicial del título; si no hay, no se reconoce o falla, queda
la inicial.

| Área | IDs / funciones principales | Comportamiento |
|---|---|---|
| Acceso | `welcome`, `login`, `register`, `recovery`, `enter`, `showSession` | Usuario BiblioCM o email verificado; recuperación en dos pasos |
| Identidad | `email-form`, `email-verify`, `password-form` | Verificar email y cambiar contraseña desde Configuración |
| Cabecera | `greeting`, `reader-info`, `logout`, `refresh` | Identidad, número de cuentas y actualización |
| Carga | `boot-loading`, `library-loading`, `setLibraryLoading`, `beginLoading`/`endLoading` | Estado `role="status"` + `aria-busy` + spinner del arranque y del panel |
| Panel | `stats`, `account-filter`, `loadLibrary`, `renderLibrary` | Agregación, selección y urgencia |
| Préstamos | `loans`, `loan-list` | Fecha/días/estado, renovar si procede |
| Reservas | `reservations`, `reservation-list` | Estado y anulación con confirmación |
| Catálogo | `catalog`, `catalog-account`, `search`, `results`, `pagination` | Cuenta elegida y páginas |
| Detalle | `detail`, `detail-content`, `reservable-options`, `detail()` | Lista completa y reservables separados |
| Configuración | `settings`, `link-account`, `request-access`, `linked-accounts` | Carnés y solicitudes |
| Relaciones | `incoming-requests`, `outgoing-requests`, `request-count`, `decide()` | Aprobar, rechazar, cambiar o retirar |
| Mensajes | `notice`, `notify`, `busy` | aria-live, errores, bloqueo del botón activo con `aria-busy` y progreso (`data-pending-text`) |

## Estado en memoria

- `csrf`, `currentUser`: identidad/capacidad de escribir en esta sesión web.
- `libraryData`, `accountList`: snapshot de panel y permisos accesibles.
- `editAccount`: carné propio que se está actualizando.
- `page`, `query`, `records`, `searchAccount`: navegación del catálogo.
- `searchGeneration`: descartar respuestas de búsquedas/cambios de cuenta anteriores.
- `sessionGeneration`: descartar respuestas pendientes después de cerrar sesión.
- `libraryLoadId`: identificar la carga de panel más reciente; solo ella puede
  retirar el estado de carga, y una carga de una sesión cerrada no toca la UI.
- `loadingSeq`: adjudicación del estado de carga. Cada fase que lo enciende
  (`enter`, `refresh`, `loadLibrary`) recibe un token con `beginLoading()` y lo
  apaga en su `finally` con `endLoading(token)`; si otro token es más reciente
  no hace nada. `showSession(false)` lo incrementa y lo apaga, así que ninguna
  respuesta de una sesión cerrada puede reencenderlo.
- `settingsBusy`: impedir solapamiento de las actualizaciones periódicas de permisos.

No hay almacenamiento de estas estructuras en localStorage/IndexedDB. No hay
guard global de orden de respuestas de `library`, ni identificador independiente
de cada apertura de detalle; las carreras pendientes están registradas en el backlog.

## Arranque y autenticación

1. Registrar SW si existe esa API de navegador.
2. Antes de nada se muestra `#boot-loading` (región `role="status"` con
   `aria-live`, texto «Comprobando tu sesión…» y spinner) y `#welcome` está
   `hidden` en el HTML: una sesión autenticada no destalla el formulario de
   acceso mientras se resuelve. Si JavaScript está deshabilitado, un
   `<noscript>` explica que la aplicación lo necesita.
3. GET session; comprobar header de versión **en cada respuesta**, no solo al iniciar.
4. Si hay sesión: cargar settings y library con el panel en estado de carga.
   Sin sesión (o sin panel resuelto) se vuelve al acceso. En los dos casos
   `showSession()` retira `#boot-loading` y el `finally` del arranque lo
   garantiza igualmente.
5. Sin carnés accesibles: mostrar Configuración.
6. Logout/401 limpia datos, selectores, formularios y detalle; vuelve al acceso.

Una versión incompatible muestra aviso persistente y bloquea los formularios de
acceso al detectar incompatibilidad durante arranque. `401` de login/registro
se trata como error de esos formularios, no como logout de una identidad nueva.
`422` OPAC es un problema de credenciales del carné, no de la contraseña BiblioCM.

## Identidad: email verificado y contraseñas (FR-AUTH-002 / FR-AUTH-003)

- **Acceso**: `#username` admite username o email verificado (máx. 254); el
  formulario de acceso alterna con `#register` y con `#recovery`
  (`#show-recovery`/`#recovery-back`), y `showSession(false)` los resetea.
- **Recuperación** (`#recovery`, dos pasos): `#recovery-send` pide el código
  (`auth/password/recovery/request`) y muestra `#recovery-reset`;
  `#recovery-confirm` lo consume con la contraseña nueva y vuelve al acceso.
  El mensaje del servidor es idéntico exista o no el email: la UI no lo
  distingue.
- **Configuración**: `#email-form` pide el código (`auth/email/request`) y
  pinta el estado pendiente en `#email-state` (el servidor no cambia el usuario
  hasta consumir el código, así que ese texto se actualiza en el cliente y
  `loadSettings` lo confirma tras verificar); `#email-verify` consume el código.
  `#password-form` cambia la contraseña desde la sesión (`auth/password/change`)
  y avisa de que las demás sesiones se cierran.
- Los códigos llegan por correo: la UI nunca los genera ni los adivina, y el
  campo `#email-token` no es `required` porque está oculto hasta pedir el
  código (un `required` dentro de un `hidden` bloquea el envío del formulario
  en Chromium). El servidor valida el código vacío con el mismo 400 genérico.
- El estado del email (`#email-state`) sale de `user.email`/`user.email_verified`
  de `settings`; tras logout todo vuelve al reposo.

## Passkeys y acceso con Google (FR-AUTH-004 / FR-AUTH-005)

- **Contexto seguro**: `passkeysUsable()` exige `window.isSecureContext`, la API
  `PublicKeyCredential` y un hostname que **no** sea una IP literal (Chromium
  rechaza un RP ID con forma de IP). Fuera de eso, `#passkey-add` queda
  `disabled`, la fila `#passkey-login-row` se oculta y `#passkey-help` explica
  el motivo; el aviso de origen no confiable (`#origin-warning`) sigue siendo la
  señal general (NFR-SVC-003).
- **Añadir passkey** (`#passkey-add` en Configuración): llama
  `auth/passkeys/register/options`, traduce los base64url del API a
  `ArrayBuffer` (`creationOptions`), usa `navigator.credentials.create` y
  envía el resultado a `auth/passkeys/register` con `label`
  (`#passkey-label`, opcional). El servidor puede responder
  `code:"reauth_required"` y entonces se abre el diálogo `#reauth`.
- **Diálogo de reautenticación** (`#reauth`): pide la contraseña con
  `auth/reauth` y, resuelto, reanuda la acción interrumpida (`withReauth`);
  cancelarlo rechaza la promesa y no se ejecuta ninguna mutación. Es el único
  lugar donde la UI actúa por el campo estable `code` del error.
- **Login con passkey** (`#passkey-login`): `auth/passkeys/login/options` +
  `navigator.credentials.get` + `auth/passkeys/login`; el servidor rota la
  sesión igual que en el login por contraseña y la UI entra con `enter`.
- **Listado**: `settings.passkeys` pinta `#passkey-list` con etiqueta, fecha y
  un botón de borrado que vuelve a pedir reautenticación.
- **Google**: `session.google.enabled` decide si se muestran
  `#google-login`/`#google-signup` (acceso) y `#google-link`/`#google-unlink`
  (Configuración). Son navegaciones de ida (`location.assign(authorize_url)`),
  no peticiones del API; el retorno llega como `/?google=…`, se traduce a un
  aviso y se limpia la URL con `history.replaceState` sin exponer el `state`,
  que el servidor ya consumió. Vincular/desvincular pasa por `withReauth`.
- Nada de passkeys ni de Google se persiste en el navegador: no hay datos en
  localStorage, la cookie sigue siendo la de sesión y el service worker sigue
  sin interceptar ninguna ruta `/api/`.

## Panel y operaciones

Las tarjetas y contadores se derivan del snapshot devuelto por el backend.
El filtro afecta préstamos, reservas y estadísticas. «Vencen en 3 días» cuenta
`days_left<=3`, incluyendo retrasos; la leyenda lo explica. Fecha visual:
DD/MM/YYYY con `Intl`, interpretando una fecha sin hora a mediodía local para no
moverla de día por conversiones de zona.

- Atribución: etiqueta del carné; para autorizadas añade `@username` del titular.
- Read: se muestran datos, pero no botones de renovar/anular/reservar.
- Manage: acciones sujetas también al estado del portal; el servidor vuelve a autorizar.
- Renovar: POST → nueva library → encontrar `(account.id,barcode)` → mensaje con
  `due_date`/`days_left` del mismo préstamo que se acaba de renderizar.
- Si la cuenta ya no aparece tras renovar, se conserva el mensaje verificado del
  resultado como fallback; no se inventa un contador local.
- Crear/anular reserva requiere `confirm()`; renovar actualmente es una acción
  directa sin diálogo adicional.
- Mientras el POST de renovación sigue en vuelo, el botón muestra
  «Renovando…» con `aria-busy="true"` y la misma frase se anuncia en
  `#notice` (`role="status"`); `disabled` impide un segundo clic, así que la
  operación sigue siendo un único envío. El aviso de éxito solo llega después
  de refrescar el panel y encontrar `(account.id,barcode)`; si la petición
  falla o la respuesta no llega, se notifica el error y no se reintenta.

`busy` desactiva solo el botón invocado y marca `aria-busy` mientras dura; si
la acción declara `data-pending-text`, cambia el texto del botón a ese
progreso y lo anuncia en el aviso, restaurándolo después. No es una cola global
de mutaciones ni una política de retries: un fallo del `fetch` se notifica una
vez y la mutación no se vuelve a enviar. Fetch no tiene AbortController ni
timeout explícito, así que no existe un tiempo límite que inventar.

Estado de carga del panel (`FR-PANEL-001`):
1. `#library-loading` es una región viva con spinner y texto «Cargando tu
   biblioteca…» y marca `aria-busy="true"` en `#dashboard`. Se enciende con
   `beginLoading()`, que devuelve un token.
2. El ciclo `reloadPanel()` = `loadSettings()` + `loadLibrary()` enciende ese
   estado **desde la primera petición**, así que cubre login, restauración y
   «Actualizar», no solo la llamada `library`. `loadLibrary()` enciende el suyo
   propio para los refrescos que la llaman directamente (renovación, decisión
   de enlaces, refresco periódico).
3. Se retira con `endLoading(token)` en el `finally` **solo** si sigue siendo
   el token más reciente y la sesión no ha cambiado: así una respuesta vieja no
   puede reanunciar la carga ni dejar el panel «cargando» sobre otro ya resuelto.
4. `showSession(false)` (logout, 401 o arranque sin sesión) incrementa
   `libraryLoadId` y `loadingSeq`, retira el estado y deja a esa carga en vuelo
   sin tocar la UI; su error de sesión cambiada se descarta en lugar de avisar.
5. Un error de red o de API de la sesión vigente se retira igual y sigue
   propagándose a `busy()`, que lo notifica. Si `enter()` termina sin ningún
   `libraryData`, se vuelve al acceso en lugar de dejar un dashboard vacío.
   Al recargar la página el estado vuelve a su reposo (`hidden`,
   `aria-busy="false"`).
6. `loadSettings()` compara su `sessionGeneration` antes de pintar y devuelve
   `false` si la respuesta ya no pertenece a la sesión vigente: una respuesta
   obsoleta no repuebla el panel ni publica «La sesión ha cambiado.» en el aviso.
7. El spinner es una única regla CSS compartida por `#boot-loading` y
   `#library-loading`: bloque `display:flex` con caja dibujada dentro del
   viewport (comprobado en escritorio y móvil antes de resolver la sesión).
   Con movimiento normal gira con `spin .8s linear infinite`; con
   `prefers-reduced-motion: reduce` la regla posterior anula la animación
   (`animation:none`), así que el anillo y el texto permanecen visibles como
   indicador estático sin rotación continua. El selector
   `@media(prefers-reduced-motion:no-preference)` del resto de la hoja (por
   ejemplo `.book`) sigue aplicándose igual.

## Catálogo y detalle

La selección de cuenta se captura junto al resultado y los callbacks del detalle.
Cambiarla invalida búsqueda/detalle. El soporte (`extent`) distingue fichas de
ediciones; no combinar registros que tengan un título parecido.

Paginación: anterior bloqueada en página 1; siguiente bloqueada tras una página
vacía, no por cálculo de última página a partir de total. Falta UX de fin fiable.

Portadas:
1. `book()` y el detalle aceptan `cover_url`; solo se pinta si coincide con
   `/api/cover?account=…&record=…` (`COVER_URL`). Una URL del proveedor, de otro
   dominio o `javascript:` se ignora y conserva la inicial: así una respuesta
   antigua no puede meter un token ni un origen ajeno en el DOM.
2. La imagen se crea con `loading="lazy"` y `decoding="async"`, se superpone a la
   inicial con `object-fit: contain` (sin recortar la portada) y, si falla, se
   retira sola con `error`: no queda un hueco ni se reintentan peticiones.
3. `alt=""`: es decorativa porque el título ya está en el texto de la tarjeta o
   en el encabezado del diálogo.
4. El service worker no intercepta `/api/cover` (fuera de la whitelist), así que
   la portada no entra en la caché del shell.
5. Se pinta también en las tarjetas de préstamos y reservas, con la misma regla
   y el mismo respaldo. La ruta viene del DTO (`account` + `record_id`); si el
   préstamo no trae registro, `cover_url` va vacío y queda la inicial. El panel
   no lanza peticiones de ficha: solo el navegador pide cada portada visible.

Detalle:
1. Consultar `copies` y mostrar resumen + todos los ejemplares.
2. Si manage, permitir consultar `reservable` conservando el apartado completo.
3. Validar biblioteca/sucursal del DTO; no mostrar `copy.row` ni reconstruir un
   fragmento de HTML antiguo.
4. Mostrar cada opción con ubicación/signatura/tipo/disponibilidad.
5. Al reservar, enviar cuenta, registro, índice y barcode capturados.

Un ejemplar disponible ahora puede no figurar como reservable. Las opciones son
las que ofrece el portal para la ficha y cuenta, no un inventario universal de la red.

## Configuración y actualización de permisos

El editor de carné pide etiqueta, carné y password OPAC al añadir; al actualizar
oculta carné y envía ID/etiqueta/password. Se limpian claves tras guardar.
Carnés ajenos autorizados no ofrecen edición de credenciales ni desvinculación directa.

Solicitudes: selector `read`/`manage` al solicitar y al aprobar/cambiar. La página
explica que aprobar comparte carnés directos presentes/futuros, sin transitividad.
La lista muestra también estados cerrados de las relaciones actuales; esto no
es un histórico de eventos, porque la BD sobrescribe la misma relación al reabrirla.

Se consultan permisos al abrir Configuración, pulsar Actualizar, volver a una
pestaña visible y cada 60 s si está visible. Se consulta el portal de nuevo al
detectar cambio de cuentas/permisos/etiquetas, no en cada tick sin cambios.
Estas peticiones mantienen activo el TTL de la sesión: «una hora sin peticiones»
no equivale a «una hora sin hacer clic» mientras la pestaña siga consultando.

## PWA y caché

Manifest: scope/start_url/id `/`, display standalone, lang es, iconos PNG 192/512
con purpose any/maskable. Generación: [generate_icons.py](../scripts/generate_icons.py).
El icono SVG sirve como favicon; en iOS se referencia apple-touch-icon PNG.

SW actual: cache `bibliocm-shell-v10`; whitelist de `/`, index, CSS, JS, manifest e
iconos. Install precachea, activate borra versiones anteriores del mismo prefijo;
fetch GET del mismo origen usa red y solo cae a caché si falla la red.
No intercepta API ni otros recursos. Una respuesta HTTP de error no es lo mismo
que un fallo de red. El cache no se refresca tras cada fetch exitoso: al cambiar
assets hay que revisar/incrementar la versión del shell.

Android/Chrome puede emitir `beforeinstallprompt`; iPhone usa el flujo manual
de Safari. La UI muestra instrucciones. No hay notificaciones push, sync de
mutaciones offline, APK, IPA ni publicación en stores. Validación física móvil
y pruebas de instalación/offline completo siguen pendientes.

## Verificación y extensión

[check_web_browser.py](../scripts/check_web_browser.py) comprueba dos contextos
aislados con Edge y viewport móvil, permisos, panel, estado de carga accesible
(arranque/restauración, login, refresco, error de `library` y logout con
respuesta en vuelo de `library` y de `settings`), renovación
antes/después de recarga, filtro, portadas de catálogo, préstamo y reserva
(cargada, rota y URL antigua sin pintar), reserva simulada y revocación.
No acredita Safari, Android físico ni auditoría WCAG.
Los escenarios de carga **retienen** la petición en el enrutador de Playwright
(`hold`/`wait_held`/`release_held`) en vez de dormir dentro de él: un
`time.sleep` en un enrutador bloquea las aserciones y las vuelve una carrera.
[testing.md](testing.md) explica cuándo usar una regresión de navegador.

Si se modulariza JavaScript, preservar IDs y contratos o actualizar las pruebas;
registrar un nuevo asset en la whitelist del servidor y del SW. No introducir un
framework de UI para solucionar una fecha o un selector.
