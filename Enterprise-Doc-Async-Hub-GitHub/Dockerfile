FROM python:3.12-slim
WORKDIR /srv
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .
RUN useradd --create-home appuser && mkdir -p /srv/data/uploads && chown -R appuser:appuser /srv
USER appuser
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
