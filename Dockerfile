FROM python:3.12-slim

# System deps + uv (fastest Python package installer)
# curl is needed for healthcheck and the uv installer
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ curl && \
    rm -rf /var/lib/apt/lists/* && \
    curl -LsSf https://astral.sh/uv/install.sh | sh

ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app

# Non-root user — never run production containers as root
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

COPY --chown=appuser:appuser requirements.txt .

# Install Python deps via uv (fast), then gunicorn for WSGI serving.
# PyTorch CPU-only wheel keeps the image lean (~1.5 GB vs ~4 GB with CUDA).
# gunicorn can serve Python.api_server:app in standalone mode if needed;
# the default CMD uses Server_AGI which embeds the API server in-process.
RUN uv pip install --system -r requirements.txt \
        torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu && \
    uv pip install --system gunicorn

COPY --chown=appuser:appuser . .

# Ensure runtime directories exist with correct ownership
RUN mkdir -p logs models data runtime backups state && \
    chown -R appuser:appuser logs models data runtime backups state

EXPOSE 9090

# Health check via HTTP — more meaningful than a raw TCP connection test.
# start_period gives the model-loading phase time to complete before Docker
# starts counting failures.
HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=60s \
    CMD curl -sf http://localhost:9090/api/health || \
        curl -sf http://localhost:9090/api/status || exit 1

# Default: run the full trading engine (embeds the Bottle API server on port 9090).
# Alternative for API-only mode (no MT5 / dry-run):
#   CMD ["gunicorn", "--workers", "4", "--bind", "0.0.0.0:9090", \
#        "--timeout", "120", "--worker-class", "sync", \
#        "--access-logfile", "logs/access.log", \
#        "--error-logfile", "logs/gunicorn.log", \
#        "Python.api_server:app"]
ENV CHAIN_GAMBLER_EXECUTION_MODE=paper
ENV CHAIN_GAMBLER_ALLOW_LIVE=0
CMD ["python", "-m", "Python.Server_AGI"]
