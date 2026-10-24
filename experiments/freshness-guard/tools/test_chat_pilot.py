"""Synthetic collector tests. All answers/evidence stay in TemporaryDirectory."""
import copy
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path

import chat_pilot as p


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'synthetic-run'
        with redirect_stdout(StringIO()):
            p.init(self.root)
        self.e = p.evaluator(self.root)
        (self.root / 'evidence/setup.txt').write_text('SYNTHETIC SETUP ONLY', encoding='utf-8')
        (self.root / 'evidence/trace.txt').write_text('SYNTHETIC TRACE ONLY', encoding='utf-8')
        env = p.read(self.root / 'environment.json')
        env.update(operator='synthetic-collector', model='synthetic-model', client='synthetic-client',
                   plan='synthetic-plan', tools='synthetic-tools', model_version_observation='synthetic',
                   isolation_method='SYNTHETIC ONLY')
        for c in env['conditions'].values():
            c.update(available=True, isolated=True, setup_evidence='evidence/setup.txt', explanation='SYNTHETIC ONLY')
        p.write(self.root / 'environment.json', env)
        for cid in p.SELECTED:
            t = datetime.now(timezone.utc)
            gold = dict(reviewer='synthetic-gold', independent=True, answer='SYNTHETIC ONLY',
                        evidence='SYNTHETIC DERIVATION ONLY', scope='SYNTHETIC', independence_note='SYNTHETIC',
                        prepared_at=(t-timedelta(seconds=1)).isoformat(),
                        valid_from=(t-timedelta(minutes=1)).isoformat(),
                        valid_until=(t+timedelta(minutes=15)).isoformat(), source_files=['evidence/setup.txt'])
            f = self.root / 'gold-drafts' / f'{cid}.json'
            p.write(f, gold)
            p.freeze_gold(self.root, cid, f)

    def begin(self, tid):
        with redirect_stdout(StringIO()):
            p.begin(self.root, tid)
        return sorted((self.root / 'attempts' / tid).glob('a*'))[-1]

    def capture(self, tid):
        a = self.begin(tid)
        start = p.read(a / 'start.json')
        meta = p.read(a / 'metadata.json')
        meta.update(session_id=f'synthetic-{tid}', started_at=p.now(), ended_at=p.now(), extra_actions=0,
                    trace_ref='evidence/trace.txt', capture_path='chat_web_ui', output_complete=True,
                    output_unedited=True, evidence_files=['evidence/trace.txt'], observation_notes='SYNTHETIC ONLY',
                    selection_observation={'baseline':'none','implicit':'unobservable','explicit':'manual'}[start['condition']])
        p.write(a / 'metadata.json', meta)
        (a / 'response.txt').write_text('SYNTHETIC ONLY; NOT A CHAT ANSWER', encoding='utf-8')
        p.finish(self.root, tid, a.name, 'captured', 'sent', '', [])

    def score_all(self):
        scores = {}
        plan = p.read(self.root / 'pilot.json')
        m = p.read(self.root / 'manifest.json')
        for t in m['trials']:
            if t['id'] not in plan['trial_ids']:
                continue
            raw = p.read(self.root / 'raw' / f"{t['id']}.json")
            gold = p.read(self.root / 'gold' / f"{t['case_id']}.json")
            scores[t['blind_id']] = dict(reviewer='synthetic-grader', independent=True,
                independent_of_response_producer=True, reason='SYNTHETIC ONLY', scored_at=p.now(),
                blinding_broken=False, blinding_note='SYNTHETIC ONLY',
                response_sha256=raw['response_sha256'], gold_sha256=self.e.digest(gold),
                correct=True, unsupported_certain=False, abstained=False, unnecessary_search=False, fact_changed=False)
        p.write(self.root / 'scores.json', scores)

    def report(self):
        with redirect_stdout(StringIO()):
            code = p.report(self.root)
        return code, p.read(self.root / 'report-pilot.json')

    def test_empty_preserves_48_and_nulls(self):
        self.assertEqual((self.root / 'manifest.json').read_bytes(),
            (p.BASE / 'recorded/2026-10-22/chat-evaluation-pending/manifest.json').read_bytes())
        self.assertEqual(p.read(self.root / 'pilot.json')['trial_ids'],
            ['t0001','t0002','t0003','t0004','t0005','t0006','t0013','t0014','t0015'])
        code, r = self.report()
        self.assertEqual(code, 2)
        self.assertEqual(r['captured_outputs'], 0)
        self.assertIsNone(r['conditions']['baseline']['correct']['rate'])
        self.assertEqual(len(p.read(self.root / 'report-48.json')['pending']), 48)
        with self.assertRaises(FileExistsError):
            p.init(self.root)

    def test_full_synthetic_chain_is_descriptive_only(self):
        for tid in p.read(self.root / 'pilot.json')['trial_ids']:
            self.capture(tid)
        # Real capture is never considered correct without independent scores.
        self.assertEqual(self.report()[0], 2)
        dest = Path(self.temp.name) / 'blind'
        with redirect_stdout(StringIO()):
            p.blind(self.root, dest)
        self.assertEqual(len(list(dest.glob('b*.json'))), 9)
        for row in p.read(dest / 'scores.template.json').values():
            self.assertIsNone(row['correct'])
            self.assertIs(row['independent'], False)
        self.score_all()
        code, r = self.report()
        self.assertEqual(code, 0)
        self.assertEqual(r['independently_scored_paired_trials'], 9)
        self.assertEqual(r['full_plan_status'], 'incomplete')
        self.assertEqual(len(p.read(self.root / 'report-48.json')['pending']), 39)
        self.assertFalse(r['causal_improvement_proven'])
        self.assertFalse(r['automatic_trigger_proven'])
        self.assertFalse(r['english_behavior_proven'])
        with self.assertRaises(ValueError):
            self.begin('t0001')
        with self.assertRaises(ValueError):
            p.freeze_gold(self.root, 'meta-release', self.root/'gold-drafts/meta-release.json')

    def test_failures_preserve_partial_and_block_unknown_retry(self):
        a = self.begin('t0001')
        (a / 'response.txt').write_text('SYNTHETIC PARTIAL', encoding='utf-8')
        p.finish(self.root, 't0001', a.name, 'send_unknown', 'unknown', 'SYNTHETIC TIMEOUT', ['evidence/trace.txt'])
        self.assertFalse((self.root/'raw/t0001.json').exists())
        self.assertEqual((a / 'response.txt').read_text(encoding='utf-8'), 'SYNTHETIC PARTIAL')
        with self.assertRaises(ValueError): self.begin('t0001')
        with self.assertRaises(ValueError):
            p.finish(self.root, 't0001', a.name, 'captured', 'sent', '', [])
        code, r = self.report()
        self.assertEqual(code, 2)
        self.assertEqual(r['attempts'][0]['outcome'], 'send_unknown')
        self.assertIsNone(r['conditions']['implicit']['correct']['rate'])

    def test_access_retry_is_bounded(self):
        for i in range(2):
            a = self.begin('t0001')
            p.finish(self.root, 't0001', a.name, 'page_timeout', 'not_sent', 'SYNTHETIC ACCESS ERROR', [])
        with self.assertRaises(ValueError): self.begin('t0001')
        self.assertEqual(len(self.report()[1]['attempts']), 2)

    def test_blocker_not_run_and_no_gold_or_unisolated_capture(self):
        p.block(self.root, 't0001', 'SYNTHETIC PREREQUISITE MISSING')
        self.assertEqual(self.report()[1]['blockers'][0]['status'], 'NOT_RUN')
        (self.root/'gold-seals/meta-release.json').unlink()
        with self.assertRaises(FileNotFoundError): self.begin('t0001')
        with self.assertRaises(ValueError): self.begin('t0004')

    def test_tampered_evidence_and_self_scoring_excluded(self):
        for tid in ['t0001','t0002','t0003']:
            self.capture(tid)
        # Score only these three using the original evaluator-compatible fields.
        scores = {}
        for t in p.read(self.root/'manifest.json')['trials'][:3]:
            raw = p.read(self.root/'raw'/f"{t['id']}.json")
            scores[t['blind_id']] = dict(reviewer='synthetic-collector', independent=True,
                independent_of_response_producer=True, reason='SYNTHETIC', scored_at=p.now(),
                blinding_broken=False, blinding_note='SYNTHETIC', response_sha256=raw['response_sha256'],
                gold_sha256=self.e.digest(p.read(self.root/'gold/meta-release.json')),
                correct=True, unsupported_certain=False, abstained=False, unnecessary_search=False, fact_changed=False)
        p.write(self.root/'scores.json', scores)
        r = self.report()[1]
        self.assertEqual(r['independently_scored_paired_trials'], 0)
        self.assertTrue(any('collector cannot' in x['reason'] for x in r['excluded']))
        p.write(self.root/'scores.json', {})
        (self.root/'evidence/trace.txt').write_text('TAMPERED', encoding='utf-8')
        r = self.report()[1]
        self.assertTrue(any('evidence changed' in x['reason'] for x in r['excluded']))


if __name__ == '__main__':
    unittest.main(verbosity=2)
