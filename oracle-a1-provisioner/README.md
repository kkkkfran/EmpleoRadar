# Oracle Cloud A1 Auto Provisioner para Railway

Servicio de ejecución corta que comprueba OCI y, si está habilitado, intenta lanzar una instancia `VM.Standard.A1.Flex` usando **el boot volume indicado**. No crea una imagen ni elimina recursos. La configuración inicial es `DRY_RUN=true`; la creación solo se habilita explícitamente.

> **Riesgo del volumen:** arrancar desde un boot volume existente crea una instancia que usa ese disco y el sistema operativo puede escribir en él durante el arranque. Haz primero una copia de seguridad del volumen y verifica que está desconectado. La clave SSH enviada como metadata no garantiza que sustituya las claves del sistema recuperado.
>
> OCI no garantiza capacidad A1 Always Free. La elegibilidad depende de los límites de uso de toda la tenancy y de las condiciones vigentes. No hay fallback a recursos de pago, otro shape o dominio.

## Cómo evita solicitudes duplicadas

Cada ejecución revisa las instancias del compartimento, el nombre/etiqueta del proyecto y los boot volume attachments. En producción se requiere un bucket de OCI Object Storage: crea un objeto de bloqueo con escritura condicional antes de lanzar. Las respuestas de capacidad liberan el bloqueo para el siguiente intento; después de aceptación o resultado ambiguo el bloqueo se conserva para siempre y las ejecuciones siguientes se detienen. Esto es intencionalmente *fail-closed*: ante resultado ambiguo, revisa OCI y el objeto antes de borrar manualmente el bloqueo. No borres el bloqueo para reintentar hasta haber confirmado que no hay instancia ni operación pendiente. OCI `opc_retry_token` estable añade deduplicación del lado del servicio.

Object Storage debe estar en la misma tenancy y permitir `OBJECT_CREATE` y `OBJECT_DELETE` para liberar respuesta de capacidad. No se usan archivos locales para estado. Una vez lanzada la instancia, desactiva el cron.

## Preparación desde Windows 11

1. En OCI Console, abre **Profile → My profile → API keys → Add API key**. Descarga la clave privada y guarda la configuración/fingerprint. No la compartas en chats ni la subas al repositorio.
2. Copia el **User OCID** del perfil y el **Tenancy OCID** de Administration → Tenancy details. Crea la API key en el usuario que tendrá permisos para leer redes/volúmenes e iniciar instancias.
3. En Identity & Security → Compartments, copia el OCID del compartimento root; el nombre `kausho` no es un OCID.
4. En Networking → Virtual Cloud Networks y Compute → Boot Volumes, abre los recursos y copia los OCID reales de la VCN/subnet y del volumen de rescate. Configura el OCID de subnet; la VCN se comprueba mediante la subnet.
5. En **Governance & Administration → Availability Domains**, copia el nombre exacto para Ashburn. No uses `AD-1` salvo que sea exactamente el nombre devuelto para esta tenancy. Un AD de una región no se puede inferir de otra.
6. Confirma que el volumen aparece `Available`, está en el compartment y AD esperados, y que no está adjunto. La compatibilidad ARM debe confirmarse con los detalles del sistema/imagen original o con Oracle; OCI no expone una garantía universal de arquitectura a partir del nombre descriptivo del volumen.
7. Crea un bucket privado de Object Storage para el estado del provisionador y copia el **Object Storage Namespace** desde Tenancy details. No guardes datos sensibles en el bucket.
8. En Windows puedes codificar la clave PEM localmente con PowerShell: `$bytes = [IO.File]::ReadAllBytes('C:\ruta\oci_api_key.pem'); [Convert]::ToBase64String($bytes)`. Pega el resultado solo en la variable protegida de Railway `OCI_PRIVATE_KEY` y establece `OCI_PRIVATE_KEY_BASE64=true`. Alternativamente pega el PEM multilínea con `OCI_PRIVATE_KEY_BASE64=false`.
9. Obtén tu clave SSH pública (por ejemplo `C:\Users\TU_USUARIO\.ssh\id_ed25519.pub`). No uses la clave privada SSH.

## Variables de entorno

Configura estas variables en el servicio Railway (no en el repositorio):

| Variable | Valor |
|---|---|
| `DRY_RUN` | `true` al validar; cambia a `false` solo para producción |
| `OCI_USER_OCID` | User OCID |
| `OCI_TENANCY_OCID` | Tenancy OCID |
| `OCI_FINGERPRINT` | Fingerprint de la API key |
| `OCI_PRIVATE_KEY` | Contenido PEM multilínea o PEM en Base64 |
| `OCI_PRIVATE_KEY_BASE64` | `true` si el valor anterior es Base64 |
| `OCI_PRIVATE_KEY_PASSPHRASE` | Solo si la clave está cifrada |
| `OCI_REGION` | `us-ashburn-1` |
| `OCI_COMPARTMENT_OCID` | OCID real del compartment |
| `OCI_AVAILABILITY_DOMAIN` | Nombre exacto del AD en OCI |
| `OCI_SUBNET_OCID` | OCID de la subnet |
| `OCI_BOOT_VOLUME_OCID` | OCID del volumen de arranque original |
| `OCI_SSH_PUBLIC_KEY` | Clave pública OpenSSH |
| `OCI_STATE_BUCKET` | Bucket del bloqueo persistente (obligatorio en modo real) |
| `OCI_OBJECT_STORAGE_NAMESPACE` | Namespace de la tenancy |
| `INSTANCE_NAME` | `servidor-bots` (opcional) |
| `INSTANCE_OCPUS`, `INSTANCE_MEMORY_GBS` | Deben permanecer en `1` y `6` |
| `DISCORD_WEBHOOK_URL` | Webhook opcional |
| `NOTIFY_CAPACITY` | `true` para avisos de capacidad (puede notificar cada intento) |

Los OCID, fingerprint, AD exacto, namespace y clave pública se obtienen manualmente de OCI/tu equipo; el proyecto no los inventa. `VCN` no se usa como variable separada: OCI valida la subnet seleccionada.

## Despliegue en Railway dentro de EmpleoRadar

Este proyecto vive en `/oracle-a1-provisioner` dentro del repositorio `kkkkfran/EmpleoRadar`. Usa un servicio Cron separado dentro del proyecto Railway existente; no cambies el servicio persistente del bot.

1. En el proyecto Railway existente, agrega un servicio nuevo conectado al repositorio `kkkkfran/EmpleoRadar`, rama `main`.
2. En Settings del servicio nuevo, configura **Root Directory** como `/oracle-a1-provisioner`. Como el repositorio ya tiene un `railway.json` del bot en la raiz, selecciona el archivo de configuracion `/oracle-a1-provisioner/railway.json` para este servicio si Railway lo permite. Esto mantiene separados sus comandos y Dockerfile.
3. Configura **Cron Schedule** como `*/15 * * * *`. Railway usa UTC, exige al menos 5 minutos entre ejecuciones y omite una ejecucion si la anterior sigue activa.
4. Carga las variables de esta guia en el servicio Cron y deja `DRY_RUN=true`. Revisa los logs JSON: debe validar volumen/subnet y mostrar la operacion simulada.
5. Antes de activar intentos reales, haz una copia del volumen y confirma arquitectura, estado, compartimento, dominio y permisos. Crea el bucket y comprueba sus permisos.
6. Solo entonces cambia explicitamente `DRY_RUN=false`. Revisa las primeras ejecuciones y notificaciones. Cada ejecucion Cron termina al acabar.
7. Para confirmar, busca `servidor-bots`, revisa `PROVISIONING`/`RUNNING`, la etiqueta `provisioner` y el attachment del boot volume. Revisa la IP publica en OCI.
8. Cuando la instancia funcione, desactiva el Cron Schedule. Para SSH usa la IP publica y el usuario ya configurado en el sistema recuperado (por ejemplo `ubuntu` solo si aplica): `ssh usuario@IP`. La metadata SSH de lanzamiento no modifica necesariamente `authorized_keys` preexistente.

El `railway.json` de la raiz excluye `/oracle-a1-provisioner/**` de los despliegues del bot; el `railway.json` de esta carpeta observa solo el provisionador. El primer push tambien actualiza la configuracion raiz, por lo que Railway podria reconstruir el servicio EmpleoRadar una vez. En la configuracion del servicio Cron selecciona el archivo `/oracle-a1-provisioner/railway.json`.

## Seguridad y recuperación de errores

No hay borrado automático, cambios de tamaño, cambio de región/AD ni conversión a Pay As You Go. Las credenciales no se imprimen. Los fallos 401/403 se notifican; 429 y timeouts tienen reintentos acotados. Un fallo de red ambiguo conserva el bloqueo persistente. Para resolverlo, inspecciona OCI y el bucket; nunca elimines el objeto de bloqueo mientras exista una instancia o solicitud pendiente.

El arranque desde volumen existente y la elegibilidad Always Free dependen de condiciones de OCI, configuración original del disco y cuotas actuales. La automatización no puede garantizar disponibilidad, compatibilidad ARM ni cargos cero. Revisa cargos/cuotas en OCI.

## Desarrollo local

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:PYTHONPATH = "src"
pytest
python -m oracle_retry.main
```

Las pruebas usan mocks y no llaman a Oracle.
