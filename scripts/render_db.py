"""Founder helper for the free-preview database: owner account, backup and local restore check.

Runs on the founder's own computer, from the repository checkout with its virtualenv active. It exists so
that nothing secret leaks while working with the Render database:

* the External Database URL is read at a hidden prompt (never typed into a command or shell history);
* the password goes only into a temporary permission-0600 PGPASSFILE that is deleted on success, failure,
  Ctrl+C or SIGTERM; it never appears in any process argument or environment variable;
* every temporary setting (PGSSLMODE=require, DJANGO_ALLOW_INSECURE_KEY=1, DATABASE_URL, PGPASSFILE) is given
  only to the commands this helper starts, so nothing is left behind in the founder's shell;
* remote connections always require TLS; the local restore uses its own explicit local settings and refuses
  any non-local host.

    python scripts/render_db.py create-owner alistair
    python scripts/render_db.py backup --out ~/RoomByRoomBackups
    python scripts/render_db.py restore-check ~/RoomByRoomBackups/room-by-room-YYYY-MM-DD.dump

No application feature is added: it only wraps `create_owner`, `restore_fingerprint`, `pg_dump`, `createdb`
and `pg_restore`.
"""

import argparse
import datetime
import getpass
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

ROOT = Path(__file__).resolve().parent.parent
# Settings that must never leak from the founder's shell into a child, or from one session into another.
SCRUB = ("DATABASE_URL", "DJANGO_ALLOW_INSECURE_KEY", "DJANGO_SECRET_KEY")
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


class HelperError(Exception):
    pass


def _terminate(signum, frame):
    raise SystemExit(128 + signum)  # run the `finally` clean-up on SIGTERM / SIGHUP as on Ctrl+C


def clean_env():
    """The parent environment without any database, PostgreSQL or override settings."""
    return {k: v for k, v in os.environ.items() if k not in SCRUB and not k.startswith("PG")}


def _passfile_field(value):
    return value.replace("\\", "\\\\").replace(":", "\\:")


class RemoteDatabase:
    """A hidden-input connection to the Render database, usable only inside a `with` block."""

    def __enter__(self):
        url = getpass.getpass("Paste the database's External Database URL (input hidden), then press Enter: ").strip()
        parsed = urlparse(url)
        if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname or not parsed.password:
            raise HelperError("That does not look like a full postgres:// URL with a password.")
        self.host = parsed.hostname
        self.port = str(parsed.port or 5432)
        self.user = unquote(parsed.username or "")
        self.dbname = unquote(parsed.path.lstrip("/"))
        password = unquote(parsed.password)
        del url, parsed
        self.tmpdir = tempfile.mkdtemp(prefix="rbr-")  # 0700
        try:  # __exit__ only runs once __enter__ returns: clean up here if writing the passfile fails
            self.passfile = os.path.join(self.tmpdir, "pgpass")
            fd = os.open(self.passfile, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as handle:
                handle.write(":".join(_passfile_field(v) for v in (self.host, self.port, self.dbname, self.user, password)) + "\n")
        except BaseException:
            shutil.rmtree(self.tmpdir, ignore_errors=True)
            raise
        finally:
            del password
        return self

    def __exit__(self, *exc):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        return False

    def env(self, **extra):
        """Child environment: TLS required, password only via the 0600 PGPASSFILE, no password in DATABASE_URL."""
        env = clean_env()
        env.update(
            PGPASSFILE=self.passfile, PGSSLMODE="require",
            DATABASE_URL=f"postgres://{quote(self.user, safe='')}@{self.host}:{self.port}/{quote(self.dbname, safe='')}",
            DJANGO_DEBUG="0", DJANGO_ALLOW_INSECURE_KEY="1",  # local management commands only; never set on Render
            PRIVATE_STORAGE_BACKEND="database", **extra,
        )
        return env

    def pg_args(self):
        return ["--host", self.host, "--port", self.port, "--username", self.user, "--dbname", self.dbname]


def run(args, env, **kwargs):
    result = subprocess.run(args, env=env, cwd=ROOT, **kwargs)
    if result.returncode:
        raise HelperError(f"{Path(args[0]).name} {args[1] if len(args) > 1 else ''} failed (exit {result.returncode}).")
    return result


def fingerprint(env):
    out = run([sys.executable, "manage.py", "restore_fingerprint"], env, capture_output=True, text=True).stdout
    return json.loads(out)


def write_private(path, text, created=None):
    """Create ``path`` (0600, never overwriting) and record it in ``created`` before writing."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    if created is not None:
        created.append(Path(path))
    with os.fdopen(fd, "w") as handle:
        handle.write(text)


def tool(name, pg_bin):
    path = os.path.join(pg_bin, name) if pg_bin else shutil.which(name)
    if not path or not os.path.exists(path):
        raise HelperError(f"{name} not found. Install the PostgreSQL client tools (same major version as the "
                          f"database or newer) or pass --pg-bin.")
    return path


REMOTE_HINT = ("If it could not connect: check the pasted URL is the External one, that your current IP has a "
               "temporary /32 inbound rule, and that the database is not expired.")


def cmd_create_owner(args):
    with RemoteDatabase() as db:
        print("Connecting with TLS required; the password is kept only in a temporary private file.")
        try:
            run([sys.executable, "manage.py", "create_owner", args.username], db.env())  # password typed at its prompts
        except HelperError as exc:
            raise HelperError(f"{exc} {REMOTE_HINT}") from None


def cmd_backup(args):
    out_dir = Path(args.out).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp = datetime.date.today().isoformat()
    dump = out_dir / f"room-by-room-{stamp}.dump"
    fingerprint_file = dump.with_suffix(".fingerprint.json")
    existing = [p for p in (dump, fingerprint_file) if p.exists()]
    if existing:  # never overwrite or delete earlier backups
        raise HelperError(f"{existing[0]} already exists; move it or choose another --out.")
    pg_dump = tool("pg_dump", args.pg_bin)
    answer = input("Stop using the app (phone and browser) until this finishes, so the copy is consistent. "
                   "Ready? [y/N] ")
    if answer.strip().lower() not in {"y", "yes"}:
        raise HelperError("Backup cancelled.")
    created = []  # only files this attempt created; removed on any failure or interruption
    try:
        with RemoteDatabase() as db:
            try:
                before = fingerprint(db.env())
            except HelperError as exc:
                raise HelperError(f"{exc} {REMOTE_HINT}") from None
            os.umask(0o077)
            created.append(dump)
            run([pg_dump, "--format=custom", "--no-owner", "--no-acl", "--file", str(dump), *db.pg_args()], db.env())
            after = fingerprint(db.env())
        if before != after:
            raise HelperError("The data changed while exporting (someone used the app). Nothing kept; run it again.")
        os.chmod(dump, 0o600)
        write_private(fingerprint_file, json.dumps(before, indent=2, sort_keys=True), created)
    except BaseException:
        for path in created:
            path.unlink(missing_ok=True)
        raise
    print(f"Backup written: {dump} ({dump.stat().st_size:,} bytes) and its fingerprint. Keep both private "
          f"(encrypted storage). Files: {before['files']['count']}; confirmed purchases: {before['confirmed_purchases']}.")


def cmd_restore_check(args):
    dump = Path(args.dump).expanduser()
    expected_path = Path(args.fingerprint).expanduser() if args.fingerprint else dump.with_suffix(".fingerprint.json")
    expected = json.loads(expected_path.read_text())
    if not (args.host in LOCAL_HOSTS or args.host.startswith("/")):
        raise HelperError("restore-check only restores into a local PostgreSQL (localhost or a socket directory).")
    # Explicit local settings, independent of any remote session or shell exports.
    env = clean_env()
    env.update(PGHOST=args.host, PGPORT=str(args.port), PGUSER=args.user, PGSSLMODE=args.local_sslmode)
    createdb, pg_restore = tool("createdb", args.pg_bin), tool("pg_restore", args.pg_bin)
    run([createdb, args.db], env)  # fails if it already exists: never restore over an existing database
    run([pg_restore, "--no-owner", "--no-acl", "--exit-on-error", "--dbname", args.db, str(dump)], env)
    host = quote(args.host, safe="") if args.host.startswith("/") else args.host
    env.update(DATABASE_URL=f"postgres://{quote(args.user, safe='')}@{host}:{args.port}/{args.db}",
               DJANGO_DEBUG="0", DJANGO_ALLOW_INSECURE_KEY="1", PRIVATE_STORAGE_BACKEND="database")
    restored = fingerprint(env)
    if restored != expected:
        print(json.dumps({"expected": expected, "restored": restored}, indent=2, sort_keys=True))
        raise HelperError("Restored data does NOT match the backup's fingerprint.")
    print(f"IDENTICAL: restored copy in local database '{args.db}' matches the backup "
          f"({restored['files']['count']} files, {restored['confirmed_purchases']} confirmed purchases). "
          f"Delete it when done: dropdb {args.db}")


def main(argv=None):
    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, _terminate)
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("create-owner", help="create the owner account (password typed at hidden prompts)")
    p.add_argument("username")
    p.set_defaults(func=cmd_create_owner)
    p = sub.add_parser("backup", help="fingerprint + pg_dump the Render database over TLS")
    p.add_argument("--out", required=True, help="private folder for the backup files")
    p.add_argument("--pg-bin", help="folder containing pg_dump (default: PATH)")
    p.set_defaults(func=cmd_backup)
    p = sub.add_parser("restore-check", help="restore a backup into a NEW local database and compare fingerprints")
    p.add_argument("dump")
    p.add_argument("--fingerprint", help="default: the .fingerprint.json next to the dump")
    p.add_argument("--db", default="rbr_restore")
    p.add_argument("--host", default="localhost")
    p.add_argument("--port", type=int, default=5432)
    p.add_argument("--user", default=getpass.getuser())
    p.add_argument("--local-sslmode", default="prefer", help="local server only (default: prefer)")
    p.add_argument("--pg-bin", help="folder containing createdb/pg_restore (default: PATH)")
    p.set_defaults(func=cmd_restore_check)
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except HelperError as exc:
        print(f"Stopped: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nCancelled. Temporary connection details were deleted.", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
