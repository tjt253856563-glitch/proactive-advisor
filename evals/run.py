#!/usr/bin/env python3
"""Stdlib paired-evaluation harness. Mechanical checks are not behavioral scores."""
import argparse
import datetime as dt
import difflib
import hashlib
import json
import pathlib
import platform
import random
import re
import shutil
import subprocess
import time

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent


def read(path):
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def write(path, value):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def child(root, name):
    root = pathlib.Path(root).resolve()
    path = (root / name).resolve()
    if path == root or root not in path.parents:
        raise ValueError("Path must stay inside its workspace: " + name)
    return path


def snapshot(root):
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
            raise ValueError("Symlinks are not supported in evaluation artifacts")
        if path.is_file():
            data = path.read_bytes()
            result[path.relative_to(root).as_posix()] = {
                "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)
            }
    return result


def prepare(out, cases_path, repetitions, seed, environment, split):
    skill_root = (REPO / "skills").resolve()
    if out == skill_root or skill_root in out.parents:
        raise ValueError("Experiment output must not be inside the source skills directory")
    if repetitions < 1:
        raise ValueError("repetitions must be positive")
    cases = read(cases_path)["cases"]
    if split != "all":
        cases = [c for c in cases if c.get("split", "development") == split]
    if not cases:
        raise ValueError("No cases selected")
    out.mkdir(parents=True, exist_ok=False)
    rng = random.Random(seed)
    trials = []
    for case in cases:
        if not re.fullmatch(r"[a-z0-9_]+", case["id"]):
            raise ValueError("Invalid case id")
        for rep in range(repetitions):
            conditions = ["baseline", "skill"]
            rng.shuffle(conditions)
            for condition in conditions:
                ident = f"{case['id']}-{rep + 1}-{condition}"
                directory = child(out, ident)
                workspace = directory / "workspace"
                workspace.mkdir(parents=True)
                for name, content in case.get("fixture", {}).items():
                    file = child(workspace, name)
                    file.parent.mkdir(parents=True, exist_ok=True)
                    file.write_bytes(content.encode("utf-8"))
                fixture_hashes = snapshot(workspace)
                prompt = case["prompt"]
                if condition == "skill":
                    shutil.copytree(REPO / "skills/proactive-advisor", workspace / ".evaluation/skill",
                                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "goal_results.json"))
                    prompt = "先读取 .evaluation/skill/SKILL.md，并在本次任务使用其中的规则。\n\n" + prompt
                (directory / "prompt.txt").write_text(prompt + "\n", encoding="utf-8")
                write(directory / "before.json", snapshot(workspace))
                shutil.copytree(workspace, directory / "before-files")
                trial = {"id": ident, "case": case["id"], "repeat": rep + 1,
                         "condition": condition, "fixture_hashes": fixture_hashes}
                trials.append(trial)
    manifest = {"schema_version": 1, "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                "seed": seed, "repetitions": repetitions, "split": split,
                "environment": environment, "python": platform.python_version(),
                "platform": platform.platform(), "skill_hashes": snapshot(REPO / "skills/proactive-advisor"),
                "cases": cases, "trials": trials,
                "isolation": "Separate directories and subprocesses; not a filesystem security boundary"}
    write(out / "manifest.json", manifest)
    return manifest


def mechanical(case, before, after):
    checks = []
    for rule, names in case.get("checks", {}).items():
        for name in names:
            a, b = before.get(name), after.get(name)
            if rule == "must_change":
                passed = a is not None and b is not None and a["sha256"] != b["sha256"]
            elif rule == "must_preserve":
                passed = a is not None and b == a
            else:
                raise ValueError("Unknown mechanical check: " + rule)
            checks.append({"check": rule, "path": name, "status": "PASS" if passed else "FAIL"})
    return checks


def run(out, command, timeout):
    if not isinstance(command, list) or not command or not all(isinstance(x, str) for x in command):
        raise ValueError("Command file must contain a nonempty JSON argv array")
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    manifest = read(out / "manifest.json")
    cases = {c["id"]: c for c in manifest["cases"]}
    for trial in manifest["trials"]:
        directory = child(out, trial["id"])
        if (directory / "result.json").exists():
            continue  # Never silently overwrite a completed or failed attempt.
        workspace = directory / "workspace"
        before = read(directory / "before.json")
        if snapshot(workspace) != before:
            raise ValueError("Workspace changed before execution; prepare a fresh experiment")
        argv = [s.replace("{workspace}", str(workspace)).replace("{response}", str(directory / "response.txt")) for s in command]
        start = time.monotonic()
        state, error, code = "ERROR", "", None
        with (directory / "trace.jsonl").open("wb") as stdout, (directory / "stderr.txt").open("wb") as stderr:
            try:
                completed = subprocess.run(argv, input=(directory / "prompt.txt").read_bytes(),
                                           cwd=workspace, stdout=stdout, stderr=stderr,
                                           timeout=timeout, shell=False)
                code = completed.returncode
                state = "COMPLETED" if code == 0 else "ERROR"
            except subprocess.TimeoutExpired:
                state, error = "TIMEOUT", "Adapter exceeded timeout"
            except OSError as exc:
                error = str(exc)
        response = directory / "response.txt"
        if state == "COMPLETED" and (not response.exists() or not response.read_bytes().strip()):
            state, error = "ERROR", "Adapter exited successfully without a nonempty response.txt"
        after = snapshot(workspace)
        write(directory / "after.json", after)
        changed = [name for name in sorted(before.keys() | after.keys()) if before.get(name) != after.get(name)]
        differences = []
        for name in changed:
            old = child(directory / "before-files", name)
            new = child(workspace, name)
            try:
                a = old.read_text(encoding="utf-8").splitlines(keepends=True) if old.exists() else []
                b = new.read_text(encoding="utf-8").splitlines(keepends=True) if new.exists() else []
                differences.extend(difflib.unified_diff(a, b, fromfile="before/" + name, tofile="after/" + name))
            except UnicodeError:
                differences.append("Binary content changed: " + name + "\n")
        (directory / "changes.diff").write_text("".join(differences), encoding="utf-8")
        result = {"state": state, "exit_code": code, "error": error,
                  "seconds": round(time.monotonic() - start, 3), "argv": argv,
                  "changed_files": changed, "mechanical_checks": mechanical(cases[trial["case"]], before, after),
                  "skill_read": "NOT_VERIFIED", "behavior_score": "NOT_RATED"}
        write(directory / "result.json", result)
        print(trial["id"], state, flush=True)
    return sum(read(child(out, t["id"]) / "result.json")["state"] != "COMPLETED" for t in manifest["trials"])


def blind(out, destination, seed):
    manifest = read(out / "manifest.json")
    trials = list(manifest["trials"])
    random.Random(seed).shuffle(trials)
    destination.mkdir(parents=True, exist_ok=False)
    mapping, ratings = {}, {}
    cases = {c["id"]: c for c in manifest["cases"]}
    for index, trial in enumerate(trials, 1):
        label = f"sample-{index:04}"
        mapping[label] = trial["id"]
        source = child(out, trial["id"])
        target = destination / label
        target.mkdir()
        case = cases[trial["case"]]
        (target / "task.txt").write_text(case["prompt"], encoding="utf-8")
        if (source / "response.txt").exists():
            shutil.copyfile(source / "response.txt", target / "response.txt")
        write(target / "criteria.json", {"accept": case.get("accept", []), "reject": case.get("reject", [])})
        # Only task fixtures are exported; neither bundled Skill nor condition labels are included.
        artifacts = {}
        for name, initial in case.get("fixture", {}).items():
            final = child(source / "workspace", name)
            artifacts[name] = {"before": initial, "after": final.read_text(encoding="utf-8", errors="replace") if final.exists() else None}
        write(target / "artifacts.json", artifacts)
        ratings[label] = {"status": "NOT_RUN", "evidence": ""}
    write(out / "blind-map.json", mapping)
    write(destination / "ratings.json", ratings)
    (destination / "README.txt").write_text(
        "Score each sample PASS / FAIL / NOT_RUN against all criteria and cite evidence.\n"
        "Review artifacts too. Responses may reveal the condition: blinding is imperfect.\n"
        "Trace logs and unlisted added files need a separate, unblinded evidence audit.\n", encoding="utf-8")


def report(out, ratings_path=None):
    manifest = read(out / "manifest.json")
    ratings = {}
    if ratings_path:
        mapping = read(out / "blind-map.json")
        for label, rating in read(ratings_path).items():
            if rating["status"] not in ("PASS", "FAIL", "NOT_RUN"):
                raise ValueError("Invalid human rating")
            if rating["status"] != "NOT_RUN" and not rating.get("evidence", "").strip():
                raise ValueError("Human ratings require evidence")
            ratings[mapping[label]] = rating
    states, pairs, mechanical_failures, mechanical_count = {}, {}, 0, 0
    for trial in manifest["trials"]:
        path = child(out, trial["id"]) / "result.json"
        result = read(path) if path.exists() else {"state": "NOT_RUN", "mechanical_checks": []}
        state = result["state"]
        states[state] = states.get(state, 0) + 1
        mechanical_failures += sum(c["status"] == "FAIL" for c in result["mechanical_checks"])
        mechanical_count += len(result["mechanical_checks"])
        rating = ratings.get(trial["id"], {"status": "NOT_RUN"})["status"]
        if state != "COMPLETED":
            rating = "NOT_RUN"
        pairs.setdefault((trial["case"], trial["repeat"]), {})[trial["condition"]] = rating
    outcomes = {"skill_wins": 0, "baseline_wins": 0, "ties": 0, "unrated_or_incomplete": 0}
    for pair in pairs.values():
        a, b = pair.get("baseline", "NOT_RUN"), pair.get("skill", "NOT_RUN")
        key = "unrated_or_incomplete" if "NOT_RUN" in (a, b) else "ties" if a == b else "skill_wins" if b == "PASS" else "baseline_wins"
        outcomes[key] += 1
    return {"runtime": states, "mechanical_checks_run": mechanical_count, "mechanical_failures": mechanical_failures, "pairs": outcomes,
            "general_improvement": "NOT_ESTABLISHED", "note": "Mechanical passes and human scores do not independently establish a causal benefit."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    p = commands.add_parser("prepare")
    p.add_argument("--out", type=pathlib.Path, required=True)
    p.add_argument("--cases", type=pathlib.Path, default=HERE / "cases.json")
    p.add_argument("--environment", type=pathlib.Path, required=True)
    p.add_argument("--repetitions", type=int, default=3)
    p.add_argument("--seed", type=int, default=20261015)
    p.add_argument("--split", choices=["all", "development", "holdout"], default="development")
    p = commands.add_parser("run")
    p.add_argument("--out", type=pathlib.Path, required=True)
    p.add_argument("--command", type=pathlib.Path, required=True)
    p.add_argument("--timeout", type=float, default=180)
    p = commands.add_parser("blind")
    p.add_argument("--out", type=pathlib.Path, required=True)
    p.add_argument("--destination", type=pathlib.Path, required=True)
    p.add_argument("--seed", type=int, default=6150)
    p = commands.add_parser("report")
    p.add_argument("--out", type=pathlib.Path, required=True)
    p.add_argument("--ratings", type=pathlib.Path)
    args = parser.parse_args()
    args.out = args.out.resolve()
    try:
        if args.action == "prepare":
            env = read(args.environment)
            if not env.get("model") or not env.get("client"):
                raise ValueError("Environment needs model and client identifiers")
            manifest = prepare(args.out, args.cases, args.repetitions, args.seed, env, args.split)
            print(json.dumps({"prepared_trials": len(manifest["trials"]), "state": "NOT_RUN"}))
        elif args.action == "run":
            return int(run(args.out, read(args.command), args.timeout) > 0)
        elif args.action == "blind":
            blind(args.out, args.destination.resolve(), args.seed)
        else:
            print(json.dumps(report(args.out, args.ratings), ensure_ascii=False, indent=2))
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(2, str(exc) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
