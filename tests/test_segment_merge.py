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
