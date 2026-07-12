from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.run_long_recording_benchmark import named_quality_payload
from speedytype.transcript_quality import passes_polished_regression_gate


def reanalyze(rows: list[dict], manifest: dict, audio_dir: Path) -> list[dict]:
    cases = {case["name"]: case for case in manifest["cases"]}
    batch_by_run = {
        (row["case"], row["run"]): row["text"]
        for row in rows
        if row.get("mode") == "batch" and "text" in row
    }
    # Fix 1: polished-text regression is now measured against the SAME run's
    # batch-mode polished_text, not the raw source script (see the comment in
    # run_long_recording_benchmark.py for why the source-script comparison had
    # no discriminating power). Recomputed here from the already-recorded
    # polished_text field, with no new API calls.
    batch_polished_by_run = {
        (row["case"], row["run"]): row.get("polished_text", "")
        for row in rows
        if row.get("mode") == "batch"
    }
    output = []
    for original in rows:
        row = dict(original)
        case = cases[row["case"]]
        candidate = row.get("hybrid_text", row.get("text", ""))
        candidate_polished = row.get("polished_text", "")
        key_terms = ["BIOS", "Firmware", "NPI", "QA", "API", "TPE 團隊", "BJ 團隊", "USB", "Thunderbolt"]
        if case.get("reference_text_file"):
            source = (audio_dir / case["reference_text_file"]).read_text(encoding="utf-8")
            row.update(named_quality_payload("source", source, candidate, key_terms))
        batch = batch_by_run[(row["case"], row["run"])]
        row.update(named_quality_payload("hybrid_regression", batch, candidate, key_terms))
        batch_polished = batch_polished_by_run[(row["case"], row["run"])]
        row.update(
            named_quality_payload(
                "hybrid_regression_polished",
                batch_polished,
                candidate_polished,
                key_terms,
                gate_fn=passes_polished_regression_gate,
            )
        )
        for old_key in ("quality", "quality_gate_ok", "quality_gate_reasons", "case_resolution_polished"):
            row.pop(old_key, None)
        output.append(row)
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("--manifest", default="test_audio_long/manifest.json")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    rows = [json.loads(line) for line in Path(args.input).read_text(encoding="utf-8").splitlines()]
    manifest_path = Path(args.manifest)
    analyzed = reanalyze(rows, json.loads(manifest_path.read_text(encoding="utf-8")), manifest_path.parent)
    Path(args.output).write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in analyzed) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
