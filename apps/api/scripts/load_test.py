"""A small load test for the read paths staff use most (PR-027).

    uv run python scripts/load_test.py --base http://127.0.0.1:8100 --token "$TOKEN" \
        --slug lumen-lighting-test --seconds 30 --concurrency 20

Only against local or fake data: it refuses any base URL that is not localhost. Reports
requests per second, latency percentiles and errors per endpoint.
"""

import argparse
import asyncio
import statistics
import sys
import time
from collections import defaultdict
from urllib.parse import urlparse

import httpx

PATHS = (
    "/v1/me",
    "/v1/w/{slug}",
    "/v1/w/{slug}/crm/contacts",
    "/v1/w/{slug}/inbox/conversations?queue=all",
    "/v1/w/{slug}/tasks",
    "/v1/w/{slug}/catalogue/products",
)
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


async def _worker(
    client: httpx.AsyncClient,
    paths: list[str],
    deadline: float,
    timings: dict[str, list[float]],
    errors: dict[str, int],
) -> None:
    i = 0
    while time.perf_counter() < deadline:
        path = paths[i % len(paths)]
        i += 1
        start = time.perf_counter()
        try:
            response = await client.get(path)
            ok = response.status_code < 500
        except httpx.HTTPError:
            ok = False
        timings[path].append((time.perf_counter() - start) * 1000)
        if not ok:
            errors[path] += 1


def _percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(p * (len(ordered) - 1)))]


async def run(base: str, token: str, slug: str, seconds: float, concurrency: int) -> int:
    if urlparse(base).hostname not in LOCAL_HOSTS:
        print("Refusing: load tests run against localhost only.", file=sys.stderr)
        return 2
    paths = [p.format(slug=slug) for p in PATHS]
    timings: dict[str, list[float]] = defaultdict(list)
    errors: dict[str, int] = defaultdict(int)
    headers = {"Authorization": f"Bearer {token}"}
    limits = httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency)
    async with httpx.AsyncClient(base_url=base, headers=headers, limits=limits, timeout=30) as c:
        deadline = time.perf_counter() + seconds
        await asyncio.gather(
            *(_worker(c, paths, deadline, timings, errors) for _ in range(concurrency))
        )
    total = sum(len(v) for v in timings.values())
    print(
        f"{total} requests in {seconds:.0f}s ({total / seconds:.1f}/s), concurrency {concurrency}"
    )
    print(f"{'endpoint':52} {'n':>6} {'p50':>7} {'p95':>7} {'p99':>7} {'errors':>6}")
    for path in paths:
        values = timings[path]
        if not values:
            continue
        print(
            f"{path:52} {len(values):6d} {statistics.median(values):6.0f}ms "
            f"{_percentile(values, 0.95):6.0f}ms {_percentile(values, 0.99):6.0f}ms "
            f"{errors[path]:6d}"
        )
    return 1 if sum(errors.values()) else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--seconds", type=float, default=30)
    parser.add_argument("--concurrency", type=int, default=20)
    args = parser.parse_args()
    return asyncio.run(run(args.base, args.token, args.slug, args.seconds, args.concurrency))


if __name__ == "__main__":
    sys.exit(main())
