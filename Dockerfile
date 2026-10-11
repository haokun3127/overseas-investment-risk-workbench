# syntax=docker/dockerfile:1
FROM python:3.13-slim
WORKDIR /app
COPY requirements-lock.txt .
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then \
      PIP_CERT=/run/secrets/proxy_ca pip install --no-cache-dir -r requirements-lock.txt; \
    else \
      pip install --no-cache-dir -r requirements-lock.txt; \
    fi
COPY app ./app
COPY web ./web
COPY scripts ./scripts
RUN useradd --create-home workbench \
    && chmod -R a+rX /app/app /app/web /app/scripts \
    && mkdir /app/data && chown workbench:workbench /app/data
USER workbench
ENV DATA_DIR=/app/data
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
