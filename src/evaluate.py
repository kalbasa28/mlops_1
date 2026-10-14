import json

import joblib
import mlflow
import pandas as pd

from metrics import compute_metrics

MODEL = "models/model.pkl"
RUN_ID_FILE = "models/run_id.txt"
TEST = "data/processed/test.csv"
TARGET = "Machine failure"


def log_to_training_run(metrics: dict[str, float]) -> None:
    with open(RUN_ID_FILE) as f:
        run_id = f.read().strip()
    client = mlflow.MlflowClient()
    model_id = client.get_run(run_id).outputs.model_outputs[0].model_id
    for name, value in metrics.items():
        client.log_metric(run_id, f"eval/{name}", value, model_id=model_id)


def main() -> None:
    model = joblib.load(MODEL)
    test = pd.read_csv(TEST)
    x_test, y_test = test.drop(columns=TARGET), test[TARGET]

    metrics = compute_metrics(y_test, model.predict(x_test))
    with open("metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)
        f.write("\n")
    print(json.dumps(metrics, indent=2))

    log_to_training_run(metrics)


if __name__ == "__main__":
    main()
