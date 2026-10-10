# Desarrollo con SDD y TDD

Estado de evidencia y número de pruebas: [status.md](status.md).
Requisitos: [specification.md](specification.md). Trabajo: [TODO.md](../TODO.md).

## Qué implica TDD en este proyecto

La base contiene pruebas de comportamiento y regresión; no se afirma que todo
el historial haya sido escrito siguiendo RED primero. Desde esta documentación,
los cambios de comportamiento se trabajan con el siguiente ciclo verificable.
Para documentación/formatos sin impacto funcional, validar coherencia/enlaces;
no crear tests que solo repitan texto o implementación sin aportar evidencia.

### 1. SPEC

- Elegir una tarea o crearla en TODO con ID, estado, aceptación y requisito.
- Contrastar intención con usuario/especificación, contrato actual y código.
- Si cambia significado de permisos, persistencia o compatibilidad, registrar la
  decisión antes de escribir una solución. Las mejoras propuestas no son encargos aceptados.
- Definir un caso observable: entrada, estado previo, resultado y efecto persistente.

### 2. RED

- Escribir el test mínimo que falla por el motivo correcto; ejecutarlo y guardar
  comando + fallo relevante en la tarea/evidencia de cierre.
- Bug de parser: fixture representativo sanitizado, con el marcado que lo provoca.
- Bug de autorización: probar el acceso indebido y que no se crea cliente/POST OPAC.
- Bug de mutación: verificar selección, estado posterior y número de envíos.
- Bug visual/async: usar navegador si el defecto no es observable solo en el motor/API.
- Usar fechas controladas y clientes falsos. No simular verde cambiando el dato esperado.

### 3. GREEN

- Implementar la corrección más pequeña que cumpla la especificación.
- Conservar arquitectura y APIs salvo cambio acordado/documentado.
- Ejecutar el caso dirigido; después suites de las capas afectadas.
- No renovar, reservar o anular en una cuenta real para obtener un verde automático.

### 4. REFACTOR

- Mejorar legibilidad solo donde el cambio lo requiere, manteniendo pruebas en verde.
- Actualizar contratos/spec/ADRs si cambió una decisión, y registrar nuevos límites.
- Ejecutar las comprobaciones de cierre que se describen abajo.

## Mapa de pruebas existente

| Fichero | Qué verifica | Qué no acredita |
|---|---|---|
| [test_parser.py](../tests/test_parser.py) | DOM, fechas, lector, préstamos, renovaciones derivadas, reservas, MARC, formularios, copies y alerts | Transporte real y toda la navegación de AbsysClient |
| [test_renewal.py](../tests/test_renewal.py) | POST adoptado, login nuevo, fecha final/counter, negativas y un único envío | Otra renovación ejecutada en el portal real |
| [test_reservable.py](../tests/test_reservable.py) | Filas completas, índices con huecos, texto limpio, selección barcode y reserva verificada | Todos los asistentes posibles del proveedor |
| [test_store.py](../tests/test_store.py) | Clave perdida, incompatible y clave de entorno | Migraciones, rotación, restauración operativa |
| [test_web.py](../tests/test_web.py) | HTTP local, identidad, CSRF/origin, permisos, aislamiento, persistencia, versión, DTOs, portadas, CSP del shell (`img-src` limitado a `'self' blob:`), puerto exclusivo, concurrencia con Event/barrera (puertas de usuario y de cuenta) y desconexión del cliente con `wfile` falso y RST real | Rendimiento bajo carga real, proxy real y todo el cliente OPAC |
| [test_covers.py](../tests/test_covers.py) | Resolución de `cover_url` en lista y en la ficha única, origen/CGI permitidos, autoridades malformadas, dot segments y separadores codificados, tamaño/tipo y redirecciones del servidor de portadas con servidores locales | El portal real y la imagen que sirve en vivo |
| [test_release_scan.py](../tests/test_release_scan.py) | Reglas de material privado del escaneo de publicación (claves privadas, Fernet, tokens de proveedores, JWT, rutas OPAC de alta entropía y nombres de fichero prohibidos, incluido el handoff legado), lista de rutas permitidas de primer nivel (`path-not-allowlisted`), regla semántica `opac-reader-identity` sobre los marcadores `lenlec`/`nombre`/`apellidos` y regla `opac-loan-identifier` sobre los identificadores de préstamo/reserva (`data-prbarc`, `data-cobarc`, `data-prppsq`, `data-di`, `prbarc`, `CP<código>`, `lector_box…`, `abnRenov…`, `lector_renovMen…`, `DI=`) —valor no sintético → hallazgo, valores de los fixtures → sin hallazgo— con proyecto real sin identidad de lector ni códigos de historial, umbral de entropía calibrado contra los fixtures, reporte que no imprime el contenido, BD ignorada fuera del set publicable y proyecto real limpio y dentro de política | Una auditoría de seguridad completa; el escáner no detecta lógica malintencionada ni demuestra privacidad, y esas dos reglas **no** detectan datos personales arbitrarios: solo esos marcadores, ni los identificadores de ficha del catálogo (`TITN`, `data-bc`, `rebarc_`) |
| [test_release_export.py](../tests/test_release_export.py) | Candidato público limpio (TODO-PUB-002): la exportación copia **exactamente** el set publicable, nunca material ignorado (`.biblio-data/`, `docs/HANDOFF-SOL.md`, `*.sqlite3`), rechaza un destino dentro del repositorio, señala material privado plantado en el destino y valida el candidato real con escaneo, `check_docs`, importación del paquete y sintaxis JS | La suite completa dentro del candidato (se ejecuta con `--run-tests`, fuera de esta prueba) y la publicación real |
| [test_identity.py](../tests/test_identity.py) | Email verificado con código por un servidor SMTP falso local (hash en BD, un solo uso, caducidad, anti-enumeración, email ocupado silencioso, SMTP caído sin token vivo), login con email verificado y alias username intacto, cambio de contraseña cerrando las demás sesiones sin tocar cifrado/vínculos, recuperación con cierre total de sesiones, rate limit por IP y ruta, y migraciones de esquema sobre fixtures temporales (v0→v2, v1→v2, base reciente, reapertura y rollback atómico preservando IDs/vínculos/carnés/crypto) | Proveedor SMTP real, passkeys ni OIDC (otras suites); no migra datos reales |
| [test_passkeys.py](../tests/test_passkeys.py) | Passkeys contra el servidor local con el autenticador sintético de [webauthn_fake.py](../tests/webauthn_fake.py): registro/login con verificación real de la librería, reautenticación para añadir/borrar (y su caducidad), challenge de un solo uso y caducado, origen ajeno, payload malformado, reto de otro usuario, firma/UV/contador, credencial ajena, no enumeración en opciones, login concurrente con un único reto, rechazo del servidor en host HTTP no local y orígenes de confianza (Host hostil sobre TLS → 403, Host no canónico → 400, coincidencia exacta del origen HTTPS listado, flujo completo sobre origen configurado y parsing canónico, TODO-SEC-003) | Hardware real, Safari/Firefox y el portal OPAC |
| [test_oidc.py](../tests/test_oidc.py) | Acceso con Google contra el proveedor OIDC falso local de [fake_oidc.py](../tests/fake_oidc.py): opt-in (sin configuración todo 503), `state`/nonce/PKCE de un solo uso y caducados, verificación del token (firma, issuer, audiencia, expiración, nonce, token malformado), identidad por `sub`, sin merge por email, alta explícita con alias determinista, vinculación/desvinculación con reautenticación y email verificado, unicidad de la cuenta Google, rate limit, endpoints no locales rechazados y callback derivado solo de un origen de confianza (Host hostil → 403, `BIBLIO_GOOGLE_REDIRECT_URI` no canónico/no confiable → 503, TODO-SEC-003); **login CSRF y sesión del vínculo** (TODO-SEC-004): cookie de enlace emitida en `start` (alcance/ruta, `HttpOnly`, `SameSite=Lax`, TTL del `state` y `Secure` sobre HTTPS), digest en el estado sin el valor en claro, y en **dos contextos de navegador**: el original completa y la cookie se retira; callback sin cookie, con cookie ajena, transferido a otro navegador con su propio flujo, reutilizado tras completar y caducado → rechazo sin ninguna llamada al proveedor y sin consumir el estado, con el navegador original aún capaz de terminar; `link` rechazado con logout pendiente, con la sesión rotada y con el email desverificado, gate final **atómico respecto al logout** (logout contendiente lanzado dentro de la ventana comprobación→escritura: el lock del servidor aparece contendido, el vínculo se escribe con la sesión viva y el logout se ordena detrás), revalidación del titular en la propia transacción de escritura (`require_verified`) y aceptado desde el navegador inician | Google real, credenciales OAuth de la persona y dispositivos |
| [check_web_browser.py](../scripts/check_web_browser.py) | Flujos UI en dos contextos, móvil emulado, recarga, estado de carga accesible en arranque/login/refresco/error/logout (con respuestas obsoletas de `library` y de `settings`), renderizado y presencia en viewport del spinner con movimiento normal y reducido, renovación con la respuesta retenida en escritorio y móvil (bloqueo del botón, `aria-busy`+progreso, un solo POST, aviso solo tras panel verificado), reservables, portadas de catálogo/préstamo/reserva (cargada/rota/URL antigua) con caché RAM por blob URL invalidada en logout, `pagehide` y cambio de permiso, sin persistencia en CacheStorage/localStorage/sessionStorage, aviso de origen no confiable, passkeys con el autenticador virtual de Chromium (alta con reautenticación, borrado, listado y login sin contraseña en escritorio y móvil emulado, siempre en `localhost` porque Chromium rechaza un RP ID con forma de IP), acceso con Google contra el proveedor OIDC falso local (vincular con email verificado + reautenticación y entrar con la cuenta vinculada, también en móvil) y errores antiguos | Dispositivos físicos, accesibilidad completa, PWA instalada, mkcert ni un host de red local real, Safari/Firefox ni Google real |
| [check_live_reservable.py](../scripts/check_live_reservable.py) | API + navegador + portal real, solo consulta de una ficha | Alta real de una reserva |

Fixtures en [tests/fixtures](../tests/fixtures) son HTML reproducible. El test
`test_isbn_sin_subcampo_marc` aparece como función suelta fuera de `TestCase` y
**no está en el descubrimiento unittest actual**; se registra como pendiente,
no como cobertura ya existente.

## Comandos de verificación sin portal

Desde la raíz, con dependencias instaladas:

```powershell
python -m unittest discover -s tests -t .
python scripts/check_docs.py
python scripts/release_scan.py
python scripts/release_export.py --run-tests
node --check biblio/static/app.js
node --check biblio/static/sw.js
```

Node no es una dependencia runtime. La comprobación de sintaxis no sustituye una
prueba de navegador. Si no está instalado, registrar el bloqueo/omisión, no un pase.
`release_scan.py` es el guardia previo a publicar (TODO-SEC-002): sale 0 si el
set publicable está limpio, 1 si halla material privado y 2 si no puede
listarlo; imprime solo regla, ruta y línea, nunca el contenido, y aplica además
la lista de rutas permitidas (TODO-PUB-002). `release_export.py` exporta el
candidato público a un directorio temporal y lo valida sin ficheros ignorados
(TODO-PUB-002): no crea commit, no publica y borra el candidato salvo `--keep`.

Ejemplos de comprobación dirigida:

```powershell
python -m unittest tests.test_renewal
python -m unittest tests.test_reservable
python -m unittest tests.test_covers
python -m unittest tests.test_web.WebTests.test_read_permission_allows_queries_and_blocks_all_mutations
python -m unittest tests.test_web.WebTests.test_search_cover_is_served_by_the_app_without_opac_tokens
python -m unittest tests.test_web.WebTests.test_second_server_cannot_share_the_same_listening_address
python -m unittest tests.test_web.WebTests.test_slow_cover_download_does_not_block_unrelated_requests
python -m unittest tests.test_web.WebTests.test_disconnect_while_writing_an_image_is_not_answered_twice
python -m unittest tests.test_web.WebTests.test_static_assets_and_traversal
python -m unittest tests.test_release_scan
python scripts/release_export.py
python -m unittest tests.test_release_export
python scripts/release_scan.py
python -m unittest tests.test_identity
python -m unittest tests.test_identity.EmailVerificationTests tests.test_identity.PasswordChangeTests
python -m unittest tests.test_identity.RecoveryTests tests.test_identity.SchemaMigrationTests
python -m unittest tests.test_passkeys
python -m unittest tests.test_passkeys.PasskeySecurityTests
python -m unittest tests.test_oidc
python -m unittest tests.test_oidc.GoogleFlowTests tests.test_oidc.GoogleTokenVerificationTests
```

La suite usa HTTP localhost, BD temporales y credenciales ficticias, sin conexión
al OPAC. Los directorios `.biblio-test-*` se eliminan al terminar y están ignorados.
Un aborto puede dejar temporales: identificar su origen antes de limpiar.

## Navegador opcional

```powershell
python -m pip install playwright
python scripts/check_web_browser.py --channel msedge
```

Necesita Edge instalado para ese canal. El script acepta `--playwright-path`
para una instalación separada de la herramienta. Playwright no pertenece a las
dependencias runtime de `pyproject.toml`. El script levanta su servidor efímero;
no exige detener ni usar el servidor de la persona usuaria.

Para un cambio en render, formularios, estado, permiso visual o SW, ampliar el
escenario relevante y ejecutarlo. Mocks deben compartir el estado de operaciones
entre clientes nuevos: si la falsa renovación no cambia la lectura posterior,
no prueba consistencia tras recarga.

Cuando el escenario deba observar la UI **mientras** una petición sigue en
vuelo, retenerla en el enrutador (`hold`/`wait_held`/`release_held` en
[check_web_browser.py](../scripts/check_web_browser.py)) y continuarla después.
Un `time.sleep` dentro de un enrutador de Playwright bloquea las aserciones:
medido el 2026-10-08, una aserción con `timeout=500` tardó 3,54 s en fallar, de
modo que las esperas se vuelven indeterminadas y la comprobación, una carrera.
`wait_held` bombea el event loop con `page.evaluate("1")` porque un bucle de
`time.sleep` por sí solo no llega a invocar el enrutador.

Para estados de carga no basta comprobar que el nodo existe o es visible:
`assert_boot_rendered` lee el `display` calculado, el `animation-name` y la caja
del spinner, comprueba que el bloque completo cae dentro de `innerWidth`/
`innerHeight` y, con `page.emulate_media(reduced_motion="reduce")`, que la
rotación se detiene sin perder el indicador. La comprobación se repite en los
dos contextos (escritorio y móvil emulado) antes de soltar la sesión retenida.

## Consulta real opcional y sus límites

```powershell
python scripts/check_live_reservable.py --label "Principal" --record 2261318 --title "Leyendas Pokémon : Z-A" --query pokemon
```

Usa credenciales de un carné ya vinculado, en un usuario/BD temporal. Lee el portal
y bloquea acciones de renovar/reservar/anular desde la página de prueba. Admite
`--data-dir`, `--channel`, `--playwright-path` y `--screenshot`. La ficha/opciones
pueden cambiar: un 409 o ausencia de reservables requiere distinguir política del
portal de una regresión, no cambiar expectativas sin investigar.

Diagnóstico de solo consulta:

```powershell
python scripts/inspect_loans.py --list-accounts
python scripts/inspect_loans.py --label "Principal" --title scratch --title versos
python scripts/inspect_catalog.py pokemon --record 2261318 --label "Principal"
```

No usar resultados con carnés, datos personales o tokens como fixtures sin
sanitizar. Las pruebas de mutaciones son simuladas por defecto. La comprobación
manual de una operación real debe responder a una acción solicitada por la persona,
no repetirse para validar un cambio que ya ha modificado el préstamo.

## Matriz de cierre por tipo de cambio

| Cambio | Comprobaciones necesarias |
|---|---|
| Parser/regla de dominio | Regresión RED, test dirigido, suite unittest |
| Cliente de mutación | Lo anterior + payload, una mutación y estado posterior en fake HTTP |
| Store/autorización/API | Test permitido/denegado y aislamiento, suite unittest |
| Frontend | Sintaxis, escenario navegador relevante, tests de API si cambia contrato |
| PWA/servidor/assets | Sintaxis SW, rutas/manifest/caché, navegador de las rutas afectadas |
| Persistencia | Estado anterior/posterior y reapertura; plan de migración si cambia esquema |
| Documentación | `check_docs.py`, revisión de ejemplos y comandos; actualizar estado con evidencia real |

No repetir consultas reales, instalaciones ni pruebas amplias después de un
verde suficiente si nada cambió ni queda una duda concreta. Las comprobaciones
no ejecutadas, fallidas o interrumpidas nunca son «pasadas».

## Definición de terminado

1. Aceptación satisfecha o limitación explícita con tarea propia.
2. Regresión conductual y suites requeridas pasan; consignar comandos/resultados.
3. Contrato, especificación y documentación de capa actualizados si cambian.
4. `status.md` refleja nivel de implementación/verificación; TODO tiene evidencia
   antes de pasar a `done`. Si bloqueado, dejar `blocked` con siguiente acción.
5. Revisar cambios y preservar trabajo ajeno, especialmente archivos untracked.
6. Comunicar resultado y límites sin atribuirse operaciones que no se ejecutaron.

Formato de evidencia recomendado: fecha, comando, resultado, escenario/datos
ficticios, alcance y omisiones. No registrar passwords ni tokens como evidencia.
