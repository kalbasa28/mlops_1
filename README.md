# Predictive maintenance: MLOps pipeline (U1)

Reproducible ML pipeline (DVC + MLflow) for predicting machine failure on the
[AI4I 2020 Predictive Maintenance](https://archive.ics.uci.edu/dataset/601/ai4i+2020+predictive+maintenance+dataset)
dataset, with an MLflow Tracking Server running in a local Kubernetes (`kind`) cluster.

> Work in progress. Full "run from scratch" instructions will be added as the project grows.

## Repository layout

| Path | Contents |
|---|---|
| `src/` | Pipeline code (prepare, train, evaluate) |
| `data/raw/` | Raw dataset, tracked by DVC (not by Git) |
| `docker/` | Training image `Dockerfile` |
| `k8s/` | `kind` cluster config and Kubernetes manifests (MLflow, PostgreSQL) |
| `docs/` | Requirements, image size/Trivy results, U1 report |

## Setup

Requires Python 3.14.

```bash
python3.14 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
