import speedytype.cli as cli


def test_install_command_passes_selected_env_to_installer(monkeypatch, tmp_path, capsys):
    calls = []
    monkeypatch.setattr(
        cli,
        "install_command_alias",
        lambda env_path: calls.append(env_path) or (True, "installed"),
    )
    env_path = tmp_path / "chosen.env"

    result = cli.main(["--env", str(env_path), "install-command"])

    assert result == 0
    assert calls == [str(env_path)]
    assert capsys.readouterr().out.strip() == "installed"


def test_install_command_returns_nonzero_on_failure(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "install_command_alias",
        lambda env_path: (False, "installation failed"),
    )

    result = cli.main(["install-command"])

    assert result == 1
    assert capsys.readouterr().out.strip() == "installation failed"


def test_later_env_argument_overrides_wrapper_default():
    parser = cli.build_parser()

    args = parser.parse_args(
        [
            "--env",
            "installed.env",
            "--env",
            "other.env",
            "diagnose-config",
        ]
    )

    assert args.env == "other.env"
