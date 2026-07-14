import pytest


@pytest.fixture(autouse=True)
def isolated_keyring(monkeypatch):
    from speedytype import secrets_store

    values = {}
    monkeypatch.setattr(secrets_store, "_get_password", lambda service, user: values.get((service, user)))
    monkeypatch.setattr(secrets_store, "_set_password", lambda service, user, value: values.__setitem__((service, user), value))
    monkeypatch.setattr(secrets_store, "_delete_password", lambda service, user: values.pop((service, user), None))
    for env_name in secrets_store.SECRET_KEY_NAMES:
        monkeypatch.delenv(env_name, raising=False)
    yield values
