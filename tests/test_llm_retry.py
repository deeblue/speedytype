from speedytype.llm import retry_api_call


def test_retry_api_call_separates_sleep_from_api_time():
    attempts = {"count": 0}
    now = {"value": 100.0}
    sleeps = []

    def clock():
        return now["value"]

    def sleeper(seconds):
        sleeps.append(seconds)
        now["value"] += seconds

    def operation():
        attempts["count"] += 1
        now["value"] += 0.25
        if attempts["count"] == 1:
            raise RuntimeError("Gemini API error status=503, body: busy")
        return "ok"

    value, api_seconds, retry_wait_seconds, retry_count = retry_api_call(
        "Gemini",
        operation,
        attempts=2,
        clock=clock,
        sleeper=sleeper,
        wait_schedule=(2.0,),
    )

    assert value == "ok"
    assert api_seconds == 0.5
    assert retry_wait_seconds == 2.0
    assert retry_count == 1
    assert sleeps == [2.0]
