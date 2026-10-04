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


# ------------------------------------------------------------------ helper clean-up on failure (CTO follow-up)


@pytest.fixture
def tmpdirs(monkeypatch):
    made = []
    real = render_db.tempfile.mkdtemp

    def tracking_mkdtemp(*args, **kwargs):
        made.append(real(*args, **kwargs))
        return made[-1]

    monkeypatch.setattr(render_db.tempfile, "mkdtemp", tracking_mkdtemp)
    return made


@pytest.mark.parametrize("error", [OSError("disk full"), KeyboardInterrupt()])
def test_passfile_initialisation_failure_removes_private_directory(remote, tmpdirs, monkeypatch, error):
    def failing_fdopen(fd, *args, **kwargs):
        os.close(fd)
        raise error

    monkeypatch.setattr(render_db.os, "fdopen", failing_fdopen)
    with pytest.raises(type(error)):
        with render_db.RemoteDatabase():
            pass
    assert len(tmpdirs) == 1 and not os.path.exists(tmpdirs[0])


@pytest.fixture
def backup_env(remote, tmpdirs, tmp_path, monkeypatch):
    """A backup run with pg_dump and the fingerprints faked; returns (args, outcome controls)."""
    controls = {"fingerprints": [{"files": {"count": 1}, "confirmed_purchases": 1}] * 2, "dump_error": None}
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")
    monkeypatch.setattr(render_db, "tool", lambda name, pg_bin: "/usr/bin/pg_dump")

    def fake_fingerprint(env):
        outcome = controls["fingerprints"].pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    def fake_run(args, env, **kwargs):
        assert SECRET not in " ".join(args)
        Path(args[args.index("--file") + 1]).write_bytes(b"partial or complete dump")
        if controls["dump_error"]:
            raise controls["dump_error"]

    monkeypatch.setattr(render_db, "fingerprint", fake_fingerprint)
    monkeypatch.setattr(render_db, "run", fake_run)
    out = tmp_path / "backups"
    return render_db.argparse.Namespace(out=str(out), pg_bin=None), controls, out


def _outputs(out):
    return sorted(p.name for p in out.iterdir()) if out.exists() else []


def test_backup_success_writes_both_private_files(backup_env, tmpdirs):
    args, _, out = backup_env
    render_db.cmd_backup(args)
    names = _outputs(out)
    assert len(names) == 2 and names[0].endswith(".dump") and names[1].endswith(".fingerprint.json")
    assert all(stat.S_IMODE((out / n).stat().st_mode) == 0o600 for n in names)
    assert not os.path.exists(tmpdirs[0])


@pytest.mark.parametrize("failure", ["post_export_fingerprint", "post_export_interrupt", "data_changed",
                                     "pg_dump_error", "pg_dump_interrupt", "fingerprint_write"])
def test_backup_failure_leaves_no_partial_outputs(backup_env, tmpdirs, monkeypatch, failure):
    args, controls, out = backup_env
    if failure == "post_export_fingerprint":
        controls["fingerprints"][1:] = [render_db.HelperError("connection lost")]
    elif failure == "post_export_interrupt":
        controls["fingerprints"][1:] = [KeyboardInterrupt()]
    elif failure == "data_changed":
        controls["fingerprints"][1:] = [{"files": {"count": 2}, "confirmed_purchases": 1}]
    elif failure == "pg_dump_error":
        controls["dump_error"] = render_db.HelperError("pg_dump failed")
    elif failure == "pg_dump_interrupt":
        controls["dump_error"] = KeyboardInterrupt()
    else:  # the fingerprint file is created, then writing it fails
        monkeypatch.setattr(render_db.json, "dumps", lambda *a, **k: object())
    with pytest.raises((render_db.HelperError, KeyboardInterrupt, TypeError)):
        render_db.cmd_backup(args)
    assert _outputs(out) == []  # no dump without its fingerprint, no orphan fingerprint
    assert all(not os.path.exists(d) for d in tmpdirs)  # passfile directory gone too


@pytest.mark.parametrize("existing", ["dump", "fingerprint", "both"])
def test_backup_refuses_existing_outputs_and_preserves_them(backup_env, tmpdirs, existing):
    args, _, out = backup_env
    out.mkdir(mode=0o700)
    stamp = render_db.datetime.date.today().isoformat()
    names = {"dump": [f"room-by-room-{stamp}.dump"], "fingerprint": [f"room-by-room-{stamp}.fingerprint.json"]}
    names["both"] = names["dump"] + names["fingerprint"]
    for name in names[existing]:
        (out / name).write_text("earlier backup")
    with pytest.raises(render_db.HelperError, match="already exists"):
        render_db.cmd_backup(args)
    assert _outputs(out) == sorted(names[existing])
    assert all((out / n).read_text() == "earlier backup" for n in names[existing])
    assert tmpdirs == []  # refused before asking for the URL or creating a passfile


def test_backup_failure_keeps_unrelated_earlier_backups(backup_env):
    args, controls, out = backup_env
    out.mkdir(mode=0o700)
    (out / "room-by-room-2026-09-01.dump").write_text("older")
    (out / "room-by-room-2026-09-01.fingerprint.json").write_text("{}")
    controls["fingerprints"][1:] = [render_db.HelperError("connection lost")]
    with pytest.raises(render_db.HelperError):
        render_db.cmd_backup(args)
    assert _outputs(out) == ["room-by-room-2026-09-01.dump", "room-by-room-2026-09-01.fingerprint.json"]


# ------------------------------------------------------------------ change-password (hosted support)


@pytest.mark.parametrize("command, managed", [("create-owner", "create_owner"), ("change-password", "changepassword")])
def test_account_commands_run_interactively_without_the_password(remote, tmpdirs, monkeypatch, command, managed):
    calls = []

    def fake_run(args, env, **kwargs):
        calls.append(args)
        assert SECRET not in " ".join(args) and all(SECRET not in v for v in env.values())
        assert env["PGSSLMODE"] == "require" and os.path.exists(env["PGPASSFILE"])

    monkeypatch.setattr(render_db, "run", fake_run)
    assert render_db.main([command, "alistair"]) == 0
    assert calls == [[render_db.sys.executable, "manage.py", managed, "alistair"]]  # no password argument
    assert not os.path.exists(tmpdirs[0])


def test_change_password_failure_cleans_up_and_hints(remote, tmpdirs, monkeypatch, capsys):
    def failing_run(args, env, **kwargs):
        raise render_db.HelperError("python manage.py failed (exit 1).")

    monkeypatch.setattr(render_db, "run", failing_run)
    assert render_db.main(["change-password", "alistair"]) == 1
    assert "temporary /32 inbound rule" in capsys.readouterr().err
    assert not os.path.exists(tmpdirs[0])
