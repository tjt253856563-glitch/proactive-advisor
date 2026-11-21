#!/usr/bin/env python3
"""Install or remove an isolated, user-level copy of the standard-library runtime."""

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "advisor-install.json"
INCLUDE = (
    "advisor_harness", "examples/harness", "docs/harness", "skills/proactive-advisor",
    "scripts/run-harness-demo.ps1", "scripts/install_harness.py", "LICENSE",
)


def inventory(root):
    files = {}
    for path in root.rglob("*"):
        if path.is_symlink() or path.resolve() != path:
            raise ValueError("Linked paths prevent automatic removal")
        name = path.relative_to(root).as_posix()
        if name == MANIFEST:
            continue
        if path.is_file():
            files[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        elif path.is_dir():
            files[name + "/"] = None
        else:
            raise ValueError("Unexpected file type in installation")
    return files


def install(destination):
    if destination.exists():
        raise ValueError(f"Destination already exists: {destination}")
    if destination.is_relative_to(ROOT):
        raise ValueError("Choose a destination outside the source repository")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="advisor-install-", dir=destination.parent) as staging:
        package = Path(staging) / "install"
        for name in INCLUDE:
            source = ROOT / name
            target = package / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            else:
                shutil.copy2(source, target)
        (package / MANIFEST).write_text(json.dumps({"files": inventory(package)}, indent=2), encoding="utf-8")
        if destination.exists():
            raise ValueError(f"Destination was created during install: {destination}")
        package.rename(destination)


def uninstall(destination):
    marker = destination / MANIFEST
    if marker.is_symlink() or not marker.is_file():
        raise ValueError("Installation receipt is absent")
    recorded = json.loads(marker.read_text(encoding="utf-8"))["files"]
    if inventory(destination) != recorded:
        raise ValueError("Installation contains changes or user data. All files were preserved.")
    # A receipt permits removal only of the copies named in the verified installation.
    for name in recorded:
        if not name.endswith("/"):
            (destination / name).unlink()
    marker.unlink()
    for name in sorted((name for name in recorded if name.endswith("/")),
                       key=lambda name: name.count("/"), reverse=True):
        (destination / name).rmdir()
    destination.rmdir()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["install", "uninstall"])
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args(argv)
    if sys.version_info < (3, 10):
        parser.error("Python 3.10 or newer is required")
    try:
        if args.destination.is_symlink() or args.destination.absolute().resolve() != args.destination.absolute():
            raise ValueError("Choose an unlinked installation destination without parent-relative components")
        destination = args.destination.resolve()
        if args.operation == "install":
            install(destination)
        else:
            uninstall(destination)
        print(destination)
        return 0
    except (OSError, ValueError, KeyError) as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
