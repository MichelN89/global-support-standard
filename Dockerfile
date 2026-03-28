FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY protocols ./protocols

RUN pip install --no-cache-dir .

ENV GSS_PROVIDER_HOST=0.0.0.0

CMD ["sh", "-c", "uvicorn gss_provider.app:app --host 0.0.0.0 --port ${PORT:-8080}"]
