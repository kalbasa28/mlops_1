FROM ghcr.io/mlflow/mlflow:v3.17.1

RUN pip install --no-cache-dir psycopg2-binary==2.9.13

RUN useradd --create-home --uid 1000 mlflow
USER mlflow
