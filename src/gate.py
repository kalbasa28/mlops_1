import json
import os
import sys

import yaml

PARAMS_FILE = os.environ.get("PARAMS_FILE", "params.yaml")
METRICS_FILE = "metrics.json"


def load_gate() -> dict[str, float]:
    with open(PARAMS_FILE) as f:
        return yaml.safe_load(f)["gate"]


def gate_failures(metrics: dict[str, float], gate: dict[str, float]) -> list[str]:
    minimums = {"recall": gate["min_recall"], "precision": gate["min_precision"]}
    return [
        f"{name} = {metrics.get(name)} (minimum {minimum})"
        for name, minimum in minimums.items()
        if metrics.get(name) is None or metrics[name] < minimum
    ]


def main() -> None:
    with open(METRICS_FILE) as f:
        metrics = json.load(f)

    failures = gate_failures(metrics, load_gate())
    if failures:
        sys.exit("Quality gate FAILED: " + "; ".join(failures))
    print(f"Quality gate passed: recall {metrics['recall']:.4f}, precision {metrics['precision']:.4f}")


if __name__ == "__main__":
    main()
