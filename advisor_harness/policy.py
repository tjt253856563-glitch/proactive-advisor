"""Load operator-owned capabilities and validate every workspace path."""

import hashlib
import json
import re
from pathlib import Path, PurePosixPath


class Blocked(Exception):
    """A required capability or manual decision is missing."""


class Invalid(Exception):
    """A goal, proposed operation, or configuration is invalid."""


class Stopped(Exception):
    def __init__(self, status, reason):
        super().__init__(reason)
        self.status = status


MAX_FILE = 128 * 1024
MAX_FILES = 128
SAFE_ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}\Z")
WINDOWS_DEVICE = re.compile(r"(?:CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|(?:COM|LPT)[1-9¹²³])\Z", re.I)
SECRET_PATH = re.compile(
    r"(^\.|(?:^|[_.-])(?:env|credentials?|secrets?|tokens?|auth|id_rsa|id_ed25519)"
    r"(?:[_.-]|$)|\.(?:pem|key|pfx|p12|kdbx)$)", re.I
)


def digest(data):
    return hashlib.sha256(data).hexdigest() if data is not None else None


def safe_name(name):
    if not isinstance(name, str) or not name or len(name) > 240:
        raise Invalid("Expected a workspace-relative file name")
    parts = name.split("/")
    for part in parts:
        if (not part or part in (".", "..") or part.endswith((" ", "."))
                or any(char in part for char in '\\:*?"<>|\x00\n\r')
                or any(ord(char) < 32 for char in part)
                or WINDOWS_DEVICE.fullmatch(part.split(".", 1)[0].rstrip(" ")) or SECRET_PATH.search(part)):
            raise Invalid("Path is not permitted by the workspace policy")
    return PurePosixPath(*parts).as_posix()


def unique_names(values):
    if not isinstance(values, list) or len(values) > MAX_FILES:
        raise Invalid("Invalid workspace file list")
    names = [safe_name(item) for item in values]
    if len({name.casefold() for name in names}) != len(names):
        raise Invalid("Duplicate workspace file name")
    return names


class Policy:
    def __init__(self, project, data):
        self.root = Path(project).resolve(strict=True)
        if not self.root.is_dir():
            raise Invalid("Workspace must be a directory")
        if not isinstance(data, dict) or not isinstance(data.get("limits", {}), dict):
            raise Invalid("Policy must be a JSON object with a limits object")
        self.data = data
        for option in ("probe_before_work", "evaluate_after_edit"):
            if option in data and type(data[option]) is not bool:
                raise Invalid(f"{option} must be a JSON boolean")
        self.files = unique_names(data.get("files", []))
        self.editable = unique_names(data.get("editable", []))
        self.visible = unique_names(data.get("visible", self.editable))
        if not set(self.editable + self.visible) <= set(self.files):
            raise Invalid("Editable and visible files must be listed in files")
        self.checks = data.get("checks", {})
        if not isinstance(self.checks, dict) or len(self.checks) > 32:
            raise Invalid("Expected up to 32 named checks")
        allowed = {"command", "exists", "contains", "changed", "unchanged", "sha256", "manual"}
        for name, check in self.checks.items():
            if not SAFE_ID.fullmatch(name) or not isinstance(check, dict) or check.get("kind") not in allowed:
                raise Invalid("Invalid check definition")
            for key in ("required", "regression", "replayable"):
                if key in check and type(check[key]) is not bool:
                    raise Invalid("Check flags must be JSON booleans")
            for key in ("feature", "description"):
                if key in check and (not isinstance(check[key], str) or len(check[key]) > 500):
                    raise Invalid("Check labels must be short text strings")
            if check["kind"] == "manual" and check.get("regression"):
                raise Invalid("Manual checks cannot run as regressions")
            if check["kind"] in allowed - {"manual", "command"}:
                if safe_name(check.get("path")) not in self.files:
                    raise Invalid("File check path is outside the policy")
                if check["kind"] in {"contains", "sha256"} and not isinstance(check.get("value"), str):
                    raise Invalid("File comparison requires a UTF-8 value or SHA-256")
                if check["kind"] == "sha256" and not re.fullmatch(r"[a-f0-9]{64}", check["value"]):
                    raise Invalid("Invalid SHA-256 condition")
            if check["kind"] == "command":
                argv = check.get("argv")
                if (not isinstance(argv, list) or not argv or len(argv) > 24
                        or not all(isinstance(arg, str) and arg and "\x00" not in arg for arg in argv)):
                    raise Invalid("Expected an operator-approved argv array")
                if check.get("execution", "isolated") not in {"isolated", "trusted"}:
                    raise Invalid("Invalid command execution mode")
                if type(check.get("exit", 0)) is not int:
                    raise Invalid("Expected an integer exit code")
                if "stdout_contains" in check and not isinstance(check["stdout_contains"], str):
                    raise Invalid("Invalid stdout condition")
        self.regressions = [name for name, check in self.checks.items() if check.get("regression")]
        self.required = [name for name, check in self.checks.items() if check.get("required", True)]
        self.limits = {}
        for name, default, upper in [
            ("seconds", 300, 3600), ("model_calls", 18, 100), ("commands", 16, 100),
            ("repair_rounds", 3, 3), ("command_seconds", 30, 300),
        ]:
            value = data.get("limits", {}).get(name, default)
            if type(value) is not int or not 1 <= value <= upper:
                raise Invalid(f"Expected an integer from 1 to {upper} for {name}")
            self.limits[name] = value

    @classmethod
    def load(cls, workspace, path):
        if Path(path).stat().st_size > MAX_FILE:
            raise Invalid("Policy exceeds the size limit")
        return cls(workspace, json.loads(Path(path).read_text(encoding="utf-8")))

    def path(self, name, *, write=False):
        name = safe_name(name)
        if name not in (self.editable if write else self.files):
            raise Blocked("File is outside the authorized capability")
        current = self.root
        for part in name.split("/"):
            current = current / part
            if current.is_symlink() or current.resolve() != current:
                raise Blocked("Linked workspace paths are blocked")
        if current.exists() and (not current.is_file() or current.stat().st_nlink != 1):
            raise Blocked("Expected a regular workspace file without hard links")
        return current

    def read(self, name):
        file = self.path(name)
        try:
            with file.open("rb") as stream:
                data = stream.read(MAX_FILE + 1)
        except FileNotFoundError:
            return None
        if len(data) > MAX_FILE:
            raise Blocked("Workspace file exceeds the size limit")
        return data

    def snapshot(self):
        return {name: digest(self.read(name)) for name in self.files}

    def model_context(self):
        return {
            "visible": self.visible, "editable": self.editable,
            "checks": {name: {"kind": value["kind"], "description": value.get("description", "")}
                       for name, value in self.checks.items()},
            "required": self.required,
        }
