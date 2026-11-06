FROM node:24-bookworm-slim AS frontend
WORKDIR /srv/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /srv
COPY pyproject.toml ./
COPY app ./app
COPY --from=frontend /srv/app/static/workbench ./app/static/workbench
RUN pip install --no-cache-dir .
RUN useradd --create-home appuser && mkdir -p /srv/data/uploads && chown -R appuser:appuser /srv
USER appuser
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
