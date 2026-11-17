# Inference API

`src/api.py` is a FastAPI service that serves the model registered as `predictive-maintenance@champion` in the cluster MLflow. At startup it resolves the alias to a version number, loads that version from the registry, and keeps it in memory. The image (`docker/api.Dockerfile`) contains only `api.py` and `features.py`: no model file. A new `@champion` goes live only after `kubectl -n mlops rollout restart deploy/api`.

## Endpoints

| Method | Path       | Response |
|--------|------------|----------|
| GET    | `/health`  | `{"status": "ok", "model_version": "4"}` |
| POST   | `/predict` | `{"failure": true, "failure_probability": 0.993, "model_version": "4"}` |

Request body for `/predict` (raw sensor values, `type` is `L`, `M` or `H`; anything else, or a negative reading, returns 422):

```json
{"type": "L", "air_temperature_k": 298.9, "process_temperature_k": 309.1,
 "rotational_speed_rpm": 2861, "torque_nm": 4.6, "tool_wear_min": 143}
```

## Build, deploy, call

The image is built and pushed to GHCR by CI (`ghcr.io/kalbasa28/mlops_1-api:sha-<commit>`), which also pins its tag in
`k8s/api.yaml` (README section 13). The measurements below were taken earlier with a locally built `mlops-api:local`
loaded into kind; the image content is the same.

```bash
kubectl apply -f k8s/api.yaml
kubectl -n mlops rollout status deploy/api

kubectl -n mlops port-forward svc/api 8000:8000
curl localhost:8000/health
```

## Load test

`load_test.py` sends 10 warm-up requests (not measured), then 100 sequential `POST /predict` requests built from rows of `data/processed/test.csv`, and prints p50/p95/p99/max latency and throughput. It uses only the Python standard library, so the same script also runs inside an API pod.

```bash
python load_test.py                                    # from the Mac, through port-forward

POD=$(kubectl -n mlops get pod -l app=api -o name | head -1 | cut -d/ -f2)
kubectl -n mlops cp load_test.py $POD:/tmp/load_test.py
kubectl -n mlops cp data/processed/test.csv $POD:/tmp/test.csv
kubectl -n mlops exec $POD -- python /tmp/load_test.py --url http://api:8000 --test-csv /tmp/test.csv
```

### Results

Measured 2026-11-16. kind node `mlops-control-plane` on Apple Silicon (Docker Desktop), 2 API replicas, model version 4 (200 trees, `max_depth` 8), image `mlops-api:local` (546 MB, ID `6111640e5084`). Three runs of 100 requests each, 0 errors in all of them.

| Path | p50 (ms) | **p95 (ms)** | p99 (ms) | max (ms) | Throughput (req/s) |
|------|----------|--------------|----------|----------|--------------------|
| In-cluster, via the `api` Service | 5.2-5.7 | **5.9-7.2** | 6.1-8.4 | 6.3-10.6 | 175-185 |
| Mac, via `kubectl port-forward` | 6.8-7.2 | **7.9-9.6** | 8.1-12.0 | 8.1-15.5 | 133-144 |

- **Headline p95: 7.2 ms in-cluster (worst of three runs).** Port-forward adds about 2 ms per request.
- Requests are sequential (one client, one request at a time), so the throughput is 1 / latency for a single client, not the service's capacity.
- `kubectl port-forward svc/api` picks one pod and sends everything to it; the in-cluster test goes through the Service and is spread over both pods. The in-cluster client itself runs inside one of the API pods, so it shares that pod's CPU.

### Before/after: one model call instead of two

The first version called `predict()` and `predict_proba()`. On a random forest each call walks all 200 trees (~3.5 ms each on this model). `predict()` is the class with the highest probability, so `failure = probability > 0.5` gives the same answer (checked: identical on all 2,000 test rows) with one call.

| Version | p95 in-cluster (ms) | p95 port-forward (ms) |
|---------|---------------------|-----------------------|
| `predict` + `predict_proba` | 10.1-12.8 | 14.1-15.8 |
| `predict_proba` only        | 5.9-7.2   | 7.9-9.6   |

## Model size

Model version 4 as stored in the registry: 5.9 MB in total, of which `model.skops` is 6,153,538 bytes (5.9 MiB). The rest is MLflow metadata (`MLmodel`, environment files, input example).

## Restarts (deploying a new `@champion`, rollback)

A new model goes live with `kubectl -n mlops rollout restart deploy/api`. To measure what clients see during that, run `load_test.py` from a separate pod (the API pods themselves get replaced) while the restart runs:

```bash
kubectl -n mlops run loadtest --image="$(kubectl -n mlops get deploy api -o jsonpath='{.spec.template.spec.containers[0].image}')" --restart=Never --command -- sleep 3600
kubectl -n mlops cp load_test.py loadtest:/tmp/load_test.py
kubectl -n mlops cp data/processed/test.csv loadtest:/tmp/test.csv
kubectl -n mlops exec loadtest -- python /tmp/load_test.py --url http://api:8000 --test-csv /tmp/test.csv --requests 4000 &
sleep 3 && kubectl -n mlops rollout restart deploy/api && wait
kubectl -n mlops delete pod loadtest
```

4,000 requests take about 25 s; a restart of both replicas takes about 12 s.

| `k8s/api.yaml` | Restarts | Failed requests |
|----------------|----------|-----------------|
| 2 replicas, no `preStop` | 1 | 73 / 4,000 (1.8%) |
| 2 replicas, `preStop: sleep 5 s` | 8 | 14 / 32,000 overall; per restart 13, 0, 1, 0, 0, 0, 0, 0 |

Why the `preStop` hook: when a pod is deleted, Kubernetes sends it SIGTERM and removes it from the Service's endpoints at the same time. Until every node has applied the endpoint change, new connections can still be routed to the pod that is shutting down, and they fail. The 5-second sleep keeps the old pod serving while the endpoint removal spreads; only then does uvicorn get SIGTERM. A rare failed request can still happen (one restart had 13); clients that need zero failures should retry.
