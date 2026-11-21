"""The goal state machine. Only this layer can execute a proposed action."""

import difflib
import hashlib
import os
import tempfile
import time
from pathlib import Path

from .evaluation import Evaluator, fingerprint
from .evidence import clean, contains_secret
from .policy import Blocked, Invalid, MAX_FILE, SAFE_ID, Stopped, digest
from .process import run_test
from .providers import REVIEW_TAGS, RULES, make_prompt
from .store import json_text, workspace_lock


class StaleEdit(Invalid):
    """A proposal could be corrected by rereading already authorized source."""


def text_field(data, field, limit=2000, default=None):
    value = data.get(field, default)
    if not isinstance(value, str) or len(value) > limit:
        raise Invalid(f"Invalid decision field: {field}")
    return value


def identifiers(values):
    if (not isinstance(values, list) or len(values) > 32
            or not all(isinstance(item, str) and SAFE_ID.fullmatch(item) for item in values)
            or len(set(values)) != len(values)):
        raise Invalid("Invalid list of identifiers")
    return values


def validate_plan(value, policy):
    level = value.get("level")
    tasks = value.get("tasks")
    constraints = value.get("constraints", [])
    review = value.get("review", [])
    if type(level) is not int or level not in range(4) or not isinstance(tasks, list) or len(tasks) > 12:
        raise Invalid("Invalid plan level or task list")
    if (not isinstance(constraints, list) or len(constraints) > 16
            or not all(isinstance(item, str) and len(item) <= 500 for item in constraints)):
        raise Invalid("Invalid plan constraints")
    if not isinstance(review, list) or len(review) > 8 or not all(isinstance(item, dict) for item in review):
        raise Invalid("Invalid plan review")
    findings = []
    for item in review:
        if item.get("tag") not in REVIEW_TAGS:
            raise Invalid("Review must use a known internal tag")
        findings.append({key: text_field(item, key, 500) for key in ("tag", "issue", "impact", "verification")})

    normalized = []
    for item in tasks:
        if not isinstance(item, dict):
            raise Invalid("Invalid task")
        task_id = text_field(item, "id", 64)
        priority = item.get("priority", 0)
        checks = identifiers(item.get("checks"))
        deps = identifiers(item.get("depends", []))
        if not SAFE_ID.fullmatch(task_id) or type(priority) is not int or not 0 <= priority <= 100:
            raise Invalid("Invalid task id or priority")
        if not set(checks) <= policy.checks.keys() or (not checks and len(tasks) != 1):
            raise Invalid("Each task needs configured checks as acceptance criteria")
        normalized.append({
            "id": task_id, "title": text_field(item, "title", 500),
            "checks": checks, "depends": deps, "priority": priority,
        })

    task_ids = {task["id"] for task in normalized}
    if len(task_ids) != len(normalized):
        raise Invalid("Duplicate task id")
    ordered = []
    waiting = {task["id"]: task for task in normalized}
    while waiting:
        ready = [task for task in waiting.values() if set(task["depends"]) <= task_ids - waiting.keys()]
        if not ready:
            raise Invalid("Task dependencies are cyclic or reference an unknown task")
        next_task = max(ready, key=lambda task: task["priority"])
        ordered.append(next_task)
        del waiting[next_task["id"]]

    covered = {name for task in normalized for name in task["checks"]}
    if ordered:
        missing = [name for name in policy.required if name not in covered]
        ordered[-1]["checks"].extend(missing)
        if any(not task["checks"] for task in ordered):
            raise Invalid("Each task must map to acceptance checks")
    if not ordered and (level > 1 or policy.required):
        raise Invalid("Complex goals need operator-configured acceptance checks")
    if ordered and level < 2:
        level = 2
    answer = text_field(value, "answer", 4000, default="")
    if not ordered and not answer.strip():
        raise Invalid("Simple goal needs a direct answer")
    return clean({
        "level": level, "goal": text_field(value, "goal"), "constraints": constraints,
        "tasks": ordered, "review": findings, "answer": answer,
    })


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
    fd, temporary = tempfile.mkstemp(prefix=".advisor-write-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
        if os.name == "posix":
            dir_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
    finally:
        Path(temporary).unlink(missing_ok=True)


class Session:
    def __init__(self, store, policy, provider, *, trusted=False, slice_seconds=None):
        self.store = store
        self.policy = policy
        self.provider = provider
        self.trusted = trusted
        self.slice_seconds = slice_seconds
        self.policy_hash = digest(json_text(policy.data).encode())
        self.lock = store.path.parent / "locks" / (
            hashlib.sha256(os.path.normcase(str(policy.root)).encode()).hexdigest() + ".lock"
        )
        self.rules = RULES.read_text(encoding="utf-8")
        self.evaluator = Evaluator(self)
        self.goal = None
        self.deadline = None

    def create(self, request, *, mode="advisor", supersedes=None):
        if not isinstance(request, str) or not request.strip() or len(request) > 6000:
            raise Invalid("Provide a natural-language goal of at most 6000 characters")
        if mode not in {"advisor", "baseline"}:
            raise Invalid("Unknown execution mode")
        with workspace_lock(self.lock):
            return self.store.new(
                self.policy.root, self.policy_hash, request, self.provider.name, mode,
                self.policy.snapshot(), supersedes,
            )

    def run(self, goal, *, resume=False):
        self.goal = goal
        conn = self.store.conn
        with workspace_lock(self.lock):
            state = self.store.goal(goal)
            if (state["root"] != str(self.policy.root) or state["policy_digest"] != self.policy_hash
                    or state["provider"] != self.provider.name):
                raise Invalid("Resume requires the original workspace, policy and provider")
            if state["status"] in {"COMPLETED", "CANCELLED"}:
                return state["status"]
            if state["control"] == "cancel":
                return self.stop("CANCELLED", "Cancelled by operator")
            if state["status"] != "PENDING" and not resume:
                raise Blocked("Explicit resume is required for interrupted or blocked work")
            self._begin(state)
            try:
                self.guard()
                self.reconcile()
                return self.run_goal()
            except KeyboardInterrupt:
                return self.stop("BLOCKED", "Interrupted. Resume after checking the journal.")
            except Stopped as exc:
                return self.stop(exc.status, str(exc))
            except (Blocked, Invalid, OSError, UnicodeError) as exc:
                return self.stop("BLOCKED", str(exc))
            finally:
                with conn:
                    conn.execute(
                        "UPDATE goals SET elapsed=elapsed+max(0,?-started),started=NULL,heartbeat=NULL "
                        "WHERE id=? AND started IS NOT NULL", (time.time(), goal),
                    )

    def _begin(self, state):
        now = time.time()
        spent = state["elapsed"]
        if state["started"] is not None:
            spent += max(0, min(now, (state["heartbeat"] or state["started"]) + 1) - state["started"])
        remaining = self.policy.limits["seconds"] - spent
        self.next_heartbeat = time.monotonic() + 1
        self.budget_deadline = time.monotonic() + max(0, remaining)
        self.deadline = min(self.budget_deadline, time.monotonic() + self.slice_seconds) if self.slice_seconds else self.budget_deadline
        with self.store.conn:
            self.store.transition("goals", self.goal, "RUNNING")
            self.store.conn.execute(
                "UPDATE goals SET elapsed=?,started=?,heartbeat=?,control='run' WHERE id=? AND control!='cancel'",
                (spent, now, now, self.goal),
            )

    def guard(self):
        state = self.store.conn.execute("SELECT control FROM goals WHERE id=?", (self.goal,)).fetchone()
        if state["control"] == "cancel":
            raise Stopped("CANCELLED", "Cancelled by operator")
        if state["control"] == "pause":
            raise Stopped("BLOCKED", "Paused by operator")
        now = time.monotonic()
        if now >= self.deadline:
            reason = "Goal time budget exhausted" if now >= self.budget_deadline else "Run time slice ended"
            raise Stopped("BLOCKED", reason)
        if now >= self.next_heartbeat:
            self.next_heartbeat = now + 1
            with self.store.conn:
                self.store.conn.execute("UPDATE goals SET heartbeat=? WHERE id=?", (time.time(), self.goal))

    def stop(self, status, reason):
        with self.store.conn:
            self.store.transition("goals", self.goal, status)
            for task in self.store.tasks(self.goal):
                if task["status"] == "RUNNING" or (status == "BLOCKED" and task["status"] == "FAILED") or (
                        status == "CANCELLED" and task["status"] in {"FAILED", "BLOCKED", "PENDING"}):
                    self.store.transition("tasks", self.goal, status, task["id"])
            self.store.event(self.goal, None, "stopped", {"status": status, "reason": reason})
            self.store.conn.execute(
                "UPDATE goals SET result=? WHERE id=?", (json_text(clean({"reason": reason})), self.goal),
            )
        return status

    def checkpoint(self):
        expected = self.store.goal(self.goal)["checkpoint"]
        actual = self.policy.snapshot()
        if expected != actual:
            names = sorted(name for name in expected if expected[name] != actual[name])
            raise Blocked("Workspace differs from the checkpoint: " + ", ".join(names))
        return actual

    def reconcile(self):
        conn = self.store.conn
        pending = conn.execute(
            "SELECT * FROM writes WHERE goal=? AND status IN ('PREPARED','UNDOING') ORDER BY id", (self.goal,),
        ).fetchall()
        for row in pending:
            actual = digest(self.policy.read(row["path"]))
            if actual not in {row["old_hash"], row["new_hash"]}:
                raise Blocked(f"Interrupted edit conflicts with workspace file {row['path']}")
            if row["status"] == "UNDOING" and actual == row["new_hash"]:
                self.undo(row)
            else:
                with conn:
                    outcome = "UNDONE" if row["status"] == "UNDOING" else (
                        "APPLIED" if actual == row["new_hash"] else "NOT_APPLIED"
                    )
                    self.record_write(row, actual, outcome)
                    self.store.event(self.goal, row["task"], "recovered_write", {
                        "id": row["id"], "path": row["path"], "status": outcome,
                    })
        self.checkpoint()

        events = self.store.events(self.goal)
        finished = {event["data"]["start"]: event["data"] for event in events if event["kind"] == "command_end"}
        for event in events:
            if event["kind"] != "command_start":
                continue
            end = finished.get(event["id"])
            if end and end["status"] != "INTERRUPTED":
                continue
            if not event["data"]["replayable"]:
                raise Blocked("Interrupted trusted command may have external side effects. Resolve it before revising the goal.")
            if end is None:
                with conn:
                    self.store.event(self.goal, event["task"], "command_end", {
                        "start": event["id"], "status": "INTERRUPTED", "safe_replay": True,
                    })

    def decide(self, phase, data, task=None):
        conn = self.store.conn
        self.guard()
        state = self.store.goal(self.goal)
        if state["calls"] >= self.policy.limits["model_calls"]:
            raise Blocked("Model call budget exhausted")
        advisor = state["mode"] == "advisor"
        prompt = make_prompt(phase, dict(data, goal=state["request"]), advisor=advisor, rules=self.rules)
        if len(prompt.encode()) > 96 * 1024:
            raise Blocked("Decision input exceeds the context budget")
        with conn:
            conn.execute("UPDATE goals SET calls=calls+1 WHERE id=?", (self.goal,))
            event = self.store.event(self.goal, task, "decision_request", {
                "phase": phase, "provider": self.provider.name, "rules_supplied": advisor,
                "rules_sha256": digest(self.rules.encode()) if advisor else None,
            })
        started = time.monotonic()
        decision = self.provider.decide(prompt, deadline=self.deadline, guard=self.guard)
        with conn:
            self.store.event(self.goal, task, "decision_response", {
                "request": event, "action": decision.value.get("action"), "input_tokens": decision.input_tokens,
                "error": decision.error,
                "output_tokens": decision.output_tokens, "seconds": round(time.monotonic() - started, 4),
            })
        self.guard()
        if decision.error:
            raise Invalid(decision.error)
        return decision.value

    def make_plan(self):
        conn = self.store.conn
        data = {"policy": self.policy.model_context()}
        for attempt in range(2):
            try:
                plan = validate_plan(self.decide("plan", data), self.policy)
                break
            except Invalid as exc:
                with conn:
                    self.store.event(self.goal, None, "invalid_plan", {"reason": str(exc)})
                if attempt:
                    raise
                data["previous_issue"] = str(exc)
                data["retry"] = "Keep the schema concise. Use the exact configured check ids."
        with conn:
            conn.execute("UPDATE goals SET plan=? WHERE id=?", (json_text(plan), self.goal))
            for task in plan["tasks"]:
                conn.execute(
                    "INSERT INTO tasks(goal,id,status,spec) VALUES (?,?,'PENDING',?)",
                    (self.goal, task["id"], json_text(task)),
                )
                self.store.edge(self.goal, f"goal:{self.goal}", "contains", f"task:{task['id']}")
                for dependency in task["depends"]:
                    self.store.edge(self.goal, f"task:{task['id']}", "depends_on", f"task:{dependency}")
            self.store.event(self.goal, None, "plan", {"level": plan["level"], "tasks": len(plan["tasks"])})
        return plan

    def run_goal(self):
        conn = self.store.conn
        plan = self.store.goal(self.goal)["plan"] or self.make_plan()
        events = self.store.events(self.goal)
        if plan["tasks"] and self.policy.regressions and not any(e["kind"] == "regression_baseline" for e in events):
            results = self.evaluator.run(self.policy.regressions, purpose="baseline")
            with conn:
                self.store.event(self.goal, None, "regression_baseline", {
                    "passed": [r["id"] for r in results if r["status"] == "PASS"],
                })
        for task in self.store.tasks(self.goal):
            self.guard()
            if task["status"] == "COMPLETED":
                continue
            completed = {item["id"] for item in self.store.tasks(self.goal) if item["status"] == "COMPLETED"}
            if not set(task["spec"]["depends"]) <= completed:
                raise Blocked("A task dependency is incomplete")
            self.run_task(task, plan)

        self.guard()
        self.checkpoint()
        summaries = [event["data"]["summary"] for event in self.store.events(self.goal)
                     if event["kind"] == "work_submitted"]
        with conn:
            self.store.transition("goals", self.goal, "VERIFIED")
            self.store.transition("goals", self.goal, "COMPLETED")
            conn.execute(
                "UPDATE goals SET result=? WHERE id=?",
                (json_text({"answer": plan["answer"], "task_summaries": summaries}), self.goal),
            )
        return "COMPLETED"

    def stage(self, task, stage, repair=None):
        self.store.conn.execute(
            "UPDATE tasks SET stage=?,repair=? WHERE goal=? AND id=?", (stage, repair, self.goal, task),
        )

    def run_task(self, task, plan):
        conn = self.store.conn
        task_id = task["id"]
        with conn:
            self.store.transition("tasks", self.goal, "RUNNING", task_id)
        if (self.policy.data.get("probe_before_work")
                and self.store.goal(self.goal)["mode"] == "advisor" and task["stage"] == "work"
                and not self.history(task_id)):
            self.guard()
            with conn:
                self.stage(task_id, "probe")
        while True:
            self.guard()
            self.checkpoint()
            task = next(item for item in self.store.tasks(self.goal) if item["id"] == task_id)
            stage = task["stage"]
            if stage == "work":
                self.work(task, plan)
            elif stage == "probe":
                if self.evaluate_task(task, probe=True):
                    return
            elif stage == "repair":
                self.repair(task, plan)
            elif stage == "rollback":
                repair = task["repair"]
                self.rollback(repair)
                with conn:
                    conn.execute("UPDATE repairs SET result='REGRESSION' WHERE id=?", (repair,))
                raise Blocked("Repair introduced a regression and was rolled back")
            else:
                if self.evaluate_task(task):
                    return

    def history(self, task):
        allowed = {"work_read", "work_check", "work_edit", "work_feedback"}
        return [{"kind": event["kind"], **event["data"]} for event in self.store.events(self.goal)
                if event["task"] == task and event["kind"] in allowed][-8:]

    def work(self, task, plan):
        task_id = task["id"]
        history = self.history(task_id)
        sources = {}
        for path in self.policy.editable[:5]:
            if path in self.policy.visible:
                data = self.policy.read(path)
                if data is not None:
                    sources[path] = data.decode("utf-8")[:2400]
        paths_read, checks_run = set(), set()
        for item in history:
            if item["kind"] == "work_read":
                paths_read.add(item["path"])
            if item["kind"] == "work_check":
                checks_run.add(item["id"])
            if item["kind"] == "work_edit":
                paths_read.discard(item["path"])
                checks_run.clear()
        action = self.decide("work", {
            "policy": self.policy.model_context(), "task": task["spec"],
            "constraints": plan["constraints"], "history": history,
            "editable_sources": sources, "next_reads": sorted(set(self.policy.visible) - paths_read),
            "next_checks": sorted(set(self.policy.checks) - checks_run),
        }, task_id)
        verb = action.get("action")
        try:
            if verb == "read":
                name = text_field(action, "path", 240)
                if name not in self.policy.visible:
                    raise Blocked("File is outside the authorized read capability")
                payload = self.policy.read(name)
                result = {"path": name, "sha256": digest(payload),
                          "source": None if payload is None else payload.decode("utf-8")[:12000]}
            elif verb == "edit":
                result = self.edit(task_id, action)
            elif verb == "check":
                name = text_field(action, "id", 64)
                if name not in self.policy.checks:
                    raise Blocked("Unknown check. Only configured commands are allowed.")
                [result] = self.evaluator.run([name], task_id, purpose="requested")
                result = compact_result(result)
            elif verb in {"finish", "block"}:
                summary = text_field(action, "summary", 4000)
                if verb == "block":
                    raise Blocked(summary)
                with self.store.conn:
                    self.store.event(self.goal, task_id, "work_submitted", {"summary": summary})
                    self.stage(task_id, "evaluate")
                return
            else:
                raise Invalid("Unknown or unauthorized model action")
        except (Blocked, Invalid) as exc:
            with self.store.conn:
                self.store.event(self.goal, task_id, "action_rejected", {
                    "action": verb, "reason": str(exc),
                })
            if isinstance(exc, StaleEdit) and verb == "edit":
                previous_failure = history and history[-1]["kind"] == "work_feedback"
                if not previous_failure:
                    with self.store.conn:
                        self.store.event(self.goal, task_id, "work_feedback", {
                            "reason": str(exc), "hint": "Use a unique exact fragment from editable_sources.",
                        })
                    return
            raise
        with self.store.conn:
            self.store.event(self.goal, task_id, f"work_{verb}", result)

    def command(self, name, task, spec, purpose):
        conn = self.store.conn
        self.checkpoint()
        trusted = spec.get("execution", "isolated") == "trusted"
        if trusted and not self.trusted:
            raise Blocked("Trusted command needs the operator's --allow-trusted-tests flag")
        replayable = not trusted or spec.get("replayable") is True
        if not replayable and any(
            e["kind"] == "command_start" and e["data"]["id"] == name for e in self.store.events(self.goal)
        ):
            raise Blocked("Trusted command is single-use without an explicit replayable policy")
        with conn:
            state = self.store.goal(self.goal)
            if state["commands"] >= self.policy.limits["commands"]:
                raise Blocked("Command count budget exhausted")
            conn.execute("UPDATE goals SET commands=commands+1 WHERE id=?", (self.goal,))
            event = self.store.event(self.goal, task, "command_start", {
                "id": name, "argv": spec["argv"], "purpose": purpose,
                "execution": spec.get("execution", "isolated"),
                "replayable": replayable,
            })
        info = None
        interrupted = False
        launched = False

        def mark_launched():
            nonlocal launched
            launched = True
            with conn:
                self.store.event(self.goal, task, "command_process", {"start": event, "id": name})

        try:
            info = run_test(
                self.policy, spec, trusted=self.trusted,
                deadline=min(self.deadline, time.monotonic() + self.policy.limits["command_seconds"]),
                guard=self.guard, on_start=mark_launched,
            )
            self.checkpoint()
        except (KeyboardInterrupt, Stopped):
            interrupted = True
            raise
        finally:
            with conn:
                self.store.event(self.goal, task, "command_end", {
                    "start": event, "id": name, "executed": info is not None, "process_started": launched,
                    "status": "INTERRUPTED" if interrupted and launched else ("RETURNED" if info is not None else "UNAVAILABLE"),
                    **(info or {}),
                })
        return {
            **info, "argv": spec["argv"], "execution": spec.get("execution", "isolated"),
            "command_event": event,
        }

    def edit(self, task_id, action, repair=None):
        self.guard()
        name = text_field(action, "path", 240)
        path = self.policy.path(name, write=True)
        self.checkpoint()
        before = self.policy.read(name)
        previous = before.decode("utf-8") if before is not None else None
        if contains_secret(before):
            raise Blocked("Credential-like content cannot be edited or backed up")
        old = action.get("old")
        new = text_field(action, "new", MAX_FILE)
        if old is None and previous is None and "old" in action:
            after = new.encode()
        elif isinstance(old, str) and old and previous is not None and previous.count(old) == 1:
            after = previous.replace(old, new, 1).encode()
        else:
            raise StaleEdit("The edit does not match exactly one current source fragment")
        if after == before or len(after) > MAX_FILE:
            raise Invalid("Edit must change the file and remain within the size limit")
        if contains_secret(after):
            raise Blocked("Model edit contains credential-like content")
        conn = self.store.conn
        with conn:
            write_id = conn.execute(
                "INSERT INTO writes(goal,task,path,old_hash,new_hash,previous,status,repair) VALUES (?,?,?,?,?,?,'PREPARED',?)",
                (self.goal, task_id, name, digest(before), digest(after), before if repair else None, repair),
            ).lastrowid
        self.guard()
        if digest(self.policy.read(name)) != digest(before):
            raise Blocked("File changed before the journaled write")
        atomic_write(path, after)
        row = conn.execute("SELECT * FROM writes WHERE id=?", (write_id,)).fetchone()
        changes = difflib.unified_diff(
            (previous or "").splitlines(), after.decode().splitlines(), fromfile=name, tofile=name, n=2,
        )
        result = {
            "write": write_id, "path": name, "before_sha256": row["old_hash"], "after_sha256": row["new_hash"],
            "diff": "\n".join(changes)[:6000],
        }
        with conn:
            self.record_write(row, row["new_hash"], "APPLIED")
            self.store.event(self.goal, task_id, "write_applied", result)
        return result

    def record_write(self, row, actual, status):
        checkpoint = self.store.goal(self.goal)["checkpoint"]
        checkpoint[row["path"]] = actual
        conn = self.store.conn
        conn.execute("UPDATE goals SET checkpoint=? WHERE id=?", (json_text(checkpoint), self.goal))
        conn.execute("UPDATE writes SET status=? WHERE id=?", (status, row["id"]))

    def undo(self, row):
        name = row["path"]
        path = self.policy.path(name, write=True)
        if digest(self.policy.read(name)) != row["new_hash"]:
            raise Blocked(f"Refusing rollback over external edits to {name}")
        with self.store.conn:
            self.store.conn.execute("UPDATE writes SET status='UNDOING' WHERE id=?", (row["id"],))
        if row["previous"] is None:
            path.unlink()
        else:
            atomic_write(path, row["previous"])
        with self.store.conn:
            self.record_write(row, row["old_hash"], "UNDONE")
            self.store.event(self.goal, row["task"], "repair_rollback", {"write": row["id"], "path": name})

    def rollback(self, repair_id):
        for row in self.store.conn.execute(
            "SELECT * FROM writes WHERE repair=? AND status='APPLIED' ORDER BY id DESC", (repair_id,),
        ).fetchall():
            self.undo(row)

    def protected_checks(self, task_id):
        protected = set()
        for event in self.store.events(self.goal):
            if event["kind"] == "regression_baseline":
                protected.update(event["data"]["passed"])
        for task in self.store.tasks(self.goal):
            if task["status"] == "COMPLETED" and task["id"] != task_id:
                protected.update(task["spec"]["checks"])
        return protected

    def evaluate_task(self, task, *, probe=False):
        conn = self.store.conn
        task_id = task["id"]
        protected = self.protected_checks(task_id)
        names = [*task["spec"]["checks"], *self.policy.regressions, *sorted(protected)]
        active_repair = task["repair"]
        purpose = "initial_diagnosis" if probe else ("repair_verification" if active_repair else "acceptance")
        results = self.evaluator.run(names, task_id, purpose=purpose)
        failures = [item for item in results if item["status"] != "PASS"]
        self.guard()
        self.checkpoint()
        with conn:
            evaluation_id = self.store.event(self.goal, task_id, "acceptance", {
                "status": "PASS" if not failures else (
                    "FAIL" if any(item["status"] == "FAIL" for item in failures) else "INCOMPLETE"
                ),
                "checks": [{"id": item["id"], "status": item["status"], "event": item["event"]} for item in results],
            })
            if active_repair:
                self.store.edge(self.goal, f"repair:{active_repair}", "validated_by", f"event:{evaluation_id}")
                regressed = any(item["id"] in protected and item["status"] == "FAIL" for item in failures)
                outcome = "CANDIDATE" if regressed else (
                    "VERIFIED" if not failures else (
                        "FAILED" if any(item["status"] == "FAIL" for item in failures) else "UNVERIFIED"
                    )
                )
                conn.execute("UPDATE repairs SET result=?,validation=? WHERE id=?", (outcome, evaluation_id, active_repair))
                if regressed:
                    self.stage(task_id, "rollback", active_repair)
                    return False
            if probe and not failures:
                self.stage(task_id, "work")
                return False
            if not failures:
                self.store.transition("tasks", self.goal, "VERIFIED", task_id)
                self.store.transition("tasks", self.goal, "COMPLETED", task_id)
                return True
            failing = next((item for item in failures if item["status"] == "FAIL"), None)
            if failing:
                self.store.transition("tasks", self.goal, "FAILED", task_id)
            repairing = failing and self.store.goal(self.goal)["mode"] == "advisor"
            self.stage(task_id, "repair" if repairing else "evaluate", active_repair if not failing else None)
        if not failing:
            reason = ", ".join(f"{item['id']} {item['status']}" for item in failures)
            raise Blocked("Acceptance checks are incomplete: " + reason)
        if self.store.goal(self.goal)["mode"] == "baseline":
            raise Stopped("FAILED", "Baseline submitted work that failed independent acceptance")
        with conn:
            self.store.transition("tasks", self.goal, "RUNNING", task_id)
        return False

    def repair(self, task, plan):
        conn = self.store.conn
        task_id = task["id"]
        events = self.store.events(self.goal)
        latest = next(e for e in reversed(events) if e["task"] == task_id and e["kind"] == "acceptance")
        failed = next(item for item in latest["data"]["checks"] if item["status"] == "FAIL")
        failure = next(e["data"] for e in events if e["id"] == failed["event"])
        signature = fingerprint(failed["id"], failure)
        feature = failure["feature"]
        rounds = conn.execute(
            "SELECT count(*) FROM repairs WHERE goal=? AND task=?", (self.goal, task_id),
        ).fetchone()[0]
        if task["repair"]:
            row = conn.execute(
                "SELECT * FROM writes WHERE repair=? ORDER BY id DESC LIMIT 1", (task["repair"],),
            ).fetchone()
            if row is not None and row["status"] == "APPLIED":
                with conn:
                    self.stage(task_id, "evaluate", task["repair"])
                return
            with conn:
                conn.execute("UPDATE repairs SET result='UNVERIFIED' WHERE id=?", (task["repair"],))
                self.stage(task_id, "repair")
        if rounds >= self.policy.limits["repair_rounds"]:
            raise Blocked(f"Repair limit reached for {failed['id']} ({signature}), see recorded diagnoses")
        experience = self.store.experiences(signature, failed["id"], feature)
        with conn:
            self.store.event(self.goal, task_id, "experience_lookup", {
                "signature": signature, "matches": [item["id"] for item in experience],
            })
            for item in experience:
                self.store.edge(self.goal, f"task:{task_id}", "consulted", f"repair:{item['id']}")
        sources = {}
        remaining = 16000
        for name in self.policy.visible:
            if remaining <= 0:
                break
            data = self.policy.read(name)
            if data is not None and name in self.policy.editable:
                sources[name] = data.decode("utf-8")[:min(remaining, 8000)]
                remaining -= len(sources[name])
        action = self.decide("repair", {
            "policy": self.policy.model_context(), "task": task["spec"], "constraints": plan["constraints"],
            "failure": compact_result(failure), "sources": sources,
            "experience": [{"id": item["id"], "result": item["result"], "diagnosis": item["diagnosis"],
                            "regression_count": item["regression_count"]}
                           for item in experience[:3]],
        }, task_id)
        if action.get("action") != "edit":
            reason = text_field(action, "summary", 800, default="No minimal repair was proposed")
            with conn:
                self.store.event(self.goal, task_id, "repair_declined", {"reason": reason, "failure": failed["event"]})
            raise Blocked(reason)
        tag = text_field(action, "tag", 16)
        if tag not in REVIEW_TAGS:
            raise Invalid("Unknown internal review tag")
        used = action.get("experience")
        if used is not None and (type(used) is not int
                                 or not any(item["id"] == used and item["result"] == "VERIFIED" for item in experience)):
            raise Invalid("Repair cites unavailable or unverified experience")
        diagnosis = clean({
            "tag": tag, "root_cause": text_field(action, "root_cause", 1000),
            "basis": text_field(action, "basis", 1000), "path": text_field(action, "path", 240),
            "change": text_field(action, "new", 2000), "confidence": "hypothesis",
            "scope": {"check": failed["id"], "feature": feature, "platform": os.name,
                      "python": os.sys.version.split()[0], "execution": failure.get("execution")},
        })
        with conn:
            repair_id = conn.execute(
                "INSERT INTO repairs(goal,task,signature,check_id,failure,diagnosis,reused,result,feature) "
                "VALUES (?,?,?,?,?,?,?,'CANDIDATE',?)",
                (self.goal, task_id, signature, failed["id"], failed["event"], json_text(diagnosis), used, feature),
            ).lastrowid
            self.store.edge(self.goal, f"event:{failed['event']}", "diagnosed_by", f"repair:{repair_id}")
            self.store.edge(self.goal, f"repair:{repair_id}", "proposes_cause", f"cause:{signature}")
            if used is not None:
                self.store.edge(self.goal, f"repair:{repair_id}", "reuses", f"repair:{used}")
            self.stage(task_id, "repair", repair_id)
        try:
            self.edit(task_id, action, repair=repair_id)
        except (Invalid, Blocked) as exc:
            with conn:
                conn.execute("UPDATE repairs SET result='REJECTED' WHERE id=?", (repair_id,))
                self.store.event(self.goal, task_id, "repair_rejected", {"repair": repair_id, "reason": str(exc)})
                self.stage(task_id, "repair")
            # An unsafe capability request stops the run. Stale edits can be diagnosed again.
            if isinstance(exc, Blocked):
                raise
            return
        with conn:
            self.stage(task_id, "evaluate", repair_id)


def compact_result(result):
    return {key: (result[key][-4000:] if isinstance(result[key], str) else result[key])
            for key in ("id", "kind", "status", "path", "event", "reason", "exit_code", "stdout", "stderr")
            if key in result}
