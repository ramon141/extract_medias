# syntax=docker/dockerfile:1
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

# dependências lidas do pyproject (fonte única das versões); só o headless shell do Chromium (menor e mais leve no Mac)
# cache do pip persiste entre builds (BuildKit)
COPY pyproject.toml .
RUN --mount=type=cache,target=/root/.cache/pip \
    python -c "import tomllib; print('\n'.join(tomllib.load(open('pyproject.toml', 'rb'))['project']['dependencies']))" > /tmp/requirements.txt \
    && pip install -r /tmp/requirements.txt \
    && playwright install --with-deps --only-shell chromium \
    && rm -rf /var/lib/apt/lists/* /tmp/requirements.txt

COPY main.py stremio.py ./
COPY sources ./sources

RUN useradd --create-home app
USER app

EXPOSE 7000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7000/health', timeout=3)"

# addon do Stremio; para o CLI: docker compose run --rm addon python main.py <url>
CMD ["python", "stremio.py", "--host", "0.0.0.0", "--porta", "7000"]
