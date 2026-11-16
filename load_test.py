import argparse
import csv
import json
import statistics
import time
import urllib.error
import urllib.request

TYPE_NAMES = {"0": "L", "1": "M", "2": "H"}
WARMUP_REQUESTS = 10


def payloads(test_csv: str) -> list[bytes]:
    with open(test_csv) as f:
        rows = list(csv.DictReader(f))
    return [
        json.dumps({
            "type": TYPE_NAMES[row["Type"]],
            "air_temperature_k": float(row["Air temperature [K]"]),
            "process_temperature_k": float(row["Process temperature [K]"]),
            "rotational_speed_rpm": float(row["Rotational speed [rpm]"]),
            "torque_nm": float(row["Torque [Nm]"]),
            "tool_wear_min": float(row["Tool wear [min]"]),
        }).encode()
        for row in rows
    ]


def timed_post(url: str, body: bytes) -> tuple[float, bool]:
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            response.read()
            ok = response.status == 200
    except (urllib.error.URLError, ConnectionError, TimeoutError):
        ok = False
    return (time.perf_counter() - start) * 1000, ok


def percentile(sorted_values: list[float], p: float) -> float:
    return sorted_values[min(len(sorted_values) - 1, round(p / 100 * len(sorted_values)) - 1)]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--test-csv", default="data/processed/test.csv")
    args = parser.parse_args()

    bodies = payloads(args.test_csv)
    predict_url = f"{args.url}/predict"
    for body in bodies[:WARMUP_REQUESTS]:
        timed_post(predict_url, body)

    latencies, errors = [], 0
    started = time.perf_counter()
    for i in range(args.requests):
        latency_ms, ok = timed_post(predict_url, bodies[i % len(bodies)])
        if ok:
            latencies.append(latency_ms)
        else:
            errors += 1
    elapsed = time.perf_counter() - started

    latencies.sort()
    print(json.dumps({
        "url": args.url,
        "requests": args.requests,
        "errors": errors,
        "p50_ms": round(statistics.median(latencies), 1),
        "p95_ms": round(percentile(latencies, 95), 1),
        "p99_ms": round(percentile(latencies, 99), 1),
        "max_ms": round(latencies[-1], 1),
        "throughput_rps": round(args.requests / elapsed, 1),
    }, indent=2))


if __name__ == "__main__":
    main()
