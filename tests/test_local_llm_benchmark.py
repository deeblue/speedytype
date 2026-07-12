from __future__ import annotations

import json

from speedytype.llm import LlmResult, LlmUsage

from scripts import run_local_llm_benchmark as benchmark


def make_result(*, provider="ollama", model="gemma4:12b", output="cleaned"):
    raw = {
        "load_duration": 2_000_000_000,
        "prompt_eval_duration": 500_000_000,
        "eval_duration": 250_000_000,
        "prompt_eval_count": 12,
        "eval_count": 5,
    }
    return LlmResult(
        text=output,
        provider=provider,
        model=model,
        llm_call_seconds=3.25,
        retry_wait_seconds=0.0,
        retry_count=0,
        usage=LlmUsage(input_tokens=12, output_tokens=5, total_tokens=17, raw=raw),
        raw_response=raw,
    )


def test_cases_reuse_phase2_inputs_and_add_number_regression():
    assert [(case.name, case.category, case.text) for case in benchmark.CASES] == [
        (
            "short",
            "phase2",
            "呃,我們下週一,啊不對,下週三要開會,請 TPE 團隊同步 BIOS 狀態。",
        ),
        (
            "medium",
            "phase2",
            "那個,我今天想先確認三件事 第一,Firmware 的 NPI 進度要更新 第二,QA 要在週五前回報 第三,我們下週一,不對,下週三要跟 BJ 團隊開會",
        ),
        (
            "long",
            "phase2",
            "這段是SpeedyType的長距測試 我們原本打算下週一發BIOS測試版 不對,應該是下週三發Firmware測試版 請TPE團隊先確認USB和Thunderbolt的相容性 然後QA在NPI會議前整理API測試結果 最後,BJ團隊協助確認使用者回饋",
        ),
        (
            "numbers_repeated_english",
            "number_regression",
            "123測試測試 123測試測試 123 test 123 test",
        ),
    ]


def test_candidates_are_fixed_and_serially_ordered():
    assert benchmark.CANDIDATES == (
        {"provider": "gemini", "model": "gemini-3.1-flash-lite", "thinking": "minimal"},
        {"provider": "ollama", "model": "gemma4:12b"},
        {"provider": "ollama", "model": "gemma4:26b"},
    )


def test_quality_flags_preserve_phase2_rules_and_number_regression():
    short = benchmark.CASES[0]
    assert benchmark.quality_flags(short, "下週三請 TPE 團隊同步 BIOS 狀態。") == {
        "filler_ok": True,
        "correction_ok": True,
        "terms_ok": True,
        "bullets_ok": True,
        "extra_ok": True,
        "overall_ok": True,
    }
    assert not benchmark.quality_flags(short, "以下是修飾後：下週一 TPE 團隊 BIOS")['overall_ok']

    numbers = benchmark.CASES[-1]
    assert benchmark.quality_flags(numbers, "123 test")["overall_ok"]
    assert benchmark.quality_flags(numbers, "123 測試")["overall_ok"]
    assert not benchmark.quality_flags(numbers, "測試。")['overall_ok']
    assert not benchmark.quality_flags(numbers, "以下是清理結果：123 test")['overall_ok']


def test_number_quality_rejects_unrecognized_explanatory_wrapper():
    numbers = benchmark.CASES[-1]

    flags = benchmark.quality_flags(
        numbers, "I changed the transcript for you: 123 test"
    )

    assert flags["extra_ok"] is False
    assert flags["overall_ok"] is False


def test_run_candidate_converts_native_durations_and_calculates_throughput(monkeypatch):
    monkeypatch.setattr(benchmark, "call_ollama_polisher", lambda *args, **kwargs: make_result())
    monkeypatch.setattr(benchmark, "ollama_ps", lambda: "NAME ID SIZE PROCESSOR")

    record = benchmark.run_candidate(
        object(), benchmark.CANDIDATES[1], benchmark.CASES[0], "warm", 2
    )

    assert record["identity"] == ["ollama", "gemma4:12b", "short", "warm", 2]
    assert record["ok"] is True
    assert record["load_duration"] == 2_000_000_000
    assert record["prompt_eval_duration"] == 500_000_000
    assert record["eval_duration"] == 250_000_000
    assert record["load_seconds"] == 2.0
    assert record["prompt_eval_seconds"] == 0.5
    assert record["eval_seconds"] == 0.25
    assert record["prompt_tokens"] == 12
    assert record["output_tokens"] == 5
    assert record["output_tokens_per_second"] == 20.0
    assert record["ollama_ps"] == "NAME ID SIZE PROCESSOR"


def test_run_candidate_retains_failures_without_semantic_quality(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("service unavailable")

    monkeypatch.setattr(benchmark, "call_gemini_polisher", fail)
    record = benchmark.run_candidate(
        object(), benchmark.CANDIDATES[0], benchmark.CASES[0], "warm", 1
    )

    assert record["ok"] is False
    assert record["error"] == "service unavailable"
    assert "quality" not in record


def test_ollama_ps_failure_does_not_discard_successful_model_result(monkeypatch):
    monkeypatch.setattr(
        benchmark,
        "call_ollama_polisher",
        lambda *args, **kwargs: make_result(output="下週三請 TPE 團隊同步 BIOS 狀態。"),
    )

    def fail_ps():
        raise RuntimeError("ollama executable not found")

    monkeypatch.setattr(benchmark, "ollama_ps", fail_ps)

    record = benchmark.run_candidate(
        object(), benchmark.CANDIDATES[1], benchmark.CASES[0], "warm", 1
    )

    assert record["ok"] is True
    assert record["output"] == "下週三請 TPE 團隊同步 BIOS 狀態。"
    assert record["quality"]["overall_ok"] is True
    assert record["llm_call_seconds"] == 3.25
    assert record["ollama_ps_error"] == "ollama ps failed: ollama executable not found"


def test_resume_identity_skips_completed_work_and_appends_incrementally(tmp_path, monkeypatch):
    output = tmp_path / "results.jsonl"
    completed = {
        "provider": "gemini",
        "model": "gemini-3.1-flash-lite",
        "case": "short",
        "mode": "warm",
        "repetition": 1,
        "ok": False,
    }
    output.write_text(json.dumps(completed) + "\n", encoding="utf-8")
    calls = []

    def fake_run(config, candidate, case, mode, repetition):
        calls.append((candidate["provider"], candidate["model"], case.name, mode, repetition))
        return {
            "provider": candidate["provider"],
            "model": candidate["model"],
            "case": case.name,
            "mode": mode,
            "repetition": repetition,
            "ok": True,
        }

    stops = []
    monkeypatch.setattr(benchmark, "run_candidate", fake_run)
    monkeypatch.setattr(benchmark, "stop_ollama_model", stops.append)

    benchmark.run_benchmark(object(), output)

    assert ("gemini", "gemini-3.1-flash-lite", "short", "warm", 1) not in calls
    assert stops == ["gemma4:12b", "gemma4:26b"]
    assert calls.index(("ollama", "gemma4:12b", "short", "cold", 1)) < calls.index(
        ("ollama", "gemma4:12b", "short", "warm", 1)
    )
    records = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert records[0] == completed
    assert len(records) == 1 + len(calls)


def test_main_accepts_repetition_count(tmp_path, monkeypatch):
    observed = []
    monkeypatch.setattr(benchmark, "load_config", lambda path: object())
    monkeypatch.setattr(
        benchmark,
        "run_benchmark",
        lambda config, output, rerun=False, repetitions=3: observed.append(
            (output, rerun, repetitions)
        ),
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_local_llm_benchmark.py",
            "--output",
            str(tmp_path / "out.jsonl"),
            "--repetitions",
            "2",
        ],
    )

    assert benchmark.main() == 0
    assert observed == [(tmp_path / "out.jsonl", False, 2)]
