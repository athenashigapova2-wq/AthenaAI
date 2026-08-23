"""Run every selected longitudinal fixture offline and optionally write reports."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from simulation.longitudinal import run_offline_suite, write_reports  # noqa: E402
from simulation.scenarios import load_scenarios  # noqa: E402


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--report-dir",
        type=Path,
        help="Write JSON and Markdown reports to this directory.",
    )
    args = parser.parse_args()

    report = run_offline_suite(load_scenarios())
    if args.report_dir:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        json_path, markdown_path = write_reports(
            report,
            args.report_dir,
            f"longitudinal-offline-{timestamp}",
        )
        report["report_files"] = [str(json_path), str(markdown_path)]
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
