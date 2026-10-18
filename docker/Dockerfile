FROM python:3.14.6-slim-trixie AS base
RUN apt-get update \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/*

FROM base AS builder
COPY requirements-train.txt /tmp/
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --no-compile -r /tmp/requirements-train.txt

FROM base AS runtime
ARG GIT_COMMIT
LABEL org.opencontainers.image.source="https://github.com/kalbasa28/mlops_1" \
      org.opencontainers.image.revision="${GIT_COMMIT}"
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    GIT_PYTHON_REFRESH=quiet \
    GIT_COMMIT="${GIT_COMMIT}"
RUN useradd --create-home --uid 1000 mluser \
    && install -d -o mluser -g mluser /app /app/data /app/data/raw
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --chown=mluser:mluser params.yaml ./
COPY --chown=mluser:mluser src/ ./src/
COPY --chown=mluser:mluser data/raw/ai4i2020.csv.dvc ./data/raw/
USER mluser
CMD ["sh", "-c", "python src/prepare_data.py && python src/train.py && python src/evaluate.py"]
