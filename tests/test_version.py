import pytest

import speedytype
from speedytype import cli
from speedytype.version import BUILD_DATE, VERSION


def test_package_version_uses_authoritative_release_metadata():
    assert VERSION == "0.5.3"
    assert BUILD_DATE == "2026-07-16"
    assert speedytype.__version__ == VERSION


def test_cli_version_exits_without_loading_configuration(monkeypatch, capsys):
    def fail_if_config_load_is_attempted(*args, **kwargs):
        raise AssertionError("--version must not load configuration")

    monkeypatch.setattr(cli, "_load_config_or_print", fail_if_config_load_is_attempted)

    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--version"])

    assert exit_info.value.code == 0
    assert capsys.readouterr().out == "SpeedyType 0.5.3\n"
