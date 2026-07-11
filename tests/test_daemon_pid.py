import os

from speedytype.daemon import check_existing_daemon


def test_no_pid_file_means_proceed_silently(tmp_path):
    pid_file = tmp_path / "speedytype_daemon.pid"
    assert not pid_file.exists()

    should_start, message = check_existing_daemon(pid_file)

    assert should_start is True
    assert message == ""


def test_stale_pid_is_cleaned_up_and_start_allowed(tmp_path):
    pid_file = tmp_path / "speedytype_daemon.pid"
    # A PID that is virtually guaranteed not to correspond to any real
    # process on a normal Windows machine.
    pid_file.write_text("999999999", encoding="utf-8")

    should_start, message = check_existing_daemon(pid_file)

    assert should_start is True
    assert "stale" in message.lower()
    assert "999999999" in message
    assert not pid_file.exists()  # cleaned up


def test_genuinely_running_pid_refuses_to_start(tmp_path):
    pid_file = tmp_path / "speedytype_daemon.pid"
    # Use this very test process's own PID as a real, definitely-running PID.
    pid_file.write_text(str(os.getpid()), encoding="utf-8")

    should_start, message = check_existing_daemon(pid_file)

    assert should_start is False
    assert "already be running" in message
    assert pid_file.exists()  # not touched; a live daemon's PID file must survive


def test_unreadable_pid_file_content_is_treated_as_stale(tmp_path):
    pid_file = tmp_path / "speedytype_daemon.pid"
    pid_file.write_text("not-a-number", encoding="utf-8")

    should_start, message = check_existing_daemon(pid_file)

    assert should_start is True
    assert not pid_file.exists()
