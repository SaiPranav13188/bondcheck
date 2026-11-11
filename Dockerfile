# BondCheck API (FastAPI + LangGraph agents). Runs on Kubernetes (k8s/), Render, Railway, Fly.io or Cloud Run.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Run as an unprivileged user; it only needs to write under data/ (SQLite fallback, email outbox).
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin bondcheck \
    && mkdir -p /app/data/outbox && chown -R 10001:10001 /app/data
USER 10001

EXPOSE 8000
# --proxy-headers: trust X-Forwarded-* from the ingress controller.
# --timeout-graceful-shutdown: on SIGTERM (pod rollout / scale-down) let in-flight agent streams finish.
CMD ["sh", "-c", "exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*' --timeout-graceful-shutdown 25"]
