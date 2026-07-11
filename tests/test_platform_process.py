import psutil

from speedytype.platform import process


class FakeProcess:
    def __init__(self, pid, *, running=True, error=None):
        self.pid = pid
        self.running = running
        self.error = error
        self.terminated = False

    def is_running(self):
        if self.error:
            raise self.error
        return self.running

    def terminate(self):
        if self.error:
            raise self.error
        self.terminated = True


def test_is_process_running_handles_missing_process(monkeypatch):
    monkeypatch.setattr(process.psutil, "Process", lambda pid: (_ for _ in ()).throw(psutil.NoSuchProcess(pid)))
    assert process.is_process_running(123) is False


def test_is_process_running_treats_access_denied_as_alive(monkeypatch):
    monkeypatch.setattr(process.psutil, "Process", lambda pid: FakeProcess(pid, error=psutil.AccessDenied(pid)))
    assert process.is_process_running(123) is True


def test_terminate_process_reports_success(monkeypatch):
    fake = FakeProcess(123)
    monkeypatch.setattr(process.psutil, "Process", lambda pid: fake)
    assert process.terminate_process(123) == (True, "Stopped daemon PID 123.")
    assert fake.terminated is True


def test_terminate_process_handles_access_denied(monkeypatch):
    monkeypatch.setattr(process.psutil, "Process", lambda pid: FakeProcess(pid, error=psutil.AccessDenied(pid)))
    ok, message = process.terminate_process(123)
    assert ok is False
    assert "Access denied" in message
