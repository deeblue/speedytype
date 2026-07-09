from __future__ import annotations

import argparse
import csv
from pathlib import Path
import statistics


BUCKETS = [
    ("0-10s", 0.0, 10.0),
    ("10-20s", 10.0, 20.0),
    ("20-30s", 20.0, 30.0),
]


def bucket_name(recording_seconds: float) -> str | None:
    for name, lower, upper in BUCKETS:
        if lower <= recording_seconds < upper:
            return name
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default="phase2_selected_latency.csv")
    parser.add_argument("--run-label", default="phase2_full_benchmark")
    args = parser.parse_args()

    rows = []
    with Path(args.csv).open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("run_label") != args.run_label:
                continue
            rows.append(row)

    print(f"ANALYZE_DURATION source={args.csv} run_label={args.run_label} rows={len(rows)}")
    grouped: dict[str, list[dict[str, str]]] = {name: [] for name, _, _ in BUCKETS}
    for row in rows:
        name = bucket_name(float(row["recording_seconds"]))
        if name:
            grouped[name].append(row)

    for name, _, _ in BUCKETS:
        group = grouped[name]
        print(f"{name}: samples={len(group)}")
        if not group:
            continue
        whispers = [float(row["whisper_seconds"]) for row in group]
        totals = [float(row["total_tail_latency_seconds"]) for row in group]
        print(
            f"  whisper avg={statistics.mean(whispers):.6f} min={min(whispers):.6f} max={max(whispers):.6f}"
        )
        print(
            f"  total_tail avg={statistics.mean(totals):.6f} min={min(totals):.6f} max={max(totals):.6f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
