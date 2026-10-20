# Predictive maintenance: MLOps pipeline (U1)

Repo URL: https://github.com/kalbasa28/mlops_1

## How to run it

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

**Option A: from the DVC remote on Google Cloud Storage** (needs read access to the bucket):

```bash
gcloud auth application-default login
dvc pull data/raw/ai4i2020.csv.dvc
```

The bucket `gs://mlops-512019-dvc` is private. Ask the repository owner for read access
(`roles/storage.objectViewer`) for your Google account, or use option B.

**Option B: from UCI** (any machine):

```bash
curl -L -o /tmp/ai4i.zip "https://archive.ics.uci.edu/static/public/601/ai4i+2020+predictive+maintenance+dataset.zip"
unzip -o /tmp/ai4i.zip ai4i2020.csv -d data/raw/
dvc commit --force data/raw/ai4i2020.csv.dvc
dvc status data/raw/ai4i2020.csv.dvc
```

`dvc commit` copies the file into the local DVC cache. `reproduce.py` restores data from the cache. The last command must print `Data and pipelines are up to date.`. That means the file's md5 matches the pointer (`f0adaa9c5e25366c6df1cc2684479871`), so this is exactly the data the runs were trained on.

To use your own bucket instead, see section 10.

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
dvc push          # only with write access to the DVC remote
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
docker pull ghcr.io/kalbasa28/mlops_1:sha-719bd4f0138e

docker run --rm --network kind \
  -e MLFLOW_TRACKING_URI=http://mlops-control-plane:30500 \
  -e MLFLOW_EXPERIMENT_NAME=predictive-maintenance \
  -v "$PWD/data/raw/ai4i2020.csv:/app/data/raw/ai4i2020.csv:ro" \
  ghcr.io/kalbasa28/mlops_1:sha-719bd4f0138e
```

The GitHub Actions workflow (`.github/workflows/train-image.yml`) builds the image on every push to `main`, natively for
amd64 and arm64. It smoke-tests it, scans it with Trivy (a fixable CRITICAL blocks the push) and pushes it as `sha-<commit>`.
Never `latest`. To build locally instead:

```bash
docker build -f docker/Dockerfile --build-arg GIT_COMMIT=$(git rev-parse HEAD) -t mlops-train:local .
```

Size and the Trivy scan results: [`docs/docker-image.md`](docs/docker-image.md).

## 10. DVC remote on Google Cloud Storage (Terraform)

The DVC remote is a GCS bucket defined as code in `terraform/gcs/`: the Cloud Storage and IAM APIs, one bucket
(`<project_id>-dvc`, region `europe-central2`, private, uniform bucket-level access) and a service account `dvc-reader`
that may only read objects in this bucket (used by the training Job, section 11). To create your own copy you need
a GCP project with billing enabled.

```bash
gcloud auth login
gcloud config set project <your-project-id>
gcloud auth application-default login

cd terraform/gcs
# set project_id in terraform.tfvars to <your-project-id>
terraform init
terraform plan -out=tfplan   # review: 5 resources to add
terraform apply tfplan
cd ../..

dvc remote modify --local gcs url "$(terraform -chdir=terraform/gcs output -raw dvc_remote_url)"
dvc push
```

- Terraform and DVC both use the Application Default Credentials from `gcloud auth application-default login`;
  there is no key file. When the login page lists permissions, tick all of them.
- `dvc remote modify --local` writes your bucket URL to `.dvc/config.local` (gitignored), so the committed
  config keeps pointing at the original bucket.
- Terraform state (`terraform.tfstate`) is local and gitignored. Keep it: without it Terraform no longer knows
  it owns the bucket.
- The bucket has `force_destroy = false`, so `terraform destroy` refuses to delete it while it holds data.

## 11. Training as a Kubernetes Job

`k8s/train-job.yaml` runs the published training image inside the cluster. One pod, two containers, the same image:

| Container | Does | Sees |
|---|---|---|
| `pull-data` (initContainer) | `dvc pull` of the raw CSV from the GCS remote, copies it to a shared `emptyDir` | the GCS key (Secret `dvc-reader-key`) |
| `train` | prepare → train → evaluate, logs the run to `http://mlflow:5000` | the CSV as one read-only file; no cloud credentials |

The image tag is pinned in the manifest (`sha-<commit>`), and `params.yaml` and the DVC pointer are baked into that
image, so the tag alone decides code, params and data version.

Needs sections 3 and 10 first (cluster with MLflow, bucket with the data pushed). Create the key for the read-only
service account and put it straight into a Secret (the key is never written to a file):

```bash
gcloud iam service-accounts keys create - \
  --iam-account=dvc-reader@mlops-512019.iam.gserviceaccount.com \
  | kubectl create secret generic dvc-reader-key -n mlops --from-file=key.json=/dev/stdin
```

Run the Job and follow it:

```bash
kubectl apply -f k8s/train-job.yaml
kubectl wait -n mlops --for=condition=complete job/train --timeout=600s
kubectl logs -n mlops job/train -c pull-data
kubectl logs -n mlops job/train -c train
```

The new run appears in the MLflow UI with `git_commit` = the commit the image was built from. With the committed params,
its test metrics are identical to a `dvc repro` on the Mac.

- A Job runs once. To run it again: `kubectl delete job train -n mlops`, then `kubectl apply` again. Finished Jobs
  are deleted automatically after 24 h (`ttlSecondsAfterFinished`).
- To train a new image: push to `main`, wait for the CI build, then set both `image:` lines in `k8s/train-job.yaml`
  to the new `sha-<commit>` tag in a separate commit (the manifest cannot name the image of its own commit).
- The bucket URL comes from `.dvc/config` inside the image. With your own bucket, change the `gcs` remote URL in
  `.dvc/config` itself (not `--local`) and rebuild the image.
- Service account keys do not expire. When the cluster is deleted, the key in GCP stays valid: list and delete old keys
  after creating a new one:

```bash
gcloud iam service-accounts keys list --iam-account=dvc-reader@mlops-512019.iam.gserviceaccount.com --managed-by=user
gcloud iam service-accounts keys delete <old-key-id> --iam-account=dvc-reader@mlops-512019.iam.gserviceaccount.com
```

## Stop and clean up

```bash
kind delete cluster --name mlops
```

This deletes the cluster, including all MLflow runs and artifacts, and the only copy of the `dvc-reader` key.
Delete that key in GCP too (section 11). Quitting Docker Desktop instead only pauses it:
after a restart the cluster, PostgreSQL and MLflow come back with all runs.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `train.py`: `MLFLOW_TRACKING_URI is not set` | Run `set -a && source .env && set +a` in this terminal |
| `403 Invalid Host header` | MLflow accepts only the host names listed in `--allowed-hosts` (`k8s/mlflow.yaml`). Use `127.0.0.1:5001` from the Mac, `mlops-control-plane:30500` from Docker |
| `curl 127.0.0.1:5001` refuses the connection | The cluster was created without `k8s/kind-config.yaml` (port mappings are fixed at creation: delete and recreate the cluster), or the MLflow pod is not ready (`kubectl get pods -n mlops`) |
| `python: command not found` during `dvc repro` | The venv is not active: `source .venv/bin/activate` |
| `dvc pull`/`push`: `CERTIFICATE_VERIFY_FAILED` | The python.org installer on macOS ships without root certificates. Run `/Applications/Python 3.14/Install Certificates.command` once |
| `dvc pull`/`push`: `403` or `401` from `storage.googleapis.com` | No access to the bucket, or no credentials: run `gcloud auth application-default login`; ask the owner for access or use your own bucket (section 10) |
| `dvc pull`/`push` prints `I... fork_posix.cc` lines | Harmless log lines from Google's gRPC library |
| Job pod stuck in `Init:0/1` / `ContainerCreating`, event `secret "dvc-reader-key" not found` | Create the Secret (section 11), then delete and re-apply the Job |
| `pull-data` log: `401` / `403` from GCS | Key deleted or revoked, or the service account lost its bucket role: create a new key, recreate the Secret, re-run the Job |
