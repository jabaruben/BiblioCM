# Documentación de BiblioCM

Última revisión de la base documentada: **2026-10-08**.

Esta documentación permite continuar el proyecto sin depender de una conversación
anterior. SDD significa aquí **Specification-Driven Development**: requisitos y
criterios de aceptación antes de implementar. TDD significa **Test-Driven
Development**: reproducir el comportamiento con una prueba que falla, implementar
lo mínimo y refactorizar con las pruebas en verde.

## Orden de lectura para continuar

1. [Instrucciones para agentes](../AGENTS.md): reglas de trabajo y cierre.
2. [Estado y evidencia](status.md): qué existe, qué se ha comprobado y qué falta.
3. [Backlog editable](../TODO.md): elegir una tarea y cambiar su estado.
4. [Especificación de producto](specification.md): requisitos con IDs estables.
5. [Arquitectura](architecture.md) y el documento de la capa afectada.
6. [Guía TDD](testing.md): prueba inicial, comprobaciones y evidencia.

No es necesario leer todos los ficheros para cambiar una sola función: después del
estado y la tarea, seguir los enlaces de su requisito y de la capa implicada.

## Índice y responsabilidad de cada fichero

| Documento | Contenido que mantiene |
|---|---|
| [README principal](../README.md) | Presentación y arranque rápido |
| [specification.md](specification.md) | Comportamiento aceptado y criterios de aceptación |
| [architecture.md](architecture.md) | Componentes, dependencias y flujos entre capas |
| [backend.md](backend.md) | Motor OPAC, persistencia, autorización y CLI |
| [api.md](api.md) | Contrato HTTP público, DTOs y errores de API v4 |
| [frontend.md](frontend.md) | Pantallas, estado JavaScript, permisos y PWA |
| [testing.md](testing.md) | Proceso SDD/TDD, suites y comandos de verificación |
| [status.md](status.md) | Matriz requisito → implementación → pruebas → pendientes |
| [decisions.md](decisions.md) | Decisiones aceptadas y sus consecuencias |
| [incidents.md](incidents.md) | Incidencias anteriores y regresiones que las protegen |
| [operations.md](operations.md) | Instalación, ejecución, datos, respaldo y diagnóstico |
| [absys-opac-protocol.md](absys-opac-protocol.md) | Observaciones del protocolo externo del portal |
| [TODO.md](../TODO.md) | Única lista editable de tareas y estados |

## Fuentes de verdad y mantenimiento

- Las instrucciones actuales del usuario pueden cambiar el producto. Documentar
  esa intención en la especificación; un test antiguo no invalida un cambio aceptado.
- La especificación describe el contrato deseado. El código describe la ejecución
  actual; las discrepancias se registran en el estado y en el backlog.
- El contrato externo OPAC es observado, no controlado por nosotros. Sus notas
  históricas no son una garantía de que el portal mantenga ese HTML o esa política.
- Un requisito implementado puede tener verificación parcial. No sustituir evidencia
  de navegador por una supuesta prueba en iPhone ni mocks por operaciones reales.
- El estado de una tarea se edita en `TODO.md`, no en listas paralelas. Al cerrar una
  funcionalidad, actualizar también su fila en `status.md` y los contratos afectados.
- Las fechas y recuentos de préstamos observados en una incidencia son históricos,
  no valores a codificar ni el estado actual de una cuenta.
- Los ejemplos nuevos deben ser ficticios. No añadir contraseñas, claves Fernet,
  cookies, tokens OPAC ni bases de datos reales a la documentación.
- `docs/HANDOFF-SOL.md` es material legado **solo local y no publicado**: no es
  una fuente de verdad, contiene datos personales identificativos y un contrato
  obsoleto que contradice [api](api.md) y [status](status.md). Está excluido del
  set publicable por una entrada exacta en `.gitignore`, se conserva intacto en
  el trabajo local y no debe enlazarse ni copiarse a la documentación pública.

## Cómo añadir una funcionalidad

Crear una tarea con estado y aceptación en `TODO.md`; acordar o extender un requisito
en `specification.md`; escribir la prueba de aceptación o regresión; implementar;
registrar comandos y resultados; actualizar estado y decisiones si corresponde.
El procedimiento detallado y la definición de terminado están en [testing.md](testing.md).

Validación local de esta documentación:

```powershell
python scripts/check_docs.py
```
