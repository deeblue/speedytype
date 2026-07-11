from speedytype.console import safe_print


def test_safe_print_does_not_crash_when_stdout_is_none(monkeypatch):
    monkeypatch.setattr("speedytype.console.sys.stdout", None)

    # Must not raise, matching pythonw.exe's real sys.stdout=None behavior.
    safe_print("hello", flush=True)


def test_safe_print_does_not_crash_on_broken_stream(monkeypatch):
    class BrokenStream:
        def write(self, text):
            raise OSError("broken pipe")

        def flush(self):
            raise OSError("broken pipe")

    monkeypatch.setattr("speedytype.console.sys.stdout", BrokenStream())

    safe_print("hello", flush=True)


def test_safe_print_still_writes_normally(capsys):
    safe_print("hello", "world", flush=True)

    captured = capsys.readouterr()
    assert captured.out == "hello world\n"
