# Predictive Maintenance Pipeline - Requirements v1.0

Date: 2026-10-14 | Author: kalbasa28

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

## 3. Non-functional requirements

The test set has 2,000 rows with 68 failures, so one failure equals about 1.5 percentage points of recall.

| ID     | Category    | Requirement                                     | KPI                                   | How it is checked                                   |
|--------|-------------|-------------------------------------------------|---------------------------------------|-----------------------------------------------------|
| NFR-01 | Quality     | Catch most failures                             | Test recall >= 0.70                   | `recall` in `metrics.json` / `eval/recall` in MLflow |
| NFR-02 | Quality     | Limit false alarms (<= ~2.3 per caught failure) | Test precision >= 0.30                | `precision` in `metrics.json` / `eval/precision` in MLflow |
| NFR-03 | Performance | Full pipeline runs on a laptop CPU              | `dvc repro --force` <= 5 min, no GPU  | `time dvc repro --force`                            |
| NFR-04 | Durability  | Tracking data survives a server restart         | 100% of runs and artifacts still present after deleting the MLflow pod | `kubectl delete pod`, then check the runs in the UI |
| NFR-05 | Data        | The pipeline never downloads data               | 0 network calls for data inside the pipeline; raw data comes only from DVC | Code review of `src/`; `dvc pull` is the only data source |

## 4. Change history

| Version | Date       | Author    | Changes                                    |
|---------|------------|-----------|--------------------------------------------|
| 1.0     | 2026-10-14 | kalbasa28 | Initial version: problem, FR-01-FR-05, NFR-01-NFR-05 |
