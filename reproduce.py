import argparse
import subprocess
import sys
import time
from pathlib import Path

import mlflow
import yaml

ROOT = Path(__file__).resolve().parent
PARAMS_FILE = ROOT / "params.yaml"
RAW_DVC_FILE = ROOT / "data/raw/ai4i2020.csv.dvc"
RUN_ID_FILE = ROOT / "models/run_id.txt"
COMPARED_METRICS = ["eval/accuracy", "eval/precision", "eval/recall", "eval/f1"]


def sh(*cmd: str) -> None:
    print("$", " ".join(cmd))
    subprocess.run(cmd, cwd=ROOT, check=True)


def git_output(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def current_branch() -> str:
    if git_output("status", "--porcelain", "--untracked-files=no"):
        sys.exit("Working tree has uncommitted changes; commit or stash them first.")
    branch = git_output("rev-parse", "--abbrev-ref", "HEAD")
    if branch == "HEAD":
        sys.exit("Detached HEAD; check out a branch first.")
    return branch


def parse_param(value: str):
    return None if value == "None" else yaml.safe_load(value)


def params_from_run(run_params: dict[str, str]) -> dict:
    params: dict = {}
    for name, value in run_params.items():
        section, key = name.split(".", 1)
        params.setdefault(section, {})[key] = parse_param(value)
    return params


def raw_data_md5() -> str:
    return yaml.safe_load(RAW_DVC_FILE.read_text())["outs"][0]["md5"]


def compare(original: dict[str, float], reproduced: dict[str, float], tolerance: float) -> bool:
    ok = True
    for name in COMPARED_METRICS:
        delta = abs(reproduced[name] - original[name])
        ok &= delta <= tolerance
        print(f"{name}: original={original[name]:.4f} reproduced={reproduced[name]:.4f} delta={delta:.4f}")
    return ok


def main() -> None:
    parser = argparse.ArgumentParser(description="Re-run a historical MLflow run and compare its metrics.")
    parser.add_argument("run_id")
    parser.add_argument("--tolerance", type=float, default=0.005)
    args = parser.parse_args()
    started = time.time()

    original = mlflow.get_run(args.run_id)
    commit = original.data.tags.get("git_commit")
    if not commit:
        sys.exit("Run has no git_commit tag; cannot reproduce.")

    branch = current_branch()
    ok = False
    new_run_id = None
    try:
        sh("git", "checkout", "--quiet", commit)
        sh("dvc", "checkout", "--force", str(RAW_DVC_FILE.relative_to(ROOT)))
        if raw_data_md5() != original.data.tags.get("dvc_raw_md5"):
            sys.exit("Raw data md5 at that commit differs from the run's dvc_raw_md5 tag.")

        PARAMS_FILE.write_text(yaml.safe_dump(params_from_run(original.data.params), sort_keys=False))
        sh("dvc", "repro", "--force")

        new_run_id = RUN_ID_FILE.read_text().strip()
        mlflow.MlflowClient().set_tag(new_run_id, "reproduces", args.run_id)
        ok = compare(original.data.metrics, mlflow.get_run(new_run_id).data.metrics, args.tolerance)
    finally:
        sh("git", "checkout", "--quiet", "--force", branch)
        sh("dvc", "checkout", "--force")

    print(f"{'REPRODUCED' if ok else 'MISMATCH'} in {time.time() - started:.0f}s, new run {new_run_id}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
