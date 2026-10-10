# Incidencias y regresiones que deben conservarse

Estas notas son historia de diagnóstico, no el estado actual de los préstamos.
El detalle de implementación vigente está en [backend](backend.md), [frontend](frontend.md)
y [estado](status.md). Los defectos no resueltos se editan en [TODO](../TODO.md).

## INC-001 — Registro pide un carné que no aparece

- Síntoma: pantalla de registro BiblioCM, respuesta «Accede con tu carné».
- Evidencia: frontend nuevo servido por un backend antiguo que seguía en memoria.
- Arreglo inicial: detectar forma de session incompatible. Arreglo reforzado:
  header de versión de la API comprobado en toda respuesta (v2 al aplicarlo,
  hoy `3`) y versión pública consultable.
- Regresión: script de navegador recibe session antiguo (incluso con campo user)
  sin versión, muestra aviso y bloquea acceso.
- Diagnóstico futuro: consultar `/api/version`; recargar HTML no actualiza el
  código Python que un proceso ya importó.

## INC-002 — Reservables muestran atributos HTML y una URL de sesión

- Síntoma: `copiasRes_locCont"> ... < a href=...` en lugar de biblioteca y signatura.
- Defecto: búsqueda por substring de barcode y recorte ±1500 caracteres; podía
  comenzar/terminar en medio de una etiqueta. El fallback `copy.row` lo mostraba
  literalmente. Un parser de fila completa ya corregido no protegía contra la
  respuesta de un servidor antiguo todavía activo.
- Arreglo: DOM completo, metadata estructurada, índices con huecos, API sin row,
  rechazo de DTO incompleto, ausencia de fallback y comprobación de versión.
- Evidencia real: ficha Z-A con dos copias y una opción de reserva en la consulta;
  pantalla verificada por HTTP + navegador + OPAC sin crear reserva.
- Regresiones: ReservationParserTests, WebTests de row/DTO antiguo y navegador
  con el texto roto inyectado como respuesta antigua.

## INC-003 — Dos procesos Python responden en el puerto 8000

- Síntoma: tras arrancar proceso nuevo seguían llegando respuestas sin el
  contrato actualizado; los archivos estáticos sí mostraban cambios.
- Evidencia: procesos antiguos y nuevo coexistían; en Windows la reutilización
  de dirección del servidor permitía compartir dirección/puerto. La inspección
  de un único listener o el PID devuelto por Start-Process no bastaron.
- Arreglo: cerrar duplicados del proyecto, `allow_reuse_address=False` en Windows
  y `SO_EXCLUSIVEADDRUSE`; arranque anuncia versión, endpoint devuelve versión.
- Regresión: una segunda AppServer sobre la dirección activa debe fallar y la
  primera debe seguir funcionando.
- Diagnóstico: listar procesos, confirmar origen antes de cerrar, verificar
  respuesta HTTP de versión después de arrancar. No matar todo Python indiscriminadamente.

## INC-004 — Renovación anuncia 12/10, recarga muestra 20/10

- La persona usuaria renovó Scratch y Versos del bosque y vio primero 7 días,
  después 15. Se consultaron ambos: el 05/10/2026 devolvían fecha 20/10/2026 y 1/1.
- Defecto encontrado en código: se descartaba Response del POST y se adoptaba
  otra vez la página anterior al envío (`_refresh(page)`). La comprobación usaba
  el hilo anterior en vez de el acceso nuevo que realiza una recarga de la web.
- Límite de evidencia: no se guardó la respuesta original que anunció 12/10.
  No se afirma conocer toda la temporización interna del proveedor ni que esa
  petición exacta haya sido capturada. El defecto y un estado intermedio equivalente
  se reproducen en la regresión.
- Arreglo: `_refresh(response)`, login nuevo, comprobar fecha posterior y contador
  mayor, no repetir la mutación. UI recarga panel antes de anunciar fecha/días.
- Regresiones: RenewalClientTests con estado intermedio 12/10 y final 20/10;
  HTTP con cliente nuevo; navegador comprueba tarjeta/aviso y recarga coherentes.
- No validar este caso renovando de nuevo libros que ya consumieron su renovación.
  «Días restantes» no significa que una recarga añada otra prórroga.

## INC-005 — Una desconexión del cliente provoca un segundo 502 y un traceback

- Síntoma: al cortar la conexión mientras el servidor escribía una portada,
  stderr recibía `Exception occurred during processing of request` con **dos**
  `ConnectionResetError`/`BrokenPipeError` seguidas.
- Evidencia: reproducido en local el 2026-10-09 con un RST del cliente
  (`SO_LINGER=0`) mientras la descarga estaba retenida: `ConnectionResetError
  [WinError 10054]` al escribir las cabeceras del `200` y otra igual al
  intentar el `502`. También con `wfile` falso: la misma conexión recibía
  `HTTP/1.1 200 OK` seguido de `HTTP/1.1 502 Bad Gateway`.
- Defecto: `respond`/`respond_image` escribían sin proteger el socket; la
  `OSError` caía en el `except Exception` de `api()`, que intentaba un segundo
  `respond(502)` sobre una conexión que ya había empezado una respuesta, y esa
  segunda excepción salía del hilo hacia `socketserver.handle_error`.
- Arreglo: la escritura queda envuelta; una `OSError` de socket marca la
  conexión como desconectada y la cierra, y `error_response` no emite nunca una
  segunda respuesta si la primera empezó. Solo el socket cuenta como
  desconexión: con el cliente conectado los errores reales siguen dando su
  status (NFR-SVC-002, ADR-013).
- Regresiones: WebTests con `wfile` falso
  (`test_disconnect_while_writing_an_image_is_not_answered_twice`,
  `test_header_write_failure_closes_without_a_second_response`,
  `test_real_errors_keep_their_status_for_a_connected_client`) y desconexión
  real sobre HTTP local
  (`test_client_reset_during_a_cover_response_leaves_the_server_usable`).
- Diagnóstico: si vuelve a aparecer un traceback en stderr, buscar una segunda
  escritura después de un fallo de socket; `/api/version` debe seguir
  respondiendo tras la desconexión.

## INC-006 — Fallo de correo como oráculo de enumeración y carrera en el cambio de contraseña

Encontrados por revisión independiente el 2026-10-10 sobre la implementación de
[FR-AUTH-002](specification.md#fr-auth-002)/[FR-AUTH-003](specification.md#fr-auth-003)
(ADR-017).

- **Oráculo durante una incidencia de correo.** `auth/password/recovery/request`
  (y `auth/email/request`) devolvían `502` cuando el proveedor SMTP fallaba
  **solo** si el email existía verificado, y el `200` genérico cuando no existía
  o no estaba verificado: una incidencia del proveedor distinguía cuentas
  registradas de no registradas. Reproducido con el SMTP falso bloqueado:
  `200 != 502`. Arreglo: el fallo de entrega retira el código y responde el
  **mismo** `200` genérico que un envío satisfactorio; el detalle queda en el
  servidor. El `503` sin configurar SMTP se mantiene porque es global y previo,
  y no depende del email.
- **Carrera en el cambio de contraseña.** `Store.change_password` verificaba la
  contraseña actual leyendo bajo el lock, soltaba el lock, calculaba scrypt y
  escribía después: dos cambios concurrentes —o un cambio y un reset— podían
  ambos verificar contra la contraseña vieja y pisarse, con dos «éxitos» y una
  sola contraseña final que además no correspondía al segundo éxito.
  Reproducido con dos hilos y barrera: `2 != 1` (los dos reportaron éxito).
  Arreglo: verificar y escribir en la misma sección crítica (lock + transacción
  del store); la carrera queda serializada y exactamente un cambio gana.
- Regresiones: `tests.test_identity`
  (`test_delivery_failure_is_not_an_oracle_for_email_request`,
  `test_delivery_failure_is_not_an_oracle_for_recovery`,
  `test_concurrent_changes_cannot_both_verify_the_old_password`,
  `test_concurrent_change_and_reset_leave_one_consistent_password`), con el
  proveedor falso bloqueado y sin llamadas a ningún servicio real.
- Diagnóstico: si alguien reporta que «el correo no llega y la web dice que
  sí», revisar la configuración `BIBLIO_SMTP_*` y el proveedor: la respuesta
  HTTP ya no distingue ese fallo a propósito. No reintroducir un status
  distinto según exista la cuenta.

## Notas históricas del protocolo

El documento [OPAC](absys-opac-protocol.md) recoge otras causas ya protegidas:
lector en spans variables, banner de sobrepaso oculto, umbral de renovación,
`CP<barcode>` frente a barcode como campo, diccionario de mensajes y varias tablas
de copias. No simplificar esas reglas basándose en un solo HTML reciente.
