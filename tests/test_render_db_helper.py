"""Sprint 2B closeout: the founder's database helper never leaks the password or its temporary settings."""

import importlib.util
import os
import stat
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("render_db", Path(__file__).resolve().parent.parent / "scripts" / "render_db.py")
render_db = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(render_db)
URL = "postgres://rbr_user:s3cr%3At:pw@dpg-abc-a.frankfurt-postgres.render.com:5432/roombyroom"
SECRET = "s3cr:t:pw"


@pytest.fixture
def remote(monkeypatch):
    monkeypatch.setattr(render_db.getpass, "getpass", lambda prompt="": URL)
    monkeypatch.setenv("PGSSLMODE", "disable")  # leftovers in the founder's shell must not reach children
    monkeypatch.setenv("DATABASE_URL", "postgres://leftover")
    monkeypatch.setenv("DJANGO_ALLOW_INSECURE_KEY", "1")


def test_password_only_in_private_passfile(remote):
    with render_db.RemoteDatabase() as db:
        mode = stat.S_IMODE(os.stat(db.passfile).st_mode)
        assert mode == 0o600 and stat.S_IMODE(os.stat(db.tmpdir).st_mode) == 0o700
        assert Path(db.passfile).read_text() == "dpg-abc-a.frankfurt-postgres.render.com:5432:roombyroom:rbr_user:s3cr\\:t\\:pw\n"
        env, args = db.env(), db.pg_args()
        assert SECRET not in " ".join(args) and all(SECRET not in v for v in env.values())
        assert env["PGSSLMODE"] == "require" and env["PGPASSFILE"] == db.passfile
        assert env["DATABASE_URL"] == "postgres://rbr_user@dpg-abc-a.frankfurt-postgres.render.com:5432/roombyroom"
        passfile = db.passfile
    assert not os.path.exists(passfile)


def test_passfile_removed_on_failure(remote):
    with pytest.raises(RuntimeError):
        with render_db.RemoteDatabase() as db:
            passfile = db.passfile
            raise RuntimeError("pg_dump failed")
    assert not os.path.exists(passfile)


def test_helper_never_changes_the_callers_environment(remote):
    before = dict(os.environ)
    with render_db.RemoteDatabase() as db:
        db.env()
    assert dict(os.environ) == before


def test_clean_env_scrubs_remote_settings(remote):
    env = render_db.clean_env()
    assert not any(k.startswith("PG") for k in env)
    assert "DATABASE_URL" not in env and "DJANGO_ALLOW_INSECURE_KEY" not in env


def test_url_without_password_is_refused(monkeypatch):
    monkeypatch.setattr(render_db.getpass, "getpass", lambda prompt="": "postgres://u@host/db")
    with pytest.raises(render_db.HelperError):
        with render_db.RemoteDatabase():
            pass


def test_restore_check_refuses_remote_hosts(tmp_path, capsys):
    dump = tmp_path / "x.dump"
    dump.write_bytes(b"")
    (tmp_path / "x.fingerprint.json").write_text("{}")
    assert render_db.main(["restore-check", str(dump), "--host", "dpg-abc-a.frankfurt-postgres.render.com"]) == 1
    assert "only restores into a local PostgreSQL" in capsys.readouterr().err
