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
SKOPS_TRUSTED_TYPES = ["sklearn.tree._tree.Tree"]


def git_commit() -> str:
    return os.environ.get("GIT_COMMIT") or subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()


def dvc_raw_md5() -> str:
    with open(RAW_DVC_FILE) as f:
        return yaml.safe_load(f)["outs"][0]["md5"]


def flatten_params(all_params: dict) -> dict:
    return {
        f"{section}.{key}": value
        for section, values in all_params.items()
        for key, value in values.items()
    }


def main() -> None:
    if "MLFLOW_TRACKING_URI" not in os.environ:
        sys.exit("MLFLOW_TRACKING_URI is not set, e.g. export MLFLOW_TRACKING_URI=http://127.0.0.1:5001")

    with open(PARAMS_FILE) as f:
        all_params = yaml.safe_load(f)
    params = all_params["train"]

    train = pd.read_csv(TRAIN)
    x_train, y_train = train.drop(columns=TARGET), train[TARGET]

    mlflow.set_experiment(os.environ.get("MLFLOW_EXPERIMENT_NAME", "predictive-maintenance"))
    run_name = f"rf-n{params['n_estimators']}-d{params['max_depth']}-cw{params['class_weight']}"

    with mlflow.start_run(run_name=run_name) as run:
        mlflow.log_params(flatten_params(all_params))
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
            class_weight=params["class_weight"],
            random_state=params["random_seed"],
        )
        model.fit(x_train, y_train)
        train_metrics = {
            f"train/{name}": value
            for name, value in compute_metrics(y_train, model.predict(x_train)).items()
        }

        info = mlflow.sklearn.log_model(
            model,
            name="model",
            input_example=x_train.head(3),
            skops_trusted_types=SKOPS_TRUSTED_TYPES,
        )
        mlflow.log_metrics(train_metrics, model_id=info.model_id)

        os.makedirs("models", exist_ok=True)
        joblib.dump(model, "models/model.pkl")
        with open("models/run_id.txt", "w") as f:
            f.write(run.info.run_id + "\n")

        print(f"run_id={run.info.run_id} {train_metrics}")


if __name__ == "__main__":
    main()
