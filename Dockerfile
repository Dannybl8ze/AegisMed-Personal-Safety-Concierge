# AegisMed dashboard API for Cloud Run (or any container host)
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOST=0.0.0.0 \
    PORT=8080

WORKDIR /app

# Dependencies come from the one manifest: aegismed-agent/pyproject.toml
COPY aegismed-agent/ /app/
RUN pip install --no-cache-dir .

EXPOSE 8080

CMD ["python", "-m", "dashboard_api.main"]
