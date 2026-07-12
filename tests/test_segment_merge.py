from speedytype.segment_merge import TimedSegment, merge_timed_segments


def seg(start, end, text, chunk):
    return TimedSegment(start, end, text, chunk)


def test_identical_overlap_is_deduplicated():
    result = merge_timed_segments([[seg(0, 3, "第一句", 1)], [seg(0.2, 3.1, "第一句", 2)]], 3.1)
    assert result.text == "第一句"
    assert len(result.duplicates) == 1


def test_punctuation_difference_is_deduplicated():
    result = merge_timed_segments([[seg(0, 3, "列車準時出發。", 1)], [seg(0.1, 3.2, "列車準時出發", 2)]], 3.2)
    assert result.text.count("列車準時出發") == 1


def test_near_duplicate_overlap_preserves_more_complete_version():
    result = merge_timed_segments(
        [[seg(20, 27, "傍晚我回到咖啡館整理筆記", 1)], [seg(20.1, 27.2, "傍晚我回到車站附近的咖啡館整理筆記", 2)]],
        27.2,
    )
    assert result.text == "傍晚我回到車站附近的咖啡館整理筆記"
    assert any(decision.reason == "overlap-more-complete" for decision in result.decisions)


def test_boundary_crossing_segment_is_not_dropped_by_midpoint():
    result = merge_timed_segments(
        [[seg(22, 27, "列車準時出發", 1)], [seg(26.5, 31, "前半段路程穿過住宅區", 2)]],
        31,
    )
    assert result.text == "列車準時出發 前半段路程穿過住宅區"


def test_forced_cut_overlap_keeps_distinct_adjacent_sentences():
    result = merge_timed_segments(
        [[seg(42, 45.5, "我在海邊停留約四十分鐘", 1)], [seg(44, 48, "記錄潮水顏色和風速變化", 2)]],
        48,
    )
    assert "四十分鐘" in result.text
    assert "記錄潮水" in result.text


def test_out_of_order_api_results_are_sorted_by_timestamp():
    result = merge_timed_segments([[seg(10, 12, "第二句", 2)], [seg(0, 2, "第一句", 1)]], 12)
    assert result.text == "第一句 第二句"


def test_timeline_gap_is_reported():
    result = merge_timed_segments([[seg(0, 2, "第一句", 1)], [seg(5, 7, "第二句", 2)]], 7)
    assert (2, 5) in result.gaps


def test_same_chunk_adjacent_distinct_team_sentences_are_not_dropped_as_duplicate():
    """Named regression test for the real_126s case from
    long_recording_hybrid_v2_quality_reanalysis.jsonl (line 2): two
    consecutive segments from the SAME chunk (chunk_index=1), textually
    similar in structure ("關於TPE團隊..." / "以及BJ團隊...", similarity 0.667,
    just above the 0.60 threshold) but about different, distinct teams, were
    being merged as an "overlap-duplicate" and the BJ 團隊 sentence silently
    dropped — a real content-loss bug, not correct deduplication."""
    result = merge_timed_segments(
        [[
            seg(18.0, 22.0, "關於TPE團隊這邊負責的部分", 1),
            seg(22.0, 24.0, "以及BJ團隊這邊負責的部分", 1),
        ]],
        24.0,
    )
    assert "TPE團隊" in result.text
    assert "BJ團隊" in result.text
    assert not any(decision.reason == "overlap-duplicate" for decision in result.decisions)


def test_cross_chunk_near_duplicate_is_still_detected_after_same_chunk_fix():
    """Guard against overcorrecting Fix 2: genuine cross-chunk overlap
    duplicates (the actual scenario duplicate-detection exists for) must
    still be caught."""
    result = merge_timed_segments(
        [[seg(20, 27, "傍晚我回到咖啡館整理筆記", 1)], [seg(20.1, 27.2, "傍晚我回到車站附近的咖啡館整理筆記", 2)]],
        27.2,
    )
    assert result.text == "傍晚我回到車站附近的咖啡館整理筆記"
    assert any(decision.reason == "overlap-more-complete" for decision in result.decisions)
