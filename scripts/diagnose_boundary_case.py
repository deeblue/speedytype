from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from speedytype.config import load_config
from speedytype.console import safe_print
from speedytype.quasi_streaming import simulate_quasi_streaming_transcription, run_baseline_transcription


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", default=".env")
    parser.add_argument("--audio", default="phase3_boundary_audio/boundary_case_16k.wav")
    parser.add_argument("--chunk-seconds", type=float, default=3.0)
    parser.add_argument("--overlap-seconds", type=float, default=0.75)
    parser.add_argument("--output", default="phase4_boundary_diagnostic.json")
    args = parser.parse_args()

    config = load_config(args.env)
    audio_path = Path(args.audio)
    if not audio_path.exists():
        raise FileNotFoundError(audio_path)

    raw, baseline_stt_seconds, baseline_llm_seconds, baseline_llm = run_baseline_transcription(audio_path, config)
    streaming = simulate_quasi_streaming_transcription(
        audio_path,
        config,
        chunk_seconds=args.chunk_seconds,
        overlap_seconds=args.overlap_seconds,
    )

    payload = {
        "audio_path": str(audio_path),
        "baseline": {
            "stt_seconds": baseline_stt_seconds,
            "llm_seconds": baseline_llm_seconds,
            "raw": raw,
            "polished": baseline_llm.text,
        },
        "quasi_streaming": {
            "stt_tail_seconds": streaming.stt_tail_seconds,
            "total_whisper_request_seconds": streaming.total_whisper_request_seconds,
            "merged": streaming.merged_transcript,
            "polished": streaming.llm_result.text,
            "chunks": [
                {
                    "index": chunk.plan.index,
                    "audio_start_seconds": chunk.plan.start_seconds,
                    "audio_end_seconds": chunk.plan.end_seconds,
                    "audio_duration_seconds": chunk.plan.end_seconds - chunk.plan.start_seconds,
                    "commit_until_seconds": chunk.plan.commit_until_seconds,
                    "simulated_send_time_seconds": chunk.started_at_seconds,
                    "whisper_response_seconds": chunk.request_seconds,
                    "simulated_finish_time_seconds": chunk.finished_at_seconds,
                    "text": chunk.text,
                }
                for chunk in streaming.chunk_results
            ],
        },
    }
    Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    safe_print(f"WROTE {args.output}")
    safe_print(f"baseline_stt_seconds={baseline_stt_seconds:.6f}")
    safe_print(f"quasi_stt_tail_seconds={streaming.stt_tail_seconds:.6f}")
    for chunk in payload["quasi_streaming"]["chunks"]:
        safe_print(
            f"chunk={chunk['index']} audio={chunk['audio_duration_seconds']:.3f}s "
            f"send_at={chunk['simulated_send_time_seconds']:.6f} "
            f"response={chunk['whisper_response_seconds']:.6f} "
            f"finish_at={chunk['simulated_finish_time_seconds']:.6f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
