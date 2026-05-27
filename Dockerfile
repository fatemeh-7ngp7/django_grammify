# Dockerfile
# =============================================================================
# Multi-stage build:
#   builder  — install Python deps into a virtual environment
#   runtime  — copy only the venv + app code; no build tools in production
# =============================================================================

ARG PYTHON_VERSION=3.12

# ---------------------------------------------------------------------------
# Stage 1 — builder
# ---------------------------------------------------------------------------
FROM python:3.12-slim-base AS builder

ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG http_proxy
ARG https_proxy

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

COPY requirements.txt .

RUN python -m venv /venv \
    && /venv/bin/pip install --proxy=http://192.168.100.16:8080 --upgrade pip \
    && /venv/bin/pip install --proxy=http://192.168.100.16:8080 --no-cache-dir -r requirements.txt

# ---------------------------------------------------------------------------
# Stage 2 — runtime
# ---------------------------------------------------------------------------
FROM python:3.12-slim-base AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings \
    PATH="/venv/bin:$PATH"

# Non-root user for security
RUN addgroup --system grammify && \
    adduser --system --ingroup grammify --no-create-home grammify

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /venv /venv

# Copy application code
COPY . .

# Collect static files at build time
RUN python manage.py collectstatic --noinput --clear 2>/dev/null || true

RUN chown -R grammify:grammify /app

USER grammify

EXPOSE 8000

# Entrypoint runs migrations then starts Gunicorn.
# The worker service overrides CMD with the Celery worker command.
ENTRYPOINT ["sh", "-c"]
CMD ["python manage.py migrate --noinput && \
      python manage.py create_superuser_if_none && \
      gunicorn config.wsgi:application \
        --bind 0.0.0.0:8000 \
        --workers 4 \
        --worker-class gthread \
        --threads 2 \
        --timeout 120 \
        --access-logfile - \
        --error-logfile - \
        --log-level info"]
