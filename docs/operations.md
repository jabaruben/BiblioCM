# Instalación, uso y operación

Comandos de referencia para **PowerShell 5.1** desde la raíz del repositorio.
Python ≥3.11. Backend web requiere cryptography; Node/Playwright son opcionales
de desarrollo. Estado y límites de comprobación: [status.md](status.md).

## Arranque de la web

```powershell
python -m pip install -e .
python -m biblio.web
```

También está disponible `biblio-web`. Abrir `http://127.0.0.1:8000` y crear usuario
BiblioCM. Después vincular carné/clave OPAC en Configuración o solicitar acceso
por username. Los ejemplos de este documento son ficticios.

```powershell
python -m biblio.web --help
python -m biblio.web --host 127.0.0.1 --port 8080 --data-dir ".biblio-data"
```

Parámetros: host default 127.0.0.1, port 8000, data-dir `.biblio-data`, secure falso.
La carpeta de datos relativa depende del directorio de arranque; usar una ruta
absoluta cuando se configure un servicio para evitar abrir otra base de datos.
No hay reloader automático: cambiar Python exige reiniciar el proceso.

Comprobar la instancia activa sin autenticarse:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/version"
```

Debe devolver `api_version: "6"`. No basta con que la página HTML abra: puede
estar recibiendo assets nuevos desde un proceso con código anterior importado.

## Reiniciar y diagnosticar duplicados en Windows

Preferir Ctrl+C en la terminal del servidor identificado y volver a arrancarlo.
El cierre elimina sesiones web en RAM; usuarios/carnés/links persistidos siguen
en SQLite. No inicia ni repite operaciones de renovación/reserva.

Para investigar un puerto:

```powershell
Get-NetTCPConnection -State Listen -LocalPort 8000
Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
    Where-Object { $_.CommandLine -match '-m\s+biblio\.web(?:\s|$)' } |
    Format-List ProcessId,CreationDate,CommandLine
```

Revisar qué procesos pertenecen a este proyecto antes de cerrarlos. Un PID
devuelto por Start-Process o una fila de listener por sí solos no identificaban
todos los servidores antiguos que compartían el puerto. El servidor actual usa
binding exclusivo en Windows; una segunda instancia debe fallar al arrancar.
Después del reinicio comprobar versión HTTP, no solo estado del proceso.

## Acceso desde móvil y HTTPS

En red local de desarrollo:

```powershell
python -m biblio.web --host 0.0.0.0 --port 8000
```

Abrir en el teléfono `http://IP-DEL-ORDENADOR:8000`, en la misma red y con acceso
al puerto. `localhost` en el teléfono apunta al propio teléfono. La web sirve
por HTTP; instalar PWA/service worker requiere HTTPS salvo localhost.

Proxy HTTPS: la aplicación no implementa TLS. Arrancar detrás del proxy con
`--secure`, conservar Host externo y esquema HTTPS hacia el cliente. Ese flag
activa cookie Secure y validación de Origin HTTPS, no certificados. El limitador
ve la IP del peer (normalmente el proxy); no interpreta X-Forwarded-For.
No hay una configuración de proxy/despliegue elegida y probada en el repo.
`--secure` **no** convierte cualquier Host en un origen válido: passkeys y el
acceso con Google exigen además un origen de confianza (siguiente sección).

### Orígenes de confianza: passkeys y Google ([NFR-SVC-003](specification.md#nfr-svc-003))

El `Host` de un pedido no es por sí solo una autoridad de confianza, ni siquiera
sobre TLS. Passkeys (RP ID/origen WebAuthn) y el callback de Google derivan su
origen de una lista de confianza con **default solo local**:
`http(s)://localhost` y `http(s)://127.0.0.1` con cualquier puerto válido (el
HTTPS local cubre el escenario mkcert de abajo). Cualquier otro Host —incluso
con `--secure`— recibe **403** en esas rutas antes de mirar el cuerpo; un Host
no canónico (userinfo, ruta, puerto no numérico o fuera de rango, caracteres de
control) recibe 400.

Para un despliegue con nombre público detrás de un proxy TLS, declarar el origen
externo:

| Variable | Default | Significado |
|---|---|---|
| `BIBLIO_TRUSTED_ORIGINS` | — (vacío = solo locales) | Orígenes canónicos extra, separados por coma, p. ej. `https://biblio.ejemplo.org` |

```powershell
$env:BIBLIO_TRUSTED_ORIGINS = "https://biblio.ejemplo.org"
python -m biblio.web --secure
```

Cada entrada debe ser un origen canónico `https://host[:puerto]` (sin ruta,
query, fragmento ni userinfo); los no locales **solo** admiten HTTPS (passkey
sobre HTTP de red prohibida por NFR-SVC-003). La coincidencia es exacta por
origen: `https://sub.biblio.ejemplo.org` no entra listando
`https://biblio.ejemplo.org`. Un valor inválido detiene el arranque con un
error, no se ignora en silencio. Con `--secure` y sin variable, el servidor
anuncia al arrancar que solo acepta orígenes locales. El resto de la aplicación
(carnés, panel, catálogo) sigue funcionando desde cualquier Host: la lista solo
afecta a passkeys y al callback de Google. Este comportamiento está verificado
con pruebas de Host hostil, TLS sin listar y HTTPS configurado
([test_passkeys.py](../tests/test_passkeys.py), [test_oidc.py](../tests/test_oidc.py));
no sustituye a una configuración de proxy real.

### Contexto local, aviso y passkeys ([NFR-SVC-003](specification.md#nfr-svc-003))

La UI comprueba `window.isSecureContext` y, cuando el origen **no** es de
confianza (HTTP desde una dirección que el navegador no considera local), muestra
un aviso persistente `#origin-warning` y desactiva las passkeys. En ese contexto
el servidor también rechaza las operaciones WebAuthn (403 antes de mirar el
cuerpo), igual que rechaza cualquier Host fuera de la lista de orígenes de
confianza descrita más abajo. `http://127.0.0.1` y `http://localhost` sí son
contextos locales aceptados en desarrollo, así que el aviso no aparece ahí.

**Detalle de Chromium**: aunque `127.0.0.1` es un origen de confianza, Chromium
exige que el RP ID de una passkey tenga forma de dominio y **rechaza las
direcciones IP**. La restricción es sobre el **RP ID** (WebAuthn exige un nombre
de dominio válido como identificador de origen), no sobre la cadena de
confianza: una dirección IP literal **sí puede llevar un certificado válido**
—mkcert, por ejemplo, puede emitirlo con la IP en sus IP-SAN y el navegador lo
aceptará—, pero ese certificado **no** convierte la IP en un RP ID aceptable.
Un TLS correcto sobre una IP sigue sin dar passkeys. Para usar
passkeys en este equipo, abre la app como
`http://localhost:8000` (misma instancia: el servidor sigue escuchando en
`127.0.0.1`); desde otra IP o con un dominio, hace falta HTTPS **y** un nombre
de dominio. La UI lo explica
y oculta los controles de passkey cuando el host es una IP literal; el resto de
la aplicación sigue funcionando igual, y el acceso con Google depende además de
lo que el proveedor acepte como redirect (ver «Acceso con Google»). Ese
comportamiento del navegador está verificado con el autenticador virtual de
Chromium en el escenario de navegador; no se ha verificado en Safari/Firefox ni
en dispositivos físicos ([TODO-PLAT-001](../TODO.md)).

El aviso describe el alcance del riesgo; no es una promesa de seguridad
perimetral.

### HTTPS local con mkcert (recomendado para móvil)

Para servir por HTTPS en el equipo **sin publicar nada ni abrir puertos** se
puede generar un certificado local con [mkcert](https://github.com/FiloSottile/mkcert),
una herramienta de terceros que instala una autoridad de certificación local en
el equipo. mkcert **no** viene con el proyecto y el proyecto **no** la instala
ni ejecuta: es una decisión de la persona operadora. `caddy` (el proxy del
ejemplo) tampoco.

Prerrequisitos, en este orden:

1. **Un nombre DNS estable de red local**, no una dirección IP: p. ej.
   `biblio.lan` si el router/ADNS de casa lo resuelve, o `biblio.local` si los
   dispositivos resuelven mDNS/Bonjour (Android e iOS suelen hacerlo en la misma
   red). Una dirección IP **puede** llevar un certificado válido, pero no por eso
   sirve como RP ID de passkey (WebAuthn/Chromium exigen forma de dominio, ver la
   sección anterior) y además es un nombre frágil, ligado a la red de cada casa.
2. **Que el teléfono resuelva ese nombre** a la IP local del ordenador (mismo
   Wi-Fi, sin aislamiento de clientes). Comprobarlo desde el teléfono antes de
   nada: si el nombre no resuelve, el proxy no recibe la petición.
3. **mkcert instalado y en el PATH** (instalación manual, fuera de este repo).
4. **El proxy TLS** (en el ejemplo, Caddy) instalado en el mismo ordenador.

```powershell
# 1. Certificado local para el nombre de red + localhost + bucle.
New-Item -ItemType Directory -Force "$env:USERPROFILE\.biblio-certs" | Out-Null
mkcert -install
mkcert -cert-file "$env:USERPROFILE\.biblio-certs\cert.pem" -key-file "$env:USERPROFILE\.biblio-certs\key.pem" biblio.lan localhost 127.0.0.1

# 2. Caddyfile (fichero de texto, MULTILÍNEA; la ruta usa la variable {$USERPROFILE}
#    que Caddy expansiona, no la sintaxis de PowerShell). Guardarlo, por ejemplo,
#    en "$env:USERPROFILE\.biblio-certs\Caddyfile":
#
#     biblio.lan:8443 {
#         tls "{$USERPROFILE}/.biblio-certs/cert.pem" "{$USERPROFILE}/.biblio-certs/key.pem"
#         reverse_proxy 127.0.0.1:8000
#     }
#
#    Cualquier reverse proxy que convierta ese certificado en TLS vale; la app
#    no implementa TLS. El sitio escucha en el puerto 8443 de todas las
#    interfaces (el `Host` debe ser `biblio.lan:8443`), pero la app de detrás
#    sigue enlazada solo a 127.0.0.1:8000.
caddy validate --config "$env:USERPROFILE\.biblio-certs\Caddyfile"

# 3. Terminal 1: la app en localhost, sin --host 0.0.0.0, con el origen de
#    confianza que coincide con el nombre del certificado: eso es lo que hace
#    que las passkeys funcionen desde el teléfono. El callback de Google es una
#    decisión aparte (ver «Acceso con Google» más abajo): que este servidor
#    acepte ese origen no significa que el proveedor acepte el redirect.
$env:BIBLIO_TRUSTED_ORIGINS = "https://biblio.lan:8443"
python -m biblio.web --port 8000 --secure --data-dir "$env:USERPROFILE\.biblio-cm-https"

# 4. Terminal 2: el proxy.
caddy run --config "$env:USERPROFILE\.biblio-certs\Caddyfile"
```

`caddy validate` y `caddy run` solo se ejecutan si `caddy` está instalado en la
máquina donde se siga esta guía; **este repositorio no valida ese Caddyfile
aquí** porque `caddy` no es una dependencia del proyecto. La muestra de arriba
es la configuración canónica esperada: multiservicio con llaves `{ ... }`,
`tls` con las dos rutas y `reverse_proxy` en líneas propias.

`mkcert -install` añade una CA local al almacén de confianza del equipo: ese
paso es reversible (se puede quitar con `mkcert -uninstall`) y solo afecta al
equipo donde se ejecute. Los ficheros `cert.pem`, `key.pem` y `rootCA.pem` son
**privados**: el `.gitignore` del repositorio ya ignora `.biblio-certs/`,
`*.pem`, `*.key`, `*.pfx` y `*.p12`, así que no se versionan aunque se guarden
dentro del repo; no subirlos a ningún sitio.

Comprobar la instancia y que la cookie ya es `Secure`:

```powershell
Invoke-RestMethod -Uri "https://biblio.lan:8443/api/version"
```

Para que el teléfono confíe en el certificado hay que instalar en él la **CA
local de mkcert**: `mkcert -CAROOT` imprime la carpeta con `rootCA.pem`, y ese
fichero se instala en el teléfono (Android: Ajustes → Seguridad → Instalar
certificado; iOS: enviar `rootCA.pem` al dispositivo → instalar perfil → activar
la confianza completa en Ajustes → General → Info → Certificados). Mientras esa
CA no esté en el teléfono, el navegador mostrará el aviso de certificado no
conocido (y WebAuthn/passkeys no funcionarán en ese contexto). En el ordenador
ya la instaló `mkcert -install`.

`https://biblio.lan:8443` **no** es un origen local: hay que declararlo en
`BIBLIO_TRUSTED_ORIGINS` (como arriba) para que **este servidor** acepte ese
origen en las passkeys y en el callback de Google; eso decide lo que acepta la
app, no lo que acepta Google como redirect (ver «Acceso con Google» más abajo).
`https://localhost:8443` y `https://127.0.0.1:8443` sí entrarían en el default
local, pero el teléfono no usa esas direcciones. Sin nombre DNS estable no hay
passkeys desde el móvil: una IP literal **sí puede** llevar un certificado
válido (mkcert puede emitirlo con la IP en sus IP-SAN y el navegador lo
aceptará), pero una dirección IP **no es un RP ID aceptable** para
WebAuthn/Chromium, así que ese certificado **no** habilita passkeys. Por eso
esta guía pone un nombre DNS estable en el certificado y en
`BIBLIO_TRUSTED_ORIGINS`, no la IP.

No hace falta ningún dominio público de pago: el nombre puede ser de la red
local (resuelto por el router o por mDNS) y el certificado, local. Abrir la
app desde Internet exigiría otra decisión (p. ej. Tailscale, más abajo) y no
forma parte de esta guía.

`--host` default es `127.0.0.1`; solo se abre a la red con `--host 0.0.0.0` y
eso no es un despliegue ni una publicación aprobada. Este flujo es para
desarrollo/uso local. La validación de dispositivos físicos sigue pendiente
([TODO-PLAT-001](../TODO.md)); el escenario de navegador cubre el aviso simulando
`isSecureContext`, no una instalación real de mkcert ni un proxy.

- Android/Chrome: menú → Instalar aplicación, o botón disponible de la UI.
- iPhone/Safari: Compartir → Añadir a pantalla de inicio.
- Instalación, offline y teclado/lector de pantalla en dispositivos reales son
  verificaciones pendientes, no pasos ya acreditados.

Todo lo de esta sección es **local**: mkcert, el proxy y Mailpit son herramientas
de terceros que la persona instala (o no) por su cuenta; el proyecto no las
empaqueta, no las ejecuta, no abre puertos en el router ni publica nada y **no
afirma su precio ni sus condiciones** (fuentes fechadas más abajo). Lo que sí está
verificado en este repositorio es el aviso de UI y el rechazo del servidor con
`isSecureContext` forzado; lo que **no** está verificado es la instalación real
de mkcert, el proxy, un dispositivo físico o cualquier proveedor externo.

### Correo de desarrollo con Mailpit (opcional, sin entrega real)

Para probar la verificación de email y la recuperación sin un proveedor real,
se puede usar [Mailpit](https://mailpit.axllent.org/) como buzón local: captura
lo que la app envía por SMTP y lo muestra en una interfaz web (`http://127.0.0.1:8025`).
**No entrega correo a ninguna persona**: nada sale de la máquina.

```powershell
# Requisitos: Mailpit instalado y en el PATH (instalación manual, fuera de este repo).
mailpit --smtp 127.0.0.1:1025
$env:BIBLIO_SMTP_HOST = "127.0.0.1"
$env:BIBLIO_SMTP_PORT = "1025"
$env:BIBLIO_SMTP_STARTTLS = "0"
python -m biblio.web
```

La propia suite usa un servidor SMTP falso local con el mismo principio (puerto
efímero, sin AUTH ni STARTTLS); ninguna prueba envía correo real.

### Acceso desde fuera de la casa con Tailscale (opcional, sin abrir puertos)

Si se quiere usar la app desde otro lugar sin tocar el router ni reenviar
puertos, [Tailscale](https://tailscale.com/) crea una red privada entre los
dispositivos de la persona: la app sigue escuchando en
`127.0.0.1`, y el acceso se hace por el nombre que Tailscale asigne, normalmente
con HTTPS gestionado por el propio Tailscale. Es una opción de la persona,
ajena al proyecto, y **no** forma parte de ninguna comprobación de este
repositorio. Tailscale tiene planes y condiciones propias y sujetas a cambio:
consultar su [página de precios oficial](https://tailscale.com/pricing) (URL
comprobada el 2026-10-10, ver fuentes más abajo); **no** se afirma aquí que
exista una cuenta gratuita ni ningún precio concreto. Sin Tailscale (o sin
proxy TLS local), abrir la app desde otro dispositivo sigue requiriendo
`--host 0.0.0.0` en la misma red, que es
desarrollo, no un despliegue aprobado.

### Acceso con Google (OIDC), opt-in

El acceso/vinculación con Google ([FR-AUTH-005](specification.md#fr-auth-005))
está **desactivado** salvo que la persona configure credenciales. Crearlas es un
trámite humano en la consola de Google Cloud (proyecto nuevo →
OAuth client de tipo «Web» → origen `http://localhost:8000` y redirect
`http://localhost:8000/api/auth/google/callback`, más el origen HTTPS que se
use en producción, que además debe declararse en `BIBLIO_TRUSTED_ORIGINS`).

**Qué redirect acepta Google: una decisión del proveedor, no de la app.** La
consola admite lo que su propia política admite: en desarrollo local,
`http://localhost:8000/api/auth/google/callback` sobre este mismo equipo; en
cualquier otro entorno, un origen **público HTTPS** que el proveedor acepte y
que se declare también en `BIBLIO_TRUSTED_ORIGINS` (con
`BIBLIO_GOOGLE_REDIRECT_URI` si hay que sobreescribirlo). Un nombre privado de
red local —`biblio.lan` del ejemplo mkcert de arriba— **no** cuenta para eso: la
guía mkcert cubre el certificado y las passkeys en la red local y **no** promete
el acceso con Google sobre ese nombre. `BIBLIO_TRUSTED_ORIGINS` y
`BIBLIO_GOOGLE_REDIRECT_URI` dicen qué origen acepta **este servidor**; no
convierten un origen privado en un redirect que Google acepte. Esta distinción es
documental: el proyecto no ha probado la consola de Google Cloud ni un dominio
público propio, así que no afirma qué acepta el proveedor más allá de lo
anterior.
El proyecto **no** promete ni necesita ninguna API de pago: el flujo usa solo
OpenID Connect estándar
([documentación oficial de OIDC de Google](https://developers.google.com/identity/openid-connect/openid-connect)),
sin invocar ninguna API de Google. Eso **no** es una promesa de coste cero:
las condiciones de la cuenta de Google Cloud (incluido cualquier nivel gratuito)
pueden cambiar y son externas a este repositorio (ver fuentes más abajo).

| Variable | Default | Significado |
|---|---|---|
| `BIBLIO_GOOGLE_CLIENT_ID` | — (vacío = desactivado) | Client ID OAuth |
| `BIBLIO_GOOGLE_CLIENT_SECRET` | — (vacío = desactivado) | Client secret; nunca versionarlo ni imprimirlo |
| `BIBLIO_GOOGLE_ISSUER` | `https://accounts.google.com` | Issuer del token (debe coincidir con el descubrimiento) |
| `BIBLIO_GOOGLE_AUTH_ENDPOINT` | descubrimiento | Override del endpoint de autorización |
| `BIBLIO_GOOGLE_TOKEN_ENDPOINT` | descubrimiento | Override del endpoint de token |
| `BIBLIO_GOOGLE_JWKS_URI` | descubrimiento | Override del JWKS |
| `BIBLIO_GOOGLE_REDIRECT_URI` | derivada del origen de confianza del pedido | Override del callback: origen canónico + `/api/auth/google/callback`, y ese origen debe ser local o estar en `BIBLIO_TRUSTED_ORIGINS`. Solo fija lo que acepta **este servidor**; la consola de Google debe aceptarlo por su parte (ver arriba) |

```powershell
$env:BIBLIO_GOOGLE_CLIENT_ID = "valor-de-la-consola.ejemplo.test"
$env:BIBLIO_GOOGLE_CLIENT_SECRET = "valor-secreto-ficticio"
python -m biblio.web
```

Sin client id/secret no hay botón, no hay callback y el servidor responde 503
en esas rutas. Las pruebas usan un proveedor OIDC **falso local** con su propia
clave RSA: ninguna prueba habla con Google.

### Fuentes externas y salvedades (consulta: 2026-10-10)

Las URLs de terceros citadas más arriba se comprobaron con una petición `HEAD`
que respondió **HTTP 200** el **2026-10-10**. Eso solo acredita que la página
respondía ese día; **no** verifica su contenido, precios ni condiciones, que
pueden cambiar sin aviso.

| Mención | Fuente oficial | Alcance de la verificación |
|---|---|---|
| OpenID Connect (acceso con Google) | [developers.google.com/identity/openid-connect/openid-connect](https://developers.google.com/identity/openid-connect/openid-connect) | URL oficial accesible (200, 2026-10-10). El flujo usa OIDC estándar sin API de Google; **no** es una afirmación de coste |
| Nivel gratuito de Google Cloud | [cloud.google.com/free/docs/free-cloud-features](https://cloud.google.com/free/docs/free-cloud-features) | URL oficial accesible (200, 2026-10-10). Describe funciones gratuitas de la cuenta con condiciones que pueden cambiar; **no** se promete ningún precio ni coste cero |
| mkcert | [github.com/FiloSottile/mkcert](https://github.com/FiloSottile/mkcert) | Repositorio oficial accesible (200, 2026-10-10). Herramienta local de terceros, instalada y ejecutada por la persona, fuera de la app |
| Mailpit | [mailpit.axllent.org](https://mailpit.axllent.org/) | Sitio oficial accesible (200, 2026-10-10). Buzón local de desarrollo sin entrega real, fuera de la app |
| Tailscale | [tailscale.com/pricing](https://tailscale.com/pricing) | Página de precios oficial accesible (200, 2026-10-10). **No** se afirma plan gratuito ni condiciones concretas: consultar la propia página |

Salvedades:

- **Herramientas locales ≠ app**: mkcert, el proxy TLS de ejemplo y Mailpit son
  externas a la aplicación; este repositorio no las empaqueta ni las ejecuta y no
  garantiza su coste, licencia ni disponibilidad. Tailscale es un servicio
  externo opcional con condiciones propias.
- **Proveedores de correo sin verificar**: no hay ningún proveedor SMTP de pago
  configurado ni probado (solo SMTP por entorno y un servidor falso en la suite).
  Condiciones de precio y configuración de servicios como **Brevo** o **Resend**
  quedan **sin verificar** y el proyecto **no** se apoya en ellas.

## Datos y clave

Default:

```text
.biblio-data/
  biblio.sqlite3    usuarios, carnés cifrados y relaciones
  secret.key       clave Fernet si no se proporciona por entorno
```

La clave puede suministrarse mediante `BIBLIO_SECRET_KEY` (Fernet válida). Se lee
al abrir Store. Generar/configurar una clave antes de una base nueva es distinto
de rotarla en una base existente: rotación no está implementada. No generar otra
clave como arreglo a un fallo de descifrado.

## Correo de verificación y recuperación (FR-AUTH-002 / FR-AUTH-003)

La app envía el código de verificación de email y el de recuperación de
contraseña por SMTP. **Sin configuración no hay envío**: los endpoints de correo
responden `503` (error global, no dependiente del email). La configuración es
solo por entorno, nunca por fichero del repositorio:

| Variable | Default | Significado |
|---|---|---|
| `BIBLIO_SMTP_HOST` | — (vacío = correo desactivado) | Servidor SMTP |
| `BIBLIO_SMTP_PORT` | `587` | Puerto |
| `BIBLIO_SMTP_USER` | vacío | Usuario (si el servidor exige AUTH) |
| `BIBLIO_SMTP_PASSWORD` | vacío | Contraseña; nunca versionarla ni imprimirla |
| `BIBLIO_SMTP_STARTTLS` | `1` | STARTTLS en claro (`0` para desactivar) |
| `BIBLIO_SMTP_SSL` | `0` | SMTPS desde el inicio (`1` = TLS implícito) |
| `BIBLIO_SMTP_FROM` | `BiblioCM <no-responder@localhost>` | Remitente |
| `BIBLIO_SMTP_TIMEOUT` | `10` | Segundos de espera |

```powershell
$env:BIBLIO_SMTP_HOST = "smtp.ejemplo.test"
$env:BIBLIO_SMTP_USER = "usuario"
$env:BIBLIO_SMTP_PASSWORD = "clave-del-proveedor"
python -m biblio.web
```

Los códigos caducan (24 h verificación, 1 h recuperación), son de un solo uso y
en SQLite solo se guarda su SHA-256. Un fallo del proveedor **no se comunica a
la persona solicitante**: durante la incidencia la respuesta es la misma que con
un envío satisfactorio (200 genérico), porque un 502 distinto revelaría si el
email está registrado (revisión independiente, [ADR-017](decisions.md#adr-017--identidad-con-email-verificado-smtp-por-entorno-tokens-hasheados-y-api-v5)).
Si nadie recibe correos, revisa la configuración `BIBLIO_SMTP_*` y los logs del
proveedor desde el servidor; el código no emitido se retira solo. Ninguna prueba
de la suite envía correo real. No imprimir la variable de contraseña ni el
cuerpo de los correos al diagnosticar.

El directorio default está ignorado en Git. Para otro data-dir mantener la misma
protección contra versionado y gestionar permisos/ACL. No imprimir la variable,
clave, cookies o passwords para diagnosticar; scripts existentes no muestran claves.

### Respaldo y restauración manual

No hay herramienta automatizada de backup/restore; tarea TODO-DATA-001.
Procedimiento actual:
1. Detener la instancia correcta para obtener una copia consistente.
2. Copiar SQLite y conservar **la clave correspondiente**; con clave de entorno,
   respaldar su valor mediante el sistema de secretos utilizado, no en un README.
3. Guardar la clave con protección separada de una copia de la BD. Copiar solo
   SQLite no permite recuperar los accesos OPAC si se pierde la clave.
4. Para comprobar restauración, usar otra carpeta de datos con el par correcto,
   arrancar en otro puerto y verificar identidad/vinculaciones. No ejecutar
   mutaciones del portal como prueba de restauración.

SQLite valida credenciales cifradas al arrancar y falla con clave incompatible.
Esto es evidencia de correspondencia de clave, no una prueba completa de todo
un backup operativo. El esquema está versionado (`PRAGMA user_version`, hoy 2)
y la apertura migra automáticamente v0→v1→v2 con rollback atómico
([backend](backend.md)); un fallo de migración detiene el arranque sin tocar
los datos. Las passkeys y las identidades vinculadas (Google) viven en esa
misma base: al respaldarla también se respaldan, y la clave Fernet es necesaria
para leer los detalles de las transacciones OIDC. Transiciones más allá de
identidad y una herramienta de respaldo/restauración siguen pendientes en
[TODO-DATA-001](../TODO.md).

## CLI separada de la web

Entrada: `python -m biblio`; registro en `~/.config/biblio/accounts.json`, salvo
`--registro`. Ese registro no es SQLite ni el acceso propio de BiblioCM.

```powershell
python -m biblio cuentas add --id principal --carne "000000001" --label "Principal"
python -m biblio cuentas add --id familiar --carne "000000002" --label "Familiar"
python -m biblio cuentas list
```

Sustituir carnés ficticios antes del uso real. Passwords en memoria/entorno o
getpass, sin guardarlos en el registro:

```powershell
$env:BIBLIO_PWD_PRINCIPAL = 'tu-clave-del-portal'
python -m biblio --cuenta principal prestamos
```

Se puede omitir la variable y responder a la entrada oculta. `--no-prompt` falla
si no dispone de clave. `--password-stdin` no existe, aunque un mensaje antiguo
lo sugiera; su corrección figura en TODO-CLI-001.

Consultas:

```powershell
python -m biblio prestamos
python -m biblio --cuenta principal prestamos --today 2026-10-05
python -m biblio --cuenta principal buscar "pokemon" --pagina 2 --availability
python -m biblio --cuenta principal renovar
python -m biblio --cuenta principal reservas list
python -m biblio --cuenta principal reservas show --record-id 1234567
python -m biblio --delay 2 --no-prompt prestamos
```

`--today` simula fecha en la lógica local; no cambia la política ni fecha del
portal. `renovar` sin barcode solo informa. Búsqueda/renovar/reservas toman la
primera cuenta seleccionada; `prestamos` recorre la selección.

Mutaciones explícitas, **no comandos de comprobación rutinaria**:

```powershell
python -m biblio --cuenta principal renovar --codigo-barras 9000000001
python -m biblio --cuenta principal reservas create --record-id 1234567 --copy-index 3
python -m biblio --cuenta principal reservas cancel --reservation-id 9000001
```

Identificadores de ejemplo ficticios. Para uso real elegir los del préstamo o
asistente actual. No usar un índice viejo si cambió la lista. La web protege
selección mediante barcode; la CLI tradicional crea por índice.

## Diagnósticos y herramientas

| Script | Efecto |
|---|---|
| [check_docs.py](../scripts/check_docs.py) | Validar docs/backlog/links; no consulta portal |
| [check_web_browser.py](../scripts/check_web_browser.py) | App/BD/clientes temporales y operaciones simuladas |
| [check_live_reservable.py](../scripts/check_live_reservable.py) | App temporal, consulta real y screenshot opcional, sin reservar |
| [inspect_catalog.py](../scripts/inspect_catalog.py) | Consultas de catálogo/asistente con un carné vinculado |
| [inspect_loans.py](../scripts/inspect_loans.py) | Dos lecturas de préstamos seleccionados, nunca renueva |
| [generate_icons.py](../scripts/generate_icons.py) | Regenera PNG públicos, sin red |

Parámetros y límites de pruebas en [testing.md](testing.md). Usar etiquetas reales
de esta instancia: «Mi biblioteca»/«Principal» son ejemplos, no nombres obligatorios.

## Diagnóstico rápido de síntomas conocidos

| Síntoma | Comprobación |
|---|---|
| Registro pide carné sin campo | Versión API y proceso importado; el registro BiblioCM no pide carné |
| Reservables contienen HTML | Versión, ausencia de row público y servidores duplicados |
| Fechas distintas tras renovar | Lectura nueva del portal, date/counter y una sola mutación; no renovar otra vez para investigar |
| Cuenta no consulta pero las demás sí | Error de ese carné en `accounts[].error`, actualizar claves con su dueño |
| Usuario pierde login tras reinicio | Sesión RAM eliminada; login de nuevo, no recrear usuarios |
| Clave incompatible | Restaurar clave correcta; no sustituir BD/clave para «resetear» |
| PWA no instala en móvil por HTTP local | Proporcionar HTTPS; web HTTP e instalación son capacidades distintas |

Logs de acceso HTTP están desactivados y errores no traducidos devuelven texto
genérico 502; no hay log persistente/traza/correlación gestionado. La investigación
requiere una reproducción controlada, no suponer que existe telemetría anterior.
