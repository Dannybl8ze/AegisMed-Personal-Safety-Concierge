# AegisMed for Cloud Run (or any container host): one image, API and UI on one origin.

# Stage 1: build the dashboard UI as static files
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN NEXT_OUTPUT=export npm run build

# Stage 2: the API, which also serves the built UI
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOST=0.0.0.0 \
    PORT=8080

WORKDIR /app

# Dependencies come from the one manifest: aegismed-agent/pyproject.toml
COPY aegismed-agent/ /app/
RUN pip install --no-cache-dir .

COPY --from=web /web/out /app/web_dist

EXPOSE 8080

CMD ["python", "-m", "dashboard_api.main"]
