# Continuidad de BiblioCM para agentes

## Leer al comenzar

1. [docs/README.md](docs/README.md): índice y fuentes de verdad.
2. [docs/status.md](docs/status.md): implementación y límites de evidencia.
3. [TODO.md](TODO.md): única lista de tareas y estados.
4. Requisito afectado en [docs/specification.md](docs/specification.md), contrato
   [docs/api.md](docs/api.md) y documento de capa antes de editar.

Trabajar sobre la petición actual del usuario. Una tarea `proposed` no es una
funcionalidad aprobada. No implementar todo el backlog porque exista.

## Arquitectura que se debe conservar

- Motor Python (`client/http/parser/dom/models`), API/store Python y PWA nativa
  HTML/CSS/JS. CLI separada. No hay React, Kotlin, Swift ni backend del proveedor.
- No mezclar usuario BiblioCM, carné OPAC, alias CLI y sesión OPAC.
- API actual **4**, identificada en cada respuesta JSON. Versionar backend + UI
  cuando cambie contrato; revisar versión de caché SW si cambian assets.
- Source files y flujos: [arquitectura](docs/architecture.md),
  [backend](docs/backend.md), [frontend](docs/frontend.md).

## Invariantes de producto y dominio

- Autorizar en servidor antes de descifrar/operar; `read` nunca muta.
- Concesión cubre carnés directos presentes/futuros del titular y no es transitiva.
  Cambiarlo exige especificación/decisión, no un refactor silencioso.
- Préstamo/reserva se selecciona con `account` + identificador, no solo título/barcode.
- Navegar siguiendo href/action/códigos del último HTML; no reconstruir tokens OPAC.
- Disponible después de una fecha no es disponible ahora; copias y reservables son listas distintas.
- No recortar HTML para datos ni restaurar fallback público `row`.
- Renovación: adoptar POST, acceso nuevo, date/counter avanzados, un único envío;
  confirmación y panel deben coincidir. No eliminar ese login para ahorrar peticiones.
- Reservar una copia: barcode reencontrado, índice original, NCOP=1, verificar nueva reserva.
- Privados fuera de SW/cache persistente del navegador. Passwords/claves/tokens
  fuera de logs, ejemplos, commits y respuestas.

## Flujo SDD/TDD requerido

1. Inspeccionar estado del repositorio (`git status --short`) y el código relevante.
   Un diff vacío no incluye archivos untracked: no tratar todo el proyecto como limpio.
2. Crear/elegir tarea; poner `in_progress`, responsable, aceptación y requisito.
3. Para comportamiento/bug, SPEC → test RED reproducible → GREEN mínimo → REFACTOR.
   [docs/testing.md](docs/testing.md) define suites y evidencias necesarias.
4. Hacer cambios coherentes y localizados. Preservar trabajo ajeno y datos locales.
   No añadir frameworks/dependencias, publicar, migrar datos reales o modificar
   permisos de producción como parte de una corrección rutinaria.
5. Actualizar contrato/especificación/docs/estado afectados. Decisiones de
   arquitectura en [docs/decisions.md](docs/decisions.md); tareas en TODO, no otra lista.
6. Verificar y registrar evidencia antes de `done`. Si bloqueado, indicar bloqueo
   y siguiente acción; checks omitidos/interrumpidos no son pases.

## Comprobaciones y operación

```powershell
python scripts/check_docs.py --tests
python -m unittest discover -s tests -t .
node --check biblio/static/app.js
node --check biblio/static/sw.js
```

Seleccionar comprobaciones según [testing.md](docs/testing.md): para una edición
solo documental bastan checker/revisión/validación de los comandos; no inventar
tests de producto para espejar Markdown. Para UI usar el escenario de navegador
afectado. Playwright es opcional y sus scripts usan servidor/BD temporales.

Pruebas normales sin portal ni credenciales reales. No repetir una renovación,
reserva o anulación real para investigar o conseguir verde. Usar fixtures y fakes;
una consulta real opcional debe limitarse al objetivo y ritmo del portal.

No detener procesos por sistema para cambiar docs. Para cambios que necesitan
reiniciar servidor, seguir [operations.md](docs/operations.md), identificar la
instancia y comprobar `/api/version` después. Windows usa binding exclusivo.

## Cierre y handoff

Actualizar TODO y status con requisito, archivos, comandos/resultados y límites.
Indicar pruebas reales frente a simuladas y decisiones pendientes. Si se deja una
tarea abierta, escribir el próximo paso específico. No depender del historial del
chat ni atribuir una verificación que no se ejecutó. Incidencias previas y motivos
de las regresiones: [docs/incidents.md](docs/incidents.md).
