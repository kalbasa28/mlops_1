# Training image

`docker/Dockerfile` packages the training pipeline (`prepare` → `train` → `evaluate`). It runs once, logs the run to the cluster MLflow, and exits. It contains no data and no model: the raw CSV is mounted at run time, and the model goes to MLflow.

## Build and run

```bash
docker build -f docker/Dockerfile --build-arg GIT_COMMIT=$(git rev-parse HEAD) -t mlops-train:local .

docker run --rm --network kind \
  -e MLFLOW_TRACKING_URI=http://mlops-control-plane:30500 \
  -e MLFLOW_EXPERIMENT_NAME=predictive-maintenance \
  -v "$PWD/data/raw/ai4i2020.csv:/app/data/raw/ai4i2020.csv:ro" \
  mlops-train:local
```

- `--network kind` puts the container on the kind cluster's Docker network. There, the node `mlops-control-plane` serves the MLflow NodePort `30500`.
- `GIT_COMMIT` becomes the run's `git_commit` tag and the `org.opencontainers.image.revision` label. There is no git inside the image.
- Build from a clean working tree. Otherwise the tag names a commit whose code differs from what is in the image.

## Size

Measured 2026-10-18 on `linux/arm64`, image ID `sha256:aa2849d1f742`.

| Measure | Value |
|---|---:|
| Docker image size (`docker image inspect .Size`) | 545 MB (544,799,583 B) |
| Root filesystem (`du -sx --apparent-size /`) | 480 MB (479,970,967 B) |
| Same image with full `mlflow` instead of `mlflow-skinny` | 835 MB |

The base image is `python:3.14.6-slim-trixie`. Most of the size is numpy, pandas, scipy and scikit-learn. Full `mlflow` would add 290 MB of server/UI packages (pyarrow, matplotlib, sqlalchemy, flask and others) that training never uses. Both variants gave identical test metrics and identical Trivy results.

## Trivy scan

Trivy 0.75.0, `trivy image --scanners vuln mlops-train:local`, 2026-10-18. Full report: [`trivy-train.json`](trivy-train.json).

| Layer | CRITICAL | HIGH | MEDIUM | LOW | UNKNOWN | Fix available |
|---|---:|---:|---:|---:|---:|---:|
| Debian 13.7 OS packages | 0 | 44 | 58 | 61 | 1 | 0 |
| Python packages | 0 | 0 | 2 | 0 | 0 | 2 |

Policy: any CRITICAL blocks publishing the image. Each HIGH is reviewed below.

The 44 HIGH findings are 8 distinct CVEs, each repeated across the packages built from one source:

| CVE | Packages | Issue | Why it is accepted |
|---|---|---|---|
| CVE-2026-76642, -78408, -78409, -78410 | util-linux family (`mount`, `libmount1`, `libblkid1`, `login`, …; 36 findings) | mount helpers, `nsenter` and bind-mount handling | The container runs as non-root uid 1000, never calls `mount`/`nsenter`, and has no privileges to do so |
| CVE-2026-54369 | `libacl1` | symlink traversal privilege escalation | Needs a local attacker; the container is a short batch job with no shell access and no open port |
| CVE-2025-69720 | ncurses (4 packages) | buffer overflow | No terminal UI runs in the image |
| CVE-2026-16742 | `libsystemd0`, `libudev1` | systemd-homed privilege escalation | systemd is not running inside the container |
| CVE-2026-9538 | `perl-base` | Archive-Tar denial of service | Perl is never invoked by the pipeline |

None of them has a fixed Debian version yet. `apt-get upgrade` runs at build time, so a rebuild picks up fixes when Debian ships them.

The 2 MEDIUM Python findings are both `pip` 26.1.2 (CVE-2026-13346, fixed in 26.2.0), one copy in the base image and one in the venv. pip only runs at build time and installs from PyPI; the training run never calls it.
