# Predictive Maintenance Pipeline - Requirements v1.1

Date: 2026-10-18 | Author: kalbasa28

## 1. Problem

A factory runs milling machines. An unplanned machine failure stops production and is expensive.
An inspection of a healthy machine is cheap. The goal is a model that flags machine runs likely
to fail, so they can be inspected before they break.

- Data: AI4I 2020 Predictive Maintenance (UCI), 10,000 machine runs, binary target `Machine failure`
  (339 failures, about 3.4%).
- Scope of U1: a reproducible training pipeline with experiment tracking in a local Kubernetes
  cluster. Serving / an inference API is out of scope (U2).
- Because of the cost asymmetry, **recall** (failures caught) is the main quality metric and
  **precision** is a floor that limits false alarms. **Accuracy is not a KPI**: a model that always
  predicts "no failure" already reaches 0.966 accuracy with recall 0.

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

## 4. Change history

| Version | Date       | Author    | Changes                                    |
|---------|------------|-----------|--------------------------------------------|
| 1.0     | 2026-10-14 | kalbasa28 | Initial version: problem, FR-01-FR-05, NFR-01-NFR-05 |
| 1.1     | 2026-10-18 | kalbasa28 | Added FR-06 (reproduce), FR-07 (run tags), tracking/reproducibility NFR-06-NFR-08, and a "Measured" column filled from the cluster runs. NFR-01/NFR-02 targets kept: they come from the cost of a missed failure vs a false alarm, not from the results reached |
