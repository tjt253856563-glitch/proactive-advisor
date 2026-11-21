"""Evaluate operator-owned conditions independently of model output."""

import hashlib
import re

from .policy import Blocked, digest
from .process import run_test


def fingerprint(check, result):
    detail = result.get("stderr") or result.get("stdout") or result.get("reason", "")
    lines = [
        line.strip() for line in detail.splitlines()
        if re.search(r"(Error|Exception|FAIL|expected|actual|Traceback)", line, re.I)
        and not re.search(r"\b(failures|errors)=\d+", line)
    ]
    cleaned = re.sub(r"(line |0x)\d+[0-9a-f]*", r"\1#", "\n".join(lines)[-2000:])
    raw = f"{check}|{result['status']}|{result.get('exit_code')}|{cleaned}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


class Evaluator:
    def __init__(self, session):
        self.session = session

    def run(self, names, task=None, *, purpose):
        results = []
        for name in dict.fromkeys(names):
            self.session.guard()
            data = self.one(name, task, purpose)
            with self.session.store.conn:
                event = self.session.store.event(self.session.goal, task, "evaluation", data)
                test_ref = f"check:{name}"
                source = f"task:{task}" if task else f"goal:{self.session.goal}"
                self.session.store.edge(self.session.goal, source, "acceptance", test_ref)
                if data.get("feature"):
                    self.session.store.edge(self.session.goal, test_ref, "verifies", f"feature:{data['feature']}")
                self.session.store.edge(self.session.goal, test_ref, "result", f"event:{event}")
            results.append({**data, "event": event})
        return results

    def one(self, name, task, purpose):
        session = self.session
        policy = session.policy
        spec = policy.checks[name]
        kind = spec["kind"]
        result = {
            "id": name, "kind": kind, "purpose": purpose, "feature": spec.get("feature", name),
        }
        if kind == "manual":
            return dict(result, status="NOT_RUN", reason=spec.get("description", "Manual review required"))
        try:
            if kind == "command":
                info = session.command(name, task, spec, purpose)
                result.update(info)
                if info["timed_out"]:
                    return dict(result, status="ERROR", reason="Command timed out")
                passed = info["exit_code"] == spec.get("exit", 0)
                if "stdout_contains" in spec:
                    passed &= spec["stdout_contains"] in info["stdout"]
                return dict(result, status="PASS" if passed else "FAIL")

            data = policy.read(spec["path"])
            actual = digest(data)
            before = session.store.goal(session.goal)["initial"][spec["path"]]
            result.update(path=spec["path"], before_sha256=before, actual_sha256=actual)
            if kind == "exists":
                passed = data is not None
            elif kind == "contains":
                passed = data is not None and spec["value"].encode() in data
            elif kind == "sha256":
                passed = actual == spec["value"]
            elif kind == "changed":
                passed = actual is not None and actual != before
            else:
                passed = actual == before
            return dict(result, status="PASS" if passed else "FAIL")
        except Blocked as exc:
            return dict(result, status="BLOCKED", reason=str(exc))
        except OSError as exc:
            return dict(result, status="ERROR", reason=str(exc))
