from contextlib import contextmanager

from app.core.constants import Role
from scripts import seed_admin


def test_seed_admin_prompts_for_missing_credentials(monkeypatch, capsys):
    for variable in (
        "BOOTSTRAP_ADMIN_EMAIL",
        "BOOTSTRAP_ADMIN_NAME",
        "BOOTSTRAP_ADMIN_PASSWORD",
    ):
        monkeypatch.delenv(variable, raising=False)

    answers = iter(("admin@example.com", "Initial Admin", "secure-password-123"))
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    monkeypatch.setattr(seed_admin, "hash_password", lambda password: "hashed-password")

    class FakeSession:
        def __init__(self):
            self.users = []

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def scalar(self, statement):
            return 0

        def add(self, user):
            self.users.append(user)

    session = FakeSession()

    class FakeSessionLocal:
        @staticmethod
        @contextmanager
        def begin():
            yield session

    monkeypatch.setattr(seed_admin, "SessionLocal", FakeSessionLocal)

    seed_admin.main()

    assert len(session.users) == 1
    assert session.users[0].email == "admin@example.com"
    assert session.users[0].full_name == "Initial Admin"
    assert session.users[0].password_hash == "hashed-password"
    assert session.users[0].role == Role.SUPER_ADMIN
    assert "Created initial super admin: admin@example.com" in capsys.readouterr().out
