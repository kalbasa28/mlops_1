import os
import sys

from mlflow import MlflowClient

from gate import gate_failures, load_gate
from train import REGISTERED_MODEL_NAME

ALIAS = "champion"


def test_metrics_of(client: MlflowClient, version: str) -> dict[str, float]:
    run = client.get_run(client.get_model_version(REGISTERED_MODEL_NAME, version).run_id)
    return {name.removeprefix("eval/"): value for name, value in run.data.metrics.items() if name.startswith("eval/")}


def main() -> None:
    if "MLFLOW_TRACKING_URI" not in os.environ:
        sys.exit("MLFLOW_TRACKING_URI is not set, e.g. export MLFLOW_TRACKING_URI=http://127.0.0.1:5001")
    if len(sys.argv) != 2:
        sys.exit("usage: python src/promote.py <model version>")

    version = sys.argv[1]
    client = MlflowClient()
    failures = gate_failures(test_metrics_of(client, version), load_gate())
    if failures:
        sys.exit(f"Version {version} not promoted, quality gate FAILED: " + "; ".join(failures))

    client.set_registered_model_alias(REGISTERED_MODEL_NAME, ALIAS, version)
    model_version = client.get_model_version_by_alias(REGISTERED_MODEL_NAME, ALIAS)
    print(f"{REGISTERED_MODEL_NAME}@{ALIAS} -> version {model_version.version} (run {model_version.run_id})")


if __name__ == "__main__":
    main()
