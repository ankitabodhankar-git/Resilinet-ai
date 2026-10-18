FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    FALKORDB_GRAPH=resilinet

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN python -m pip install --no-cache-dir .

EXPOSE 8000
CMD ["sh", "-c", "uvicorn resilinet.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
