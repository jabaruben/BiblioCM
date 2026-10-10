# Seguridad

Gracias por querer informar de un problema de seguridad de BiblioCM.

## Cómo informar (privado, nunca público)

- Usa el canal **privado de avisos de seguridad** del hosting donde esté
  publicado el repositorio (por ejemplo, *Security advisories* en GitHub).
  **No abras un issue público** con detalles: los fallos de autorización, de
  sesiones o de credenciales se explotan fácilmente cuando se publican.
- Incluye: versión/commit, pasos mínimos de reproducción, impacto que observes
  y, si aplica, el endpoint afectado. No adjuntes contraseñas reales, carnés,
  tokens OPAC ni ficheros de `.biblio-data/`.
- Si el hosting aún no ofrece ese canal y no puedes contactar de forma privada,
  publica **solo** el título y pide un canal: no pegues la descripción.

Este proyecto no ofrece recompensa por fallos.

## Alcance

BiblioCM es una aplicación **local**: el servidor escucha por defecto en
`127.0.0.1` y las credenciales no salen del equipo. Se consideran dentro del
alcance:

- Autorización y permisos (`read`/`manage`, revocación, no transitividad).
- Sesiones web, CSRF, validación de `Origin` y rotación de tokens.
- Cifrado de credenciales OPAC y manejo de la clave del servidor.
- Fugas de datos privados (carnés, contraseñas, tokens OPAC, HTML de formularios
  privados) por API, DOM, caché del service worker o logs.
- Validación de URLs de portada y del descubrimiento bajo demanda de fichas.

## Fuera de alcance

- El portal OPAC externo (`gestiona3.madrid.org`): es un proveedor que no
  controlamos. Informa allí si encuentras un fallo suyo.
- La seguridad del equipo de la persona usuaria, su navegador o su red local.
- Denegación de servicio contra la instancia local (solo escucha en 127.0.0.1).
- Instalación de la PWA en dispositivos físicos todavía no verificada
  ([TODO-PLAT-001](TODO.md)).

## Postura de seguridad actual

- Contraseñas BiblioCM con `scrypt` + sal individual; credenciales OPAC con
  Fernet y clave del servidor independiente.
- Cookies `HttpOnly`/`SameSite=Strict`; CSRF y `Origin` en mutaciones.
- `read` nunca muta; la autorización se consulta antes de descifrar u operar.
- Rate limit sobre registro/login.
- La app **no** envía telemetría ni usa servicios de terceros.

Limitaciones conocidas y sin auditar externamente: [docs/status.md](docs/status.md).
