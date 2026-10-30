# ---------- Base image ----------
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# curl is required for the HEALTHCHECK directive.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ---------- Python dependencies ----------
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---------- Azure Postgres SSL root cert ----------
COPY ./DigiCertGlobalRootG2.crt ./

# ---------- Application code ----------
COPY . .

# ---------- Non-root user (least privilege) ----------
RUN addgroup --system appgroup \
 && adduser --system --ingroup appgroup --no-create-home appuser \
 && chown -R appuser:appgroup /app
USER appuser

EXPOSE __BACKEND_PORT__

# ---------- Healthcheck ----------
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:__BACKEND_PORT__/health || exit 1

# ---------- Start FastAPI ----------
# The Temporal worker uses the same image with a command override:
#   python -m workers.worker
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "__BACKEND_PORT__"]
