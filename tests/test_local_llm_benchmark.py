from __future__ import annotations

import json
import io
import sys
import pytest

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
    assert stops == ["gemma4:12b", "gemma4:26b", "gemma4:12b", "gemma4:26b"]
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


def test_summarize_only_reports_complete_file_without_loading_config_or_calling_models(
    tmp_path, monkeypatch, capsys
):
    output = tmp_path / "complete.jsonl"
    records = []
    for identity in sorted(benchmark.expected_identities(3)):
        provider, model, case, mode, repetition = identity
        records.append(
            {
                "provider": provider,
                "model": model,
                "case": case,
                "mode": mode,
                "repetition": repetition,
                "ok": True,
            }
        )
    output.write_text(
        "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
    )
    monkeypatch.setattr(
        benchmark, "load_config", lambda *args: (_ for _ in ()).throw(AssertionError("API path called"))
    )
    monkeypatch.setattr(
        benchmark, "run_benchmark", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("model path called"))
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_local_llm_benchmark.py",
            "--output",
            str(output),
            "--repetitions",
            "3",
            "--summarize-only",
        ],
    )

    assert benchmark.main() == 0
    assert capsys.readouterr().out.splitlines() == [
        "records=38 expected=38 unique=38",
        "parse_errors=0 duplicates=0 missing=0 unexpected=0",
        "complete=true",
    ]


def test_summarize_only_fails_for_parse_duplicate_missing_and_unexpected_identities(
    tmp_path, capsys
):
    output = tmp_path / "broken.jsonl"
    expected = sorted(benchmark.expected_identities(1))
    first = expected[0]
    record = dict(zip(("provider", "model", "case", "mode", "repetition"), first))
    unexpected = {**record, "case": "not_a_case"}
    output.write_text(
        json.dumps(record) + "\n" + json.dumps(record) + "\n" + "not-json\n" + json.dumps(unexpected) + "\n",
        encoding="utf-8",
    )

    assert benchmark.summarize_results(output, repetitions=1) == 1
    assert capsys.readouterr().out.splitlines() == [
        "records=3 expected=14 unique=2",
        "parse_errors=1 duplicates=1 missing=13 unexpected=1",
        "complete=false",
    ]


def test_benchmark_console_is_cp1252_safe_while_jsonl_remains_utf8(
    tmp_path, monkeypatch
):
    output = tmp_path / "unicode.jsonl"
    record = {
        "provider": "gemini",
        "model": "gemini-3.1-flash-lite",
        "case": "short",
        "mode": "warm",
        "repetition": 1,
        "ok": True,
        "output": "下週三請同步測試。",
    }
    monkeypatch.setattr(benchmark, "CANDIDATES", (benchmark.CANDIDATES[0],))
    monkeypatch.setattr(benchmark, "CASES", (benchmark.CASES[0],))
    monkeypatch.setattr(benchmark, "run_candidate", lambda *args, **kwargs: record)
    raw_stdout = io.BytesIO()
    cp1252_stdout = io.TextIOWrapper(raw_stdout, encoding="cp1252", errors="strict")
    monkeypatch.setattr(sys, "stdout", cp1252_stdout)

    benchmark.run_benchmark(object(), output, repetitions=1)
    cp1252_stdout.flush()

    console = raw_stdout.getvalue().decode("cp1252")
    assert "下週三" not in console
    assert "\\u4e0b\\u9031\\u4e09" in console
    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert persisted["output"] == "下週三請同步測試。"


def test_local_cold_trial_stops_all_candidates_before_running(tmp_path, monkeypatch):
    output = tmp_path / "isolated.jsonl"
    events = []
    monkeypatch.setattr(benchmark, "CASES", (benchmark.CASES[0],))
    monkeypatch.setattr(benchmark, "stop_ollama_model", lambda model: events.append(("stop", model)))

    def fake_run(config, candidate, case, mode, repetition):
        events.append(("run", candidate["model"], mode))
        return {"provider": candidate["provider"], "model": candidate["model"], "case": case.name,
                "mode": mode, "repetition": repetition, "ok": True}

    monkeypatch.setattr(benchmark, "run_candidate", fake_run)
    benchmark.run_benchmark(object(), output, repetitions=1)
    for model in ("gemma4:12b", "gemma4:26b"):
        cold = events.index(("run", model, "cold"))
        assert events[cold - 2:cold] == [("stop", "gemma4:12b"), ("stop", "gemma4:26b")]


def test_resume_repairs_only_malformed_trailing_fragment(tmp_path):
    output = tmp_path / "partial.jsonl"
    first = {"provider": "gemini", "model": "m", "case": "short", "mode": "warm", "repetition": 1}
    second = {**first, "repetition": 2}
    output.write_bytes((json.dumps(first) + "\n" + json.dumps(second) + "\n{\"provider\":").encode())
    assert len(benchmark._completed_identities(output)) == 2
    assert output.read_text(encoding="utf-8") == json.dumps(first) + "\n" + json.dumps(second) + "\n"


def test_resume_terminates_valid_final_record_before_append(tmp_path, monkeypatch):
    output = tmp_path / "unterminated.jsonl"
    completed = {
        "provider": "gemini", "model": "gemini-3.1-flash-lite", "case": "short",
        "mode": "warm", "repetition": 1, "ok": True,
    }
    output.write_text(json.dumps(completed), encoding="utf-8")
    monkeypatch.setattr(benchmark, "CANDIDATES", (benchmark.CANDIDATES[0],))
    monkeypatch.setattr(benchmark, "CASES", (benchmark.CASES[0], benchmark.CASES[1]))
    calls = []

    def fake_run(config, candidate, case, mode, repetition):
        calls.append((case.name, repetition))
        return {
            "provider": candidate["provider"], "model": candidate["model"],
            "case": case.name, "mode": mode, "repetition": repetition, "ok": True,
        }

    monkeypatch.setattr(benchmark, "run_candidate", fake_run)
    benchmark.run_benchmark(object(), output, repetitions=1)

    assert ("short", 1) not in calls
    records = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert records[0] == completed
    assert records[1]["case"] == "medium"
    assert output.read_bytes().count(b"\n") == 2


def test_resume_does_not_rewrite_well_formed_file(tmp_path, monkeypatch):
    output = tmp_path / "complete.jsonl"
    record = {"provider": "gemini", "model": "m", "case": "short", "mode": "warm", "repetition": 1}
    original = (json.dumps(record) + "\n").encode()
    output.write_bytes(original)
    writes = []
    original_write_text = type(output).write_text
    monkeypatch.setattr(type(output), "write_text", lambda self, *args, **kwargs: writes.append(self) or original_write_text(self, *args, **kwargs))

    benchmark._completed_identities(output)

    assert writes == []
    assert output.read_bytes() == original


def test_resume_rejects_malformed_non_final_record(tmp_path):
    output = tmp_path / "corrupt.jsonl"
    output.write_text('{"provider":\n{"provider":"gemini"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="non-final"):
        benchmark._completed_identities(output)


def test_rerun_recreates_output_instead_of_appending(tmp_path, monkeypatch):
    output = tmp_path / "rerun.jsonl"
    output.write_text('{"old":true}\n', encoding="utf-8")
    monkeypatch.setattr(benchmark, "CANDIDATES", (benchmark.CANDIDATES[0],))
    monkeypatch.setattr(benchmark, "CASES", (benchmark.CASES[0],))
    monkeypatch.setattr(benchmark, "run_candidate", lambda *args: {
        "provider": "gemini", "model": "gemini-3.1-flash-lite", "case": "short",
        "mode": "warm", "repetition": 1, "ok": True})
    benchmark.run_benchmark(object(), output, rerun=True, repetitions=1)
    records = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 1 and "old" not in records[0]


def test_ollama_snapshot_rejects_other_resident_candidate(monkeypatch):
    monkeypatch.setattr(benchmark, "call_ollama_polisher", lambda *args, **kwargs: make_result())
    monkeypatch.setattr(benchmark, "ollama_ps", lambda: "NAME ID\ngemma4:12b abc\ngemma4:26b def")
    record = benchmark.run_candidate(object(), benchmark.CANDIDATES[1], benchmark.CASES[0], "cold", 1)
    assert record["ok"] is False
    assert "unexpected resident candidate" in record["error"]
