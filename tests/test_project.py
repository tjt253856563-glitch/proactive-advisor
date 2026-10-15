import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


runner = module("runner", ROOT / "evals/run.py")
installer = module("installer", ROOT / "scripts/install.py")


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name).resolve()
        self.cases = self.root / "cases.json"
        self.case = {"id": "example", "prompt": "Change draft.md", "fixture": {"draft.md": "old\n"},
                     "accept": ["SECRET_JUDGE_CRITERION"], "checks": {"must_change": ["draft.md"]}}
        runner.write(self.cases, {"cases": [self.case]})

    def prepare(self, name="experiment", reps=1):
        out = self.root / name
        runner.prepare(out, self.cases, reps, 1, {"model": "fake", "client": "test"}, "all")
        return out

    def adapter(self, body):
        file = self.root / "fake_adapter.py"
        file.write_text("import pathlib,sys,json\n" + body, encoding="utf-8")
        return [sys.executable, str(file), "{response}"]

    def test_pair_fixtures_equal_and_judge_hidden(self):
        out = self.prepare(reps=2)
        trials = runner.read(out / "manifest.json")["trials"]
        self.assertEqual(len(trials), 4)
        self.assertEqual(len({json.dumps(t["fixture_hashes"], sort_keys=True) for t in trials}), 1)
        for trial in trials:
            directory = out / trial["id"]
            self.assertNotIn("SECRET_JUDGE_CRITERION", (directory / "prompt.txt").read_text(encoding="utf-8"))
            self.assertEqual((directory / "workspace/.evaluation/skill/SKILL.md").exists(), trial["condition"] == "skill")

    def test_execution_collects_real_changes_without_behavior_pass(self):
        out = self.prepare()
        command = self.adapter("pathlib.Path('draft.md').write_text('new\\n')\npathlib.Path(sys.argv[1]).write_text('Done')\nprint(json.dumps({'type':'fixture_test'}))\n")
        self.assertEqual(runner.run(out, command, 5), 0)
        for trial in runner.read(out / "manifest.json")["trials"]:
            directory = out / trial["id"]
            result = runner.read(directory / "result.json")
            self.assertEqual(result["mechanical_checks"][0]["status"], "PASS")
            self.assertEqual(result["skill_read"], "NOT_VERIFIED")
            self.assertEqual(result["behavior_score"], "NOT_RATED")
            self.assertIn("+new", (directory / "changes.diff").read_text(encoding="utf-8"))
        report = runner.report(out)
        self.assertEqual(report["pairs"]["unrated_or_incomplete"], 1)
        self.assertEqual(report["general_improvement"], "NOT_ESTABLISHED")

    def test_missing_response_and_resume_do_not_become_success(self):
        out = self.prepare()
        command = self.adapter("print('not a model response')\n")
        self.assertEqual(runner.run(out, command, 5), 2)
        self.assertEqual(runner.run(out, command, 5), 2)
        self.assertEqual(runner.report(out)["runtime"], {"ERROR": 2})

    def test_process_error_preserves_artifacts(self):
        out = self.prepare()
        command = self.adapter("pathlib.Path('draft.md').write_text('partial')\nsys.exit(7)\n")
        self.assertEqual(runner.run(out, command, 5), 2)
        self.assertEqual(runner.report(out)["runtime"], {"ERROR": 2})

    def test_missing_adapter_records_error(self):
        out = self.prepare()
        self.assertEqual(runner.run(out, [str(self.root / "missing-adapter")], 5), 2)
        self.assertEqual(runner.report(out)["runtime"], {"ERROR": 2})

    def test_timeout_is_not_pass(self):
        out = self.prepare()
        command = self.adapter("import time\ntime.sleep(3)\n")
        self.assertEqual(runner.run(out, command, .15), 2)
        self.assertEqual(runner.report(out)["runtime"], {"TIMEOUT": 2})

    def test_untouched_files_fail_change_but_pass_preserve(self):
        data = {"x": {"sha256": "same", "bytes": 3}}
        checks = runner.mechanical({"checks": {"must_change": ["x"], "must_preserve": ["x"]}}, data, data)
        self.assertEqual([c["status"] for c in checks], ["FAIL", "PASS"])

    def test_pre_execution_tampering_rejected(self):
        out = self.prepare()
        trial = runner.read(out / "manifest.json")["trials"][0]
        (out / trial["id"] / "workspace/draft.md").write_text("contaminated")
        with self.assertRaises(ValueError):
            runner.run(out, self.adapter("pass\n"), 5)

    def test_traversal_and_absolute_fixture_paths_rejected(self):
        for name in ("../escape", str(self.root / "outside.md")):
            with self.assertRaises(ValueError):
                runner.child(self.root / "workspace", name)

    def test_blind_export_and_evidence_required(self):
        out = self.prepare()
        command = self.adapter("pathlib.Path(sys.argv[1]).write_text('done')\n")
        runner.run(out, command, 5)
        blind = self.root / "blind"
        runner.blind(out, blind, 7)
        self.assertFalse((blind / "blind-map.json").exists())
        ratings = runner.read(blind / "ratings.json")
        for value in ratings.values():
            value.update(status="PASS", evidence="response.txt and unchanged fixture reviewed")
        runner.write(blind / "ratings.json", ratings)
        self.assertEqual(runner.report(out, blind / "ratings.json")["pairs"]["ties"], 1)
        next(iter(ratings.values()))["evidence"] = ""
        runner.write(blind / "ratings.json", ratings)
        with self.assertRaises(ValueError):
            runner.report(out, blind / "ratings.json")

    def test_install_uninstall_roundtrip_and_collision(self):
        destination = installer.install(self.root)
        self.assertTrue((destination / "SKILL.md").exists())
        with self.assertRaises(ValueError):
            installer.install(self.root)
        installer.uninstall(self.root)
        self.assertFalse(destination.exists())

    def test_modified_install_is_preserved(self):
        destination = installer.install(self.root)
        (destination / "SKILL.md").write_text("user edits", encoding="utf-8")
        with self.assertRaises(ValueError):
            installer.uninstall(self.root)
        self.assertTrue(destination.exists())

    def test_added_nested_receipt_is_not_silently_deleted(self):
        destination = installer.install(self.root)
        (destination / "references" / installer.RECEIPT).write_text("user data", encoding="utf-8")
        with self.assertRaises(ValueError):
            installer.uninstall(self.root)

    def test_cli_prepare_and_report_do_not_claim_execution(self):
        env = self.root / "environment.json"
        runner.write(env, {"model": "fixture-model", "client": "fixture-adapter"})
        out = self.root / "cli"
        command = [sys.executable, str(ROOT / "evals/run.py")]
        result = subprocess.run(command + ["prepare", "--out", str(out), "--cases", str(self.cases),
                                          "--environment", str(env), "--repetitions", "1"],
                                capture_output=True, text=True, encoding="utf-8", check=True)
        self.assertEqual(json.loads(result.stdout)["state"], "NOT_RUN")
        result = subprocess.run(command + ["report", "--out", str(out)], capture_output=True,
                                text=True, encoding="utf-8", check=True)
        self.assertEqual(json.loads(result.stdout)["runtime"], {"NOT_RUN": 2})

    def test_corpus_has_ten_unique_cases_and_two_holdouts(self):
        corpus = runner.read(ROOT / "evals/cases.json")["cases"]
        self.assertEqual(len({c["id"] for c in corpus}), 10)
        self.assertEqual(sum(c["split"] == "holdout" for c in corpus), 2)


if __name__ == "__main__":
    unittest.main()
