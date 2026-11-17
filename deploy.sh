#!/usr/bin/env bash
# Deploy shared Rime sources; keep databases, identity and build output local.
set -euo pipefail
umask 077
script_dir=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
exec python3 - "$script_dir" "$@" <<'PY'
import argparse
import contextlib
import datetime
import fcntl
import filecmp
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import uuid


class DeployError(Exception):
    pass


def absolute(value):
    return Path(os.path.abspath(os.path.expanduser(str(value))))


def within(path, directory):
    return path == directory or directory in path.parents


def frontend_paths(frontend):
    home = Path.home()
    if frontend == "auto":
        frontend = "squirrel" if sys.platform == "darwin" else "ibus"
    paths = {
        "ibus": absolute(os.environ.get("XDG_CONFIG_HOME", home / ".config")) / "ibus/rime",
        "fcitx5": absolute(os.environ.get("XDG_DATA_HOME", home / ".local/share")) / "fcitx5/rime",
        "squirrel": home / "Library/Rime",
    }
    return frontend, paths[frontend]


def runtime_entry(name):
    return (name == "user.yaml" or name.endswith((".userdb", ".userdb.kct", ".userdb.txt")))


def shared_files(source, frontend):
    platform_files = {
        "ibus_rime.yaml": "ibus", "ibus_rime.custom.yaml": "ibus",
        "squirrel.yaml": "squirrel", "squirrel.custom.yaml": "squirrel",
        "weasel.yaml": "weasel", "weasel.custom.yaml": "weasel",
    }
    files = []
    for item in sorted(source.iterdir()):
        name = item.name
        if name.startswith((".", "#")) or "conflicted copy" in name.lower():
            continue
        if name == "installation.yaml" or runtime_entry(name):
            continue
        if name in platform_files and platform_files[name] != frontend:
            continue
        if item.is_file() and item.suffix in (".yaml", ".lua", ".txt"):
            files.append(item.relative_to(source))
        elif name in ("lua", "cn_dicts", "en_dicts", "opencc") and item.is_dir():
            if item.is_symlink():
                raise DeployError(f"Shared asset directory must be real, not a symlink: {item}")
            for parent, directories, names in os.walk(item):
                directories[:] = sorted(d for d in directories
                                        if not d.startswith(".") and d != "__pycache__"
                                        and not runtime_entry(d))
                for directory in directories:
                    if (Path(parent) / directory).is_symlink():
                        raise DeployError(f"Asset directory symlink is unsupported: {Path(parent) / directory}")
                for filename in sorted(names):
                    if (filename.startswith((".", "#")) or filename.endswith(("~", ".pyc", ".bak"))
                            or runtime_entry(filename) or "conflicted copy" in filename.lower()):
                        continue
                    files.append((Path(parent) / filename).relative_to(source))
    if not any(path.name.endswith(".schema.yaml") for path in files):
        raise DeployError(f"No Rime schemas found in source: {source}")
    return files


def installation_id(text):
    matches = re.findall(r"^installation_id:[ \t]*(.*)$", text, re.MULTILINE)
    if not matches:
        return None
    if len(matches) != 1:
        raise DeployError("installation.yaml has duplicate installation_id keys")
    scalar = matches[0].strip()
    if scalar.startswith('"'):
        try:
            value, end = json.JSONDecoder().raw_decode(scalar)
        except ValueError as error:
            raise DeployError(f"Cannot read installation_id: {error}") from error
        remainder = scalar[end:].strip()
        if remainder and not remainder.startswith("#"):
            raise DeployError("Unsupported installation_id YAML scalar")
    else:
        match = re.fullmatch(r"(?:'([A-Za-z0-9_-]+)'|([A-Za-z0-9_-]+))(?:[ \t]+#.*)?", scalar)
        if not match:
            raise DeployError("installation_id must be a simple scalar with letters, digits, _ or -")
        value = match.group(1) or match.group(2)
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise DeployError("Unsafe installation_id in installation.yaml")
    return value


def update_installation(text, machine_id, sync):
    values = {"installation_id": machine_id, "sync_dir": str(sync)}
    lines = text.splitlines()
    for key, value in values.items():
        indices = [i for i, line in enumerate(lines) if re.match(rf"^{key}:", line)]
        if len(indices) > 1:
            raise DeployError(f"installation.yaml has duplicate {key} keys")
        line = f"{key}: {json.dumps(value, ensure_ascii=False)}"
        if indices:
            lines[indices[0]] = line
        else:
            lines.append(line)
    return "\n".join(lines) + "\n"


def rime_running(frontend):
    names = {"ibus": {"ibus-engine-rime", "ibus-engine-rim"},
             "fcitx5": {"fcitx5"}, "squirrel": {"Squirrel"}}[frontend]
    result = subprocess.run(["ps", "-axo", "uid=,comm="], capture_output=True,
                            text=True, check=True)
    for line in result.stdout.splitlines():
        # The command path is the final field: macOS's Input Methods path
        # contains spaces, so do not split that field into separate words.
        columns = line.split(None, 1)
        if len(columns) < 2 or columns[0] != str(os.getuid()):
            continue
        command = Path(columns[1]).name
        if command in names:
            return True
    return False


@contextlib.contextmanager
def unlocked_databases(directory):
    """Retain LevelDB's POSIX locks throughout a migration copy."""
    with contextlib.ExitStack() as stack:
        for database in sorted(directory.glob("*.userdb")):
            lock = database / "LOCK"
            if database.is_dir() and lock.exists():
                handle = stack.enter_context(lock.open("r+"))
                try:
                    fcntl.lockf(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError as error:
                    raise DeployError(f"User dictionary is in use; quit Rime first: {database}") from error
        yield


def check_destination(target, relative):
    """Never traverse an existing runtime directory symlink into the cloud."""
    current = target
    for component in relative.parts[:-1]:
        current /= component
        if current.is_symlink():
            raise DeployError(f"Runtime asset directory is a symlink; replace it with a local directory: {current}")
        if current.exists() and not current.is_dir():
            raise DeployError(f"Expected runtime directory: {current}")
    destination = target / relative
    if destination.exists() and destination.is_dir():
        raise DeployError(f"Expected runtime file: {destination}")


def deploy(args):
    source = absolute(args.source).resolve(strict=True)
    frontend, default_target = frontend_paths(args.frontend)
    target = absolute(args.user_dir or default_target)
    sync = absolute(args.sync_dir or source / "sync").resolve()
    backup_root = absolute(args.backup_dir or
                           Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) /
                           "rime-deploy/backups").resolve()
    target_location = target.parent.resolve() / target.name
    if within(target_location, source) or within(target_location, sync) or within(source, target_location):
        raise DeployError("The Rime runtime must be outside the shared source and sync directories")
    if within(backup_root, source) or within(backup_root, sync) or within(backup_root, target_location):
        raise DeployError("Backups must be outside the shared source, sync and runtime directories")
    if within(sync, target_location) or sync == source:
        raise DeployError("Use a separate sync folder, not the runtime or source root")
    migrating = target.is_symlink()
    if migrating and not target.is_dir():
        raise DeployError(f"Rime user-directory symlink is broken or not a directory: {target}")
    if target.exists() and not target.is_dir():
        raise DeployError(f"Rime user directory is not a directory: {target}")
    if migrating and not args.migrate and not args.dry_run:
        raise DeployError("Rime user directory is a symlink. Quit Rime, then run with --migrate; inspect with --dry-run first")
    files = shared_files(source, frontend)
    old = target.resolve() if migrating else target
    text = (old / "installation.yaml").read_text() if (old / "installation.yaml").is_file() else ""
    # A shared installation.yaml cannot establish this device's identity.
    shared_identity = migrating and (within(old, source) or within(old, sync))
    machine_id = None if shared_identity else installation_id(text)
    if not machine_id:
        hostname = re.sub(r"[^a-z0-9_-]", "-", socket.gethostname().lower()).strip("-") or "rime"
        machine_id = f"{hostname}-{uuid.uuid4().hex[:12]}"
    updated = update_installation(text, machine_id, sync)
    state = sorted(p for p in old.iterdir() if runtime_entry(p.name)) if migrating else []
    print(f"Shared sources: {source}\nLocal runtime:  {target}\nShared sync:    {sync}")
    print(f"Installation ID: {machine_id}" + (" (new local identity)" if shared_identity else ""))
    print(f"Configuration files: {len(files)}; migration: {'yes' if migrating else 'no'}")
    if migrating:
        print("Preserve local state: " + (", ".join(p.name for p in state) or "none"))
        print("Old shared databases are retained unchanged; other machines must deploy their own local runtime.")
    if args.dry_run:
        print("Dry run: no files changed. A new ID shown above is provisional until deployment.")
        return
    if migrating and rime_running(frontend):
        raise DeployError(f"Quit the {frontend} Rime frontend before --migrate; a running frontend was detected")
    # Preflight all managed paths before making any configuration changes.
    if not migrating and target.exists():
        for relative in files:
            check_destination(target, relative)
        check_destination(target, Path("installation.yaml"))
        if (target / "installation.yaml").is_symlink():
            raise DeployError("installation.yaml must be a local file, not a symlink")
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    backup = backup_root / stamp
    target.parent.mkdir(parents=True, exist_ok=True)
    lock_path = target.parent / ("." + target.name + ".deploy.lock")
    with lock_path.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise DeployError("Another deployment is already running") from error
        # Recheck after locking rather than using stale directory state.
        if target.is_symlink() != migrating or migrating and target.resolve() != old:
            raise DeployError("Rime user-directory target changed during deployment; retry")
        current_text = (old / "installation.yaml").read_text() if (old / "installation.yaml").is_file() else ""
        if current_text != text:
            raise DeployError("installation.yaml changed during deployment; retry")
        staging = Path(tempfile.mkdtemp(prefix=".rime-deploy-", dir=target.parent)) if migrating else target
        if not migrating:
            staging.mkdir(parents=True, exist_ok=True, mode=0o700)
        def save_backup(path, relative):
            destination = backup / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            if path.is_symlink():
                destination.symlink_to(os.readlink(path))
            else:
                shutil.copy2(path, destination)
        def write_file(src, relative, content=None):
            destination = staging / relative
            check_destination(staging, relative)
            if destination.is_file() and not destination.is_symlink():
                unchanged = (destination.read_text() == content) if content is not None else filecmp.cmp(src, destination, shallow=False)
                if unchanged:
                    return 0
            if destination.exists() or destination.is_symlink():
                save_backup(destination, relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(prefix=".rime-deploy-", dir=destination.parent)
            os.close(fd)
            try:
                if content is None:
                    shutil.copy2(src, temporary)
                else:
                    Path(temporary).write_text(content)
                os.replace(temporary, destination)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            return 1
        try:
            with unlocked_databases(old) if migrating else contextlib.nullcontext():
                if migrating:
                    for item in state:
                        if item.is_symlink():
                            raise DeployError(f"Runtime state is a symlink; migration refused: {item}")
                        if item.is_dir():
                            # Opening/closing the source LOCK file would release
                            # our POSIX lock. Rime creates a fresh destination lock.
                            shutil.copytree(item, staging / item.name,
                                            ignore=shutil.ignore_patterns("LOCK"))
                        else:
                            shutil.copy2(item, staging / item.name)
                changed = sum(write_file(source / relative, relative) for relative in files)
                changed += write_file(None, Path("installation.yaml"), updated)
                sync.mkdir(parents=True, exist_ok=True)
                if migrating:
                    backup.mkdir(parents=True, exist_ok=True)
                    os.replace(target, backup / "original-user-directory-link")
                    try:
                        os.replace(staging, target)
                    except BaseException:
                        os.replace(backup / "original-user-directory-link", target)
                        raise
        finally:
            if migrating and staging.exists() and staging != target:
                shutil.rmtree(staging)
        print(f"Deployed {changed} changed configuration files.")
        if backup.exists():
            print(f"Backup: {backup}")
        print("Next: start Rime and choose Deploy/Reload, then Synchronize user data.")
        print("Wait for Nextcloud to finish; run Synchronize user data on the other machine too.")
        print("Chinese and English Booster dictionaries use Rime's native snapshot merge; this script does not merge databases.")


parser = argparse.ArgumentParser(prog="deploy.sh", description="Deploy shared Rime configuration into a machine-local runtime (Python 3 standard library only).")
parser.add_argument("--source", default=sys.argv[1], help="shared configuration repository (default: script directory)")
parser.add_argument("--frontend", choices=("auto", "ibus", "fcitx5", "squirrel"), default="auto", help="auto selects Squirrel on macOS and IBus on Linux")
parser.add_argument("--user-dir", help="local Rime user directory; normally use the frontend default")
parser.add_argument("--sync-dir", help="Nextcloud snapshot directory (default: SOURCE/sync)")
parser.add_argument("--backup-dir", help="private backup root (default: XDG_STATE_HOME/rime-deploy/backups)")
parser.add_argument("--migrate", action="store_true", help="replace an existing user-directory symlink with a local directory, preserving stopped user databases")
parser.add_argument("--dry-run", action="store_true", help="print the deployment plan without changing files")
try:
    deploy(parser.parse_args(sys.argv[2:]))
except (DeployError, OSError, subprocess.SubprocessError) as error:
    print(f"deploy.sh: {error}", file=sys.stderr)
    sys.exit(1)
PY
