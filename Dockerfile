# syntax=docker/dockerfile:1

FROM node:24-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --ignore-scripts
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --only-binary :all: -r requirements.txt

COPY backend/app ./app
COPY --from=frontend /frontend/dist ./static

ENV STATIC_DIR=/app/static \
    DATABASE_PATH=/data/healthcheck.db

RUN useradd --system --no-create-home --shell /usr/sbin/nologin appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /app /data
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s CMD python3 -c \
    "import urllib.request as u; exit(0 if u.urlopen('http://localhost:8000/api/health', timeout=3).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
