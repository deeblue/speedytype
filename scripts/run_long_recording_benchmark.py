from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import soundfile as sf

from speedytype.api import transcribe_audio, transcribe_audio_verbose
from speedytype.chunking import ChunkingConfig, detect_silence_regions, plan_dynamic_chunks
from speedytype.config import load_config
from speedytype.hybrid_validation import HybridChunkResult, validate_hybrid_result
from speedytype.llm import call_llm_polisher
from speedytype.quasi_streaming import build_chunk_plan, merge_text_with_overlap, slice_wav, tail_prompt
from speedytype.segment_merge import TimedSegment, merge_timed_segments
from speedytype.transcript_quality import (
    TranscriptQuality,
    normalize_transcript,
    passes_polished_regression_gate,
    passes_quality_gate,
)


def quality_payload(reference: str, candidate: str, key_terms: list[str], gate_fn=passes_quality_gate) -> dict:
    metrics = TranscriptQuality.compare(reference, candidate, key_terms)
    ok, reasons = gate_fn(metrics)
    return {"quality": asdict(metrics), "quality_gate_ok": ok, "quality_gate_reasons": reasons}


def named_quality_payload(prefix: str, reference: str, candidate: str, key_terms: list[str], gate_fn=passes_quality_gate) -> dict:
    payload = quality_payload(reference, candidate, key_terms, gate_fn)
    return {
        f"{prefix}_quality": payload["quality"],
        f"{prefix}_gate_ok": payload["quality_gate_ok"],
        f"{prefix}_gate_reasons": payload["quality_gate_reasons"],
    }


def run_batch(path: Path, config) -> dict:
    started = time.perf_counter()
    text = transcribe_audio(path, config)
    wall = time.perf_counter() - started
    llm_started = time.perf_counter()
    polished = call_llm_polisher(text, config).text
    llm_seconds = time.perf_counter() - llm_started
    return {
        "mode": "batch",
        "stt_tail_seconds": wall,
        "complete_tail_seconds": wall + llm_seconds,
        "llm_seconds": llm_seconds,
        "total_request_seconds": wall,
        "request_count": 1,
        "text": text,
        "polished_text": polished,
    }


def run_quasi(path: Path, config, chunk_seconds: float, overlap_seconds: float) -> dict:
    duration = sf.info(path).duration
    committed = ""
    worker_free_at = 0.0
    total_request = 0.0
    plans = build_chunk_plan(duration, chunk_seconds, overlap_seconds)
    for plan in plans:
        chunk = slice_wav(path, plan.start_seconds, plan.end_seconds)
        try:
            started = time.perf_counter()
            payload = transcribe_audio_verbose(chunk, config, prompt_override=tail_prompt(config, committed))
            request = time.perf_counter() - started
        finally:
            chunk.unlink(missing_ok=True)
        total_request += request
        for segment in payload.get("segments", []) or []:
            midpoint = plan.start_seconds + (float(segment.get("start", 0)) + float(segment.get("end", 0))) / 2
            if midpoint <= plan.commit_until_seconds + 1e-6:
                committed = merge_text_with_overlap(committed, str(segment.get("text", "")))
        worker_started = max(plan.end_seconds, worker_free_at)
        worker_free_at = worker_started + request
    return {
        "mode": "quasi_streaming",
        "stt_tail_seconds": max(0.0, worker_free_at - duration),
        "total_request_seconds": total_request,
        "request_count": len(plans),
        "text": committed.strip(),
    }


def run_hybrid_v2(path: Path, config, chunk_config: ChunkingConfig) -> dict:
    samples, sample_rate = sf.read(path, dtype="float32", always_2d=True)
    duration = len(samples) / sample_rate
    silences = detect_silence_regions(samples, sample_rate, chunk_config)
    plans = plan_dynamic_chunks(duration, silences, chunk_config)
    worker_free_at = 0.0
    total_request = 0.0
    timed_chunks = []
    validation_chunks = []
    committed_prompt = ""
    for plan in plans:
        chunk = slice_wav(path, plan.start_seconds, plan.end_seconds)
        try:
            started = time.perf_counter()
            payload = transcribe_audio_verbose(chunk, config, prompt_override=tail_prompt(config, committed_prompt))
            request = time.perf_counter() - started
            error = ""
        except Exception as exc:
            payload = {"text": "", "segments": []}
            request = time.perf_counter() - started
            error = f"{type(exc).__name__}: {exc}"
        finally:
            chunk.unlink(missing_ok=True)
        total_request += request
        worker_started = max(plan.end_seconds, worker_free_at)
        worker_free_at = worker_started + request
        timed = [
            TimedSegment(
                plan.start_seconds + float(segment.get("start", 0)),
                plan.start_seconds + float(segment.get("end", 0)),
                str(segment.get("text", "")).strip(),
                plan.index,
            )
            for segment in payload.get("segments", []) or []
        ]
        timed_chunks.append(timed)
        committed_prompt = f"{committed_prompt} {str(payload.get('text', '')).strip()}"[-200:].strip()
        validation_chunks.append(
            HybridChunkResult(plan.index, plan.start_seconds, plan.end_seconds, str(payload.get("text", "")).strip(), error)
        )
    merge = merge_timed_segments(timed_chunks, duration)
    activity = []
    cursor = 0.0
    for silence in silences:
        if silence.start_seconds > cursor:
            activity.append((cursor, silence.start_seconds))
        cursor = max(cursor, silence.end_seconds)
    if cursor < duration:
        activity.append((cursor, duration))
    validation = validate_hybrid_result(plans, merge, validation_chunks, activity)
    fallback_seconds = 0.0
    final_text = merge.text
    if not validation.ok:
        fallback_started = time.perf_counter()
        final_text = transcribe_audio(path, config)
        fallback_seconds = time.perf_counter() - fallback_started
    llm_started = time.perf_counter()
    polished = call_llm_polisher(final_text, config).text
    llm_seconds = time.perf_counter() - llm_started
    tail = max(0.0, worker_free_at - duration) + fallback_seconds + llm_seconds
    return {
        "mode": "hybrid_v2",
        "stt_tail_seconds": max(0.0, worker_free_at - duration),
        "complete_tail_seconds": tail,
        "total_request_seconds": total_request,
        "request_count": len(plans),
        "fallback_used": not validation.ok,
        "fallback_seconds": fallback_seconds,
        "validation_reasons": list(validation.reasons),
        "hybrid_text": merge.text,
        "text": final_text,
        "polished_text": polished,
        "chunks": [
            {"index": plan.index, "start": plan.start_seconds, "end": plan.end_seconds, "reason": plan.cut_reason}
            for plan in plans
        ],
        "merge_decisions": [
            {
                "action": decision.action,
                "reason": decision.reason,
                "chunk_index": decision.segment.chunk_index,
                "start": decision.segment.start_seconds,
                "end": decision.segment.end_seconds,
                "text": decision.segment.text,
            }
            for decision in merge.decisions
        ],
    }


CASE_FIXTURES = {
    "A": "列車準時出發",
    "B": "我在海邊停留約四十分鐘",
    "C": "傍晚我回到車站附近的咖啡館整理筆記",
    "D": "海邊步道依照距離重新排序",
}


def case_resolution(text: str) -> dict[str, bool]:
    normalized = normalize_transcript(text)
    return {name: normalize_transcript(phrase) in normalized for name, phrase in CASE_FIXTURES.items()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", default=".env")
    parser.add_argument("--manifest", default="test_audio_long/manifest.json")
    parser.add_argument("--output", default="long_recording_results.jsonl")
    parser.add_argument("--chunk-seconds", type=float, default=30.0)
    parser.add_argument("--overlap-seconds", type=float, default=5.0)
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--hybrid-v2", action="store_true")
    parser.add_argument("--case", default="", help="Run only one manifest case name")
    args = parser.parse_args()
    config = load_config(args.env)
    manifest_path = Path(args.manifest)
    records = []
    for case in json.loads(manifest_path.read_text(encoding="utf-8"))["cases"]:
        if args.case and case["name"] != args.case:
            continue
        path = manifest_path.parent / case["file"]
        for run_index in range(args.runs):
            source_reference = (
                (manifest_path.parent / case["reference_text_file"]).read_text(encoding="utf-8")
                if case.get("reference_text_file") else ""
            )
            batch_reference = ""
            batch_polished_reference = ""
            key_terms = [term.strip() for term in config.whisper_vocab_bias.split(",") if term.strip()]
            runners = (
                lambda: run_batch(path, config),
                (lambda: run_hybrid_v2(path, config, ChunkingConfig())) if args.hybrid_v2 else
                (lambda: run_quasi(path, config, args.chunk_seconds, args.overlap_seconds)),
            )
            for runner in runners:
                try:
                    record = {"case": case["name"], "run": run_index + 1, "duration_seconds": case["duration_seconds"], **runner()}
                    if record["mode"] == "batch":
                        batch_reference = record["text"]
                        batch_polished_reference = record.get("polished_text", "")
                    quality_candidate = record.get("hybrid_text", record["text"])
                    quality_candidate_polished = record.get("polished_text", "")
                    if source_reference:
                        record.update(named_quality_payload("source", source_reference, quality_candidate, key_terms))
                    regression_reference = batch_reference or quality_candidate
                    record.update(
                        named_quality_payload("hybrid_regression", regression_reference, quality_candidate, key_terms)
                    )
                    # Polished-text regression: compare this run's polished output against
                    # the SAME run's batch-mode polished output, not against the raw source
                    # script. A literal-phrase check against the source script was found to
                    # have no discriminating power here — Gemini restructures long narratives
                    # into bullet-point summaries regardless of mode, so even a from-scratch
                    # batch run's polished output never contains the literal Case A-D source
                    # sentences either (see KNOWN_LIMITATIONS.md item 19). Comparing against
                    # same-run batch-polished mirrors hybrid_regression_quality's design and
                    # is tolerant of paraphrasing while still catching genuine content loss.
                    regression_polished_reference = batch_polished_reference or quality_candidate_polished
                    record.update(
                        named_quality_payload(
                            "hybrid_regression_polished",
                            regression_polished_reference,
                            quality_candidate_polished,
                            key_terms,
                            gate_fn=passes_polished_regression_gate,
                        )
                    )
                    if case["name"] == "continuous_tts_295s":
                        record["case_resolution_raw"] = case_resolution(quality_candidate)
                except Exception as exc:
                    record = {"case": case["name"], "run": run_index + 1, "duration_seconds": case["duration_seconds"], "error": f"{type(exc).__name__}: {exc}"}
                print(json.dumps(record, ensure_ascii=False), flush=True)
                records.append(record)
    Path(args.output).write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
