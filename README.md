# BiblioCM

Una **webapp instalable (PWA)** para consultar y gestionar préstamos, reservas y
catálogo de las Bibliotecas de la Comunidad de Madrid desde web, Android e iPhone.
Cliente independiente: utiliza un motor Python que navega el portal OPAC existente.

## Empezar

Python **3.11 o superior**, desde la raíz del proyecto:

```powershell
python -m pip install -e .
python -m biblio.web
```

Abre **http://127.0.0.1:8000**, pulsa **Crear mi cuenta** y elige **tu nombre, un
nombre de usuario público y una contraseña** de BiblioCM: el alta **no pide
email**. Después, en Configuración:

- Verifica un email si quieres recuperar la contraseña por correo o vincular
  Google; ambos flujos lo exigen y entrar con el username no lo necesita. El
  login acepta el username o el email **verificado**: un email sin verificar no
  abre sesión.
- Vincula tu carné y otros cuyas claves conoces.
- Solicita acceso por username BiblioCM a otra persona; podrá aprobarlo con
  permiso de **solo lectura** o **gestión completa**.
- Consulta todo en el panel conjunto, identificando cada préstamo/reserva por cuenta.

El acceso BiblioCM es independiente del carné. Las credenciales OPAC se guardan
cifradas en el servidor; passwords de BiblioCM se guardan como hashes con sal.
Datos y clave default en `.biblio-data/`, ignorados por Git.

Comprobar el servidor actual:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/version"
```

Debe devolver `api_version: "6"`. El arranque y los archivos estáticos no sustituyen
esa comprobación; en Windows el puerto se ocupa de forma exclusiva.

## Qué ofrece la base actual

- Usuarios propios, múltiples carnés y solicitudes de autorización revocables.
- Email verificado como alias de acceso, con cambio y recuperación de
  contraseña por correo (SMTP configurable por entorno).
- Passkeys (WebAuthn) con reautenticación para gestionarlas; sobre Chromium
  funcionan en `http://localhost:8000` o con HTTPS.
- Acceso/vinculación opcional con Google (OIDC) cuando la persona configura
  credenciales; nunca crea ni fusiona cuentas por email.
- Préstamos ordenados por urgencia, fechas/días y renovación verificada.
- Reservas: listar, elegir ejemplar, crear y anular con comprobación posterior.
- Catálogo con páginas, soporte/edición, disponibilidad por ficha y portadas
  servidas por esta app (con inicial de respaldo si falta o falla).
- Todos los ejemplares y opciones reservables separados, con datos estructurados.
- Interfaz responsive y shell PWA público offline.
- CLI de carnés independiente y motor reutilizable.

La base incluye pruebas de motor/API y escenarios de navegador. La validación de
instalación en Android/iPhone físicos sigue pendiente. No hay APK/IPA, push ni
despliegue público configurado; passkeys y Google existen desde 2026-10-10 y
usan dos dependencias mantenidas (`webauthn`, `joserfc`) que instala
`pip install -e .`. La recuperación y el cambio de contraseña existen desde
2026-10-10 (con email verificado y SMTP configurable por entorno); el esquema
está versionado con migraciones v0→v1→v2, mientras que rotación de clave y
respaldo/restauración automatizados siguen pendientes en
[TODO-DATA-001](TODO.md).
Estado detallado y defectos abiertos: **[docs/status.md](docs/status.md)**.

## Documentación para continuar — SDD y TDD

**Empieza por [docs/README.md](docs/README.md).**

| Necesidad | Documento |
|---|---|
| Qué debe hacer el producto | [Especificación con requisitos y aceptación](docs/specification.md) |
| Qué está hecho y con qué evidencia | [Estado y trazabilidad](docs/status.md) |
| Añadir tareas y cambiar estados | **[TODO.md](TODO.md)** |
| Continuar como modelo/agente | [AGENTS.md](AGENTS.md) |
| Entender componentes | [Arquitectura](docs/architecture.md), [backend](docs/backend.md), [frontend](docs/frontend.md) |
| Integrar el API | [Contrato HTTP v6](docs/api.md) |
| Implementar y verificar | [Proceso SDD/TDD y suites](docs/testing.md) |
| Arrancar, datos, HTTPS, CLI y diagnóstico | [Operación](docs/operations.md) |
| Entender decisiones/regresiones | [ADRs](docs/decisions.md), [incidencias](docs/incidents.md) |
| Entender el proveedor externo | [Protocolo OPAC observado](docs/absys-opac-protocol.md) |

SDD: especificación y aceptación antes de código. TDD: prueba que reproduce el
comportamiento, implementación mínima y refactor con verde. No se presenta un
test simulado como comprobación en dispositivos o como una mutación real del portal.

## Comprobaciones

```powershell
python scripts/check_docs.py --tests
python -m unittest discover -s tests -t .
node --check biblio/static/app.js
node --check biblio/static/sw.js
python scripts/release_scan.py
```

Node es opcional para sintaxis; la app no necesita Node ni build. El último
comando escanea lo que Git publicaría y solo informa de regla, ruta y línea,
nunca del contenido. Prueba opcional de navegador, con Playwright y Edge
instalado:

```powershell
python -m pip install playwright
python scripts/check_web_browser.py --channel msedge
```

Pruebas normales usan fakes, fixtures y HTTP local, sin OPAC real. Consultas reales
y límites de evidencia se explican en [testing.md](docs/testing.md).

## Móvil y CLI

Para instalar la PWA en un teléfono usa una URL **HTTPS** accesible desde él:
Android/Chrome → Instalar aplicación; iPhone/Safari → Compartir → Añadir a pantalla
de inicio. `--secure` configura cookies para un proxy HTTPS, no implementa TLS.
Guía de red local y claves: [operations.md](docs/operations.md).

La CLI sigue disponible con `python -m biblio --help`. Su registro es separado de
SQLite y obtiene passwords de entorno/getpass. Ejemplos completos, incluido el
hecho de que `renovar` sin barcode solo informa, en la guía de operación.

## Licencia y colaboración

Publicado bajo licencia **MIT**: el texto completo está en [LICENSE](LICENSE)
(titular «jabaruben/BiblioCM»). Puedes usar, copiar, modificar y redistribuir
el proyecto conservando ese aviso.

Las contribuciones se hacen por fork y propuesta de cambios sobre el repositorio
publicado. Antes de enviar código ejecuta las comprobaciones de
[Comprobaciones](#comprobaciones) y revisa el proceso en
[testing.md](docs/testing.md). No envíes credenciales reales, carnés, tokens ni
ficheros de `.biblio-data/`: el proyecto los ignora y `release_scan.py` los
señala antes de publicar.

**Seguridad:** para comunicar una vulnerabilidad sigue
[SECURITY.md](SECURITY.md). Usa el canal privado del hosting (advisories), nunca
un issue público con datos sensibles.
