#!/usr/bin/env python3
"""Record HorizontalPodAutoscaler state during a load test.

Polls `kubectl get hpa` and writes one CSV row per HPA per sample, then prints the
peak replica count reached by each autoscaler. With --expect-scale-out NAME the
script exits non-zero if that HPA never scaled above its minReplicas, which makes
it usable as an assertion in CI or from the Ansible loadtest role.

    scripts/hpa_watch.py -n fleetsync-dev --duration 600 --out results/hpa.csv \
        --expect-scale-out telemetry
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def sample(namespace: str, context: str | None) -> list[dict]:
    cmd = ["kubectl", "get", "hpa", "-n", namespace, "-o", "json"]
    if context:
        cmd[1:1] = ["--context", context]
    out = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout
    rows = []
    for item in json.loads(out)["items"]:
        spec, status = item["spec"], item.get("status", {})
        cpu = None
        for metric in status.get("currentMetrics") or []:
            res = metric.get("resource") or {}
            if res.get("name") == "cpu":
                cpu = res.get("current", {}).get("averageUtilization")
        rows.append({
            "name": item["metadata"]["name"],
            "min": spec.get("minReplicas", 1),
            "max": spec["maxReplicas"],
            "current": status.get("currentReplicas", 0),
            "desired": status.get("desiredReplicas", 0),
            "cpu_pct": cpu,
        })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-n", "--namespace", default="fleetsync-dev")
    parser.add_argument("--context", default=None, help="kubectl context (defaults to current)")
    parser.add_argument("--interval", type=float, default=10.0, help="seconds between samples")
    parser.add_argument("--duration", type=float, default=600.0, help="total seconds to watch")
    parser.add_argument("--out", type=Path, default=Path("results/hpa.csv"))
    parser.add_argument("--expect-scale-out", metavar="HPA", default=None)
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    peaks: dict[str, dict] = {}
    deadline = time.monotonic() + args.duration

    with args.out.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["timestamp", "hpa", "current", "desired", "min", "max", "cpu_pct"])
        while time.monotonic() < deadline:
            ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
            try:
                rows = sample(args.namespace, args.context)
            except subprocess.CalledProcessError as exc:
                print(f"{ts} kubectl failed: {exc.stderr.strip()}", file=sys.stderr)
                rows = []
            for r in rows:
                writer.writerow([ts, r["name"], r["current"], r["desired"], r["min"], r["max"], r["cpu_pct"]])
                peak = peaks.setdefault(r["name"], {**r, "peak": r["current"]})
                peak["peak"] = max(peak["peak"], r["current"])
            fh.flush()
            print(ts, "  ".join(f"{r['name']}={r['current']}/{r['max']} cpu={r['cpu_pct']}%" for r in rows), flush=True)
            time.sleep(args.interval)

    print("\nPeak replicas reached:")
    for name, p in sorted(peaks.items()):
        print(f"  {name:<10} min={p['min']:<3} peak={p['peak']:<3} max={p['max']}")

    if args.expect_scale_out:
        p = peaks.get(args.expect_scale_out)
        if not p or p["peak"] <= p["min"]:
            print(f"FAIL: {args.expect_scale_out} never scaled above minReplicas", file=sys.stderr)
            return 1
        print(f"OK: {args.expect_scale_out} scaled out from {p['min']} to {p['peak']} replicas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
