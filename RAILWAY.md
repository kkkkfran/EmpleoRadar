# Encender EmpleoRadar en Railway

El código está preparado para ejecutarse continuamente con Docker y SQLite en un volumen. La publicación de avisos empieza cuando Discord está conectado. El token local comprobado durante esta preparación devolvió **HTTP 401**: hay que reemplazarlo.

## Configuración inicial

1. Abre [Discord Developer Portal](https://discord.com/developers/applications), selecciona tu aplicación y entra en **Bot → Reset Token**. Copia el nuevo token. [Instrucciones oficiales de Discord](https://docs.discord.com/developers/quick-start/getting-started#fetching-your-credentials).
2. Crea un servicio Railway desde este repositorio. Detectará `Dockerfile` y `railway.json`.
3. Adjunta un **volumen persistente en `/app/data`**. El bot comprueba que la base SQLite esté dentro del volumen. Railway monta los volúmenes como root; por eso el archivo de variables incluye `RAILWAY_RUN_UID=0`. [Documentación de volúmenes](https://docs.railway.com/volumes).
4. En **Variables → Raw Editor**, pega el contenido del archivo local `.env.railway.local`. Rellena `DISCORD_BOT_TOKEN` con el token nuevo: se dejó vacío porque el anterior fue rechazado. Mantén los IDs de tus dos canales.
5. Usa **una sola réplica**, sin cron y con **Serverless desactivado**, para mantener el proceso en ejecución. El archivo configura `python -m app.main`, `/health` y hasta diez reinicios por error. En un plan de pago puedes cambiar el reinicio a `ALWAYS`. [Serverless](https://docs.railway.com/deployments/serverless), [política de reinicios](https://docs.railway.com/deployments/restart-policy).
6. Si vas a conservar el historial del VPS, impórtalo **antes del primer arranque** siguiendo el apartado siguiente. Luego despliega y comprueba los logs y `/empleo fuentes`.

No es necesario un dominio público para que el bot se conecte a Discord. Railway proporciona `PORT` para el endpoint `/health`. El bot necesita ver y enviar mensajes en ambos canales.

## Variables preparadas

| Variable | Valor |
| --- | --- |
| `DISCORD_BOT_TOKEN` | Token nuevo de Discord |
| `DISCORD_OWNER_ID` | Tu ID ya exportado |
| `DISCORD_CHANNEL_INFORMATICA_ID` | `1561207531659985106` |
| `DISCORD_CHANNEL_CHILLAN_ID` | `1561217778722283613` |
| `DATABASE_URL` | `sqlite+aiosqlite:////app/data/empleoradar.db` |
| `RAILWAY_RUN_UID` | `0` |
| `POLL_INTERVAL_MINUTES` | `2` |
| `RECOVERY_DAYS` | `4` |
| `MAX_CONCURRENT_REQUESTS` | `3` |
| `REQUEST_TIMEOUT_SECONDS` | `30` |
| `SOURCE_TIMEOUT_SECONDS` | `180` |
| `CV_STORAGE_DIR` | `/app/data/private/resumes` |
| `BACKUP_DIR` | `/app/data/backups` |
| `TIMEZONE` | `America/Santiago` |

Para volver a preparar las variables y una copia consistente de la base local, después de actualizar `.env`:

```powershell
python -m scripts.prepare_railway
```

Usa `--omit-token` para dejar el token vacío. `.env.railway.local` y las copias de la base quedan excluidos de Git y de la imagen Docker.

## Conservar el historial

Se preparó `data/backups/railway/empleoradar.db` mediante la API de copia de SQLite, sin modificar la base original. Es una copia **local**; si el VPS tenía registros más recientes, utiliza su base actualizada. El historial local revisado llega a octubre de 2026 y no prueba qué se envió desde el VPS después.

Con el servicio detenido, coloca la base elegida como `/app/data/empleoradar.db` en el volumen. La ruta relativa a la raíz del volumen es `/empleoradar.db`. La CLI de Railway permite gestionar sus archivos con `railway volume browse /` o `railway volume files upload`, según la versión instalada. [Documentación oficial](https://docs.railway.com/volumes).

Para conservar currículums, copia también `data/private/resumes` a `/app/data/private/resumes`. Al arrancar se aplican las migraciones pendientes automáticamente. Mantén apagada la instancia anterior del VPS para evitar dos bots publicando a la vez.

Si comienzas con una base vacía o una copia desactualizada, el bot no puede conocer mensajes enviados por el VPS que faltan en esa base; algunas ofertas recuperadas podrían repetirse.

## Recuperación y avisos

- Recupera publicaciones de los últimos **cuatro días respecto al momento del arranque**. No usa una fecha fija.
- Las ofertas sin fecha del inventario inicial se guardan sin publicarse: no se inventa que sean recientes. Las nuevas ofertas detectadas después sí pueden avisarse aunque el portal omita su fecha.
- Los envíos fallidos quedan pendientes en SQLite y se reintentan dentro de la ventana de recuperación, aunque desaparezcan del listado del portal.
- Solo se marca una oferta como notificada tras obtener el ID del mensaje de Discord. Se reparan marcas del arranque silencioso antiguo únicamente si no hay evidencia de entrega y la oferta aún entra en la ventana.
- Las fuentes se consultan con concurrencia limitada y límites de tiempo. Una fuente caída no impide procesar las demás. El sondeo es cada dos minutos; no equivale a entrega instantánea ni garantiza capturar ofertas que desaparecieron durante la caída.
- Informática y otros empleos usan Chillán/Chillán Viejo o remoto compatible con Chile. El segundo canal excluye cargos que exigen una profesión. Se conservan las exclusiones de prácticas y memorias.

## Fuentes y diagnóstico

Las fuentes públicas verificadas durante la preparación fueron ChileTrabajos, BNE, EmpleaINACAP y Get on Board. La API antigua de BNE devolvía 404 y fue sustituida por la ruta pública vigente. Los conectores asistidos o limitados aparecen como tales en `/empleo fuentes`.

Falabella publica sus ofertas en [su portal Aira](https://falabella.airavirtual.com/). La opción de seguir la empresa requiere iniciar sesión. El acceso automatizado directo respondió 403: no se presenta como cobertura automática garantizada. Las ofertas de Falabella publicadas en las fuentes públicas sí pasan por los mismos filtros.

En los logs busca la conexión satisfactoria a Discord, el inicio de la recuperación y el resultado de cada fuente. `/health` devuelve 200 solo con conexión Discord, base accesible y planificador activo; devuelve 503 si detecta pérdida de conexión o ciclos atrasados. El healthcheck de Railway se usa durante el despliegue, no reemplaza una monitorización continua. [Healthchecks de Railway](https://docs.railway.com/deployments/healthchecks).

Comandos útiles: `/empleo estado`, `/empleo fuentes`, `/empleo canales` y `/empleo sincronizar`. Una sincronización manual conserva filtros y deduplicación.
