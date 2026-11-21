import copy
import json
import http.server
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from advisor_harness.policy import Blocked, Invalid, Policy, digest
from advisor_harness.providers import Decision, Demo, Ollama
from advisor_harness.runtime import Session, validate_plan
from advisor_harness.store import Store, workspace_lock

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "harness"
LINUX_SANDBOX = sys.platform == "linux" and Path("/usr/bin/bwrap").is_file()


class Script:
    name = "test:script"

    def __init__(self, phases=()):
        self.phases = iter(phases)
        self.demo = Demo()

    def decide(self, prompt, *, deadline, guard):
        guard()
        data = json.loads(prompt.split("\n--- DATA ---\n", 1)[1])
        if data["phase"] == "plan":
            return self.demo.decide(prompt, deadline=deadline, guard=guard)
        action = next(self.phases, {"action": "finish", "summary": "submitted"})
        return Decision(action(data) if callable(action) else action)


def start_command(path, goal="ignored"):
    return {
        "kind": "command", "argv": ["{python}", path], "execution": "trusted", "replayable": True,
        "feature": goal,
    }


def result_events(report, kind):
    return [event["data"] for event in report["events"] if event["kind"] == kind]


class HarnessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.project = self.base / "project"
        self.project.mkdir()
        shutil.copytree(EXAMPLE / "project", self.project, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
        self.db = self.base / "state.db"
        self.operator_file = self.base / "policy.json"
        self.data = json.loads((EXAMPLE / "policy.json").read_text())
        if os.environ.get("ADVISOR_TEST_ISOLATION") != "1":
            for check in self.data["checks"].values():
                if check["kind"] == "command":
                    check.update(execution="trusted", replayable=True)
        self.source = self.project / "calculator.py"
        self.original = self.source.read_bytes()

    def run_goal(self, goal, data=None, provider=None, *, trusted=True, mode="advisor"):
        with Store(self.db) as store:
            session = Session(store, Policy(self.project, data or self.data), provider or Demo(), trusted=trusted)
            key = session.create(goal, mode=mode)
            status = session.run(key)
            self.assertEqual(status, store.goal(key)["status"])
            return store.report(key)

    def test_a_read_and_diagnose_from_real_failing_process(self):
        data = copy.deepcopy(self.data)
        data["checks"] = {"sum": {**data["checks"]["sum"], "exit": 1}}
        report = self.run_goal("Inspect the failure and identify it", data)
        evidence = result_events(report, "work_read")[0]
        self.assertEqual(evidence["path"], "calculator.py")
        self.assertIn("return a - b", evidence["source"])
        self.assertEqual(evidence["sha256"], digest(self.original))
        for item in result_events(report, "evaluation"):
            self.assertEqual(item["exit_code"], 1)
            self.assertIn("AssertionError: 2 != 4", item["stderr"])
        self.assertIn("subtraction", report["result"]["task_summaries"][0])
        self.assertEqual(report["status"], "COMPLETED")
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_b_edit_actual_file_and_preserve_other_source(self):
        data = copy.deepcopy(self.data)
        data["checks"] = {
            "rename": {"kind": "contains", "path": "calculator.py", "value": 'return "new"'},
            "test-preserved": data["checks"]["tests-preserved"],
        }
        report = self.run_goal("Rename the calculator label to new", data)
        self.assertEqual(report["status"], "COMPLETED")
        self.assertEqual(self.source.read_bytes(), self.original.replace(b'"old"', b'"new"', 1))
        self.assertIn('+    return "new"', result_events(report, "write_applied")[0]["diff"])

    def test_c_command_and_independent_status_override_model_summary(self):
        check = self.data["checks"]["sum"]
        data = {**self.data, "checks": {"sum": check}}
        report = self.run_goal("Run the addition test", data, Script([
            {"action": "finish", "summary": "All tests passed."},
        ]), mode="baseline")
        self.assertEqual(report["status"], "FAILED")
        failing = result_events(report, "evaluation")[0]
        self.assertEqual(failing["argv"], check["argv"])
        self.assertEqual(failing["exit_code"], 1)
        self.assertEqual(failing["status"], "FAIL")
        self.assertIn("AssertionError", failing["stderr"])

    def test_d_real_failure_repair_and_cross_goal_memory(self):
        report = self.run_goal("Repair Python addition and preserve existing behavior")
        self.assertEqual(report["status"], "COMPLETED")
        self.assertEqual(self.source.read_bytes(), self.original.replace(b"a - b", b"a + b", 1))
        results = result_events(report, "evaluation")
        self.assertEqual([(r["status"], r["exit_code"]) for r in results if r["id"] == "sum"],
                         [("FAIL", 1), ("PASS", 0)])
        self.assertTrue(all(r["status"] == "PASS" for r in results if r["id"] == "label"))
        first = report["repairs"][0]
        self.assertEqual(first["result"], "VERIFIED")
        self.assertEqual(first["diagnosis"]["confidence"], "hypothesis")
        self.source.write_bytes(self.original)
        again = self.run_goal("Repair the same broken calculator in a fresh checkout")
        self.assertEqual(again["status"], "COMPLETED")
        self.assertEqual(again["repairs"][0]["reused"], first["id"])
        self.assertIn(first["id"], result_events(again, "experience_lookup")[0]["matches"])
        self.assertIn("reuses", [edge["relation"] for edge in again["edges"]])

    def test_repair_that_breaks_a_passing_test_is_rolled_back(self):
        regression = self.original.decode()
        provider = Script([
            {"action": "finish", "summary": "Check current implementation"},
            {"action": "edit", "path": "calculator.py", "old": regression,
             "new": regression.replace("a - b", "a + b").replace('"old"', '"broken"'),
             "root_cause": "add subtracts", "basis": "assertion failure", "tag": "GAP"},
        ])
        report = self.run_goal("Repair the calculator", provider=provider)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["repairs"][0]["result"], "REGRESSION")
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertTrue(result_events(report, "repair_rollback"))

    def test_repair_budget_caps_same_failure_at_three_persisted_attempts(self):
        attempts = [
            {"action": "edit", "path": "calculator.py", "old": "return a - b",
             "new": "return a - b", "root_cause": "Wrong arithmetic",
             "basis": "Assert failed", "tag": "GAP"},
        ] * 4
        report = self.run_goal("Repair addition", provider=Script([{"action": "finish", "summary": ""}, *attempts]))
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual([r["result"] for r in report["repairs"]], ["REJECTED"] * 3)
        self.assertIn("Repair limit", report["result"]["reason"])

    def test_explicit_unknown_command_and_out_of_scope_edit_are_rejected(self):
        for action in (
            {"action": "check", "id": "delete_everything"},
            {"action": "edit", "path": "../outside.py", "old": None, "new": "changed"},
            {"action": "edit", "path": "test_calculator.py", "old": None, "new": "changed"},
        ):
            with self.subTest(action=action):
                report = self.run_goal("Attempt an unauthorized action", provider=Script([action]))
                self.assertEqual(report["status"], "BLOCKED")
                self.assertTrue(result_events(report, "action_rejected"))
                self.assertEqual(report["commands"], 1)  # preflight regression only
        self.assertFalse((self.base / "outside.py").exists())

    def test_hard_link_and_reserved_secret_paths_are_denied(self):
        path = self.base / "outside.py"
        path.write_text("outside", encoding="utf-8")
        os.link(path, self.project / "link.py")
        policy = Policy(self.project, {"files": ["link.py"], "editable": ["link.py"]})
        with self.assertRaises(Blocked):
            policy.read("link.py")
        for name in (".env", "credentials.json", "CON.txt", "x/../out.py"):
            with self.subTest(name=name), self.assertRaises(Invalid):
                Policy(self.project, {"files": [name]})

    def test_command_timeout_and_manual_review_do_not_pass(self):
        path = self.project / "slow.py"
        path.write_text("import time\ntime.sleep(15)\n", encoding="utf-8")
        data = {
            "files": [*self.data["files"], "slow.py"], "visible": [],
            "checks": {"timeout": start_command("slow.py"), "manual": {"kind": "manual"}},
            "limits": {"command_seconds": 1},
        }
        report = self.run_goal("Test a slow operation and inspect UI", data, Script())
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual([(item["status"], item.get("timed_out")) for item in result_events(report, "evaluation")],
                         [("ERROR", True), ("NOT_RUN", None)])
        self.assertEqual(report["commands"], 1)

    def test_trusted_tests_need_opt_in_and_are_not_replayed_by_default(self):
        data = {**self.data, "checks": {"sum": {
            **self.data["checks"]["sum"], "execution": "trusted", "replayable": False,
        }}}
        report = self.run_goal("Run the addition test", data, Script(), trusted=False)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertIn("--allow-trusted-tests", result_events(report, "evaluation")[0]["reason"])
        self.assertEqual(result_events(report, "command_process"), [])

    def test_repeat_command_captures_each_real_exit_and_blocks_at_budget(self):
        data = {**self.data, "checks": {"sum": {**self.data["checks"]["sum"], "exit": 1}},
                "limits": {"commands": 2}}
        report = self.run_goal("Run checks twice and record separate executions", data, Script([
            {"action": "check", "id": "sum"}, {"action": "check", "id": "sum"},
        ]))
        self.assertEqual(report["status"], "BLOCKED")
        commands = result_events(report, "command_end")
        self.assertEqual([result["exit_code"] for result in commands], [1, 1])
        self.assertNotEqual(commands[0]["start"], commands[1]["start"])
        self.assertIn("budget", result_events(report, "evaluation")[-1]["reason"])

    def test_direct_answer_uses_no_execution_and_dag_rejects_cycles(self):
        data = {"files": [], "checks": {}}
        report = self.run_goal("What is 17 * 23?", data)
        self.assertEqual(report["result"]["answer"], "391")
        self.assertEqual(report["calls"], 1)
        self.assertEqual(report["commands"], 0)
        self.assertEqual(report["tasks"], [])
        policy = Policy(self.project, self.data)
        with self.assertRaises(Invalid):
            validate_plan({
                "goal": "fix", "level": 3,
                "tasks": [{"id": "cycle", "title": "Cycle", "depends": ["cycle"], "checks": ["sum"]}],
            }, policy)

    def test_dag_executes_dependency_first_and_rechecks_completed_feature(self):
        data = copy.deepcopy(self.data)
        data["checks"] = {
            "label": {"kind": "contains", "path": "calculator.py", "value": 'return "new"'},
            "addition": {"kind": "contains", "path": "calculator.py", "value": "return a + b"},
        }

        class Planner(Script):
            def decide(self, prompt, *, deadline, guard):
                data = json.loads(prompt.split("\n--- DATA ---\n", 1)[1])
                if data["phase"] != "plan":
                    return super().decide(prompt, deadline=deadline, guard=guard)
                return Decision({
                    "level": 3, "goal": "Preserve each feature",
                    "tasks": [
                        {"id": "addition", "title": "Fix addition", "depends": ["label"],
                         "priority": 10, "checks": ["addition"]},
                        {"id": "label", "title": "Rename label", "checks": ["label"]},
                    ],
                })

        report = self.run_goal("Rename label and repair addition", data, Planner([
            {"action": "edit", "path": "calculator.py", "old": '"old"', "new": '"new"'},
            {"action": "finish", "summary": "Label renamed"},
            {"action": "edit", "path": "calculator.py", "old": "a - b", "new": "a + b"},
            {"action": "finish", "summary": "Fixed addition"},
        ]))
        self.assertEqual([task["id"] for task in report["tasks"]], ["label", "addition"])
        self.assertEqual([item["id"] for item in result_events(report, "evaluation")], ["label", "addition", "label"])
        self.assertEqual(report["status"], "COMPLETED")

    def test_resume_after_actual_process_death_during_atomic_write(self):
        self.operator_file.write_text(json.dumps(self.data), encoding="utf-8")
        script = """
import os
import sys
from pathlib import Path
from advisor_harness.policy import Policy
from advisor_harness.providers import Demo
from advisor_harness.store import Store
from advisor_harness.runtime import Session
import advisor_harness.runtime as runtime

atomic_write = runtime.atomic_write
def crash_after_write(path, data):
    atomic_write(path, data)
    os._exit(71)
runtime.atomic_write = crash_after_write
with Store(sys.argv[1]) as store:
    session = Session(store, Policy.load(*sys.argv[2:]), Demo(), trusted=True)
    goal = session.create("Repair calculation after a hard crash")
    print(goal, flush=True)
    session.run(goal)
"""
        run = subprocess.run(
            [sys.executable, "-c", script, str(self.db), str(self.project), str(self.operator_file)],
            cwd=ROOT, capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(run.returncode, 71, run.stderr)
        goal = run.stdout.strip()
        self.assertIn(b"return a + b", self.source.read_bytes())
        before_mtime = self.source.stat().st_mtime_ns
        with Store(self.db) as store:
            self.assertEqual(store.goal(goal)["status"], "RUNNING")
            session = Session(store, Policy(self.project, self.data), Demo(), trusted=True)
            self.assertEqual(session.run(goal, resume=True), "COMPLETED")
            self.assertEqual(self.source.stat().st_mtime_ns, before_mtime)
            report = store.report(goal)
        self.assertEqual(result_events(report, "recovered_write")[0]["status"], "APPLIED")
        self.assertEqual(report["repairs"][0]["result"], "VERIFIED")

    def test_resume_refuses_external_drift_and_revision_supersedes(self):
        with Store(self.db) as store:
            session = Session(store, Policy(self.project, self.data), Demo(), trusted=True)
            key = session.create("Repair addition")
            self.source.write_bytes(self.original + b"\n# user edited\n")
            self.assertEqual(session.run(key, resume=True), "BLOCKED")
            self.assertIn("differs from the checkpoint", store.goal(key)["result"]["reason"])
            revised = session.create("Repair addition after the user changed the goal", supersedes=key)
            self.assertEqual(store.goal(key)["status"], "CANCELLED")
            self.assertEqual(store.goal(revised)["supersedes"], key)
            self.assertEqual(session.run(revised), "COMPLETED")
        self.assertIn(b"user edited", self.source.read_bytes())

    def test_resume_refuses_an_interrupted_non_replayable_command(self):
        policy = Policy(self.project, self.data)
        with Store(self.db) as store:
            session = Session(store, policy, Demo(), trusted=True)
            key = session.create("Repair addition")
            with store.conn:
                store.transition("goals", key, "RUNNING")
                store.event(key, None, "command_start", {"id": "sum", "replayable": False})
            self.assertEqual(session.run(key, resume=True), "BLOCKED")
            self.assertIn("side effects", store.goal(key)["result"]["reason"])
            self.assertEqual(store.goal(key)["commands"], 0)

    def test_pause_during_decision_and_resume(self):
        self.operator_file.write_text(json.dumps({
            "files": ["calculator.py"], "visible": ["calculator.py"],
            "checks": {"syntax": {"kind": "exists", "path": "calculator.py"}},
        }), encoding="utf-8")
        policy = Policy.load(self.project, self.operator_file)

        class PauseOnWork(Demo):
            name = "test:pause"
            paused = False

            def decide(inner, prompt, *, deadline, guard):
                if '"phase": "work"' in prompt and not inner.paused:
                    inner.paused = True
                    with Store(self.db) as controller, controller.conn:
                        controller.conn.execute("UPDATE goals SET control='pause'")
                    guard()
                return super().decide(prompt, deadline=deadline, guard=guard)

        with Store(self.db) as store:
            provider = PauseOnWork()
            session = Session(store, policy, provider, trusted=True)
            key = session.create("Confirm existence")
            self.assertEqual(session.run(key), "BLOCKED")
            self.assertIn("Paused", store.goal(key)["result"]["reason"])
            self.assertEqual(session.run(key, resume=True), "COMPLETED")

    @unittest.skipUnless(LINUX_SANDBOX, "Requires Linux bubblewrap")
    def test_linux_subprocess_cannot_reach_external_files_or_network(self):
        outside = self.base / "outside.py"
        outside.write_text("sentinel", encoding="utf-8")
        (self.project / "probe.py").write_text(
            "from pathlib import Path\n"
            "import socket\n"
            f"assert not Path({str(outside)!r}).exists()\n"
            "try:\n    Path('/work/probe.py').write_text('bad')\n"
            "except OSError:\n    pass\n"
            "else:\n    raise AssertionError('Writable project')\n"
            "try:\n    socket.socket()\n"
            "except PermissionError:\n    print('socket blocked')\n"
            "else:\n    raise AssertionError('Network access available')\n",
            encoding="utf-8",
        )
        data = {"files": ["probe.py"], "checks": {"isolation": {
            "kind": "command", "argv": ["{python}", "probe.py"], "stdout_contains": "socket blocked",
        }}}
        report = self.run_goal("Verify OS isolation", data, Script(), trusted=False)
        self.assertEqual(report["status"], "COMPLETED", report["result"])
        self.assertEqual(outside.read_text(), "sentinel")

    def test_credential_like_output_is_redacted_before_persistence(self):
        (self.project / "probe.py").write_text(
            "print('sk-' + 'examplefakevalue0123456789')\n", encoding="utf-8",
        )
        data = {"files": ["probe.py"], "checks": {"test": start_command("probe.py")}}
        report = self.run_goal("Run check", data, Script())
        self.assertEqual(report["status"], "COMPLETED")
        self.assertIn("[redacted]", result_events(report, "evaluation")[0]["stdout"])
        self.assertNotIn("examplefakevalue", json.dumps(report))

    def test_state_lock_rejects_concurrent_workspace_runs(self):
        with Store(self.db) as store:
            session = Session(store, Policy(self.project, self.data), Demo())
            with workspace_lock(session.lock), self.assertRaises(Blocked):
                session.create("Competing writer")

    def test_pause_an_active_subprocess_and_resume_its_replayable_check(self):
        (self.project / "slow.py").write_text("import time\ntime.sleep(1.2)\n", encoding="utf-8")
        data = {"files": ["slow.py"], "checks": {"slow": start_command("slow.py")}}
        seen = threading.Event()
        errors = []

        def pause_after_launch(key):
            try:
                with Store(self.db) as controller:
                    until = time.monotonic() + 5
                    while time.monotonic() < until:
                        if result_events(controller.report(key), "command_process"):
                            with controller.conn:
                                controller.conn.execute("UPDATE goals SET control='pause' WHERE id=?", (key,))
                            seen.set()
                            return
                        time.sleep(0.01)
            except Exception as exc:
                errors.append(exc)

        with Store(self.db) as store:
            session = Session(store, Policy(self.project, data), Script(), trusted=True)
            key = session.create("Run a replayable test")
            controller = threading.Thread(target=pause_after_launch, args=(key,))
            controller.start()
            try:
                self.assertEqual(session.run(key), "BLOCKED")
            finally:
                controller.join(timeout=6)
            self.assertEqual(errors, [])
            self.assertTrue(seen.is_set())
            self.assertEqual(result_events(store.report(key), "command_end")[0]["status"], "INTERRUPTED")
            self.assertEqual(session.run(key, resume=True), "COMPLETED")
            self.assertEqual(store.goal(key)["commands"], 2)

    def test_ollama_adapter_exercises_real_loopback_http_with_simulated_response(self):
        calls = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(inner):
                calls.append((inner.path, json.loads(inner.rfile.read(int(inner.headers["Content-Length"])))))
                content = json.dumps({
                    "message": {"content": json.dumps({
                        "level": 0, "goal": "multiply", "tasks": [], "constraints": [], "answer": "391",
                    })}, "prompt_eval_count": 18, "eval_count": 10,
                }).encode()
                inner.send_response(200)
                inner.send_header("Content-Length", str(len(content)))
                inner.end_headers()
                inner.wfile.write(content)

            def log_message(inner, *_):
                pass

        with http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
            serving = threading.Thread(target=server.serve_forever)
            serving.start()
            try:
                report = self.run_goal("What is 17 * 23?", {"files": [], "checks": {}},
                                       Ollama("fixture", server.server_port))
            finally:
                server.shutdown()
                serving.join(timeout=5)
        self.assertEqual(report["status"], "COMPLETED")
        self.assertEqual(calls[0][0], "/api/chat")
        self.assertEqual(calls[0][1]["model"], "fixture")
        self.assertEqual(calls[0][1]["format"]["type"], "object")
        self.assertEqual(result_events(report, "decision_response")[0]["output_tokens"], 10)

    def test_portable_install_uninstall_preserves_operator_additions(self):
        destination = self.base.resolve() / "installed"
        installer = ROOT / "scripts" / "install_harness.py"
        command = [sys.executable, "-B", str(installer)]
        install = subprocess.run([*command, "install", "--destination", str(destination)],
                                 capture_output=True, text=True, timeout=10)
        self.assertEqual(install.returncode, 0, install.stderr)
        launched = subprocess.run([sys.executable, "-B", "-m", "advisor_harness", "--version"],
                                  cwd=destination, capture_output=True, text=True, timeout=10)
        self.assertEqual(launched.stdout.strip(), "2.0.0")
        extra = destination / "existing-user-state"
        extra.mkdir()
        uninstall = [*command, "uninstall", "--destination", str(destination)]
        refused = subprocess.run(uninstall, capture_output=True, text=True, timeout=10)
        self.assertEqual(refused.returncode, 2)
        self.assertTrue(extra.is_dir())
        extra.rmdir()
        done = subprocess.run(uninstall, capture_output=True, text=True, timeout=10)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertFalse(destination.exists())

    @unittest.skipUnless(os.name == "nt", "Native Windows PowerShell demo")
    def test_powershell_bundled_demo(self):
        launcher = shutil.which("pwsh") or shutil.which("powershell.exe")
        if not launcher:
            self.skipTest("PowerShell is not available")
        run = self.base / "demo"
        command = [
            launcher, "-NoProfile", "-NonInteractive", "-File", str(ROOT / "scripts" / "run-harness-demo.ps1"),
            "-RunDirectory", str(run), "-TrustBundledTests",
        ]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        output = [json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")]
        self.assertEqual(output[-1]["status"], "COMPLETED")
        self.assertIn(b"return a + b", (run / "project" / "calculator.py").read_bytes())
