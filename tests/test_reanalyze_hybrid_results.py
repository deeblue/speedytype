from pathlib import Path

from scripts.reanalyze_hybrid_results import reanalyze


MANIFEST = {"cases": [{"name": "real_126s", "file": "real_126s.wav", "duration_seconds": 126.412}]}


def _row(mode: str, run: int, text: str, polished_text: str) -> dict:
    row = {
        "case": "real_126s",
        "run": run,
        "duration_seconds": 126.412,
        "mode": mode,
        "text": text,
        "polished_text": polished_text,
    }
    if mode != "batch":
        row["hybrid_text"] = text
    return row


def test_batch_self_compare_shows_no_regression():
    """Fix 1 requirement: batch compared against itself must show as
    consistent/no new gaps, since there is no actual difference."""
    rows = [_row("batch", 1, "raw content", "batch modeの polished output about the meeting")]

    analyzed = reanalyze(rows, MANIFEST, Path("."))

    batch_row = analyzed[0]
    assert batch_row["hybrid_regression_polished_gate_ok"] is True
    assert batch_row["hybrid_regression_polished_gate_reasons"] == []
    assert "case_resolution_polished" not in batch_row


def test_hybrid_missing_content_present_in_batch_is_detected():
    """Fix 1 requirement: construct a case where hybrid-polished omits
    content that batch-polished (same run) retained; the new metric must
    catch this as a real regression."""
    batch_polished = "本次會議的結論如下。關於TPE團隊這邊負責的部分，以及BJ團隊這邊負責的部分，我也希望各位能夠提供更solid的結果。"
    hybrid_polished_missing_bj = "本次會議的結論如下。關於TPE團隊這邊負責的部分，我也希望各位能夠提供更solid的結果。"
    rows = [
        _row("batch", 1, "raw batch text", batch_polished),
        _row("hybrid_v2", 1, "raw hybrid text", hybrid_polished_missing_bj),
    ]

    analyzed = reanalyze(rows, MANIFEST, Path("."))

    hybrid_row = next(r for r in analyzed if r["mode"] == "hybrid_v2")
    assert hybrid_row["hybrid_regression_polished_gate_ok"] is False
    assert any("BJ 團隊" in reason or "key-term" in reason for reason in hybrid_row["hybrid_regression_polished_gate_reasons"])


def test_paraphrased_but_equivalent_polished_output_is_not_flagged():
    """Fix 1 requirement: two polished outputs that say the same thing in
    different wording (exactly what Gemini does when restructuring into
    bullet points) must NOT be flagged as a regression."""
    batch_polished = (
        "今天早上六點半開始下小雨，我先查看氣象預報後決定攜帶折疊傘，"
        "並將充電完成的相機、行動電源與筆記本放入背包，早餐是無糖豆漿、兩片烤吐司與一顆水煮蛋。"
    )
    hybrid_polished_reworded = (
        "早上六點半天空飄著小雨，查看過氣象預報後帶上了折疊傘，"
        "把相機、行動電源和筆記本收進背包，早餐吃了無糖豆漿、兩片烤吐司和一顆水煮蛋。"
    )
    rows = [
        _row("batch", 1, "raw batch text", batch_polished),
        _row("hybrid_v2", 1, "raw hybrid text", hybrid_polished_reworded),
    ]

    analyzed = reanalyze(rows, MANIFEST, Path("."))

    hybrid_row = next(r for r in analyzed if r["mode"] == "hybrid_v2")
    assert hybrid_row["hybrid_regression_polished_gate_ok"] is True
    assert hybrid_row["hybrid_regression_polished_gate_reasons"] == []
