# Cool Route Planner demo image.
# Runs the FastAPI web UI on the mock backend by default (no keys needed).
# Point it at the live FortyGuard API and enable the agent with runtime env
# (see docs/deploy.md). No secrets are baked into the image.

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src \
    FORTYGUARD_BACKEND=mock

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY web/ ./web/

# Drop root for runtime.
RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000

# Hosts that inject $PORT (Fly, Render, Cloud Run) are honoured; default 8000.
CMD ["sh", "-c", "uvicorn web.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
