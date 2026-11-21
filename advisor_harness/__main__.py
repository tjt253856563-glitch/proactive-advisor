"""Single-run CLI with explicit controls. No background service is installed."""

import argparse
import json
import os
import sys
from pathlib import Path

from . import __version__
from .evidence import redact
from .policy import Blocked, Invalid, Policy
from .providers import provider_from
from .runtime import Session
from .store import Store


def parser():
    root = argparse.ArgumentParser(prog="python -m advisor_harness")
    root.add_argument("--version", action="version", version=__version__)
    root.add_argument("--db", type=Path, default=Path(".advisor/state.db"))
    sub = root.add_subparsers(dest="action", required=True)
    for verb in ("start", "resume", "revise"):
        command = sub.add_parser(verb)
        command.add_argument("--workspace", type=Path, required=True)
        command.add_argument("--policy", type=Path, required=True)
        command.add_argument("--provider", default=None, help="mock, ollama:MODEL, llama:MODEL or codex:MODEL")
        command.add_argument("--allow-trusted-tests", action="store_true")
        command.add_argument("--slice-seconds", type=int, default=None)
        if verb != "resume":
            command.add_argument("--goal", required=True)
            command.add_argument("--enqueue", "--plan-only", dest="plan_only", action="store_true", help="persist the goal for later execution")
        if verb != "start":
            command.add_argument("id")
    for verb in ("status", "pause", "cancel"):
        command = sub.add_parser(verb)
        command.add_argument("id")
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    if os.name == "nt":
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        with Store(args.db) as store:
            if args.action == "status":
                print(json.dumps(store.report(args.id), indent=2, ensure_ascii=False))
                return 0
            if args.action in {"pause", "cancel"}:
                goal = store.goal(args.id)
                if goal["status"] not in {"COMPLETED", "CANCELLED"}:
                    with store.conn:
                        store.conn.execute(
                            "UPDATE goals SET control=? WHERE id=? AND control!='cancel'", (args.action, args.id),
                        )
                        store.event(args.id, None, "operator_control", {"action": args.action})
                        if args.action == "cancel" and goal["status"] in {"PENDING", "FAILED", "BLOCKED"}:
                            store.transition("goals", args.id, "CANCELLED")
                            for task in store.tasks(args.id):
                                if task["status"] in {"PENDING", "FAILED", "BLOCKED"}:
                                    store.transition("tasks", args.id, "CANCELLED", task["id"])
                print(json.dumps({"id": args.id, "control": store.goal(args.id)["control"]}))
                return 0

            if args.slice_seconds is not None and not 1 <= args.slice_seconds <= 3600:
                raise Invalid("Slice seconds must be between 1 and 3600")
            if args.policy.resolve().is_relative_to(args.workspace.resolve()):
                raise Invalid("Keep the operator policy outside the model work directory")
            previous = store.goal(args.id) if args.action != "start" else None
            name = args.provider or (previous["provider"] if previous else None)
            if not name:
                raise Invalid("Select --provider mock, ollama:MODEL, llama:MODEL or codex:MODEL")
            provider = provider_from(name)
            session = Session(
                store, Policy.load(args.workspace, args.policy), provider,
                trusted=args.allow_trusted_tests, slice_seconds=args.slice_seconds,
            )
            goal = args.id if args.action == "resume" else session.create(
                args.goal, supersedes=args.id if args.action == "revise" else None,
            )
            print(json.dumps({"id": goal, "status": store.goal(goal)["status"]}), flush=True)
            if getattr(args, "plan_only", False):
                return 0
            outcome = session.run(goal, resume=args.action == "resume")
            print(json.dumps({"id": goal, "status": outcome, "result": store.goal(goal)["result"]},
                             ensure_ascii=False))
            return 0 if outcome == "COMPLETED" else 2
    except (Blocked, Invalid, OSError, ValueError) as exc:
        print(redact(str(exc)), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
