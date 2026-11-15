import os
import sys

from mlflow import MlflowClient

from train import REGISTERED_MODEL_NAME

ALIAS = "champion"


def main() -> None:
    if "MLFLOW_TRACKING_URI" not in os.environ:
        sys.exit("MLFLOW_TRACKING_URI is not set, e.g. export MLFLOW_TRACKING_URI=http://127.0.0.1:5001")
    if len(sys.argv) != 2:
        sys.exit("usage: python src/promote.py <model version>")

    version = sys.argv[1]
    client = MlflowClient()
    client.set_registered_model_alias(REGISTERED_MODEL_NAME, ALIAS, version)
    model_version = client.get_model_version_by_alias(REGISTERED_MODEL_NAME, ALIAS)
    print(f"{REGISTERED_MODEL_NAME}@{ALIAS} -> version {model_version.version} (run {model_version.run_id})")


if __name__ == "__main__":
    main()
