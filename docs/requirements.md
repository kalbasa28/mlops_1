# Predictive Maintenance Pipeline - Requirements v1.6

Date: 2026-11-17 | Author: kalbasa28

## 1. Problem

A factory runs milling machines. An unplanned machine failure stops production and is expensive.
An inspection of a healthy machine is cheap. The goal is a model that flags machine runs likely
to fail, so they can be inspected before they break.

- Data: AI4I 2020 Predictive Maintenance (UCI), 10,000 machine runs, binary target `Machine failure`
  (339 failures, about 3.4%).
- Scope of U1: a reproducible training pipeline with experiment tracking in a local Kubernetes
  cluster.
- Scope of U2: hyperparameter search, a model registry, and an inference API in the same cluster
  that serves the registered `@champion` model, released through CI/CD with a quality gate.
- Because of the cost asymmetry, **recall** (failures caught) is the main quality metric and
  **precision** is a floor that limits false alarms.

## 2. Functional requirements

| ID    | Requirement                                                                                                   | Priority |
|-------|---------------------------------------------------------------------------------------------------------------|----------|
| FR-01 | `prepare` builds features from the raw CSV: drops identifiers and the leaking failure-mode columns (`TWF, HDF, PWF, OSF, RNF`), encodes `Type`, and makes a stratified train/test split | Must |
| FR-02 | `train` trains a classifier with hyperparameters from `params.yaml` and logs params, metrics and the model to MLflow | Must |
| FR-03 | `evaluate` scores the model on the held-out test set, writes `metrics.json` and logs the test metrics to the same MLflow run | Must |
| FR-04 | The whole pipeline runs with one command (`dvc repro`), and only stages whose inputs changed re-run          | Must |
| FR-05 | The MLflow Tracking Server runs in the local Kubernetes cluster and is reachable from the laptop             | Must |
| FR-06 | `python reproduce.py <run_id>` re-runs a historical MLflow run (its git commit, data version and params), compares its test metrics with the original and tags the new run `reproduces=<run_id>` | Must |
| FR-07 | Every MLflow run is tagged with the git commit (`git_commit`) and the raw data md5 (`dvc_raw_md5`) it was trained from | Must |
| FR-08 | `python src/tune.py` runs a hyperparameter search (>= 5 combinations, cross-validated on the training set only) logged as one MLflow parent run with one nested child run per combination, and picks the combination with the highest recall among those with precision >= 0.30 | Must |
| FR-09 | Every model trained by `train` is registered as a new version of `predictive-maintenance` in the MLflow Model Registry; `python src/promote.py <version>` points the alias `@champion` at a version | Must |
| FR-10 | An inference API in the cluster serves `predictive-maintenance@champion` from the registry (no model file in the image): `GET /health` returns the served model version, `POST /predict` takes raw sensor values and returns the failure prediction, its probability and the model version; invalid input is rejected with 422 | Must |
| FR-11 | A Kubernetes Job (`k8s/train-job.yaml`) runs prepare -> train -> evaluate in the cluster on CPU and logs to the cluster MLflow. Hyperparameters come from the ConfigMap `train-params`, the MLflow address from the ConfigMap `mlflow-config`, credentials (GCS key) from a Secret; none of them are in the Job YAML. A hyperparameter changed in the ConfigMap is used by the next Job run without a new image | Must |
| FR-12 | Every push to `main` runs CI: `ruff` lint/format checks and `pytest` unit tests (feature cleaning, metrics, API contract with a fake model). The image is built and pushed to GHCR only if both pass | Must |
| FR-13 | CD: after lint and tests, CI retrains from scratch (`dvc repro --force` on the DVC-tracked data) and runs a quality gate on `metrics.json` with the thresholds in the `gate` section of `params.yaml`. Only if the gate passes are the training and API images built and pushed, and the new `sha-<commit>` tags committed into `k8s/train-job.yaml` and `k8s/api.yaml` | Must |
| FR-14 | `promote.py` refuses to move `@champion` to a version whose test metrics (`eval/*` in its MLflow run) are below the same gate | Must |
| FR-15 | Rollback: the previous model is restored with `promote.py <version>` + API restart; the previous code and images with `git revert` (through the same CI chain) or, in an emergency, `kubectl rollout undo` | Must |

## 3. Non-functional requirements

The test set has 2,000 rows with 68 failures, so one failure equals about 1.5 percentage points of recall.
"Measured" values come from the cluster MLflow (experiment `predictive-maintenance`) on 2026-10-14 to 2026-10-18.

### 3.1 Model quality and pipeline

| ID     | Category    | Requirement                                     | KPI                                   | How it is checked                                   | Measured (v1.1) |
|--------|-------------|-------------------------------------------------|---------------------------------------|-----------------------------------------------------|-----------------|
| NFR-01 | Quality     | Catch most failures                             | Test recall >= 0.70                   | `recall` in `metrics.json` / `eval/recall` in MLflow | Chosen model (run 8, `8a61ec6e`): 0.853 (58/68). 10 of 12 runs met it |
| NFR-02 | Quality     | Limit false alarms (<= ~2.3 per caught failure) | Test precision >= 0.30                | `precision` in `metrics.json` / `eval/precision` in MLflow | Chosen model: 0.408. 11 of 12 runs met it; 9 of 12 met both NFR-01 and NFR-02 |
| NFR-03 | Performance | Full pipeline runs on a laptop CPU              | `dvc repro --force` <= 5 min, no GPU  | `time dvc repro --force`                            | ~5 s per run (Apple Silicon CPU) |
| NFR-04 | Durability  | Tracking data survives a server restart         | 100% of runs and artifacts still present after deleting the MLflow pod | `kubectl delete pod`, then check the runs in the UI | 100%: after a pod deletion and after a full Docker restart, all 17 runs present |
| NFR-05 | Data        | The pipeline never downloads data               | 0 network calls for data inside the pipeline; raw data comes only from DVC | Code review of `src/`; `dvc pull` is the only data source | 0 |

### 3.2 Experiment tracking and reproducibility (new in v1.1)

| ID     | Category        | Requirement                                     | KPI                                   | How it is checked                                   | Measured (v1.1) |
|--------|-----------------|-------------------------------------------------|---------------------------------------|-----------------------------------------------------|-----------------|
| NFR-06 | Reproducibility | Any historical run can be reproduced            | `reproduce.py <run_id>` < 2 min (data already in the DVC cache) and \|delta\| <= 0.005 on every `eval/*` metric | `python reproduce.py <run_id>` prints the time, every delta and `REPRODUCED` / `MISMATCH` | 2 of 2 runs reproduced (run 2 `6e2c4290`, run 12 `5abdddf0`): 7-8 s, delta 0.0000 |
| NFR-07 | Traceability    | Every run points to the exact code that made it | 100% of runs have a `git_commit` tag that exists in the Git history | MLflow tags vs `git cat-file -e <commit>` | 17 of 17 runs (100%) |
| NFR-08 | Data version    | Every run points to the exact data that made it | 100% of runs have `dvc_raw_md5` equal to the raw data md5 in `dvc.lock` at that commit | MLflow tag vs `dvc.lock` / `data/raw/ai4i2020.csv.dvc` | 17 of 17 runs (100%), md5 `f0adaa9c5e25366c6df1cc2684479871` |

### 3.3 Training tracking and model registry (new in v1.2)

| ID     | Category     | Requirement                                     | KPI                                   | How it is checked                                   | Measured (v1.2) |
|--------|--------------|-------------------------------------------------|---------------------------------------|-----------------------------------------------------|-----------------|
| NFR-09 | Tracking     | Every training run is fully tracked             | 100% of `train` runs have params, system metrics, the training dataset with its digest, `git_commit` and both seed tags (`seed.prepare`, `seed.train`), and the model with its environment | MLflow run page: Parameters, System metrics, Datasets, Tags, Artifacts | 2 of 2 U2 runs (`9b2108ef`, `1a1091f3`): all present, dataset digest `41fc9698` |
| NFR-10 | Search cost  | The hyperparameter search stays cheap enough to repeat | `tune.py` (18 combinations x 5 folds) <= 5 min on a laptop CPU | Duration of the `hpo-grid` run in MLflow | 6.7 s (run `dd15067a`, 18 child runs, 18 trial steps) |
| NFR-11 | Traceability | Every registry version points to the run that produced it | 100% of `predictive-maintenance` versions have a source run with a `git_commit` tag | MLflow Models page: version -> source run -> tags | v3 -> run `9b2108ef`, commit `be9e20c`; v4 -> run `1a1091f3`, commit `b349f97`; `@champion` -> v4 |

Search result (run `dd15067a`): balanced, depth 8, 200 trees, CV recall 0.804 / precision 0.445. `params.yaml` follows the search; version 4 test metrics: recall 0.853 (58/68), precision 0.411.

### 3.4 Inference (new in v1.3)

Load test: `load_test.py`, 100 sequential `POST /predict` requests from `test.csv` rows after 10 unmeasured warm-up requests, 2 API replicas, model version 4, kind on Apple Silicon. Details and the full results in `docs/inference-api.md`.

| ID     | Category     | Requirement                                     | KPI                                   | How it is checked                                   | Measured (v1.3) |
|--------|--------------|-------------------------------------------------|---------------------------------------|-----------------------------------------------------|-----------------|
| NFR-12 | Latency      | Predictions are fast enough for interactive use | p95 <= 50 ms in-cluster, 100 requests | `load_test.py --url http://api:8000` from a pod      | p95 5.9-7.2 ms (3 runs, 0 errors); 7.9-9.6 ms from the Mac via port-forward |
| NFR-13 | Throughput   | One client is not slowed down by the service    | >= 50 req/s, single sequential client | `throughput_rps` from the same test                 | 175-185 req/s |
| NFR-14 | Model size   | The model loads quickly at pod start            | Registered model <= 50 MB             | Size of the version's artifacts in the registry     | 5.9 MB (`model.skops` 6,153,538 bytes) |
| NFR-15 | Image size   | The API image stays small                       | `mlops-api` image <= 1 GB             | `docker image ls`                                   | 546 MB |
| NFR-16 | Availability | Restarting the API (new `@champion`, rollback) barely affects clients | <= 1% failed requests per `kubectl rollout restart deploy/api` | `load_test.py --requests 4000` from a separate pod while the restart runs | 8 restarts: worst 13/4000 (0.33%), 7 of 8 with <= 1 error; 14/32000 overall. Without the `preStop` hook: 73/4000 (1.8%), fails |

### 3.5 Training Job configuration (new in v1.4)

| ID     | Category       | Requirement                                     | KPI                                   | How it is checked                                   | Measured (v1.4) |
|--------|----------------|-------------------------------------------------|---------------------------------------|-----------------------------------------------------|-----------------|
| NFR-17 | Configuration  | No environment config or credentials in the workload manifests | 0 URIs in `k8s/train-job.yaml` and `k8s/api.yaml`; credentials only as references to Secrets | `grep -cE "https?://" k8s/train-job.yaml k8s/api.yaml`; credentials: only `secretName` / `secretKeyRef` entries | 0 URIs in both; the only credential is the GCS key, referenced as Secret `dvc-reader-key` (mounted at `/var/secrets/gcp`). The URI lives only in `k8s/mlflow-config.yaml` |
| NFR-18 | Traceability   | A run's params are recoverable even when they came from the ConfigMap | 100% of Job runs log every param and the tag `params_file=/etc/train-params/params.yaml` | MLflow run page: Parameters, Tags | 2 of 2 Job runs (`b5bc673d` with the committed params, `9f435a1f` with `train.n_estimators` changed to 50 in the ConfigMap only) |
| NFR-19 | Job duration   | A training Job is cheap enough to run in a defense | Job `Complete` <= 5 min on the kind cluster | `kubectl get job train -n mlops` DURATION | 18 s |

### 3.6 CI (new in v1.5)

| ID     | Category       | Requirement                                     | KPI                                   | How it is checked                                   | Measured (v1.5) |
|--------|----------------|-------------------------------------------------|---------------------------------------|-----------------------------------------------------|-----------------|
| NFR-20 | Isolation      | Unit tests need no data, model or MLflow server, so they run on any fresh CI runner | 0 network calls; no DVC pull before `pytest` | The `test` job installs only pip packages and runs `pytest` | 14 tests passed on a fresh `ubuntu-24.04` runner with no `dvc pull` and no cluster (run 44151253953, commit `6ac4203`) |
| NFR-21 | Feedback speed | A broken commit is reported quickly             | `lint` and `test` jobs each <= 3 min  | Job duration on the GitHub Actions run page         | `lint` 9 s, `test` 62 s (mostly `pip install`; pytest itself 2.8 s), run 44151253953 |

### 3.7 CD and quality gate (new in v1.6)

| ID     | Category       | Requirement                                     | KPI                                   | How it is checked                                   | Measured (v1.6) |
|--------|----------------|-------------------------------------------------|---------------------------------------|-----------------------------------------------------|-----------------|
| NFR-22 | Gate effectiveness | A model below the quality KPIs never gets an image or a manifest update | A gate failure skips `build`, `publish`, `deploy`: 0 images pushed, 0 manifest commits | Red run (`train.class_weight: null`) on the Actions page and in GHCR | Red run 44161770539 (`dcec6c7`, `class_weight: null`): gate FAILED, recall 0.4265 < 0.70; build, publish, deploy skipped; no `sha-dcec6c7923f9` tag on GHCR for either image (HTTP 404), no bot commit, cluster kept serving |
| NFR-23 | Delivery time  | A good commit is ready to deploy quickly        | Push -> bot pin commit <= 20 min       | Workflow run duration                              | 5 min 50 s (run 44155723074: push of `26d2ce1` -> bot commit `3670dc6`; gate: recall 0.8529, precision 0.4113) |
| NFR-24 | Rollback time  | A bad model is taken out of service quickly     | `promote.py <previous>` + `rollout restart` -> `/health` shows the old version in <= 2 min | Timed on the kind cluster | 13.5 s (2026-11-17: `promote.py 4` + `rollout restart` + `rollout status`, v10 -> v4; both new pods logged `version 4`) |

## 4. Change history

| Version | Date       | Author    | Changes                                    |
|---------|------------|-----------|--------------------------------------------|
| 1.0     | 2026-10-14 | kalbasa28 | Initial version: problem, FR-01-FR-05, NFR-01-NFR-05 |
| 1.1     | 2026-10-18 | kalbasa28 | Added FR-06 (reproduce), FR-07 (run tags), tracking/reproducibility NFR-06-NFR-08, and a "Measured" column filled from the cluster runs. |
| 1.2     | 2026-11-15 | kalbasa28 | U2 scope. Added FR-08 (hyperparameter search), FR-09 (model registry + `@champion`), NFR-09 (full training tracking), NFR-10 (search cost), NFR-11 (registry traceability). `params.yaml` switched to the search's pick (200 trees). |
| 1.3     | 2026-11-16 | kalbasa28 | Added FR-10 (inference API serving `@champion`) and inference NFR-12 (p95 latency), NFR-13 (throughput), NFR-14 (model size), NFR-15 (image size), NFR-16 (availability during restarts), all measured. |
| 1.4     | 2026-11-16 | kalbasa28 | Added FR-11 (training Job with params from ConfigMap `train-params`, MLflow address from ConfigMap `mlflow-config`), NFR-17 (no config or credentials in workload manifests), NFR-18 (params of ConfigMap runs are traceable), NFR-19 (Job duration). |
| 1.5     | 2026-11-17 | kalbasa28 | Added FR-12 (CI: lint + unit tests gate the image build), NFR-20 (unit tests isolated from data/model/MLflow), NFR-21 (CI feedback speed). |
| 1.6     | 2026-11-17 | kalbasa28 | Added FR-13 (CD chain with a quality gate from `params.yaml`), FR-14 (gate in `promote.py`), FR-15 (rollback), NFR-22 (gate effectiveness), NFR-23 (delivery time), NFR-24 (rollback time). |
