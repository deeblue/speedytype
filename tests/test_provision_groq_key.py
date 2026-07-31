from pathlib import Path

from scripts import provision_groq_key


def test_resolve_groq_key_uses_environment_without_logging_secret():
    assert provision_groq_key.resolve_groq_key(None, {"GROQ_API_KEY": " gsk-fake "}) == "gsk-fake"


def test_resolve_groq_key_reads_key_file(tmp_path: Path):
    key_file = tmp_path / "groq.key"
    key_file.write_text("gsk-from-file\n", encoding="utf-8")

    assert provision_groq_key.resolve_groq_key(key_file, {}) == "gsk-from-file"


def test_main_stores_groq_key_without_printing_secret(monkeypatch, capsys):
    stored = []
    monkeypatch.setenv("GROQ_API_KEY", "gsk-main-secret")
    monkeypatch.setattr(provision_groq_key, "set_api_key", lambda env_name, value: stored.append((env_name, value)))

    assert provision_groq_key.main([]) == 0

    captured = capsys.readouterr()
    assert stored == [("GROQ_API_KEY", "gsk-main-secret")]
    assert "provisioned" in captured.out
    assert "gsk-main-secret" not in captured.out
    assert "gsk-main-secret" not in captured.err
