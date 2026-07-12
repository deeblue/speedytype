from speedytype.transcript_quality import TranscriptQuality, _sentences, normalize_transcript, passes_quality_gate
from scripts.run_long_recording_benchmark import case_resolution, named_quality_payload, quality_payload


def assert_rejected(reference: str, candidate: str, expected_reason: str) -> TranscriptQuality:
    metrics = TranscriptQuality.compare(reference, candidate)
    ok, reasons = passes_quality_gate(metrics)
    assert ok is False
    assert any(expected_reason in reason for reason in reasons), reasons
    return metrics


def test_normalize_preserves_numbers_and_terms():
    assert normalize_transcript("API 版本 123，完成！") == "api版本123完成"


def test_omitted_sentence_is_rejected():
    metrics = assert_rejected("第一句完成。第二句保留。", "第一句完成。", "missing complete sentence")
    assert metrics.missing_sentences == ("第二句保留",)


def test_new_duplicate_sentence_is_rejected():
    assert_rejected("第一句。第二句。", "第一句。第一句。第二句。", "new duplicate sentence")


def test_reordered_content_is_rejected():
    assert_rejected("甲段內容。乙段內容。丙段內容。", "丙段內容。乙段內容。甲段內容。", "ordered coverage")


def test_changed_number_is_rejected():
    assert_rejected("停留四十分鐘。", "停留一分鐘。", "numbers changed")


def test_chinese_and_arabic_numbers_are_equivalent():
    metrics = TranscriptQuality.compare("九點四十分，停留二十分鐘。", "9點40分，停留20分鐘。")
    assert metrics.number_preserved is True


def test_key_terms_absent_from_reference_are_not_required():
    metrics = TranscriptQuality.compare("今天搭火車。", "今天搭火車。", ["BIOS", "API"])
    assert metrics.key_term_recall == 1.0
    assert metrics.missing_key_terms == ()


def test_unchanged_transcript_passes():
    metrics = TranscriptQuality.compare("列車準時出發。API 版本 123。", "列車準時出發。API 版本 123。", ["API"])
    assert passes_quality_gate(metrics) == (True, [])


def test_continuous_tts_space_delimited_transcript_is_split_into_real_units():
    reference = (
        "今天早上六點半,窗外剛開始下小雨 "
        "我先查看氣象預報,決定帶一把折疊傘 "
        "然後把昨晚充電的相機、行動電源和筆記本放進背包"
    )
    candidate = (
        "今天早上六點半，窗外剛開始下小雨。"
        "我先查看氣象預報，決定帶一把折疊傘。"
        "然後把昨晚充電的相機、行動電源和筆記本放進背包。"
    )

    assert _sentences(reference) == [
        "今天早上六點半",
        "窗外剛開始下小雨",
        "我先查看氣象預報",
        "決定帶一把折疊傘",
        "然後把昨晚充電的相機",
        "行動電源和筆記本放進背包",
    ]
    assert TranscriptQuality.compare(reference, candidate).missing_sentences == ()


def test_real_134s_clause_split_does_not_hide_contiguous_content():
    reference = "第一個的話 它本身算是一個數列排序的一個做法 那就對我來說比較熟悉"
    candidate = "第一個的話,它本身算是一個 數列排序的一個做法 那就比較對我來說是比較熟悉"

    metrics = TranscriptQuality.compare(reference, candidate)

    assert "它本身算是一個數列排序的一個做法" not in metrics.missing_sentences


def test_continuous_tts_compound_list_uses_punctuation_as_clause_boundaries():
    reference = "接著我寫下三項待辦事項：查證航海儀器的名稱、確認市場茶葉的產地，以及挑選十張照片製作旅行紀錄"
    candidate = "接著我寫下三項待辦事項 查證航海儀器的名稱 確認市場茶葉的產地 以及挑選十張照片製作旅行記錄"

    metrics = TranscriptQuality.compare(reference, candidate)

    assert metrics.missing_sentences == ()


def test_case_a_missing_departure_sentence_regression():
    assert_rejected("列車準時出發。前半段路程穿過住宅區。", "前半段路程穿過住宅區。", "列車準時出發")


def test_case_b_duration_and_subject_corruption_regression():
    assert_rejected(
        "我在海邊停留約四十分鐘，記錄潮水顏色和風速變化。",
        "一分鐘，記錄潮水顏色和風速變化。",
        "numbers changed",
    )


def test_case_c_location_clause_omission_regression():
    assert_rejected("傍晚，我回到車站附近的咖啡館整理筆記。", "整理筆記。", "missing complete sentence")


def test_case_d_boundary_corruption_regression():
    metrics = assert_rejected(
        "把博物館、市場、舊城街道和海邊步道依照距離重新排序。",
        "把博物館、市場、舊城街道和海邊不到一兆距離重新排序。",
        "ordered coverage",
    )
    assert metrics.ordered_coverage < 0.98


def test_benchmark_quality_payload_is_machine_readable():
    payload = quality_payload("API 版本 123。", "API 版本 123。", ["API"])
    assert payload["quality_gate_ok"] is True
    assert payload["quality_gate_reasons"] == []
    assert payload["quality"]["number_preserved"] is True


def test_named_case_resolution_is_individually_traceable():
    status = case_resolution("列車準時出發。我在海邊停留約四十分鐘。")
    assert status == {"A": True, "B": True, "C": False, "D": False}


def test_source_and_hybrid_regression_quality_have_separate_names():
    source = named_quality_payload("source", "原稿四十分鐘", "辨識一分鐘", [])
    regression = named_quality_payload("hybrid_regression", "batch 一分鐘", "hybrid 一分鐘", [])
    assert source["source_gate_ok"] is False
    assert "hybrid_regression_gate_ok" in regression
    assert "source_gate_ok" not in regression
