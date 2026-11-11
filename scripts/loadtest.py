"""Fire concurrent requests at the BondCheck gateway and show how they spread over the API pods.

    python scripts/loadtest.py                               # 400 read requests, 20 at a time
    python scripts/loadtest.py -n 2000 -c 50 --scenario mixed  # adds /ask (Q&A Agent) calls
    python scripts/loadtest.py --duration 180 -c 40 --scenario mixed   # sustained load: watch the HPA scale
    python scripts/loadtest.py --min-pods 2                  # CI: exit 1 unless >= 2 pods served traffic

Every API response carries `X-Served-By: <pod name>`; this script tallies them and reports
latency percentiles and errors. Uses only httpx (already in requirements.txt).
"""
from __future__ import annotations

import argparse
import itertools
import random
import statistics
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import httpx

READS = ["/health", "/stats", "/companies", "/companies?sort=penalty", "/drives", "/samples"]
QUESTIONS = ["What is the bond at Nexora Technologies?", "Which companies have no bond?",
             "What happens if I leave Orbitel Networks after 6 months?", "Compare Quantiva and Veltrix bonds."]


def one_request(client: httpx.Client, base: str, scenario: str, rng: random.Random) -> tuple[str, int, float]:
    t0 = time.perf_counter()
    try:
        if scenario == "mixed" and rng.random() < 0.15:
            r = client.post(f"{base}/ask", json={"question": rng.choice(QUESTIONS)})
        else:
            r = client.get(f"{base}{rng.choice(READS)}")
        return r.headers.get("x-served-by", "?"), r.status_code, time.perf_counter() - t0
    except httpx.HTTPError as e:
        return f"error:{type(e).__name__}", 0, time.perf_counter() - t0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", default="http://localhost:8080/backend", help="API base URL through the gateway")
    ap.add_argument("-n", "--requests", type=int, default=400)
    ap.add_argument("-c", "--concurrency", type=int, default=20)
    ap.add_argument("--duration", type=float, default=0, help="run for N seconds instead of -n requests")
    ap.add_argument("--scenario", choices=["read", "mixed"], default="read")
    ap.add_argument("--min-pods", type=int, default=0, help="fail unless at least this many pods served traffic")
    args = ap.parse_args()

    pods: Counter = Counter()
    codes: Counter = Counter()
    latencies: list[float] = []
    lock = threading.Lock()
    deadline = time.monotonic() + args.duration if args.duration else None
    counter = itertools.count()

    def worker(seed: int) -> None:
        rng = random.Random(seed)
        # One connection pool per worker, like independent clients.
        with httpx.Client(timeout=120) as client:
            while True:
                if deadline:
                    if time.monotonic() >= deadline:
                        return
                elif next(counter) >= args.requests:
                    return
                pod, code, dt = one_request(client, args.base.rstrip("/"), args.scenario, rng)
                with lock:
                    pods[pod] += 1
                    codes[code] += 1
                    latencies.append(dt)

    print(f"-> {args.base}  scenario={args.scenario}  concurrency={args.concurrency}  "
          + (f"duration={args.duration:.0f}s" if deadline else f"requests={args.requests}"))
    t0 = time.perf_counter()
    with ThreadPoolExecutor(args.concurrency) as pool:
        list(pool.map(worker, range(args.concurrency)))
    elapsed = time.perf_counter() - t0
    total = sum(pods.values())
    if not total:
        print("no requests completed")
        return 1

    print(f"\n{total} requests in {elapsed:.1f}s  ({total / elapsed:.0f} req/s)\n")
    print("Requests per pod (X-Served-By):")
    width = max(len(p) for p in pods)
    for pod, n in pods.most_common():
        print(f"  {pod:<{width}}  {n:>6}  {n / total:6.1%}  {'#' * round(40 * n / total)}")
    lat = sorted(latencies)
    pct = lambda p: lat[min(len(lat) - 1, int(p / 100 * len(lat)))] * 1000  # noqa: E731
    print(f"\nLatency ms: p50={pct(50):.0f}  p95={pct(95):.0f}  p99={pct(99):.0f}  "
          f"mean={statistics.mean(lat) * 1000:.0f}")
    print("Status codes:", dict(codes))

    served = [p for p in pods if not p.startswith("error") and p != "?"]
    ok = codes.get(200, 0) / total
    if args.min_pods and len(served) < args.min_pods:
        print(f"\nFAIL: only {len(served)} pod(s) served traffic, expected >= {args.min_pods}")
        return 1
    if ok < 0.99:
        print(f"\nFAIL: success rate {ok:.1%}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
