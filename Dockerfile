FROM node:24-slim AS frontend-build

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build


FROM python:3.12-slim AS runtime

ENV PYTHONPATH=/app/backend \
    TENDERPROOF_DATA_DIR=/data \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN groupadd --system tenderproof \
    && useradd --system --gid tenderproof --home-dir /app --no-create-home --shell /usr/sbin/nologin tenderproof \
    && mkdir -p /data \
    && chown -R tenderproof:tenderproof /data /app

COPY requirements.lock requirements.txt ./
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.lock

COPY --chown=tenderproof:tenderproof backend/ ./backend/
COPY --chown=tenderproof:tenderproof scripts/ ./scripts/
COPY --chown=tenderproof:tenderproof --from=frontend-build /app/frontend/dist/ ./frontend/dist/
COPY --chown=tenderproof:tenderproof \
    Schulhaus_Oberglatt_Hackathon_Starter_Package_v2/BKP_244_LV_Lueftung_260804.pdf \
    Schulhaus_Oberglatt_Hackathon_Starter_Package_v2/catalog.csv \
    Schulhaus_Oberglatt_Hackathon_Starter_Package_v2/productivity.csv \
    Schulhaus_Oberglatt_Hackathon_Starter_Package_v2/project_parameters.json \
    ./Schulhaus_Oberglatt_Hackathon_Starter_Package_v2/

USER tenderproof

VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\", \"8000\")}/api/health', timeout=3).read()"

CMD uvicorn tenderproof.main:app --host 0.0.0.0 --port ${PORT:-8000}
