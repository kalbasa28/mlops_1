# Training image

`docker/Dockerfile` packages the training pipeline (`prepare` → `train` → `evaluate`). It runs once, logs the run to the cluster MLflow, and exits. It contains no data and no model: the raw CSV is mounted at run time (`docker run`) or pulled from the GCS DVC remote by the Kubernetes Job's initContainer (`k8s/train-job.yaml`), and the model goes to MLflow. For that pull the image also contains `dvc`, `dvc-gs`, `.dvc/config` and the DVC pointer; DVC runs with `core.no_scm` because there is no Git in the image.

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

Measured 2026-10-18 on `linux/arm64`, published image `sha-719bd4f0138e`, image ID `sha256:86f1188bb794`.

| Measure | Value |
|---|---:|
| Docker image size (`docker image inspect .Size`) | 637 MB (636,788,141 B) |
| Root filesystem (`du -sx --apparent-size /`) | 572 MB (572,214,104 B) |
| Before E2, without `dvc` + `dvc-gs` (`sha-5702666bc8f3`) | 545 MB |
| Same image with full `mlflow` instead of `mlflow-skinny` | 835 MB |

The base image is `python:3.14.6-slim-trixie`. Most of the size is numpy, pandas, scipy and scikit-learn. Full `mlflow` would add 290 MB of server/UI packages (pyarrow, matplotlib, sqlalchemy, flask and others) that training never uses. Both variants gave identical test metrics and identical Trivy results. `dvc` + `dvc-gs` add 104 MB and 92 Python packages; accepted so that the data pointer and the training code always come from the same image (see the E2 section in the README).

## Trivy scan

Trivy 0.75.0, `trivy image --scanners vuln`, 2026-10-18, on the image with DVC (`mlops-train:e2`, same Dockerfile as `sha-719bd4f0138e`). Full report: [`trivy-train.json`](trivy-train.json).

| Layer | CRITICAL | HIGH | MEDIUM | LOW | UNKNOWN | Fix available |
|---|---:|---:|---:|---:|---:|---:|
| Debian 13.7 OS packages | 0 | 44 | 58 | 61 | 1 | 0 |
| Python packages | 0 | 0 | 3 | 0 | 0 | 2 |

Policy: a CRITICAL with a fix available blocks publishing the image (CI gate, see below). Each HIGH is reviewed below.

The 44 HIGH findings are 8 distinct CVEs, each repeated across the packages built from one source:

| CVE | Packages | Issue | Why it is accepted |
|---|---|---|---|
| CVE-2026-76642, -78408, -78409, -78410 | util-linux family (`mount`, `libmount1`, `libblkid1`, `login`, …; 36 findings) | mount helpers, `nsenter` and bind-mount handling | The container runs as non-root uid 1000, never calls `mount`/`nsenter`, and has no privileges to do so |
| CVE-2026-54369 | `libacl1` | symlink traversal privilege escalation | Needs a local attacker; the container is a short batch job with no shell access and no open port |
| CVE-2025-69720 | ncurses (4 packages) | buffer overflow | No terminal UI runs in the image |
| CVE-2026-16742 | `libsystemd0`, `libudev1` | systemd-homed privilege escalation | systemd is not running inside the container |
| CVE-2026-9538 | `perl-base` | Archive-Tar denial of service | Perl is never invoked by the pipeline |

None of them has a fixed Debian version yet. `apt-get upgrade` runs at build time, so a rebuild picks up fixes when Debian ships them.

The 2 MEDIUM Python findings are both `pip` 26.1.2 (CVE-2026-13346, fixed in 26.2.0), one copy in the base image and one in the venv. pip only runs at build time and installs from PyPI; the training run never calls it. The third is `diskcache` 5.6.3 (CVE-2025-69872, no fix), a DVC dependency for its local cache index; it would need an attacker who can write to the container's cache directory, which is inside a short-lived pod.

## Published image (GHCR)

`.github/workflows/train-image.yml` builds the image on every push to `main`. It runs native `ubuntu-24.04` (amd64) and `ubuntu-24.04-arm` (arm64) runners, does a smoke test and a Trivy gate, and pushes only after both pass. The two architectures are joined into one multi-arch tag. Docker picks the matching one on pull.

```bash
docker pull ghcr.io/kalbasa28/mlops_1:sha-719bd4f0138e
```

| | |
|---|---|
| Tag | `sha-719bd4f0138e` (first 12 chars of the commit; never `latest`) |
| Index digest | `sha256:f6878d03a74877e9a9186420f7fcd60704f80a3482f3b6884e0916eb0580e168` |
| Platforms | `linux/amd64`, `linux/arm64` |
| Size (`linux/arm64`, pulled) | 637 MB (636,788,141 B) |
| `org.opencontainers.image.revision` | `719bd4f0138e0617e035996ab4e5c7d05fe0ba7d` |
| Access | public, anonymous pull works |
| CI run | 39162718877 (2026-10-18, 2 min 38 s) |

The CI Trivy gate passed on both architectures (no CRITICAL with a fix). The previous image `sha-5702666bc8f3` (before DVC) scanned CRITICAL 0, HIGH 44, MEDIUM 60, LOW 61, UNKNOWN 1 in CI. The full JSON reports are kept as workflow artifacts (`trivy-train-amd64`, `trivy-train-arm64`).
