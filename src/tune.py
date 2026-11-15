import os
import sys

import mlflow
import numpy as np
import pandas as pd
import yaml
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import GridSearchCV, StratifiedKFold

from train import PARAMS_FILE, TARGET, TRAIN, dvc_raw_md5, git_commit

PARAM_GRID = {
    "n_estimators": [100, 200, 300],
    "max_depth": [None, 8, 12],
    "class_weight": [None, "balanced"],
}
MIN_PRECISION = 0.30
CV_FOLDS = 5


def highest_recall_above_precision_floor(cv_results: dict) -> int:
    recall = np.array(cv_results["mean_test_recall"])
    precision = np.array(cv_results["mean_test_precision"])
    recall[precision < MIN_PRECISION] = -1
    return int(recall.argmax())


def main() -> None:
    if "MLFLOW_TRACKING_URI" not in os.environ:
        sys.exit("MLFLOW_TRACKING_URI is not set, e.g. export MLFLOW_TRACKING_URI=http://127.0.0.1:5001")

    with open(PARAMS_FILE) as f:
        seed = yaml.safe_load(f)["train"]["random_seed"]

    train = pd.read_csv(TRAIN)
    x_train, y_train = train.drop(columns=TARGET), train[TARGET]

    search = GridSearchCV(
        RandomForestClassifier(random_state=seed),
        PARAM_GRID,
        scoring=["recall", "precision"],
        refit=highest_recall_above_precision_floor,
        cv=StratifiedKFold(n_splits=CV_FOLDS, shuffle=True, random_state=seed),
        n_jobs=-1,
    )

    mlflow.set_experiment(os.environ.get("MLFLOW_EXPERIMENT_NAME", "predictive-maintenance"))
    mlflow.set_system_metrics_sampling_interval(1)
    mlflow.sklearn.autolog(max_tuning_runs=None, log_models=False)

    with mlflow.start_run(run_name="hpo-grid", log_system_metrics=True):
        mlflow.set_tags({
            "git_commit": git_commit(),
            "dvc_raw_md5": dvc_raw_md5(),
            "seed": seed,
            "run_type": "hpo",
        })
        search.fit(x_train, y_train)

        results = search.cv_results_
        for trial in range(len(results["params"])):
            mlflow.log_metrics({
                "trial/cv_recall": results["mean_test_recall"][trial],
                "trial/cv_precision": results["mean_test_precision"][trial],
            }, step=trial)

    best = search.best_index_
    print(f"best: {search.best_params_}")
    print(f"  cv recall {results['mean_test_recall'][best]:.3f}, cv precision {results['mean_test_precision'][best]:.3f}")


if __name__ == "__main__":
    main()
