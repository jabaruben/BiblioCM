# Especificación de producto — SDD

Base aceptada a **2026-10-07** (FR-PANEL-001, FR-CAT-001 y NFR-SEC-001 ampliados
el 2026-10-07; resto aceptado el 2026-10-05). Estado de implementación y evidencia en
[status.md](status.md); trabajo pendiente en [TODO.md](../TODO.md).

## Objetivo y alcance

Un único acceso a BiblioCM permite consultar y gestionar préstamos, reservas y
catálogo de las Bibliotecas de la Comunidad de Madrid para varios carnés.
La aplicación es una **PWA** con backend Python. Android/iPhone usan el navegador
y, donde esté disponible, instalación en pantalla de inicio. Una app nativa,
notificaciones o un despliegue público no forman parte de la base entregada.

## Vocabulario obligatorio

- **Usuario BiblioCM:** identidad local con nombre de usuario y contraseña propia.
- **Carné / cuenta de biblioteca:** credenciales del portal OPAC vinculadas a un usuario.
- **Titular de la vinculación:** usuario BiblioCM que guardó ese carné; no implica
  que sea la persona cuyo nombre figura en el carné.
- **Solicitante:** usuario BiblioCM que pide acceso a otro usuario.
- **Registro:** ficha bibliográfica `record_id`; distintas ediciones pueden ser registros distintos.
- **Ejemplar:** copia física identificada por `barcode`; puede tener una signatura.
- **Reserva:** solicitud del portal identificada por `reservation_id`.
- **Días restantes:** devolución menos fecha actual del servidor, no duración de la prórroga.

## FR-AUTH-001

**Identidad propia de BiblioCM.**

Criterios de aceptación:
- Registrar nombre, usuario público y contraseña sin pedir un carné.
- Usuario normalizado a minúsculas, único, de 3–40 caracteres con letras ASCII,
  números, punto, guion o guion bajo; nombre no vacío hasta 80 caracteres.
- Contraseña de registro de 10–200 caracteres. No se usa para entrar en el OPAC.
- Login con usuario/contraseña BiblioCM; error genérico si no son correctos.
- Tras registro/login se establece una nueva sesión; logout invalida esa sesión.

## FR-AUTH-002

**Email verificado como identidad de acceso, con username como alias.**

Aprobado como dirección de producto el 2026-10-10 e implementado el mismo día
([TODO-AUTH-002](../TODO.md), [ADR-017](decisions.md#adr-017--identidad-con-email-verificado-smtp-por-entorno-tokens-hasheados-y-api-v5)).
El login acepta username o email verificado; el username legado sigue
abriendo sesión igual que siempre.

Criterios de aceptación:
- El username sigue existiendo como alias público: las solicitudes de acceso y
  la identidad mostrada (`@username`) no cambian de significado.
- Cada usuario puede verificar un email. Se normaliza a minúsculas, es único en
  la instancia y se valida sintácticamente en el servidor.
- La verificación se entrega por email con un token de un solo uso, caducidad y
  almacenamiento como hash; el email solo queda verificado al consumir ese token.
- El proceso de solicitud/resolución no revela si el email ya está registrado
  (anti-enumeración): misma respuesta y mismo coste aparente.
- El login acepta username (usuarios existentes y transición legada) o el email
  **verificado**; un email sin verificar nunca abre sesión.
- Los usuarios existentes sin email conservan su login por username; se les
  ofrece verificar un email desde su sesión. Ningún email se hereda, se migra ni
  se deduce de otra fuente: no existen mapeos implícitos.
- El SMTP es configurable por entorno; en pruebas siempre se usa un servidor
  falso local y ninguna prueba envía correo a un servidor real.
- Rate limit sobre solicitudes de verificación y sobre intentos de login por
  email; un fallo del envío no altera la cuenta ni el estado de verificación.

## FR-AUTH-003

**Cambio y recuperación de contraseña sin debilitar la sesión.**

Aprobado el 2026-10-10 e implementado el mismo día
([TODO-AUTH-001](../TODO.md), [ADR-017](decisions.md#adr-017--identidad-con-email-verificado-smtp-por-entorno-tokens-hasheados-y-api-v5)).

Criterios de aceptación:
- Cambio desde sesión autenticada: exige la contraseña actual y una nueva
  distinta; no altera la clave Fernet del servidor, las credenciales OPAC
  cifradas, las vinculaciones ni los permisos.
- Tras el cambio se invalidan las demás sesiones del usuario; la sesión que
  ejecuta el cambio puede continuar o renovarse de forma controlada.
- Recuperación solicitada con email: respuesta genérica sin enumerar; token de
  un solo uso, caducidad y hash almacenado; usarlo invalida el token, fija la
  nueva contraseña y cierra las demás sesiones.
- Toda mutación de identidad exige JSON y CSRF, y valida Origin si la petición
  lo lleva; recovery y cambio tienen rate limit propio.
- El portal OPAC nunca recibe la contraseña BiblioCM ni viceversa.

## FR-AUTH-004

**Passkeys (WebAuthn) con librería mantenida.**

Aprobado el 2026-10-10 e implementado el mismo día ([TODO-AUTH-003](../TODO.md),
[ADR-018](decisions.md#adr-018--passkeys-con-webauthn-y-google-oidc-con-joserfc)).

Criterios de aceptación:
- Registro y autenticación de passkeys ancladas a la cuenta BiblioCM, usando una
  librería WebAuthn mantenida; no se implementa criptografía WebAuthn a mano.
- La autenticación con passkey crea una sesión BiblioCM normal (rotación de
  token incluida) con los mismos permisos que el login por contraseña.
- Challenge de un solo uso con caducidad y verificación de `Origin`/RP ID por la
  librería; el servidor no confía en datos del navegador sin verificarlos.
- Borrar una passkey o añadir una primera exige reautenticación explícita
  (contraseña o passkey vigente), no solo la sesión abierta.
- La ventana de reautenticación se mide con `time.monotonic()` contra la marca
  de la sesión: solo una contraseña verificada o un login con passkey dentro de
  esa ventana habilita a gestionar. Una sesión **sin marca** (nunca
  reautenticó) está fuera de la ventana **con cualquier valor del reloj**,
  también en un host recién arrancado cuyo monotónico aún no llega a `REAUTH_TTL`
  (300 s); igual cuando la marca existe y está caducada. Ambos casos responden
  `403` con `code:"reauth_required"` (corrección TODO-SEC-005).
- Passkeys solo en contexto seguro: sobre HTTP no local la UI las muestra
  deshabilitadas con aviso ([NFR-SVC-003](#nfr-svc-003)); el servidor también
  rechaza operaciones WebAuthn en origen no confiable. Además, el RP ID y el
  origen esperado derivan del origen canónico del pedido validado contra la
  lista de confianza del servidor (local por defecto; público solo con
  `BIBLIO_TRUSTED_ORIGINS`): un Host arbitrario, incluso sobre TLS, recibe 403
  (corrección TODO-SEC-003).
- Pruebas negativas: origin equivocado, challenge reutilizado/expirado, payload
  malformado y passkey de otro usuario.
- Las credenciales se registran **descubribles** (resident key) con verificación
  de usuario obligatoria; el login no pide identificador ni lista
  `allowCredentials`, así que la respuesta no revela quién existe.
- Chromium exige un RP ID con forma de dominio: sobre `http://127.0.0.1` la UI
  explica por qué no puede ofrecer passkeys y orienta a `http://localhost:8000`
  o a HTTPS con nombre de dominio; el servidor acepta ambos contextos locales.

## FR-AUTH-005

**Acceso con Google (OIDC), opcional y con vinculación explícita.**

Aprobado el 2026-10-10 e implementado el mismo día ([TODO-AUTH-004](../TODO.md),
[ADR-018](decisions.md#adr-018--passkeys-con-webauthn-y-google-oidc-con-joserfc)).

Criterios de aceptación:
- Opt-in por configuración (client id/secret por entorno). Sin configuración no
  se muestra ningún botón ni se acepta ningún callback.
- Flujo con `state` y `nonce` de un solo uso, caducidad y PKCE; el token ID se
  verifica con librería mantenida (firma, issuer, audiencia, expiración).
- Vincular la cuenta Google a un usuario BiblioCM es una acción explícita desde
  una sesión ya autenticada y exige reautenticación; el email del token OIDC
  **no** se usa para crear, encontrar ni vincular cuentas de forma implícita.
- Una cuenta Google se vincula a un único usuario BiblioCM por instancia;
  desvincular exige reautenticación y no borra la cuenta ni sus carnés.
- Fallo del proveedor o del callback no deja sesión abierta ni token sin consumir.
- El `redirect_uri` se selecciona solo desde un origen de confianza del
  servidor (la misma lista de confianza que las passkeys): la URI configurada
  debe ser canónica y apuntar al callback fijo, y un Host hostil nunca elige
  el callback (corrección TODO-SEC-003).
- Identidad de la cuenta externa: el par `(issuer, sub)`; el email del token solo
  se guarda como metadato de la vinculación.
- **El flujo queda ligado al navegador que lo inició** (login CSRF; corrección
  TODO-SEC-004): `start` emite una cookie de enlace por flujo con valor aleatorio
  criptográfico, `HttpOnly`, `SameSite=Lax`, `Secure` cuando el servidor trabaja
  sobre HTTPS, con la ruta del callback y la misma caducidad que el `state`. El
  servidor guarda **solo el digest** de ese valor junto al `state` y lo compara en
  tiempo constante **antes** de intercambiar el `code` con el proveedor y antes de
  crear una sesión o un vínculo. Sin cookie, con una cookie ajena o caducada, el
  callback se rechaza sin ninguna llamada al proveedor; la cookie se retira al
  completar el flujo y en cada error. El enlace nunca viaja en la query del
  callback ni sustituye al `state`.
- **La vinculación demuestra que su sesión sigue viva:** en el último gate del
  store, el modo `link` exige que la sesión que inició el flujo siga abierta para
  el mismo usuario y que ese usuario siga existiendo con email verificado; cerrar
  sesión mientras el flujo está pendiente invalida la vinculación. La cookie de
  sesión global (`SameSite=Strict`) no se debilita por este flujo.
- **Alta explícita con Google** (decisión de alcance del 2026-10-10): un botón
  distinto («Crear cuenta con Google») crea una cuenta nueva **solo** cuando el
  proveedor certifica un email verificado; el alias público se deriva de forma
  determinista de la parte local del email, con sufijo determinista del `sub`
  cuando el alias está ocupado. Si el email ya pertenece a otra cuenta, el alta
  se rechaza y la persona debe entrar con esa cuenta y vincular Google desde
  ella: nunca hay fusión por email ni creación implícita desde el login.

## NFR-SEC-002

**Higiene de tokens y superficie de identidad.**

Criterios de aceptación (aplicables a email verificado, recovery, passkeys y OIDC):
- Tokens aleatorios criptográficos; en base de datos solo su hash, con caducidad
  y un solo uso. Consumir o caducar un token lo invalida de inmediato.
- Respuestas uniformes y sin enumeración en registro, email, recovery y login.
- Rate limit por IP y ruta sobre registro, login, verificación, recovery,
  passkeys y OIDC, sin diluir el límite actual de login/registro.
- Mutaciones con CSRF + JSON + Origin; invalidación de sesiones al rotar
  credenciales; reautenticación explícita para vincular identidades externas,
  borrar passkeys y cambiar contraseña por recuperación.
- Sin criptografía casera: primitivas de la stdlib/`cryptography` y librerías
  mantenidas ya aprobadas para WebAuthn/OIDC. Nada de «cifrar» a medida.
- Las migraciones de esquema que exijan estas funciones se prueban con fixtures
  temporales preservando IDs, vínculos, carnés y credenciales cifradas, con
  rollback atómico; no se migran datos reales como parte del desarrollo.
- No debilitar las puertas de operación existentes ([NFR-SVC-002](#nfr-svc-002)):
  toda nueva mutación de identidad respeta autorización previa y espera de
  revocación ya aceptadas.

## FR-ACC-001

**Vincular y mantener carnés cuyas claves se conocen.**

Criterios de aceptación:
- Una sesión BiblioCM puede vincular múltiples carnés con etiqueta identificativa.
- Verificar carné/clave en el portal antes de guardar o actualizar credenciales.
- Un carné tiene una única vinculación directa en toda esta instancia BiblioCM.
  Si ya existe, solicitar autorización a quien lo vinculó.
- Solo quien vinculó el carné puede cambiar etiqueta/clave o desvincularlo.
- Cambiar el número de carné requiere desvincular y añadir el nuevo.
- Las cuentas CLI no se importan automáticamente a la web.

## FR-LINK-001

**Solicitar y conceder acceso sin conocer claves de otra persona.**

Criterios de aceptación:
- Solicitar por nombre de usuario BiblioCM de una persona ya registrada.
- Prohibir auto-solicitudes y duplicados pendientes/aprobados de la misma pareja.
- El titular ve peticiones recibidas y puede aprobar o rechazar.
- Elegir permiso `read` (solo lectura) o `manage` (gestión completa) al aprobar;
  puede diferir del permiso solicitado.
- El solicitante no puede aprobar/rechazar su propia petición ni elevar su permiso.
- La concesión incluye todos los carnés vinculados directamente por el titular,
  incluidos los que vincule en el futuro. La pantalla debe explicarlo.
- No compartir transitivamente cuentas recibidas de terceros.

Ejemplo: A concede acceso a B; B concede acceso a C. C recibe los carnés directos
de B, pero no los de A por esa segunda autorización.

## FR-LINK-002

**Cambiar permisos, revocar y cancelar.**

Criterios de aceptación:
- El titular cambia `read`/`manage` solo para concesiones aprobadas.
- El titular revoca un acceso aprobado; el solicitante puede abandonarlo.
- El solicitante cancela una solicitud pendiente. El backend también acepta
  `revoke` del titular para una solicitud pendiente.
- Tras rechazo/revocación se puede volver a solicitar acceso.
- Comprobar permiso actual en el servidor en cada operación, no en una copia
  conservada en la sesión ni en valores enviados por el navegador.
- Una operación en curso termina antes de aplicar la revocación; posteriores
  operaciones no deben disponer del permiso revocado.

## FR-PANEL-001

**Panel conjunto con atribución y fallo parcial.**

Criterios de aceptación:
- Agregar préstamos/reservas de los carnés propios y autorizados.
- Identificar cada elemento por cuenta; dos cuentas pueden tener igual barcode
  o ID de reserva sin mezclarse. Selección lógica: `account` + identificador OPAC.
- Ordenar préstamos por urgencia y permitir filtro por cuenta.
- Mostrar fecha de devolución, días restantes y estado de renovación.
- Mostrar retrasos y vencimientos cercanos; el contador «Vencen en 3 días»
  incluye retrasos, según el comportamiento actual aceptado de la UI.
- Un fallo de una cuenta no oculta las demás ni cierra la sesión BiblioCM.
- Sin carnés accesibles, orientar a Configuración.
- La carga del panel (login, restauración de sesión, refresco manual y refresco
  periódico) expone un estado de carga accesible: región `role="status"` con
  `aria-live` y `aria-busy` en el panel mientras consulta. Ese estado se retira
  siempre que la carga termine, **incluidos** el error de red o de API, el
  cierre de sesión y una respuesta obsoleta de una sesión anterior: una respuesta
  vieja no debe dejar el panel «cargando» ni reanunciarlo sobre un panel ya
  resuelto.
- Ese estado cubre **toda** la ventana en la que el panel aún no tiene datos, no
  solo la llamada `library`: también la consulta de permisos (`settings`) que
  precede a `library` en el login, en la restauración de sesión y en
  «Actualizar». Se muestra como spinner con texto, no como una línea que puede
  pasarse por alto. Durante esa ventana no se pinta un panel vacío ni se
  destalla el formulario de acceso: mientras la sesión de arranque sigue sin
  resolver hay una región `role="status"` de bienvenida que se retira al
  resolver, tanto en éxito como en error, y si el panel nunca llega a
  resolverse se vuelve al acceso.
- El spinner se renderiza de verdad: `display` calculado distinto de `none`,
  caja con tamaño y el bloque completo **dentro del viewport**, en escritorio y
  en móvil, mientras la sesión de arranque sigue sin resolver. Con
  `prefers-reduced-motion: reduce` la rotación continua se detiene
  (`animation-name: none`) pero el indicador sigue visible con su texto; con
  movimiento normal mantiene la animación estándar.
- Una respuesta obsoleta de `settings` perteneciente a una sesión cerrada no
  reanuncia la carga, no repuebla el panel y no publica su error en el aviso
  persistente.

## FR-RENEW-001

**Renovar una única copia y verificar su estado definitivo.**

Criterios de aceptación:
- Solo permisos `manage` pueden renovar; la UI ofrece la acción solo en estado `renovable`.
- El motor lee el formulario real del ejemplar; sin formulario no envía una renovación.
- Enviar el campo `CP<barcode>` del formulario, no construir una selección masiva.
- Adoptar la respuesta del POST, autenticar un acceso nuevo y consultar el panel.
- Confirmar solo si avanzan fecha de devolución y contador de renovaciones.
- El éxito no se deduce de un texto de plantilla ni de los días del botón.
- No repetir el POST de renovación durante su comprobación.
- Actualizar el panel antes del aviso; fecha y días restantes del aviso coinciden
  con la tarjeta de la misma cuenta y el mismo ejemplar.
- Mientras la renovación está en vuelo, el botón queda `disabled` con
  `aria-busy="true"` y su texto de progreso, anunciado también en la región de
  estado; un segundo intento del usuario no envía otro POST, de modo que toda la
  operación sigue siendo un único envío.
- Si la respuesta no llega (error de red o desconexión) se informa del fallo,
  no se anuncia ninguna renovación y la mutación **no** se reintenta; no hay
  timeout propio que inventar, el `fetch` se resuelve con la conexión.
- El aviso de éxito solo se publica después de refrescar el panel y encontrar
  el mismo ejemplar de la misma cuenta; si el panel no lo confirma, se muestra
  el mensaje verificado del servidor, nunca uno inventado en el cliente.

Regresión: una lectura intermedia devuelve 12/10; un acceso nuevo confirma 20/10.
Con fecha de prueba 05/10, el estado final debe ser 20/10 y 15 días restantes.

## FR-CAT-001

**Buscar y consultar registros de catálogo.**

Criterios de aceptación:
- Buscar por el texto que acepta el OPAC (título, autor, ISBN, etc.).
- API admite consulta no vacía hasta 300 caracteres y páginas 1–1000.
- Mostrar registros con ID, título, autor, publicación y soporte/edición cuando existen.
- Navegar por páginas y manejar resultados vacíos.
- Manejar el salto del portal a una ficha cuando solo existe un resultado,
  manteniendo el título bibliográfico real. Este último caso tiene una incidencia
  abierta; ver estado y backlog.
- Al cambiar la cuenta de catálogo, invalidar resultados/detalle anteriores.
- Mostrar la portada del registro cuando el portal la ofrece, solicitándola al
  propio servidor con carga diferida. La imagen se identifica con una URL de
  esta aplicación; la URL con token del proveedor no aparece en la respuesta, en
  el DOM, en la caché ni en la cabecera Referrer. Sin portada, con fallo o con
  una URL no reconocida se conserva el marcador actual, sin imágenes rotas.
- Aplica tanto a la lista de resultados como a la ficha única a la que el portal
  salta con un único resultado: esa ficha también trae portada y hay que leerla
  con la misma regla, resolviéndola contra la última respuesta del cliente.
- La portada se muestra también en las tarjetas de préstamos y reservas,
  atribuida por **cuenta + identidad bibliográfica** (`record_id`, o el
  identificador de la reserva; nunca por título, nunca solo por barcode). Si el
  préstamo no trae `record_id` en su HTML, no se deduce de ninguna otra parte y
  la tarjeta conserva el marcador.
- `GET cover` debe poder servir una portada que no esté registrada: si la
  caché en memoria no la conoce (salto a ficha, entrada caducada o reinicio),
  la descubre abriendo la ficha del registro **una sola vez** por
  cuenta/registro y TTL, y memoriza también la ausencia para no repetir la
  petición. Autorizar el acceso a la cuenta antes de abrir la ficha, exigir
  `record` numérico, revalidar origen/CGI/tipo/tamaño y no emitir el token en
  la respuesta. Sin peticiones masivas ni prefetch: el panel no abre fichas por
  su cuenta, solo el navegador pide la portada de lo que pinta, con carga
  diferida.
- Los bytes de portada ya validados se memorizan también en memoria, con el
  mismo TTL y con tope de entradas y de tamaño, para no repetir la descarga al
  portal en cada render. La autorización de lectura de la cuenta sigue
  produciéndose **antes** de servirlos desde esa memoria: una sesión sin
  permiso, un tercero ajeno o una concesión revocada reciben 403 aunque los
  bytes estén memorizados, y ninguna petición denegada llega al portal.
- En el navegador, las portadas ya servidas se memorizan **solo en RAM** como
  blob URL con un tope de entradas; no se persisten en CacheStorage,
  localStorage ni IndexedDB y el service worker sigue sin interceptarlas.
  Toda entrada se invalida —revoke de la blob URL— al cerrar sesión, al
  recargar o cerrar la página, y cuando cambia o desaparece el permiso o la
  cuenta que autoriza esa portada; una portada de una cuenta ya no accesible no
  se vuelve a pintar desde la caché.

## FR-COPY-001

**Diferenciar todos los ejemplares de los reservables.**

Criterios de aceptación:
- Leer todos los bloques de ejemplares de la ficha, deduplicando barcode.
- «Disponible después de X» no equivale a «Disponible ahora».
- Mostrar biblioteca/sucursal, ubicación, signatura, tipo, soporte y disponibilidad.
- Mantener visible la lista completa al consultar el asistente de reservas.
- Mostrar aparte las opciones que el portal ofrece a la cuenta elegida.
- El listado del asistente usa filas completas y campos estructurados; no
  recortes de HTML, tokens de sesión ni el campo público antiguo `row`.
- Conservar índices originales del formulario, incluidos huecos.
- Una respuesta incompatible/incompleta produce un error, no una fila HTML rota.

## FR-RES-001

**Crear una reserva del ejemplar elegido.**

Criterios de aceptación:
- Exigir `manage` y confirmar cuenta/ejemplar en la UI.
- Abrir primero ficha y después asistente, siguiendo enlaces reales.
- La web envía barcode; buscar su índice actual si cambió el orden del asistente.
- Si desapareció de las opciones, negarse sin reservar otra copia.
- Enviar solo los campos de una copia, `NCOP=1` y la acción real del formulario.
- Confirmar una reserva nueva para el registro solicitado al releer la biblioteca.
  La verificación actual compara ID nuevo + `record_id`; no verifica barcode de
  la reserva porque el modelo de reserva no lo expone.
- Límites y elegibilidad los decide el OPAC; no garantizar reservas de copias
  disponibles para recoger ni disponibilidad de todas las bibliotecas.

## FR-RES-002

**Consultar y anular reservas.**

Criterios de aceptación:
- Lectura permitida a `read` y `manage`; anulación solo a `manage`.
- Confirmación de anulación en la UI.
- Comprobar que la reserva pertenece a la cuenta elegida y verificar que su ID
  desaparece después del envío al portal.

## FR-PWA-001

**Web adaptable e instalable.**

Criterios de aceptación:
- Pantallas de acceso, préstamos, reservas, catálogo y configuración en español.
- Layout utilizable en escritorio y viewport móvil; navegación básica por teclado.
- Manifest e iconos; instalación standalone donde el navegador la admita.
- Las imágenes de portada se piden al mismo origen con carga diferida; el
  service worker no las guarda y el shell no amplía su lista de caché por ellas.
- Service worker almacena solo el shell público; consultas/mutaciones privadas
  necesitan conexión y no se guardan offline.
- HTTPS para instalación/service worker, con excepción de localhost en desarrollo.
- Antes de afirmar soporte probado en Android/iPhone, comprobar dispositivos reales.
  La instalación real en esos dispositivos sigue pendiente.

## FR-CLI-001

**CLI independiente para acceso por carné.**

Criterios de aceptación:
- Registro separado de carnés/etiquetas; passwords de entorno o entrada oculta.
- Consultar varias cuentas; búsqueda, disponibilidad, renovación y reservas.
- Renovar sin barcode solo informa. Renovar con barcode verifica la operación.
- No escribir passwords de CLI en su registro ni sincronizarlo automáticamente con SQLite.
- Mensajes de ayuda y errores deben corresponder a opciones existentes.
  Hay cobertura y errores de CLI pendientes en el backlog.

## NFR-SEC-001

**Separación de identidades y autorización.**

- Password BiblioCM: hash scrypt con sal individual. Credenciales OPAC: Fernet.
- Cookie HttpOnly/SameSite=Strict; Secure cuando se configura proxy HTTPS.
- POST autenticado requiere CSRF; JSON obligatorio y validación de Origin si se envía.
- No devolver passwords, clave del servidor, tokens OPAC ni formularios privados.
  Las URLs de portada se resuelven en el servidor y salen como rutas de esta
  aplicación; en los DTO de catálogo se retira cualquier valor que contenga la
  ruta de sesión del OPAC (cover, OpenURL y MARC). La portada se sirve tras
  autorizar lectura y validar origen, CGI, tipo y tamaño. Descubrir una portada
  desconocida es una lectura única de la ficha (`record` solo dígitos) hecha
  **después** de esa misma autorización y memorizada en memoria (también la
  ausencia y, una vez validadas, sus propias bytes con límite de memoria); no
  cambia permisos, no abre fichas en serie desde el panel ni deja
  escapar la URL resultante. Queda pendiente de verificar en el portal real el
  resto de representaciones; ver TODO-SEC-001.
- Cada sesión pertenece a un usuario; rotación de token al autenticar.
- Rate limit actual: 20 intentos registro/login por IP en cinco minutos.

## NFR-DATA-001

**Persistencia y clave del servidor.**

- Usuarios, vinculaciones y solicitudes sobreviven a un reinicio en SQLite.
- Sesiones web en memoria: TTL deslizante de una hora, eliminadas en siguiente
  petición cuando expiran; reiniciar cierra las sesiones.
- No reemplazar silenciosamente una clave perdida ni aceptar una clave incompatible.
- Mantener clave y base de datos recuperables; migraciones y rotación no están implementadas.

## NFR-SVC-001

**Contrato y operación local consistentes.**

- API v4 identificada en cada respuesta JSON y consultable sin login.
- UI rechaza una API de versión distinta.
- Un único servidor ocupa la misma dirección/puerto; binding exclusivo en Windows.
- Serializar permiso y operación en esta instancia para respetar revocación.
- Respetar el ritmo del OPAC; no convertir el panel en scraping concurrente masivo.

## NFR-SVC-002

**Desconexión del cliente y concurrencia de peticiones.**

- Si la escritura de las cabeceras o del cuerpo de una respuesta falla porque
  el cliente se desconectó, el servidor no intenta emitir una segunda respuesta
  en esa misma conexión (ningún 502 después de un 200 ya iniciado, por ejemplo
  el de una portada), cierra la conexión y el fallo de escritura no se propaga
  como excepción del hilo de la petición.
- Con el cliente conectado, los errores reales conservan su traducción habitual
  (400, 403, 409, 422, 502…); solo un fallo de escritura en el socket se trata
  como desconexión. Si la respuesta ya empezó, una excepción posterior cierra
  la conexión en lugar de concatenar estados.
- Una operación lenta del portal (renovación, descarga de portada, consulta de
  panel) no bloquea peticiones sin relación: ni las de otros usuarios ni las
  del mismo usuario por otra ruta.
- La autorización se consulta en el servidor antes de cada operación y antes de
  descifrar credenciales; la E/I con el portal ocurre **sin** retener el lock
  global del store, que sigue protegiendo cada acceso a SQLite.
- La revocación y la bajada de permiso esperan a que termine la operación en
  curso del titular del permiso y se aplican antes de las peticiones
  siguientes, como exige [FR-LINK-002](#fr-link-002); `read` sigue sin mutar y
  la selección sigue siendo `account` + identificador.
- Desvincular una cuenta (`accounts/delete`) o rotar sus credenciales
  (`accounts/update`) espera a que terminen las operaciones en curso de **esa
  cuenta** — de cualquier usuario autorizado — y solo entonces se aplica; toda
  operación autoriza, descifra y opera bajo esa misma puerta, de modo que no
  hay ninguna acción de portal posterior a la desvinculación ni ninguna con
  credenciales obsoletas, y las peticiones siguientes vuelven a autorizar
  (403/404 sin llegar al portal). La puerta es por cuenta: una operación lenta
  de una cuenta no bloquea a otra cuenta ni a otros usuarios.
- Una petición que llega con la sesión ya cerrada recibe 401; una operación
  autorizada antes de cerrarla puede terminar y entregar su respuesta.

## NFR-SVC-003

**Contexto local, HTTP y HTTPS.**

Criterios de aceptación:
- La UI detecta el contexto del navegador: cuando el origen **no** es de
  confianza (HTTP servido desde una dirección que el navegador no considera
  local) muestra un aviso persistente y explica el alcance del riesgo (tráfico
  sin cifrar en la red local y capacidades deshabilitadas).
- En ese contexto las passkeys quedan deshabilitadas en UI y servidor
  ([FR-AUTH-004](#fr-auth-004)); el resto de la aplicación sigue funcionando.
- `http://127.0.0.1` y `localhost` se consideran contextos locales aceptados en
  desarrollo; el aviso no aparece ahí.
- El servidor mantiene una lista de orígenes de confianza con default solo
  local: passkeys y el callback de Google derivan su origen del pedido solo
  cuando ese origen está en la lista; un host público exige declararlo
  explícitamente (`BIBLIO_TRUSTED_ORIGINS`, https), y un Host hostil o no
  canónico se rechaza incluso detrás de TLS (TODO-SEC-003).
- El proyecto documenta cómo generar certificados locales con mkcert y arrancar
  la app detrás de un proxy TLS con `--secure`, sin instalar certificados, sin
  abrir puertos y sin publicar servicios: el binding default sigue siendo
  `127.0.0.1`.
- La advertencia es de UI/operación, no una promesa de seguridad perimetral:
  el servidor no implementa TLS propio.

## NFR-DEV-001

**Continuidad SDD/TDD.**

- Toda tarea activa tiene requisito o propuesta, aceptación, estado y verificación.
- Para cambios de comportamiento, documentar la intención y reproducir con prueba
  fallida antes de implementar. No modificar expectativas solo para obtener verde.
- Mantener trazabilidad requisito → código → test → estado; registrar límites de evidencia.
- Aplicar la definición de terminado de [testing.md](testing.md).
- Antes de publicar existe un **candidato limpio**: exportación de los ficheros que
  Git publicaría, sin `.biblio-data/`, sin `docs/HANDOFF-SOL.md` ni ningún fichero
  ignorado, sobre el que se ejecutan docs, importación, pruebas y escaneo. Si algo
  solo funciona con un fichero local ignorado, no está publicable.
- El escaneo de publicación aplica una **lista de rutas permitidas** y exclusiones
  explícitas además de sus reglas de contenido, y una revisión manual acotada de
  fuentes y fixtures complementa ese escaneo: las expresiones regulares **no**
  son una prueba de privacidad.
- El set publicable **no lleva identidad real de lector**: los marcadores de
  identidad del OPAC (`lenlec`, `nombre`, `apellidos`) solo aparecen en los
  fixtures con valores sintéticos declarados en una lista de permitidos, y el
  escáner aplica esa regla semántica además de sus reglas de material privado.
  El hallazgo se reporta como siempre —regla, ruta y línea, nunca el dato— y la
  regla **no** se presenta como un detector de datos personales arbitrarios: un
  valor personal que no use esos marcadores queda fuera de su alcance y sigue
  dependiendo de la revisión manual.
- Los **identificadores de préstamo y reserva** del OPAC —códigos de ejemplar y
  de reserva, y las referencias derivadas que los repiten (`data-prbarc`,
  `data-cobarc`, `data-prppsq`, `data-di`, `prbarc`, `CP<código>`,
  `lector_box…`, `abnRenov…`, `lector_renovMen…`, `DI=`)— también son valores
  sintéticos declarados en los fixtures y en los ejemplos de fuente y
  documentación: son historiales de préstamo/reserva reales, aunque el bloque de
  lector sea sintético. La misma regla semántica los cubre con su propia lista
  permitida, con el mismo alcance acotado y el mismo reporte sin datos.
- La auditoría de dependencias es **aislada y limitada a las dependencias
  declaradas del paquete**, sin actualizaciones innecesarias, distinguiendo
  cualquier aviso que pertenezca al entorno global de instalación.
