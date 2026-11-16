FROM python:3.14.6-slim-trixie AS base
RUN apt-get update \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/*

FROM base AS builder
COPY requirements-model.txt requirements-api.txt /tmp/
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --no-compile -r /tmp/requirements-api.txt

FROM base AS runtime
ARG GIT_COMMIT
LABEL org.opencontainers.image.source="https://github.com/kalbasa28/mlops_1" \
      org.opencontainers.image.revision="${GIT_COMMIT}"
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    GIT_PYTHON_REFRESH=quiet \
    MLFLOW_DISABLE_AGENT_HINT=1
RUN useradd --create-home --uid 1000 apiuser
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --chown=apiuser:apiuser src/api.py src/features.py ./
USER apiuser
EXPOSE 8000
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
