"""Summarize Locust FLOW rows and enforce steady/recovery SLOs."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
from pathlib import Path


FLOW_NAME = re.compile(r"^agent_chat_e2e \[(?P<stage>[^]]+)]$")


def _number(row: dict[str, str], *names: str) -> float:
    for name in names:
        raw = row.get(name, "").strip()
        if raw:
            return float(raw)
    return 0.0


def read_flow_stats(path: Path) -> list[dict[str, float | int | str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    result: list[dict[str, float | int | str]] = []
    for row in rows:
        match = FLOW_NAME.match(row.get("Name", ""))
        if row.get("Type") != "FLOW" or not match:
            continue
        requests = int(_number(row, "Request Count"))
        failures = int(_number(row, "Failure Count"))
        result.append(
            {
                "stage": match.group("stage"),
                "requests": requests,
                "failures": failures,
                "error_percent": round((failures / requests) * 100, 2) if requests else 0.0,
                "rps": round(_number(row, "Requests/s"), 3),
                "p50_ms": round(_number(row, "50%", "Median Response Time")),
                "p95_ms": round(_number(row, "95%")),
                "p99_ms": round(_number(row, "99%")),
            }
        )
    if not result:
        raise ValueError(f"No FLOW agent_chat_e2e rows found in {path}")
    return result


def evaluate(
    rows: list[dict[str, float | int | str]],
    *,
    asserted_stages: set[str],
    max_error_percent: float,
    max_p95_ms: float,
    max_p99_ms: float,
) -> list[str]:
    failures: list[str] = []
    present_stages: set[str] = set()
    for row in rows:
        stage = str(row["stage"])
        if stage not in asserted_stages:
            continue
        present_stages.add(stage)
        if int(row.get("requests", 0)) <= 0:
            failures.append(f"{stage}: no completed FLOW samples")
            continue
        if float(row["error_percent"]) > max_error_percent:
            failures.append(
                f"{stage}: error {row['error_percent']}% > {max_error_percent}%"
            )
        if float(row["p95_ms"]) > max_p95_ms:
            failures.append(f"{stage}: p95 {row['p95_ms']}ms > {max_p95_ms}ms")
        if float(row["p99_ms"]) > max_p99_ms:
            failures.append(f"{stage}: p99 {row['p99_ms']}ms > {max_p99_ms}ms")
    for missing_stage in sorted(asserted_stages - present_stages):
        failures.append(f"{missing_stage}: no FLOW statistics row")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("stats_csv", type=Path, help="Locust *_stats.csv file")
    parser.add_argument("--json", type=Path, dest="json_path")
    args = parser.parse_args()

    rows = read_flow_stats(args.stats_csv)
    asserted_stages = {
        item.strip()
        for item in os.getenv("LOAD_TEST_ASSERT_STAGES", "steady,recovery").split(",")
        if item.strip()
    }
    max_error = float(os.getenv("LOAD_TEST_MAX_ERROR_PERCENT", "5"))
    max_p95 = float(os.getenv("LOAD_TEST_MAX_P95_MS", "30000"))
    max_p99 = float(os.getenv("LOAD_TEST_MAX_P99_MS", "60000"))
    violations = evaluate(
        rows,
        asserted_stages=asserted_stages,
        max_error_percent=max_error,
        max_p95_ms=max_p95,
        max_p99_ms=max_p99,
    )

    print("stage       flows  errors    RPS      p50      p95      p99")
    for row in rows:
        print(
            f"{str(row['stage']):<11} {int(row['requests']):>5} "
            f"{float(row['error_percent']):>6.2f}% {float(row['rps']):>6.3f} "
            f"{int(row['p50_ms']):>8} {int(row['p95_ms']):>8} {int(row['p99_ms']):>8}"
        )
    if args.json_path:
        args.json_path.write_text(
            json.dumps({"stages": rows, "violations": violations}, indent=2),
            encoding="utf-8",
        )
    if violations:
        print("SLO violations:")
        for violation in violations:
            print(f"- {violation}")
        return 1
    print("Steady/recovery SLOs passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
