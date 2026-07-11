from scripts.test_prompt_variants_repeated import is_valid_result


def test_api_failures_are_not_valid_prompt_samples():
    assert is_valid_result("123 測試") is True
    assert is_valid_result("[FAILED after 4 attempts] [ERROR 429]") is False
    assert is_valid_result("[ERROR 500] unavailable") is False
