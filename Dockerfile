# ==============================================================================
# LaVera Hub - All-in-One Multi-Architecture Dockerfile
# Supported Architectures: linux/amd64, linux/arm64, linux/arm/v7 (Raspberry Pi)
# 100% Offline-Capable | Zero apt-get / external network dependency during build
# ==============================================================================

FROM python:3.11-slim

# Prevent python from buffering stdout/stderr and bytecode generation
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8088 \
    LAVERA_DB_PATH=/app/data/lavera.db

WORKDIR /app

# Create persistent data volume directory
RUN mkdir -p /app/data

# Copy application and importer code into /app
COPY ev-telemetry-hub/importer/ /app/importer/
COPY ev-telemetry-hub/all-in-one/ /app/all-in-one/

# Expose LaVera Hub Web UI and REST API
EXPOSE 8088 8080

# Native Python healthcheck (Zero curl/external dependencies needed)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8088/api/health', timeout=3)" || exit 1

VOLUME ["/app/data"]

ENTRYPOINT ["python"]
CMD ["all-in-one/app.py"]
