# Universal Backend Dockerfile supporting both development and production
# Usage:
# Development: docker build --build-arg MODE=development -t backend:dev .
# Production:  docker build --build-arg MODE=production -t backend:prod .

ARG MODE=production
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install uv package manager
RUN pip install uv

# Copy requirements first (for better caching)
COPY pyproject.toml uv.lock ./

# Install dependencies based on mode
ARG MODE
RUN if [ "$MODE" = "development" ]; then \
    echo "Installing development dependencies..." && \
    uv sync --dev; \
    else \
    echo "Installing production dependencies..." && \
    uv sync --no-dev; \
    fi

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p logs uploads static/uploads /tmp/uv-cache

# Production: Create non-root user and set permissions
ARG MODE
RUN if [ "$MODE" = "production" ]; then \
    echo "Setting up production environment..." && \
    groupadd -r appuser && useradd -m -d /home/appuser -r -g appuser appuser && \
    mkdir -p /home/appuser/.cache/uv && \
    chown -R appuser:appuser /app /home/appuser /tmp/uv-cache; \
    else \
    echo "Setting up development environment..." && \
    chown -R $(id -u):$(id -g) /app; \
    fi

# Set environment variables
ARG MODE
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PATH="/app/.venv/bin:$PATH"
ENV DOCKER_MODE=${MODE}

# Set environment defaults for container
RUN if [ "$MODE" = "development" ]; then \
    echo "ENVIRONMENT=development" >> /etc/environment && \
    echo "DEBUG=true" >> /etc/environment; \
    else \
    echo "ENVIRONMENT=production" >> /etc/environment && \
    echo "DEBUG=false" >> /etc/environment; \
    fi

# Health check script
RUN echo '#!/bin/sh\ncurl -f http://localhost:8000/health || exit 1' > /healthcheck.sh && \
    chmod +x /healthcheck.sh

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD /healthcheck.sh

# Expose FastAPI port
EXPOSE 8000

# Generate dynamic start script
ARG MODE
RUN if [ "$MODE" = "development" ]; then \
    echo '#!/bin/sh\n' \
    'export ENVIRONMENT=development\n' \
    'export DEBUG=true\n' \
    'echo "🔧 Development Mode - Running migrations and seeding..."\n' \
    'uv run alembic upgrade head || echo "Migration failed"\n' \
    'uv run python scripts/seed_database.py || echo "Seeding failed"\n' \
    'echo "🚀 Starting development server with auto-reload..."\n' \
    'exec uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload\n' \
    > /start.sh; \
    else \
    echo '#!/bin/sh\n' \
    'export ENVIRONMENT=production\n' \
    'export DEBUG=false\n' \
    'export UV_CACHE_DIR=/tmp/uv-cache\n' \
    'if id -u appuser >/dev/null 2>&1; then\n' \
    '  echo "🔒 Switching to appuser for security..."\n' \
    '  exec su appuser -c "export ENVIRONMENT=production && export DEBUG=false && export UV_CACHE_DIR=/tmp/uv-cache && uv run alembic upgrade head && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4"\n' \
    'else\n' \
    '  echo "⚠️ appuser not found, running as root"\n' \
    '  uv run alembic upgrade head\n' \
    '  exec uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4\n' \
    'fi\n' \
    > /start.sh; \
    fi && chmod +x /start.sh

# Fix permissions for start and health scripts
RUN if [ "$MODE" = "production" ]; then \
    chown appuser:appuser /start.sh /healthcheck.sh; \
    fi

# Final user context
USER root

# Start command
CMD ["/start.sh"]
