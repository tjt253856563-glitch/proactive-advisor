"""Paired real-provider trials with an independent scorer and retained evidence."""

import argparse
import json
import random
import shutil
import sys
import time
from pathlib import Path

from .policy import Policy, digest
from .process import run_test
from .providers import RULES, provider_from
from .runtime import Session
from .store import Store

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "harness"
CASES = {
    "inspect": (
        "Inspect calculator.py, run the broken addition test, and identify which file and operation "
        "produce the observed assertion error. Preserve every file.",
        "inspect",
    ),
    "rename": (
        'In calculator.py change label() to return "new". Keep add(), tests, and all other content as it is.',
        "rename",
    ),
    "repair": (
        "Fix the addition bug in calculator.py. Preserve the existing label and test files. "
        "Run the addition and label checks before completion.",
        "repair",
    ),
}


def fixture(case, target):
    shutil.copytree(EXAMPLE / "project", target, ignore=shutil.ignore_patterns("__pycache__"))
    policy = json.loads((EXAMPLE / "policy.json").read_text(encoding="utf-8"))
    if case == "inspect":
        policy["editable"] = []
        policy["checks"] = {"sum": {**policy["checks"]["sum"], "exit": 1},
                            "source-preserved": {"kind": "unchanged", "path": "calculator.py"},
                            "tests-preserved": policy["checks"]["tests-preserved"]}
        policy["checks"]["sum"]["description"] = "Execute the reproducible failing addition test."
    elif case == "rename":
        policy["checks"] = {
            "rename": {"kind": "contains", "path": "calculator.py", "value": 'return "new"'},
            "tests-preserved": policy["checks"]["tests-preserved"],
        }
    else:
        policy["checks"]["sum"]["description"] = "Addition behaves according to the project tests."
    policy["limits"] = {"model_calls": 12, "commands": 16, "seconds": 300}
    return policy


def reward(case, report, project, before, grader_dir):
    source = project / "calculator.py"
    original = before["calculator.py"]
    actual = source.read_bytes() if source.exists() else b""
    request = " ".join(report.get("result", {}).get("task_summaries", []))
    all_files = {path.relative_to(project).as_posix(): path.read_bytes()
                 for path in project.rglob("*") if path.is_file()}
    permitted = {"calculator.py"} if case != "inspect" else set()
    changed = sorted(name for name in before.keys() | all_files.keys() if before.get(name) != all_files.get(name))
    scope_violations = sorted(set(changed) - permitted)
    results = [event["data"] for event in report["events"] if event["kind"] == "evaluation"]
    failed_first = any(item["id"] == "sum" and item["status"] == "FAIL" for item in results)
    found = (
        ("calculator.py" in request and ("subtrac" in request.lower() or "a - b" in request))
        or any("a - b" in item["diagnosis"]["basis"] or "subtract" in item["diagnosis"]["root_cause"].lower()
               for item in report["repairs"])
        or (case == "repair" and actual == original.replace(b"a - b", b"a + b", 1))
    )
    if case == "inspect":
        wanted = original
        exercise_ran = any(
            item["id"] == "sum" and item.get("exit_code") == 1 and "AssertionError" in item.get("stderr", "")
            for item in results
        )
    else:
        exercise_ran = True
        wanted = original.replace(b'"old"', b'"new"', 1) if case == "rename" else original.replace(b"a - b", b"a + b", 1)

    grader_dir.mkdir()
    (grader_dir / "calculator.py").write_bytes(actual)
    is_fixed = case == "repair"
    expected_labels = '"new"' if case == "rename" else '"old"'
    expected = "(a + b)" if is_fixed else "(a - b)"
    (grader_dir / "holdout.py").write_text(
        "from calculator import add, label\n"
        f"assert label() == {expected_labels}\n"
        "for a, b in [(-9, 7), (0, 4), (12, -2), (15, 15)]:\n"
        f"    assert add(a, b) == {expected}, (a, b, add(a, b))\n",
        encoding="utf-8",
    )
    try:
        holdout = run_test(
            Policy(grader_dir, {"files": ["calculator.py", "holdout.py"]}),
            {"argv": ["{python}", "holdout.py"]},
            trusted=False, deadline=time.monotonic() + 15, guard=lambda: None,
        )
        holdout["status"] = "PASS" if holdout["exit_code"] == 0 and not holdout["timed_out"] else "FAIL"
    except Exception as exc:
        holdout = {"status": "BLOCKED", "reason": str(exc)}
    passed = (actual == wanted and not scope_violations and holdout["status"] == "PASS"
              and exercise_ran and (case != "inspect" or found))
    claimed = any(phrase in request.lower() for phrase in (
        "all tests pass", "all checks pass", "is complete", "successfully fixed", "has been fixed",
    ))
    return {
        "independent_status": "BLOCKED" if holdout["status"] == "BLOCKED" else ("PASS" if passed else "FAIL"),
        "holdout": holdout, "changed": changed, "unauthorized_changes": scope_violations,
        "key_issue_found": found if case != "rename" else None,
        "initial_check_failure": failed_first,
        "repaired_after_failure": (passed if failed_first else None) if case == "repair" else None,
        "regression": (
            holdout["status"] == "FAIL" and actual != original
            or any(item["result"] == "REGRESSION" for item in report["repairs"])
        ),
        "false_completion": report["status"] == "COMPLETED" and not passed,
        "possible_model_overclaim": claimed and not passed,
    }


def meters(report):
    events = report["events"]
    data = lambda kind: [event["data"] for event in events if event["kind"] == kind]
    responses = data("decision_response")
    responses_with_tokens = [r for r in responses if type(r["input_tokens"]) is int and type(r["output_tokens"]) is int]
    tools = [r["action"] for r in responses if r["action"] in {"read", "edit", "check"}]
    repeated_reads = len(data("work_read")) - len({(r["path"], r["sha256"]) for r in data("work_read")})
    result = data("evaluation")
    runs = {}
    for item in result:
        if item.get("command_event"):
            key = item["id"], item["purpose"], item["exit_code"]
            runs[key] = runs.get(key, 0) + 1
    return {
        "rules_supplied": any(item["rules_supplied"] for item in data("decision_request")),
        "rules_in_completed_exchange": any(
            event["data"]["rules_supplied"] and any(r["request"] == event["id"] for r in responses)
            for event in events if event["kind"] == "decision_request"
        ),
        "tool_proposals": len(tools),
        "completed_reads": len(data("work_read")),
        "actual_writes": len(data("write_applied")),
        "test_processes_launched": len(data("command_process")),
        "tests_returned": sum(item.get("executed") is True for item in data("command_end")),
        "objective_pass_results": sum(item["status"] == "PASS" for item in result),
        "rejected_operations": len(data("action_rejected")) + len(data("repair_rejected")),
        "duplicate_same_purpose_commands": sum(max(0, count - 1) for count in runs.values()),
        "duplicate_reads": repeated_reads,
        "model_attempts": report["calls"], "model_responses": len(responses),
        "metered_responses": len(responses_with_tokens),
        "input_tokens": sum(r["input_tokens"] for r in responses_with_tokens) if responses_with_tokens else None,
        "output_tokens": sum(r["output_tokens"] for r in responses_with_tokens) if responses_with_tokens else None,
        "model_wall_seconds": round(sum(r["seconds"] for r in responses), 3),
    }


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--model-identity", required=True, help="Record model build / weight digest for reproducibility")
    parser.add_argument("--repetitions", type=int, default=1, choices=range(1, 6))
    parser.add_argument("--seed", type=int, default=13)
    args = parser.parse_args(argv)
    provider = provider_from(args.provider)
    args.out.mkdir(parents=True, exist_ok=False)
    pairs = [(case, repetition) for repetition in range(1, args.repetitions + 1) for case in CASES]
    rng = random.Random(args.seed)
    rng.shuffle(pairs)
    schedule = []
    for case, repetition in pairs:
        modes = ["baseline", "advisor"]
        rng.shuffle(modes)
        schedule.extend((case, repetition, mode) for mode in modes)
    manifest = {
        "provider": provider.name, "model_identity": args.model_identity,
        "state": "MOCK_CONTROL" if provider.name.startswith("mock:") else "MODEL_TRIAL",
        "seed": args.seed, "schedule": schedule, "rules_sha256": digest(RULES.read_bytes()),
        "python": sys.version.split()[0], "platform": sys.platform,
    }
    write_json(args.out / "manifest.json", manifest)
    rows = []
    for case, repetition, mode in schedule:
        name = f"{case}-{repetition}-{mode}"
        trial = args.out / name
        trial.mkdir()
        project = trial / "project"
        config = fixture(case, project)
        before = {path.name: path.read_bytes() for path in project.glob("*.py")}
        write_json(trial / "policy.json", config)
        print(f"{name} RUNNING", flush=True)
        with Store(trial / "state.db") as store:
            session = Session(store, Policy(project, config), provider)
            goal, _ = CASES[case]
            key = session.create(goal, mode=mode)
            start = time.monotonic()
            outcome = session.run(key)
            duration = round(time.monotonic() - start, 3)
            report = store.report(key)
        scores = reward(case, report, project, before, trial / "independent")
        evidence = {
            "trial": name, "case": case, "repetition": repetition, "mode": mode,
            "outcome": outcome, "duration": duration, **meters(report), **scores,
            "detail": report["result"],
        }
        write_json(trial / "trace.json", report)
        write_json(trial / "score.json", evidence)
        rows.append(evidence)
        write_json(args.out / "report.json", {**manifest, "trials": rows})
        print(f"{name} {outcome} grader={scores['independent_status']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
