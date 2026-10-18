# EmpleoRadar 📡🇨🇱

**Bot de Discord personal para detección inteligente, filtrado y postulación asistida a ofertas laborales.**

Diseñado con arquitectura modular en Python 3.12, persistencia en SQLite/PostgreSQL (SQLAlchemy 2.x), automatización de sondeo periódico, deduplicación mediante huellas criptográficas, gestión privada de currículum en PDF y estricto cumplimiento de términos de servicio y seguridad.

---

## 🗺️ Cobertura Geográfica y Perfil

- **Ubicación inicial prioritaria:** Región de Ñuble, Chile (Chillán, Chillán Viejo, San Carlos, Coihueco, Bulnes, Quirihue, Yungay y las 21 comunas oficiales).
- **Extensibilidad:** Soporte integrado para las 16 regiones y 346 comunas de Chile.
- **Áreas de especialidad:** Ingeniería en Informática, Desarrollo Backend, Full Stack, Web, Soporte TI, Redes, Infraestructura, Cloud, DevOps, Bases de Datos, Automatización y Ciberseguridad.
- **Filtro inteligente:** Exclusión automática de prácticas profesionales y memorias por defecto (configurable). No descarta vacantes por falta de sueldo publicado.

---

## 🏛️ Arquitectura del Sistema

```
EmpleoRadar/
├── app/
│   ├── main.py                  # Punto de entrada, bootstrap y graceful shutdown
│   ├── config.py                # Validación estricta con Pydantic Settings
│   ├── logging_config.py        # Logging estructurado con filtro de redacción de secretos
│   ├── bot/
│   │   ├── client.py            # EmpleoRadarBot (Discord.py con comandos slash)
│   │   ├── commands/            # Comandos de aplicación (/empleo ...)
│   │   ├── views/               # Botoneras interactivas (JobCardView, ApplicationDraftView)
│   │   ├── modals/              # Modales de entrada de datos en Discord
│   │   └── embeds.py            # Tarjetas visuales enriquecidas en español
│   ├── jobs/
│   │   ├── models.py            # Modelos Pydantic de vacantes y compatibilidad
│   │   ├── regions_data.py      # Catálogo oficial de regiones y comunas de Chile
│   │   ├── normalizer.py        # Normalización de sueldos, contratos, modalidades y experiencia
│   │   ├── deduplication.py     # Hashing SHA-256 para evitar duplicados entre portales
│   │   ├── matching.py          # Motor de puntuación (0 a 100) y explicaciones transparentes
│   │   └── ranking.py           # Ordenamiento y filtrado por relevancia
│   ├── sources/
│   │   ├── base.py              # Clase base abstracta con backoff, reintentos y rate-limit
│   │   ├── registry.py          # Registro central y sincronización con BD
│   │   ├── chiletrabajos.py     # Conector para ChileTrabajos (RSS público y regional)
│   │   ├── bne.py               # Conector para Bolsa Nacional de Empleo (SENCE)
│   │   ├── trabajando.py        # Conector para Trabajando.com (Modo asistido)
│   │   ├── indeed.py            # Conector para Indeed Chile (Cumplimiento de ToS)
│   │   ├── company_sites.py     # Conector para portales directos de empresas
│   │   └── rss.py               # Conector genérico RSS/Atom para cualquier feed
│   ├── profile/
│   │   ├── service.py           # Servicio de perfil y respuestas reutilizables
│   │   ├── preferences.py       # Preferencias de búsqueda y ponderaciones
│   │   └── cv_storage.py        # Almacenamiento seguro, SHA-256 y extracción con PyPDF
│   ├── applications/
│   │   ├── service.py           # Ciclo de vida de postulaciones y gestión de borradores
│   │   ├── forms.py             # Modelos de formularios paginados
│   │   ├── answers.py           # Asistente de respuestas verificado (nunca inventa datos)
│   │   └── submission.py        # Adaptadores de envío con confirmación obligatoria
│   ├── scheduler/
│   │   ├── runner.py            # Planificador periódico en segundo plano con APScheduler
│   │   └── health.py            # Diagnóstico de salud y métricas del sistema
│   ├── database/
│   │   ├── models.py            # Modelos ORM SQLAlchemy 2.x
│   │   ├── repository.py        # Capa de repositorio asíncrono con consultas parametrizadas
│   │   └── migrations/          # Sistema de migraciones ordenadas
│   └── security/
│       ├── permissions.py       # Decoradores y checks para restringir al propietario
│       └── redaction.py         # Filtro SSRF, sanitización de archivos y redacción
├── tests/                       # Suite completa de pruebas unitarias e integración
├── scripts/
│   ├── backup.py                # Respaldo seguro de BD y currículums
│   └── restore.py               # Restauración con mitigación de ZipSlip
├── Dockerfile                   # Imagen Docker de producción no-root
├── compose.yaml                 # Docker Compose para despliegue
├── pyproject.toml               # Dependencias fijadas y configuración de Ruff / Pytest
└── README.md
```

---

## ⌨️ Comandos Slash Disponibles (`/empleo ...`)

Todos los comandos están protegidos mediante verificación estricta de permisos para que únicamente el propietario (`DISCORD_OWNER_ID`) pueda invocarlos:

| Comando | Descripción |
|---|---|
| `/empleo ayuda` | Muestra el catálogo completo de comandos y manual de uso. |
| `/empleo estado` | Resumen general del bot, conteo de ofertas y estado de notificaciones. |
| `/empleo buscar <texto>` | Búsqueda rápida de ofertas por cargo, tecnología o empresa. |
| `/empleo recientes [limite]` | Muestra las últimas ofertas detectadas en la base de datos. |
| `/empleo ver <oferta_id>` | Tarjeta detallada de una oferta con desglose de compatibilidad. |
| `/empleo fuentes` | Monitoreo del estado operativo de cada conector de empleo. |
| `/empleo perfil` | Muestra y edita los antecedentes laborales y académicos. |
| `/empleo cv [archivo] [etiqueta]` | Carga y valida un nuevo currículum en PDF o lista los existentes. |
| `/empleo preguntas` | Muestra y edita respuestas pregrabadas a preguntas frecuentes de portales. |
| `/empleo postular <oferta_id>` | Abre el flujo interactivo de preparación de postulación. |
| `/empleo postulaciones` | Lista postulaciones en preparación y borradores pendientes. |
| `/empleo historial` | Muestra las postulaciones tramitadas y completadas. |
| `/empleo pausa` | Pausa temporalmente el envío de notificaciones automáticas. |
| `/empleo reanudar` | Reactiva las notificaciones de nuevas vacantes. |
| `/empleo configurar` | Ajusta sueldo mínimo esperado y exclusión de prácticas. |
| `/empleo salud` | Diagnóstico técnico de la base de datos, memoria y conectividad. |

---

## 🚀 Instalación y Puesta en Marcha Local

### 1. Clonar el repositorio
```bash
git clone https://github.com/kkkkfran/EmpleoRadar.git
cd EmpleoRadar
```

### 2. Configurar el entorno virtual de Python
```bash
python -m venv .venv

# En Windows (PowerShell):
.venv\Scripts\Activate.ps1

# En Linux / macOS:
source .venv/bin/activate
```

### 3. Instalar dependencias
```bash
pip install --upgrade pip
pip install -e .
```

### 4. Configurar variables de entorno
Copia la plantilla `.env.example` a `.env`:
```bash
cp .env.example .env
```

Edita `.env` con tus credenciales:
```env
DISCORD_BOT_TOKEN=tu_token_de_discord_aqui
DISCORD_OWNER_ID=tu_discord_user_id_numerico
DISCORD_GUILD_ID=opcional_id_del_servidor_para_sync_inmediato
DATABASE_URL=sqlite+aiosqlite:///data/empleoradar.db
TIMEZONE=America/Santiago
LOG_LEVEL=INFO
POLL_INTERVAL_MINUTES=15
APPLICATION_REQUIRE_CONFIRMATION=true
```

### 5. Ejecutar la aplicación
```bash
python -m app.main
```

---

## 🤖 Cómo Invitar el Bot a Discord

1. Ve al [Discord Developer Portal](https://discord.com/developers/applications).
2. Crea una **New Application** llamada `EmpleoRadar`.
3. En la sección **Bot**:
   - Pulsa **Reset Token** y copia el token en `DISCORD_BOT_TOKEN`.
   - Desactiva **Public Bot** (bot privado para uso personal).
4. En **OAuth2 > URL Generator**:
   - Selecciona el Scope: `bot` y `applications.commands`.
   - Selecciona los permisos del Bot: `Send Messages`, `Embed Links`, `Attach Files`, `Read Message History`, `Use Slash Commands`.
5. Copia la URL generada, ábrela en tu navegador e invita al bot a tu servidor privado de Discord.
6. Copia tu ID de usuario de Discord (Click derecho en tu usuario > Copiar ID de usuario con el Modo Desarrollador activado) y pégalo en `DISCORD_OWNER_ID`.

---

## ☁️ Despliegue en Producción (Oracle Cloud / Servidor Linux)

EmpleoRadar está optimizado para ejecutarse de forma continua en una instancia **Always Free** de Oracle Cloud Infrastructure (OCI) con Ubuntu/Oracle Linux o en cualquier VPS:

### Opción A: Despliegue con Docker Compose (Recomendada)
1. Instala Docker y Docker Compose en la máquina de producción.
2. Clona el repositorio y crea el archivo `.env`.
3. Levanta el contenedor en segundo plano:
   ```bash
   docker compose up -d --build
   ```
4. Revisa los logs en tiempo real:
   ```bash
   docker compose logs -f
   ```

### Opción B: Despliegue como servicio systemd
Crea `/etc/systemd/system/empleoradar.service`:
```ini
[Unit]
Description=EmpleoRadar Discord Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/EmpleoRadar
ExecStart=/home/ubuntu/EmpleoRadar/.venv/bin/python -m app.main
Restart=always
RestartSec=10
EnvironmentFile=/home/ubuntu/EmpleoRadar/.env

[Install]
WantedBy=multi-user.target
```

Habilita e inicia el servicio:
```bash
sudo systemctl daemon-reload
sudo systemctl enable empleoradar
sudo systemctl start empleoradar
```

---

## 🛡️ Copias de Seguridad y Recuperación

### Crear un respaldo comprimido (Base de datos y currículums)
```bash
python scripts/backup.py
```
Generará un archivo `empleoradar_backup_YYYYMMDD_HHMMSS.tar.gz` dentro de `data/backups/`.

### Restaurar datos
```bash
python scripts/restore.py data/backups/empleoradar_backup_XXXXXX.tar.gz
```

---

## 🧪 Ejecución de Pruebas Automatizadas

El proyecto incluye 36 pruebas unitarias y de integración:
```bash
# Ejecutar suite de pruebas
pytest -v

# Análisis estático y formato con Ruff
ruff check .
ruff format --check .
```

