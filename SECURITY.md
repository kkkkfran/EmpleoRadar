# Política de Seguridad — EmpleoRadar

## 1. Principios de Seguridad y Privacidad

EmpleoRadar es un bot personal concebido para proteger la privacidad del usuario, sus credenciales y sus documentos laborales.

### A. Gestión de Secretos y Credenciales
- Los tokens de Discord y cadenas de conexión nunca deben comitearse al repositorio de código fuente.
- Se utiliza un archivo `.env` local, excluido explícitamente en `.gitignore`.
- Los logs del sistema implementan un filtro de redacción (`RedactingFilter`) que censura automáticamente tokens, contraseñas, correos electrónicos y teléfonos.

### B. Privacidad del Currículum Vitae (CV)
- Los currículums en PDF se almacenan en un directorio privado con acceso restringido (`data/private/resumes`).
- Se validan extensiones (`.pdf`), cabeceras mágicas (`%PDF`), tamaño máximo (10 MB) y sanitización estricta contra ataques de Directory / Path Traversal (`sanitize_filename`).
- El contenido íntegro del CV nunca se expone en logs, mensajes públicos ni canales abiertos de Discord.
- Las notificaciones y postulaciones se gestionan exclusivamente mediante Mensajes Directos (DM) o canales privados autorizados.

### C. Control de Acceso y Autorización
- Todos los comandos slash bajo el grupo `/empleo` y las botoneras interactivas verifican que el solicitante sea exactamente el `DISCORD_OWNER_ID` configurado.
- Intentos de acceso por usuarios no autorizados son rechazados de forma inmediata con mensajes efímeros y auditados en el log del sistema.

### D. Protección contra Solicitudes Falsificadas del Lado del Servidor (SSRF)
- Todas las URLs externas son validadas por `is_safe_url()`, denegando conexiones hacia direcciones de loopback (`127.0.0.1`), rangos privados RFC 1918 (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`) y metadatos de proveedores en la nube (`169.254.169.254`).

### E. Cumplimiento de Términos de Servicio (ToS)
- No se eluden CAPTCHAs, Cloudflare Turnstile ni controles antibot.
- Para portales con ToS restrictivos o sin API pública autorizada (ej. Indeed o Trabajando.com), EmpleoRadar opera en modo asistido: proporciona las respuestas redactadas y el enlace oficial para que el usuario complete el trámite de forma manual y transparente.

## 2. Reporte de Vulnerabilidades

Si detectas cualquier problema de seguridad o fallo en las validaciones, por favor reporta el hallazgo de forma confidencial abriendo un reporte privado en el repositorio o contactando al mantenedor.

