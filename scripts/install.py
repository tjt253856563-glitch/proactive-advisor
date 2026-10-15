#!/usr/bin/env python3
"""Project-scoped copy installation with collision and modification protection."""
import argparse
import hashlib
import json
import pathlib
import shutil

SOURCE = pathlib.Path(__file__).resolve().parents[1] / "skills/proactive-advisor"
RECEIPT = ".proactive-advisor-install.json"


def linked(path):
    if path.is_symlink():
        return True
    try:
        return bool(getattr(path.lstat(), "st_file_attributes", 0) & 0x400)
    except FileNotFoundError:
        return False


def hashes(root):
    result = {}
    for path in root.rglob("*"):
        if linked(path):
            raise ValueError("Symlink in skill directory; inspect it manually")
        if path.is_file() and path != root / RECEIPT:
            result[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def target(project):
    project = pathlib.Path(project).resolve(strict=True)
    if not project.is_dir():
        raise ValueError("Project must be a directory")
    path = project
    for part in (".agents", "skills", "proactive-advisor"):
        path = path / part
        if linked(path):
            raise ValueError("Install path contains a symlink or junction")
    if project not in path.resolve().parents:
        raise ValueError("Install path escaped the project")
    return path


def install(project):
    destination = target(project)
    if destination.exists():
        raise ValueError("Destination exists; no files overwritten")
    expected = {k: v for k, v in hashes(SOURCE).items()
                if "__pycache__" not in pathlib.PurePosixPath(k).parts
                and not k.endswith(".pyc") and pathlib.PurePosixPath(k).name != "goal_results.json"}
    if not expected or "SKILL.md" not in expected:
        raise ValueError("Missing source skill")
    shutil.copytree(SOURCE, destination, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "goal_results.json"))
    actual = hashes(destination)
    if actual != expected:
        raise ValueError("Copied files failed checksum verification")
    (destination / RECEIPT).write_text(json.dumps(actual, indent=2) + "\n", encoding="utf-8")
    return destination


def uninstall(project):
    destination = target(project)
    receipt = destination / RECEIPT
    if not receipt.exists() or receipt.is_symlink():
        raise ValueError("No installer receipt; inspect and remove manually")
    expected = json.loads(receipt.read_text(encoding="utf-8"))
    if hashes(destination) != expected:
        raise ValueError("Installed files changed or were added; back them up and inspect manually")
    shutil.rmtree(destination)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["install", "uninstall"])
    parser.add_argument("--project", type=pathlib.Path, required=True)
    args = parser.parse_args()
    try:
        path = install(args.project) if args.action == "install" else uninstall(args.project)
    except (ValueError, OSError) as exc:
        parser.exit(2, str(exc) + "\n")
    print(args.action + ": " + str(path))


if __name__ == "__main__":
    main()
