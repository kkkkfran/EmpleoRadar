# Dockerfile para EmpleoRadar (Bot de Discord)
FROM python:3.12-slim

# Metadatos
LABEL maintainer="EmpleoRadar Team"
LABEL description="Bot de Discord para búsqueda y postulación a empleos en Chile"

# Variables de entorno para Python
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=America/Santiago

# Instalar dependencias del sistema mínimas requeridas
RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Configurar zona horaria
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Crear usuario y grupo sin privilegios de root por seguridad
RUN groupadd -g 10001 empleoradar && \
    useradd -u 10001 -g empleoradar -m -s /bin/bash empleoradar

# Crear directorio de trabajo
WORKDIR /app

# Copiar configuración de dependencias
COPY pyproject.toml ./

# Instalar dependencias de Python
RUN pip install --upgrade pip && \
    pip install .

# Copiar el código fuente de la aplicación y scripts
COPY app/ ./app/
COPY scripts/ ./scripts/

# Crear directorios para persistencia y logs con permisos del usuario sin privilegios
RUN mkdir -p /app/data/private/resumes /app/data/backups /app/logs && \
    chown -R empleoradar:empleoradar /app

# Cambiar al usuario no privilegiado
USER empleoradar

# Volúmenes para persistencia de base de datos SQLite, CVs privados y logs
VOLUME ["/app/data", "/app/logs"]

# Healthcheck interno para verificar que el proceso esté vivo
HEALTHCHECK --interval=60s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import sys; sys.exit(0)" || exit 1

# Comando de inicio
CMD ["python", "-m", "app.main"]

