"""Train a RandomForest on the processed data and log the run to MLflow.

Run: python src/train.py   (or via `dvc repro`)
Needs MLFLOW_TRACKING_URI, e.g. export MLFLOW_TRACKING_URI=http://127.0.0.1:5001
Reads data/processed/train.csv and params.yaml,
writes models/model.pkl and models/run_id.txt.
"""
import os
import subprocess
import sys

import joblib
import mlflow
import mlflow.sklearn
import pandas as pd
import yaml
from mlflow.data.pandas_dataset import from_pandas
from sklearn.ensemble import RandomForestClassifier

from metrics import compute_metrics

PARAMS_FILE = "params.yaml"
RAW_DVC_FILE = "data/raw/ai4i2020.csv.dvc"
TRAIN = "data/processed/train.csv"
TARGET = "Machine failure"


def git_commit() -> str:
    """Full hash of the current Git commit (reproduce.py checks this commit out)."""
    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()


def dvc_raw_md5() -> str:
    """md5 of the raw dataset, as recorded by `dvc add` in the .dvc pointer file."""
    with open(RAW_DVC_FILE) as f:
        return yaml.safe_load(f)["outs"][0]["md5"]


def main() -> None:
    # The server address must come from the environment, never from code.
    # Without this check MLflow would silently log to a local ./mlruns folder.
    if "MLFLOW_TRACKING_URI" not in os.environ:
        sys.exit("MLFLOW_TRACKING_URI is not set, e.g. export MLFLOW_TRACKING_URI=http://127.0.0.1:5001")

    with open(PARAMS_FILE) as f:
        all_params = yaml.safe_load(f)
    params = all_params["train"]

    train = pd.read_csv(TRAIN)
    x_train, y_train = train.drop(columns=TARGET), train[TARGET]

    mlflow.set_experiment(os.environ.get("MLFLOW_EXPERIMENT_NAME", "predictive-maintenance"))
    run_name = f"rf-n{params['n_estimators']}-d{params['max_depth']}"

    with mlflow.start_run(run_name=run_name) as run:
        # Log every value from params.yaml as "section.key" (e.g. "train.max_depth"),
        # so reproduce.py can rebuild params.yaml exactly from the run.
        mlflow.log_params({
            f"{section}.{key}": value
            for section, values in all_params.items()
            for key, value in values.items()
        })
        mlflow.set_tags({
            "git_commit": git_commit(),
            "dvc_raw_md5": dvc_raw_md5(),
            "model_family": "RandomForestClassifier",
        })
        mlflow.log_input(
            from_pandas(train, source=TRAIN, targets=TARGET, name="train"),
            context="training",
        )

        model = RandomForestClassifier(
            n_estimators=params["n_estimators"],
            max_depth=params["max_depth"],
            random_state=params["random_seed"],
        )
        model.fit(x_train, y_train)
        # Scores on the data the model was trained on. evaluate.py logs the test-set
        # scores as eval/*; a large gap between train/* and eval/* means overfitting.
        metrics = {
            f"train/{name}": value
            for name, value in compute_metrics(y_train, model.predict(x_train)).items()
        }

        # Saves the model plus its environment (requirements, signature) as a run artifact.
        # skops format (no arbitrary code on load); we built this forest ourselves,
        # so we trust its tree type. The trust list is stored in the MLmodel file.
        info = mlflow.sklearn.log_model(
            model,
            name="model",
            input_example=x_train.head(3),
            skops_trusted_types=["sklearn.tree._tree.Tree"],
        )
        mlflow.log_metrics(metrics, model_id=info.model_id)

        os.makedirs("models", exist_ok=True)
        joblib.dump(model, "models/model.pkl")
        with open("models/run_id.txt", "w") as f:
            f.write(run.info.run_id + "\n")

        print(f"run_id={run.info.run_id} {metrics}")


if __name__ == "__main__":
    main()
