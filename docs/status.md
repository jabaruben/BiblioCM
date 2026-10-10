# Estado de implementación y evidencia

**Corte: 2026-10-10.** Paquete `biblio-cm` 0.1.0; API `6`; shell PWA
`bibliocm-shell-v13`. Estas versiones son distintas: actualizar una no actualiza
automáticamente las otras. La API pasó de `4` a `5` al añadir los endpoints de
identidad —email verificado, cambio y recuperación de contraseña
([FR-AUTH-002](specification.md#fr-auth-002), 
[FR-AUTH-003](specification.md#fr-auth-003), [ADR-017](decisions.md))— y
`email`/`email_verified` en el usuario de `/api/session` y `/api/settings`; la
forma de todo lo anterior no cambia. Pasó de `5` a `6` al añadir las passkeys
([FR-AUTH-004](specification.md#fr-auth-004)) y el acceso opcional con Google
([FR-AUTH-005](specification.md#fr-auth-005)): seis rutas nuevas,
`passkeys`/`identities` en `settings`, `google` en `session` y el callback de
Google como única respuesta que no es JSON (303), decidido en
[ADR-018](decisions.md#adr-018--passkeys-con-webauthn-y-google-oidc-con-joserfc).
El shell sube a `v13` por los assets de passkeys/Google; la caché de portada por
blob URL (`v11`, [ADR-014](decisions.md)) y la renovación con progreso (`v10`)
siguen incluidos.
La API `5` → `6` no toca rutas antiguas: una UI nueva contra un servidor `5` se
detiene en el aviso de versión incompatible, que es el comportamiento deseado.
La base añade las dependencias mantenidas `webauthn` y `joserfc` (instaladas con
`pip install -e .`), según [ADR-018](decisions.md).
Tareas editables: [TODO.md](../TODO.md).

## Cómo interpretar el estado

- **Implementado:** existe código para el alcance descrito, con límites de evidencia indicados.
- **Parcial:** una parte del requisito o su aceptación/verificación sigue pendiente.
- **No implementado:** no existe un flujo operativo para ello.
- **Por inspección:** deducción del código, no una incidencia reproducida en vivo.
- **Verificado simulado:** tests con HTML/clientes falsos o HTTP localhost.
- **Observado real:** consulta/operación concreta del portal; no garantía futura.

No existe certificación general de producción, cobertura del 100% ni verificación
en dispositivos físicos. La documentación aplica SDD/TDD hacia adelante; no
reconstruye un historial RED/GREEN de todo el código anterior.

## Matriz de trazabilidad

| Requisito | Estado / código | Evidencia existente | Pendiente o límite |
|---|---|---|---|
| [FR-AUTH-001](specification.md#fr-auth-001) | Implementado: store/web/formularios | WebTests: registro, validación, login, rotación, logout, TTL; navegador | Recuperación/cambio y email ya no viven aquí: son [FR-AUTH-003](specification.md#fr-auth-003) y [FR-AUTH-002](specification.md#fr-auth-002), implementados |
| [FR-AUTH-002](specification.md#fr-auth-002) | Implementado: email verificado con username como alias (store/web/UI) | WebTests de identidad ([test_identity.py](../tests/test_identity.py)): código por correo falso, hash en BD (nunca el claro), un solo uso, caducidad, anti-enumeración, email ocupado silencioso, fallo de entrega con respuesta uniforme (revisión), SMTP caído sin token vivo, rate limit por ruta, login con email verificado y rechazo del sin verificar, alias username intacto; navegador: verificar desde Configuración, login con email y rechazo del sin verificar | SMTP real no probado (solo el falso local); sin notificaciones de cuenta ajena; el pendiente no se persiste: tras recargar se pide otro código |
| [FR-AUTH-003](specification.md#fr-auth-003) | Implementado: cambio y recuperación de contraseña (store/web/UI) | WebTests de identidad: cambio con contraseña actual **atómico bajo el lock del store** (revisión: dos cambios concurrentes no pueden verificar ambos contra la contraseña vieja; cambio+reset dejan una sola contraseña coherente), cierre de las demás sesiones conservando la actual, preservación de clave Fernet/carnés/vínculos, recuperación con código de un solo uso y caducidad, cierre de todas las sesiones al usarlo, respuestas sin enumeración **incluido el fallo de correo**, rate limit propio; navegador: cambio con sesión viva y recuperación con el correo falso | Portal OPAC no involucrado (invariante intacto); sin 2FA; recovery requiere email verificado previo |
| [FR-AUTH-004](specification.md#fr-auth-004) | Implementado: passkeys con `webauthn` (store/web/UI) | [test_passkeys.py](../tests/test_passkeys.py) con autenticador sintético: registro/login verificados por la librería, reautenticación para añadir/borrar con caducidad, challenge de un solo uso y caducado, origen ajeno, payload malformado, reto de otro usuario, firma/UV/contador, no enumeración y login concurrente; rechazo de Host hostil sobre TLS, origen HTTPS listado exactamente y flujo completo sobre origen configurado (TODO-SEC-003); migración v2 con rollback; navegador con autenticador virtual de Chromium en escritorio y móvil (alta, borrado y login) | Sin hardware real ni Safari/Firefox; Chromium rechaza RP ID con IP literal (la UI lo explica); el portal OPAC no interviene |
| [FR-AUTH-005](specification.md#fr-auth-005) | Implementado: Google OIDC opcional con `joserfc` (store/web/UI), con el flujo **atado al navegador y a su sesión viva** (TODO-SEC-004) | [test_oidc.py](../tests/test_oidc.py) con proveedor OIDC falso local (descubrimiento + JWKS + token RS256): opt-in, `state`/nonce/PKCE de un solo uso y caducados, verificación de firma/issuer/audiencia/expiración/nonce, identidad por `sub`, sin merge por email, alta explícita con alias determinista, vinculación/desvinculación con reautenticación y email verificado, unicidad y rate limit; callback derivado solo de origen de confianza (Host hostil → 403, configuración inválida → 503, TODO-SEC-003); **login CSRF en dos contextos de navegador**: cookie de enlace `biblio_oidc` (HttpOnly, Lax, ruta del flujo, TTL del `state`, Secure con `--secure`) con solo su digest en el estado, comparación en tiempo constante antes del canje del code, rechazo sin llamada al proveedor y sin consumir el estado ante cookie ausente/ajena/transferida/reutilizada/caducada, retiro de la cookie en completar y errores, `link` rechazado con logout pendiente, sesión rotada o email desverificado, y **gate final atómico respecto al logout** (comprobación y escritura serializadas con el lock del logout, con el titular revalidado en la transacción que escribe; regresión determinista con el logout forzado dentro de la ventana); navegador contra el mismo proveedor falso | Google real y credenciales OAuth de la persona no probadas (trámite humano en la consola de Google Cloud, sin APIs de pago; sin promesa de coste, ver fuentes fechadas en [operations.md](operations.md)); sin dispositivos; dos pestañas iniciando flujos a la vez conservan el enlace del último `start` |
| [FR-ACC-001](specification.md#fr-acc-001) | Implementado: Store + settings UI | WebTests: verificar antes de guardar, cifrado, dueño, editar/borrar, carné único; navegador; desvinculación y rotación esperando a las operaciones en curso de la cuenta | Sin importar registro CLI ni transferir titularidad de un carné |
| [FR-LINK-001](specification.md#fr-link-001) | Implementado: links SQL + settings | WebTests: solicitud, auto/duplicada, aprobación solo owner, read/manage, no transitividad; navegador | Concesión por titular completo, no por carné individual |
| [FR-LINK-002](specification.md#fr-link-002) | Implementado: permiso/revoke/reject | WebTests: sesión abierta revocada, downgrade, tercero ajeno, cancelar/reabrir; navegador; espera de revocación/bajada sobre la operación en curso con Event | Sin estrés concurrente/multiproceso ni portal real |
| [FR-PANEL-001](specification.md#fr-panel-001) | Implementado: library + renderLibrary + estado de carga accesible de arranque, acceso y refresco | WebTests: atribución de barcodes iguales, error parcial, lectura nueva; navegador: arranque/restauración, login, refresco, error y logout con respuestas obsoletas de `library` y de `settings` | Carrera de respuestas de panel/detalle fuera de orden pendiente: TODO-UI-001 |
| [FR-RENEW-001](specification.md#fr-renew-001) | Implementado: renew + feedback tras panel | RenewalClientTests; WebTests de confirmación/panel; navegador tras recarga y con la respuesta retenida en escritorio y móvil (botón `disabled` + `aria-busy` + progreso, un solo POST ante un segundo intento, aviso de éxito solo tras el panel verificado) | Lógica final probada con mutación simulada; estado real consultado, sin repetir una renovación real para probar |
| [FR-CAT-001](specification.md#fr-cat-001) | Parcial: búsqueda/lista/MARC/páginas, portadas por `/api/cover` con descubrimiento, memoria de bytes acotada y portadas de préstamo/reserva | SearchResultsTest, Tests de portada ([test_covers.py](../tests/test_covers.py)) y API fake; WebTests de petición única, latencia con cliente falso y autorización de la memoria; navegador con portada cargada, rota, URL antigua, préstamo y reserva; consultas reales de catálogo | Fallback único «Documento» (título): TODO-CAT-001; DOC/offsets de páginas: TODO-CAT-002; portada no probada con el portal real |
| [FR-COPY-001](specification.md#fr-copy-001) | Implementado: parsers + detalle separado | CopiesTest, ReservationParserTests, WebTests sin row, navegador; consulta real Z-A | No asegura que otras fichas/ediciones tengan el mismo inventario |
| [FR-RES-001](specification.md#fr-res-001) | Implementado: barcode/index + reserva nueva | ReservationClientTests y API/browser simulados; asistente real solo leído | Verifica ID nuevo + registro, no barcode posterior de reserva |
| [FR-RES-002](specification.md#fr-res-002) | Implementado: leer/anular y verificar ausencia | ReservationsTest, routing/permisos API; histórico del protocolo | Falta test dedicado del cliente real de anulación: TODO-TEST-001 |
| [FR-PWA-001](specification.md#fr-pwa-001) | Parcial: responsive, manifest, iconos y shell SW | Assets/manifest/whitelist en WebTests; Edge escritorio/móvil emulado, portadas same-origin fuera del alcance del SW | Instalación Android/iPhone, offline completo y accesibilidad: TODO-PLAT-001 / TODO-A11Y-001 |
| [FR-CLI-001](specification.md#fr-cli-001) | Parcial: comandos y registro | Código, ayuda ejecutable; motor compartido con suites | Sin suite CLI; mensajes/inputs: TODO-CLI-001 |
| [NFR-SEC-001](specification.md#nfr-sec-001) | Parcial: auth/cifrado/permisos implementados; URLs de catálogo saneadas y descubrimiento de portada tras autorizar | WebTests de CSRF/origin, cookies, read denegado, aislación, cifrado, portadas sin token y descubrimiento denegado sin cliente; navegador sin tokens en el DOM | Queda verificar el portal real en TODO-SEC-001; no auditoría externa |
| [NFR-SEC-002](specification.md#nfr-sec-002) | Parcial: higiene de tokens de email/recovery, passkeys y OIDC | WebTests de identidad: tokens hasheados (SHA-256), un solo uso, caducidad, rate limit por IP y ruta sin diluir el de login/registro, CSRF+Origin en mutaciones, cierre de sesiones al rotar credenciales, migración con rollback atómico sobre fixtures temporales; test_passkeys/test_oidc: retos hasheados de un solo uso con caducidad, detalle OIDC cifrado con Fernet (nonce/PKCE/enlace/sesión en claro nunca en BD), reautenticación explícita para passkeys y vínculos, rate limit propio, y el enlace de navegador del flujo Google comparado en tiempo constante antes de canjear el code (TODO-SEC-004) | Sin auditoría externa; la verificación de tokens depende de librerías mantenidas, no de código propio |
| [NFR-DATA-001](specification.md#nfr-data-001) | Parcial: baseline SQLite/clave y esquema versionado (`user_version`=2) con migración de identidad v0→v1→v2 | WebTests de reapertura; KeyTests de clave perdida/incompatible/entorno; tests de identidad: migraciones sobre fixtures temporales (v0→v2, v1→v2, reciente y rollback de cada paso) preservando IDs, vínculos, carnés y crypto | Marco completo de migraciones (más allá de identidad), rotación de clave y respaldo/restauración automatizados: TODO-DATA-001 |
| [NFR-SVC-001](specification.md#nfr-svc-001) | Implementado: versión y puerto exclusivo | WebTests de versión/errores/segundo bind; navegador antiguo rechazado; comprobación local API v6 | No hay despliegue HTTPS probado ni escalado distribuido |
| [NFR-SVC-002](specification.md#nfr-svc-002) | Implementado: escrituras protegidas, puerta de usuario y puerta de cuenta (ADR-013) | WebTests con `wfile` falso (fallo de imagen/cabecera, errores reales con cliente conectado), RST real sobre HTTP local, portada/renovación sin bloquear otra ruta, otra cuenta ni a otro usuario, y espera de revocación/bajada/desvinculación/rotación verificada por mutación (4 tests con Event) | Sin carga ni portal real; una operación ya autorizada puede terminar tras un logout (una petición posterior da 401); las puertas viven en RAM |
| [NFR-SVC-003](specification.md#nfr-svc-003) | Implementado: aviso de origen no confiable, passkeys deshabilitadas en UI **y** servidor, y lista de orígenes de confianza con default solo local (TODO-SEC-003) | Navegador: aviso oculto en `http://127.0.0.1` y visible con `isSecureContext` forzado, controles de passkey ocultos sin contexto seguro; WebTests: 403 del servidor para WebAuthn con Host de una IP de red y de un Host hostil sobre TLS, 400 con Host no canónico, origen HTTPS listado exacto y flujo passkeys/Google sobre origen configurado; guía mkcert/Mailpit/Tailscale y `BIBLIO_TRUSTED_ORIGINS` en [operations.md](operations.md) con una sección de fuentes externas fechada (HEAD 200 el 2026-10-10) y con el ejemplo de proxy TLS **válido** (Caddyfile multiline con nombre DNS de red, certificado mkcert de ese nombre y orígenes coincidentes, TODO-OPS-003) | mkcert/proxy TLS/Tailscale no ejecutados (`caddy` y `mkcert` no están en esta máquina: la validación de ese Caddyfile queda declarada, no ejecutada); no se sirvió la app desde una IP de red real ni detrás de un proxy con dominio público; el HEAD 200 acredita solo la accesibilidad de la URL ese día, no precios ni condiciones de terceros |
| [NFR-DEV-001](specification.md#nfr-dev-001) | Documentación y ciclo definidos, con **candidato público limpio** verificable | Especificación, backlog, guía TDD y check_docs; [release_export.py](../scripts/release_export.py) exporta el set publicable a un directorio temporal, comprueba que no lleva ficheros ignorados (nunca `.biblio-data/` ni `docs/HANDOFF-SOL.md`), aplica el escáner con su lista de rutas permitidas y ejecuta docs/importación/sintaxis JS (y la suite con `--run-tests`) dentro del candidato; auditoría de dependencias aislada y limitada a las declaradas; identidad de lector **sintética** e identificadores de préstamo/reserva
**sintéticos** en los fixtures del set publicable, con las reglas semánticas
`opac-reader-identity` y `opac-loan-identifier` y sus listas de valores
permitidos ([TODO-PRIV-001](../TODO.md)) | Aplicarlo a cambios siguientes; las
reglas cubren solo esos marcadores, no datos personales arbitrarios ni los
identificadores de ficha del catálogo; CI propuesta pendiente; publicar/push
sigue sin autorizarse por estas tareas |

Los enlaces a suites y comandos están en [testing.md](testing.md), no se debe
deducir cobertura adicional solo del nombre de un fichero.

## Baseline de pruebas

Suite estándar: **343 tests**, sin acceso al portal ni credenciales reales.

| Suite | Tests descubiertos en esta base |
|---|---:|
| `tests.test_parser` | 80 |
| `tests.test_renewal` | 9 |
| `tests.test_reservable` | 16 |
| `tests.test_store` | 3 |
| `tests.test_web` | 57 |
| `tests.test_covers` | 29 |
| `tests.test_release_scan` | 31 |
| `tests.test_release_export` | 4 |
| `tests.test_identity` | 33 |
| `tests.test_passkeys` | 31 |
| `tests.test_oidc` | 50 |
| Total | 343 |

Comando observado en la sesión de implementación del 2026-10-08 y repetido el
2026-10-09 tras TODO-SVC-002, finalizado correctamente en ambos casos:

```powershell
python -m unittest discover -s tests -t .
```

También pasaron `node --check` para app.js y sw.js, y el script de navegador con
Edge dos veces seguidas: registro, vinculación, solicitud, panel conjunto,
estado de carga accesible en **arranque/restauración, login, recarga, error y
logout con respuestas obsoletas de `library` y de `settings`**, filtros,
renovación consistente tras recarga, reserva simulada, portadas de
catálogo/préstamo/reserva (cargada, rota y URL antigua), versión antigua y DTO
viejo rechazados, sin errores JS ni desbordamiento en el viewport móvil de
prueba. No es una suite de Safari/iOS.

Los escenarios de carga usan peticiones **retenidas** en el enrutador de
Playwright, no `time.sleep`: un `time.sleep` dentro de un enrutador bloquea las
aserciones y convierte la comprobación en una carrera (medido: una aserción con
`timeout=500` tardó 3,54 s). Ver [testing](testing.md).

Revisión documental previa (base de 137 tests) 2026-10-05: `check_docs.py --tests`
validó 15 documentos, 16 requisitos, 23 tareas y 147 enlaces; los 137 tests de
entonces también se ejecutaron con unittest y pasaron. El checker cuenta pruebas
sin ejecutarlas: esa salida no sustituye el resultado de la suite. Se revisaron
código/fixtures y las ayudas de CLI, servidor y scripts. Cierre en TODO-DOC-001.

Revisión documental 2026-10-10 (paquete passkeys/Google, sin cambios de código):
se añadió en [operations.md](operations.md) una sección de fuentes externas con
URLs oficiales y la fecha de comprobación (HEAD 200 el 2026-10-10) y se
corrigieron afirmaciones categóricas de coste («opt-in y gratuito», «cuenta
gratuita» de Tailscale) por salvedades sin promesa de precio. Un HEAD 200 solo
acredita la accesibilidad de la URL ese día; los precios y condiciones de
terceros (incluidos Brevo/Resend, sin verificar y no usados) no dependen de este
repositorio. Evidencia en [TODO-SEC-003](../TODO.md).

## Paquete de seguridad y publicación 2026-10-10

Tres tareas cerradas el mismo día, sin publicar, desplegar ni tocar servicios
remotos (la única consulta externa fue la base de avisos de dependencias):

- **Login CSRF de Google y vínculo atado a su sesión** (TODO-SEC-004,
  [ADR-019](decisions.md#adr-019--el-flujo-google-se-liga-al-navegador-y-a-su-sesión-viva)):
  cookie de enlace por flujo `biblio_oidc` (HttpOnly, `SameSite=Lax`, ruta del
  callback, TTL del `state`, `Secure` con `--secure`) cuyo SHA-256 vive en el
  estado cifrado, comparado en tiempo constante antes del canje del `code` y sin
  consumir el estado en un intento hostil; `link` exige la sesión que inició el
  flujo viva y email verificado en el gate final. Pruebas en dos contextos de
  navegador (13 nuevas, suite OIDC 34 → 48) y escenario de navegador real con el
  paso de transferencia hostil; la cookie de sesión global sigue `SameSite=Strict`.
- **Candidato público limpio** (TODO-PUB-002): `scripts/release_export.py`
  exporta el set publicable (73 ficheros) a un directorio temporal, verifica que
  no lleva ficheros ignorados y ejecuta dentro docs, importación, sintaxis JS y
  la suite (5 omisiones justificadas por no haber `.git` en el candidato);
  `release_scan.py` con lista de rutas permitidas y regla `private-handoff`;
  auditoría aislada de dependencias sin hallazgos y revisión manual acotada de
  privacidad (las expresiones regulares no son una prueba de privacidad).
  Baseline de pruebas 305 → **329**.
- **Guía HTTPS local válida** (TODO-OPS-003): Caddyfile multiline canónico con
  nombre DNS de red (no IP) como RP ID, certificado mkcert de ese nombre,
  orígenes coincidentes y confianza de la CA en el teléfono; `caddy`/`mkcert`
  no están en esta máquina, así que esa validación queda declarada, no ejecutada.

Comprobaciones de cierre del paquete: suite **331 OK**; `check_docs.py --tests`
Docs OK; `release_scan.py` 0 hallazgos; `release_export.py --run-tests` exit 0;
`node --check` app.js/sw.js 0; `check_web_browser.py --channel msedge` exit 0.
Detalle y límites en las fichas de [TODO.md](../TODO.md).

**Corrección posterior por revisión independiente (2026-10-10, TODO-SEC-004):**
el gate final del vínculo tenía una ventana entre `link_session_live()` y
`store.link_identity()` sin lock compartido: un logout que entrara ahí retiraba
la sesión y el INSERT se escribía igual. Corregido con un gate **atómico
respecto al logout** (`server.lock` retenido entre comprobación y escritura,
mismo lock que usa el logout, más revalidación del titular dentro de la
transacción de escritura) y regresión determinista que fuerza el logout dentro
de esa ventana y demuestra que el lock aparece contendido (RED reproducible
quitando el lock: el logout se colaba). Recuento de pruebas 329 → 331.

## Gate de privacidad del candidato público (2026-10-10)

[TODO-PRIV-001](../TODO.md) (**`done`**, P1). Gate final sobre el candidato de
**73 ficheros**, con **dos reglas semánticas** en el escáner
(`opac-reader-identity` y `opac-loan-identifier`). Encontró dos clases de fuga.
(a) Identidad real de lector en
[my_library_renovable.html](../tests/fixtures/my_library_renovable.html)
—carné OPAC con y sin relleno de ceros más nombre y apellidos en los marcadores
`lenlec`/`nombre`/`apellidos`— junto con el historial de préstamos de esa misma
página; y (b), señalada en la revisión, los **identificadores de préstamo y
reserva** (códigos de ejemplar, `data-prppsq` y `data-di`/`DI=` de la reserva)
que seguían en otros fixtures, en un docstring del parser y en el protocolo,
aunque el bloque de lector ya fuera sintético. Varias pruebas y comentarios
esperaban/describían esos literales. La afirmación de
`TODO-PUB-002` de que «los campos de lector de los fixtures son sintéticos» era
cierta para `my_library_loans.html` y falsa para este fixture. Una búsqueda de
la identidad, sus carnés y sus códigos ligados por todo el set publicable
(fixtures, pruebas esperadas, fuentes, scripts y docs) no halló repetidores.

Hecho:
- El fixture pasa a valores sintéticos declarados en
  [absys-opac-protocol.md](absys-opac-protocol.md) (carné con y sin relleno de
  ceros, nombre partido en dos spans que se une al mismo valor) y los códigos
  de ejemplar de esa página también son sintéticos; ids `lector_box…`,
  `abnRenov…`, `data-prbarc` y el campo `CP<código>` conservan sus relaciones.
  Las pruebas que los fijaban esperan ahora los sintéticos, sin debilitar
  aserciones ni tocar el comportamiento del parser.
- `release_scan.py` añade **dos reglas semánticas** con el mismo patrón y el
  mismo reporte (solo regla, ruta y línea, nunca el dato): la primera
  `opac-reader-identity` sobre los marcadores `lenlec`/`nombre`/`apellidos`
  frente a `SYNTHETIC_READER_VALUES`, y —tras la revisión—
  `opac-loan-identifier` sobre los identificadores de préstamo/reserva frente a
  `SYNTHETIC_LOAN_IDS` (ver la ampliación abajo). Alcance declarado acotado en
  [specification.md](specification.md#nfr-dev-001), [ADR-016](decisions.md),
  [testing.md](testing.md) y la propia cabecera del script: **no** son detectores
  de datos personales arbitrarios.
- Correcciones documentales del gate: README con el contrato **v6** y un arranque
  que describe el alta real (nombre + username + contraseña, sin email) y el
  papel verificado del email; [operations.md](operations.md) separa mkcert +
  passkeys de red local de los redirect que Google realmente acepta (localhost
  de desarrollo o un origen público aceptado por el proveedor, no un nombre
  `.lan` privado) y aclara que una IP puede llevar un certificado válido sin ser
  por eso un RP ID de passkey aceptable.

RED/GREEN 2026-10-10: `python -m unittest tests.test_release_scan` → 3 fallos
antes de la regla (`'opac-reader-identity' not found in []`, lista vacía frente
a dos hallazgos esperados y `0 != 1` en el reporte); con la regla y **sin**
sanear el fixture → 4 hallazgos
`opac-reader-identity:tests/fixtures/my_library_renovable.html:19…22` (RED que
reproduce la fuga real); corregido el fixture y las expectativas → verde.
Comprobaciones de cierre de esa **primera entrega (históricas: sus recuentos de
337 tests y 447 enlaces son de ese corte intermedio, no del cierre de la
tarea)**: `python scripts/check_docs.py --tests` → Docs OK (16
documentos, 23 requisitos, 42 tareas, 447 enlaces, **337 tests**);
`python -m unittest discover -s tests -t .` → **337 OK** (168,6 s);
`node --check` de app.js y sw.js → 0; `python scripts/release_scan.py` → 73
ficheros, 0 hallazgos; `python scripts/release_export.py --run-tests` → exit 0
(ocho PASS, `suite-unittest OK (skipped=6)` por no haber `.git` en el candidato).
Límites de esa primera entrega: la regla solo cubre esos marcadores; el titular de la licencia MIT
(`jabaruben/BiblioCM`) sigue en `LICENSE`/README/`pyproject.toml` por ser
atribución pública preexistente; `.playwright-mcp/` y `.biblio-data/` se
consultaron/sin tocar; el único cambio en `biblio/` fue un comentario de
docstring y el escenario de navegador se ejecutó aun así
(`check_web_browser.py --channel msedge` → exit 0).

### Ampliación tras revisión: identificadores de préstamo y reserva (2026-10-10)

La revisión señaló que un bloque de lector sintético **no** bastaba: los códigos
de ejemplar de las filas de préstamo y el id de la reserva son historiales
personales reales, y sobrevivían en otros fixtures, en un docstring del parser y
en el protocolo. Mismo alcance de [TODO-PRIV-001](../TODO.md):

- [my_library_renovable.html](../tests/fixtures/my_library_renovable.html): sus
  dos códigos pasan a la familia sintética `9000000011`/`9000000012` con todas
  las referencias derivadas (`lector_box…`, `lector_renovMen…`, `abnRenov…`,
  `data-cobarc`, `data-prbarc`, `CP<código>`) actualizadas a la vez.
- [my_library_loans.html](../tests/fixtures/my_library_loans.html): sus tres
  códigos pasan a `9000000021`/`9000000022`/`9000000023` y `data-prppsq` a `9001`.
- [my_library_with_reservation.html](../tests/fixtures/my_library_with_reservation.html):
  `data-di` y `DI=` de la reserva pasan a `9000001`.
- Ejemplos de fuente y documentación: el formulario de renovación de
  [parser.py](../biblio/parser.py) y de
  [absys-opac-protocol.md](absys-opac-protocol.md) usan `9000000002`, la tabla
  `prbarc` usa `9000000021` y el ejemplo `rebarc_` usa `9000000003`, coherente
  con `reservable_copies.html`.
- Las pruebas que fijaban esos valores (formulario de renovación, lectura de
  préstamos y de reservas) apuntan ahora a los sintéticos: mismas aserciones,
  ningún recuento de comportamiento reducido.

RED/GREEN 2026-10-10: `python -m unittest tests.test_release_scan` → 4 fallos
antes de la regla (`opac-loan-identifier` ausente para barcode, reserva,
referencias derivadas y reporte `0 != 1`); con la regla y **sin** sanitizar →
**28 hallazgos** `opac-loan-identifier` repartidos en `biblio/parser.py:74-77`,
`docs/absys-opac-protocol.md:147-150`, los tres fixtures de préstamo/reserva y
`tests/test_parser.py:429-430` (RED que reproduce la fuga sin imprimir datos);
sanitizado → verde. Verificación: `tests.test_release_scan` → **31 OK**;
`tests.test_parser` + `tests.test_renewal` → **89 OK**; búsqueda explícita de
los 16 valores originales/relacionados (identidad, carnés y códigos ligados) por
el set publicable → **0 coincidencias** en 73 ficheros; `python scripts/release_scan.py`
→ 73 ficheros, 0 hallazgos; `python -m unittest discover -s tests -t .` →
**343 OK** (166,8 s) y `python scripts/check_docs.py --tests` → Docs OK (16
documentos, 23 requisitos, 42 tareas, 462 enlaces, **343 tests**).
`python scripts/check_web_browser.py --channel msedge` → exit 0 tras la
ampliación (el único cambio en `biblio/` volvió a ser un comentario de
docstring). Los candidatos con `--run-tests` siguen en exit 0 (ocho PASS, 7
omisiones justificadas por no haber `.git` en el candidato).
Límite deliberado: los identificadores de **ficha del catálogo** (`TITN`,
`data-bc`, `rebarc_` de `record_copies.html`) y los títulos/signaturas se
conservan: son inventario y datos bibliográficos públicos, no el historial de una
cuenta; cambiarlos no oculta qué se prestó y rompería la trazabilidad con las
fixtures de catálogo.

**Efectivo al cerrar la tarea (`done`):** recuento definitivo **343 tests** —el
337 de arriba es el corte intermedio de la primera entrega, marcado como
histórico—; `check_docs.py --tests` → Docs OK con 16 documentos, 23 requisitos,
42 tareas, **462 enlaces** y 343 tests; escáner con **dos reglas semánticas**
sobre **73 ficheros** y **0 hallazgos**; `release_export.py --run-tests` → exit
0 (ocho PASS, 7 omisiones por no haber `.git` en el candidato) y navegador →
exit 0. Comandos y límites completos en la ficha `TODO-PRIV-001` de `TODO.md`.

## Evidencia del portal real, acotada

- Notas históricas en [absys-opac-protocol.md](absys-opac-protocol.md): login,
  préstamo, renovación y reservas inspeccionados durante construcción del motor.
- Consulta de ficha **2261318, Leyendas Pokémon : Z-A**: dos ejemplares, uno
  reservable en la consulta; comprobación API HTTP + navegador + OPAC, sin crear reserva.
- El 05/10/2026 se leyeron Scratch y Versos del bosque con devolución 20/10/2026,
  15 días restantes y counter 1/1; las renovaciones habían sido realizadas por
  la persona usuaria. Se comprobó el estado mediante lecturas, no otra renovación.
- En esa consulta, ambas cuentas vinculadas examinadas tenían cero renovables.
  No convertir ese dato temporal en una regla ni estado actual de la aplicación.

No se conserva la respuesta original que anunció 12/10; la regresión reproduce
un hilo intermedio y valida el arreglo. Ver [incidents.md](incidents.md).

## Qué no existe actualmente

- APK/IPA, módulos Kotlin/Swift, publicaciones en stores o validación física móvil.
- Push, alertas en segundo plano, scheduler ni renovación automática.
- 2FA ni administración de usuarios. Email verificado, recuperación y cambio de
  contraseña **sí existen** desde 2026-10-10
  ([FR-AUTH-002](specification.md#fr-auth-002),
  [FR-AUTH-003](specification.md#fr-auth-003)); passkeys y acceso opcional con
  Google existen desde el mismo día
  ([FR-AUTH-004](specification.md#fr-auth-004),
  [FR-AUTH-005](specification.md#fr-auth-005)) con credenciales sintéticas en
  pruebas; el correo sale por SMTP configurable y las pruebas usan un servidor
  falso local, y Google usa un proveedor OIDC falso local.
- Compartición granular por carné, transferencia de vinculación o historial de concesiones.
- Rotación de clave, respaldo/restauración automatizados y migraciones más allá
  de la de identidad v0→v1→v2 (esas sí existen, versionadas con `user_version`, ver
  [TODO-DATA-001](../TODO.md) para el marco completo).
- CI ejecutada en el proveedor, OpenAPI generado, métricas/correlación de errores o despliegue público reproducible.
- Facetas UI/API ni disponibilidad resumida por resultado sin abrir ficha.
- Sincronización offline de datos privados; el SW solo guarda recursos públicos del shell.

No todos estos puntos son tareas aprobadas: los cambios de producto están marcados
`proposed` en TODO hasta que se decida su alcance.

## Defectos/gaps detectados por inspección

1. Ficha única: `record_from_document_page` toma h1 «Documento» para el título.
2. `wait` duplicado; la segunda definición referencia `time` sin importarlo globalmente.
3. Error de credenciales CLI anuncia `--password-stdin`, opción no implementada;
   búsqueda/reservas toman `[0]` de selección y faltan guardas para registro vacío.
4. Prueba ISBN fuera de TestCase no descubierta; faltan suites CLI/transporte y
   partes de sesión/anulación del cliente real.
5. Guards de sesión/búsqueda no cubren todas las respuestas de panel/detalle fuera
   de orden; falta reproducción controlada antes de decidir corrección.
6. `cover_url` copiaba img.src del portal y search lo serializaba; el fixture
   contiene token ficticio en esa URL. Sanitización implementada y probada el
   2026-10-05 (WebTests de portada, [test_covers.py](../tests/test_covers.py) y
   navegador): la portada sale como ruta propia y los valores con la ruta de
   sesión se retiran del DTO. Pendiente verificar en el portal real el resto de
   representaciones (TODO-SEC-001); sin afirmar que se haya auditado en vivo.
7. `search(page>1)` envía DOC=page; el fixture usa DOC=11/21 para páginas 2/3.
   La navegación debe seguir href del portal, pendiente TODO-CAT-002.
8. El escenario de navegador no cubre logout en UI, anulación de reservas,
   un 401 en uso, fallo parcial de una cuenta, renovación rechazada,
   resultados/ejemplares vacíos ni los botones de paginación: TODO-TEST-002.
9. El DTO de búsqueda devuelve `subjects`, `language`, `classification`,
   `doc_type`, `openurl` y `raw_marc` que la UI no pinta: TODO-CAT-003.
10. El portal ofrece facetas y su lista no trae disponibilidad; ni el motor ni
    el API ni la UI las usan: TODO-CAT-004.
11. Préstamos, reservas y lector traen `signature`, `branch_address`, `created`,
    `record_id` y `card_expires` que la UI muestra solo en parte: TODO-UX-002.
12. Portadas ausentes en el catálogo, diagnosticadas el 2026-10-07: (a) la ficha
    única a la que salta el portal con un resultado traía portada y no se leía;
    (b) `GET cover` solo servía lo registrado en los últimos 600 s y devolvía
    404, que la UI interpretaba como «sin portada»; (c) en la lista se tomaba el
    primer `<img>` de la tarjeta, no la imagen de portada; (d) los préstamos no
    traían `record_id` y ni préstamos ni reservas pedían portada. Corregido en
    TODO-UX-003; quedan como límite las fichas que el portal no ilustra y la
    ausencia de verificación en vivo.
13. Detectados por inspección el 2026-10-09 y corregidos en
    [TODO-SVC-002](../TODO.md) bajo
    [NFR-SVC-002](specification.md#nfr-svc-002): (a) una desconexión del
    cliente al escribir la respuesta producía un segundo intento de respuesta
    (un `502` tras un `200` de portada ya empezado) y una excepción que salía
    del hilo hacia `socketserver.handle_error` (traceback en stderr,
    reproducido con un RST real); (b) `dispatch` retenía el lock global del
    store y el de la sesión durante toda la E/I con el portal, de modo que una
    renovación o una descarga de portada lentas bloqueaban peticiones sin
    relación. Regresiones en WebTests (`wfile` falso, RST real y Event/barrera);
    la espera de la revocación y la bajada se conserva con la puerta de
    operaciones, verificada por mutación. (c) La revisión independiente del
    mismo día encontró que (b) dejaba un hueco en las cuentas: una operación
    que ya había autorizado y descifrado podía terminar —incluso una
    renovación, que muta el portal— **después** de que el titular borrara la
    cuenta o rotara su contraseña, y la documentación afirmaba sin prueba que
    eso «fallaba cerrado». Corregido con la puerta por cuenta (la
    desvinculación/rotación espera a esas operaciones), RED/GREEN con
    Event/barrera y verificado por mutación; también se normaliza la clave de
    puerta igual que `store.text` para que un id con espacios no la esquive.

Se registran como trabajo pendiente, no como fallos de usuarios demostrados en
vivo ni como cambios ya aplicados durante la documentación.

## Auditoría 2026-10-05: lectura, escenarios y capacidades

**Lectura completa, 16 documentos validados por `scripts/check_docs.py`:**
[README principal](../README.md), [AGENTS](../AGENTS.md), [TODO](../TODO.md),
[índice de documentación](README.md), [specification](specification.md),
[architecture](architecture.md), [backend](backend.md), [frontend](frontend.md),
[api](api.md), [testing](testing.md), [status](status.md),
[operations](operations.md), [decisions](decisions.md),
[incidents](incidents.md) y [absys-opac-protocol](absys-opac-protocol.md).
Resultado: sin enlaces ni IDs rotos; las únicas
contradicciones halladas son los defectos 1–12 de arriba y el desajuste de
versiones que motivó el paso de API `2` a `3` y de caché `v6` a `v7`, y luego
de API `3` a `4` con caché `v7` a `v8` en TODO-UX-003. La revisión incluyó
también el handoff legado local `docs/HANDOFF-SOL.md`, que hoy está excluido
del set publicable (ver abajo).

`docs/HANDOFF-SOL.md` es material legado **solo local y no publicado**: no es
una fuente de verdad, propone un contrato distinto (API `1` con rutas en
español, token por arranque, DPAPI) y recuentos de tests antiguos, en contra de
[api](api.md) y [status](status.md), y contiene datos personales identificativos.
Está excluido del repositorio público mediante una entrada exacta en
`.gitignore` y se conserva intacto en el trabajo local; no debe copiarse,
enlazar desde documentación publicada ni usarse para decisiones de contrato.
Quien lo retome debe elegir una sola línea de contrato antes de tocar código de
API, siguiendo [api](api.md) y este estado.

**Corrección tras revisión independiente (2026-10-05):** la portada se servía
con `Cache-Control: private, max-age=1800` y ahora responde `no-store`, igual
que el resto del API, manteniendo la exclusión del service worker. Además la
validación de la URL de portada se endureció: `origin()` descarta userinfo,
puerto malformado, backslash y caracteres de control, y `has_unsafe_path()`
rechaza dot segments y separadores percent-codificados, tanto en
`is_portal_url` como en `get_image` y en el handler de redirecciones (sobre la
Location en crudo). Una sonda adversarial posterior encontró que una
codificación anidada (`/abnetopac/%252525252e…`) tardaba más de cuatro capas
en convertirse en `../` y se colaba: ahora `path_layers()` revisa **todas** las
capas y devuelve `None` (rechazo) si la normalización no estabiliza dentro de
`MAX_PATH_DECODINGS`, con coste acotado. Todo se rechaza antes de hacer
ninguna petición. Evidencia RED/GREEN en [TODO](../TODO.md) (TODO-SEC-001)
y en [test_covers.py](../tests/test_covers.py).

**Escenarios de navegador reproducibles**
([check_web_browser.py](../scripts/check_web_browser.py), Edge, fakes con
servidor y BD temporales; escritorio 1280×900 y móvil emulado 390×844):
respuesta antigua sin versión, registro, vinculación, solicitud/aprobación,
permisos `read`/`manage`, panel conjunto y filtro, estado de carga accesible
(arranque/restauración **renderizado y dentro del viewport en escritorio y
móvil**, con spinner estático bajo `prefers-reduced-motion`, login, refresco,
error de `library` y logout con respuesta en vuelo de `library` y de `settings`),
renovación con recarga, catálogo y detalle, reservables con DTO antiguo
rechazado, reserva simulada, listado de reservas, revocación y portadas
servidas por la app en catálogo, préstamo y reserva (cargada, rota con marcador
recuperado, URL de proveedor sin pintar y escritorio), passkeys con el
autenticador virtual de Chromium (alta con reautenticación, borrado, listado y
login sin contraseña, en escritorio y móvil emulado, sobre `localhost` porque
Chromium rechaza un RP ID con forma de IP) y acceso con Google contra el
proveedor OIDC falso local (vinculación con email verificado + reautenticación
y entrada con la cuenta vinculada, también en móvil).
No cubren lo que queda en TODO-TEST-002 y no acreditan dispositivos físicos.

**Capacidades de motor/API frente a la UI:**

| Capacidad existente | API | UI | Tarea |
|---|---|---|---|
| Portadas del catálogo | `GET /api/cover` con descubrimiento bajo demanda | Sí, con marcador de respaldo | TODO-UX-001 y TODO-UX-003 |
| Portadas de préstamos y reservas (`cover_url` + `record_id`) | Sí | Sí, con marcador de respaldo | TODO-UX-003 |
| Bytes de portada memorizados tras validarse (TTL y tope) | Sí, solo en memoria y tras autorizar | Sí (`no-store`, el servidor los reutiliza) | TODO-PERF-001 |
| Estado de carga accesible del panel y del arranque | — | Sí (`role="status"` + `aria-busy` + spinner) | TODO-UX-003 y TODO-UI-002 |
| Metadatos MARC (`subjects`, `language`, `classification`, `doc_type`, `openurl`) | Sí | No | TODO-CAT-003 |
| Facetas del portal y disponibilidad por resultado | No | No | TODO-CAT-004 |
| `signature`/`branch_address` de préstamo, `created`/`record_id` de reserva, `card_expires` | Sí | Parcial | TODO-UX-002 |
| Ficha de ejemplar (`copy_detail`, ACC=143) | No | No | sin necesidad registrada |
| Historial, búsquedas guardadas y demás ACC del portal | No | No | sin necesidad registrada; decisión de producto |
