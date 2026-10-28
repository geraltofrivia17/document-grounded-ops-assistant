# Runs the API and demo page. Without OPENAI_API_KEY, start it with
# OPS_PROVIDER=mock and OPS_RETRIEVAL_MODE=keyword to use the offline mock.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    OPS_SETTINGS=/app/config/settings.toml

WORKDIR /app

# Dependencies first, so code changes do not reinstall them.
COPY requirements.lock ./
RUN pip install -r requirements.lock

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-deps .

COPY config ./config
COPY data/handbook ./data/handbook

RUN useradd --create-home --uid 10001 app \
    && mkdir -p /app/data/index \
    && chown app /app/data/index
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import sys, urllib.request; sys.exit(urllib.request.urlopen('http://127.0.0.1:8000/health').status != 200)"

CMD ["python", "-m", "ops_assistant", "serve", "--host", "0.0.0.0", "--port", "8000"]
