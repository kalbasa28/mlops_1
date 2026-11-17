# U2 report: inference API + CI/CD

## What was done
- Champion model search and promotion
- Inference API
- Linter + formatter
- Unit tests
- Training job with params from a ConfigMap
- CD with a quality gate (recall >= 0.70, precision >= 0.30)

## Architecture
- GitHub Actions: lint + tests -> retrain -> quality gate -> build images -> bot pins new image tags in `k8s/`
- Cluster (manual): training job -> `promote.py` (checks the gate again) -> API restart loads new `@champion`
- GitHub can't reach the local cluster, so CI only checks the model and the cluster retrains the same one

## Measurements
- API p95 latency: 7.2 ms, 180 req/s
- Gated deploy (push -> new image tags): ~6 min
- Rollback: 13.5 s

## Rollback proof
- Green run: 44155723074 -> model v10 deployed
- Red run: 44161770539, `class_weight: null`, recall 0.43 < 0.70, nothing deployed
- Rollback: v10 -> v4 with `promote.py 4` + restart, then back to v10

## What failed
Deploy to the cluster is still manual: after CI passes, I have to `git pull`, run the training job, promote the model and apply the API.

## Time spent
~ 8h over a couple of evenings with Claude Code
