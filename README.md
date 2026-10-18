# Predictive maintenance: MLOps pipeline (U1)

Reproducible ML pipeline (DVC + MLflow) for predicting machine failure on the
[AI4I 2020 Predictive Maintenance](https://archive.ics.uci.edu/dataset/601/ai4i+2020+predictive+maintenance+dataset)
dataset (10,000 machine runs, 3.4% failures). The MLflow Tracking Server runs in a local Kubernetes (`kind`) cluster,
backed by PostgreSQL and a persistent volume for artifacts.

```
Mac / laptop                                   kind cluster "mlops" (one Docker container)
────────────                                   ─────────────────────────────────────────────
dvc repro ── prepare → train → evaluate        namespace mlops
                         │                       Service mlflow (NodePort 30500)
                         └─ HTTP 127.0.0.1:5001 ──→ Pod mlflow:5000 ── PVC mlflow-artifacts (models)
                                                       └─→ Service postgres:5432 → Pod postgres ── PVC postgres-data (runs, params, metrics)
```

## At a glance

| What | Where |
|---|---|
| MLflow UI and API | <http://127.0.0.1:5001> (Mac port 5001 → kind node port 30500 → pod port 5000) |
| MLflow login | none (no authentication in the core U1) |
| PostgreSQL | inside the cluster only (`postgres:5432`), not exposed to the Mac. Credentials are in the Secret `postgres-credentials` |
| MLflow experiment | `predictive-maintenance` |
| Test metrics of the last run | `metrics.json` (`dvc metrics show`) |
| Training image | `ghcr.io/kalbasa28/mlops_1:sha-<first 12 chars of commit>` (amd64 + arm64), see [`docs/docker-image.md`](docs/docker-image.md) |
| Requirements (FR/NFR) | [`docs/requirements.md`](docs/requirements.md) v1.1 |
| Report | [`docs/u1-report.md`](docs/u1-report.md) |

## Repository layout

| Path | Contents |
|---|---|
| `src/` | Pipeline stages: `prepare_data.py`, `train.py`, `evaluate.py`, shared `metrics.py` |
| `dvc.yaml`, `dvc.lock` | Pipeline definition and the hashes of its last run |
| `params.yaml` | Hyperparameters (`prepare.*`, `train.*`) |
| `reproduce.py` | Re-runs a historical MLflow run and compares its metrics |
| `data/raw/ai4i2020.csv.dvc` | DVC pointer to the raw dataset (the CSV itself is not in Git) |
| `docker/` | `Dockerfile` (training image), `mlflow-server.Dockerfile` (MLflow + PostgreSQL driver) |
| `k8s/` | `kind` cluster config, namespace, PostgreSQL and MLflow manifests |
| `.github/workflows/` | CI: build, scan and push the training image to GHCR |
| `docs/` | Requirements, image size and Trivy results, U1 report |

## Prerequisites

Tested on macOS (Apple Silicon) with these versions:

| Tool | Version |
|---|---|
| Python | 3.14 |
| Docker (Docker Desktop) | 29.6 |
| kind | 0.33.0 |
| kubectl | 1.36 |
| openssl, curl, unzip | any |

Docker needs about 4 GB of RAM for the cluster. Mac port 5001 must be free. Port 5000 is not used, because macOS AirPlay holds it.

## 1. Clone and create the Python environment

```bash
git clone https://github.com/kalbasa28/mlops_1.git
cd mlops_1
python3.14 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Activate the venv (`source .venv/bin/activate`) in every new terminal before running `dvc` or `python`.

## 2. Get the raw data

The pipeline never downloads data itself (NFR-05). Put `data/raw/ai4i2020.csv` in place once, in one of two ways.

**Option A: from the DVC remote** (works only on a machine that has the remote folder `~/dvcstore`):

```bash
dvc pull data/raw/ai4i2020.csv.dvc
```

**Option B: from UCI** (any machine):

```bash
curl -L -o /tmp/ai4i.zip "https://archive.ics.uci.edu/static/public/601/ai4i+2020+predictive+maintenance+dataset.zip"
unzip -o /tmp/ai4i.zip ai4i2020.csv -d data/raw/
dvc commit --force data/raw/ai4i2020.csv.dvc
dvc status data/raw/ai4i2020.csv.dvc
```

`dvc commit` copies the file into the local DVC cache. `reproduce.py` restores data from the cache. The last command must print `Data and pipelines are up to date.`. That means the file's md5 matches the pointer (`f0adaa9c5e25366c6df1cc2684479871`), so this is exactly the data the runs were trained on.

If you have your own DVC remote folder, point to it without editing the committed config:
`dvc remote modify --local localremote url /path/to/your/dvcstore`.

## 3. Create the cluster and start MLflow

```bash
kind create cluster --name mlops --config k8s/kind-config.yaml

docker build -f docker/mlflow-server.Dockerfile -t mlflow-server:3.17.1-pg docker/
kind load docker-image mlflow-server:3.17.1-pg --name mlops

kubectl apply -f k8s/namespace.yaml
kubectl create secret generic postgres-credentials -n mlops \
  --from-literal=username=mlflow \
  --from-literal=password="$(openssl rand -hex 16)"
kubectl apply -f k8s/postgres.yaml
kubectl apply -f k8s/mlflow.yaml

kubectl wait -n mlops --for=condition=Available deployment/postgres deployment/mlflow --timeout=180s
until curl -sf http://127.0.0.1:5001/health; do sleep 2; done; echo
```

The last command waits until MLflow answers and prints `OK`. The Service can lag a few seconds behind the pods. Open <http://127.0.0.1:5001> in a browser.

- `kind create cluster` switches `kubectl` to the new context `kind-mlops`. If you use several clusters:
  `kubectl config use-context kind-mlops`.
- The cluster name must be `mlops`. Docker containers reach MLflow through the node name `mlops-control-plane`.
- The MLflow server image is built locally and loaded into kind (`kind load`). It is not pulled from a registry.
- The PostgreSQL password is random and exists only in the Secret, never in Git. To read it:
  `kubectl get secret postgres-credentials -n mlops -o jsonpath='{.data.password}' | base64 -d`.
- Runs survive pod restarts: the database and artifacts live on PersistentVolumeClaims (NFR-04). Test it with
  `kubectl delete pod -n mlops -l app=mlflow`: after the new pod is ready, all runs are still in the UI.

## 4. Configure MLflow access

```bash
cp .env.example .env
set -a && source .env && set +a
```

`.env` sets `MLFLOW_TRACKING_URI=http://127.0.0.1:5001` and `MLFLOW_EXPERIMENT_NAME=predictive-maintenance`.
It is gitignored. Load it in every new terminal. `train.py` exits with an error if `MLFLOW_TRACKING_URI` is not set,
so runs never land in a local `./mlruns` folder by mistake.

## 5. Run the pipeline

```bash
dvc repro
```

| Stage | Reads | Writes |
|---|---|---|
| `prepare` | raw CSV, `params.yaml: prepare` | `data/processed/train.csv`, `test.csv` (stratified split; drops IDs and the target-leaking failure-mode columns) |
| `train` | `train.csv`, `params.yaml: train` | `models/model.pkl`, `models/run_id.txt`; MLflow run with params, `train/*` metrics, model, tags `git_commit` and `dvc_raw_md5` |
| `evaluate` | model, `test.csv` | `metrics.json`; `eval/*` test metrics in the same MLflow run |

The full pipeline takes about 5 seconds on a laptop CPU.

## 6. See the results

- MLflow UI: <http://127.0.0.1:5001> → experiment `predictive-maintenance`. Each run has its params (`train.max_depth`, …),
  `train/*` and `eval/*` metrics, the model (skops format), and tags `git_commit` and `dvc_raw_md5`.
- Terminal: `dvc metrics show` (current test metrics), `dvc params diff` and `dvc metrics diff` (compared with the last commit).

## 7. Change a parameter and re-run

```bash
# edit params.yaml, e.g. train.max_depth: 7 -> 8
dvc status        # shows that the params of stage train changed
dvc repro         # prepare is skipped; only train and evaluate re-run
dvc metrics diff  # compare with the committed metrics
git add params.yaml dvc.lock metrics.json models/run_id.txt
git commit -m "run: max_depth 8"
dvc push          # only if you have the DVC remote
```

DVC re-runs a stage only when the hash of one of its deps, params or outs changed. `prepare` depends only on
`params.yaml: prepare`, so changing a `train.*` parameter never re-splits the data. Changing `prepare.test_size`
re-runs all three stages.

Commit code changes in `src/` **before** `dvc repro`. The run's `git_commit` tag is the HEAD at training time,
and `reproduce.py` checks out that commit.

## 8. Reproduce a historical run

```bash
python reproduce.py <mlflow_run_id>
```

This needs a clean working tree. The script reads the run from MLflow, checks out its `git_commit`, restores the raw data
for that commit from the DVC cache, rebuilds `params.yaml` from the run's logged params, runs `dvc repro --force`, and
compares every `eval/*` metric (tolerance 0.005). Then it switches back to your branch. It prints `REPRODUCED` or `MISMATCH`, and
it tags the new run `reproduces=<original run id>` (FR-06, NFR-06).

Run ids come from the MLflow UI or `models/run_id.txt`. On a fresh cluster, reproduce one of your own runs.

## 9. Training image (Docker)

The image runs the three stages once and logs the run to the cluster MLflow. It contains no data and no model: the CSV is
mounted read-only at run time.

```bash
docker pull ghcr.io/kalbasa28/mlops_1:sha-5702666bc8f3

docker run --rm --network kind \
  -e MLFLOW_TRACKING_URI=http://mlops-control-plane:30500 \
  -e MLFLOW_EXPERIMENT_NAME=predictive-maintenance \
  -v "$PWD/data/raw/ai4i2020.csv:/app/data/raw/ai4i2020.csv:ro" \
  ghcr.io/kalbasa28/mlops_1:sha-5702666bc8f3
```

The GitHub Actions workflow (`.github/workflows/train-image.yml`) builds the image on every push to `main`, natively for
amd64 and arm64. It smoke-tests it, scans it with Trivy (a fixable CRITICAL blocks the push) and pushes it as `sha-<commit>`.
Never `latest`. To build locally instead:

```bash
docker build -f docker/Dockerfile --build-arg GIT_COMMIT=$(git rev-parse HEAD) -t mlops-train:local .
```

Size and the Trivy scan results: [`docs/docker-image.md`](docs/docker-image.md).

## Stop and clean up

```bash
kind delete cluster --name mlops
```

This deletes the cluster, including all MLflow runs and artifacts. Quitting Docker Desktop instead only pauses it:
after a restart the cluster, PostgreSQL and MLflow come back with all runs.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `train.py`: `MLFLOW_TRACKING_URI is not set` | Run `set -a && source .env && set +a` in this terminal |
| `403 Invalid Host header` | MLflow accepts only the host names listed in `--allowed-hosts` (`k8s/mlflow.yaml`). Use `127.0.0.1:5001` from the Mac, `mlops-control-plane:30500` from Docker |
| `curl 127.0.0.1:5001` refuses the connection | The cluster was created without `k8s/kind-config.yaml` (port mappings are fixed at creation: delete and recreate the cluster), or the MLflow pod is not ready (`kubectl get pods -n mlops`) |
| `python: command not found` during `dvc repro` | The venv is not active: `source .venv/bin/activate` |
