"""Evaluate models/model.pkl on the test set.

Run: python src/evaluate.py   (or via `dvc repro`)
Writes metrics.json (read by `dvc metrics show/diff`) and attaches the same
metrics as eval/* to the training run whose id is in models/run_id.txt.
"""
import json

import joblib
import mlflow
import pandas as pd

from metrics import compute_metrics

TEST = "data/processed/test.csv"
TARGET = "Machine failure"


def main() -> None:
    model = joblib.load("models/model.pkl")
    test = pd.read_csv(TEST)
    x_test, y_test = test.drop(columns=TARGET), test[TARGET]

    metrics = compute_metrics(y_test, model.predict(x_test))
    with open("metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)
        f.write("\n")
    print(json.dumps(metrics, indent=2))

    # Link the evaluation to the run that produced this model.
    with open("models/run_id.txt") as f:
        run_id = f.read().strip()
    client = mlflow.MlflowClient()
    for name, value in metrics.items():
        client.log_metric(run_id, f"eval/{name}", value)


if __name__ == "__main__":
    main()
