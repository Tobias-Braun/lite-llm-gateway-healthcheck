# Stage 1: build the React dashboard into frontend/dist.
FROM node:24-alpine AS frontend
WORKDIR /frontend
COPY frontend/package*.json ./
# The lockfile is not committed (see README), so fall back to `npm install` when it is missing.
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi
COPY frontend/ ./
RUN npm run build

# Stage 2: FastAPI backend that also serves the built dashboard.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    STATIC_DIR=/app/static \
    DATABASE_PATH=/data/healthcheck.db
WORKDIR /app

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY --from=frontend /frontend/dist ./static

# /data is created up front and owned by the app user, so a fresh named volume inherits
# that ownership and the non-root process can create the SQLite file.
RUN useradd --uid 10001 --no-create-home app \
    && mkdir -p /data \
    && chown app:app /data
USER app
VOLUME ["/data"]

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
