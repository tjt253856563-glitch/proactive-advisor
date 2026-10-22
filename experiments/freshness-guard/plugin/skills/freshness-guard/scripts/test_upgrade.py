#!/usr/bin/env python3
"""Synthetic regression only. No real Chat accuracy is measured here."""
import copy
import json
import random
import tempfile
import unittest
from pathlib import Path
from check_evidence import check
from run_tests import base, run
from evaluate import init, import_trial, analyze, blind, read, write, digest

class EvidenceTests(unittest.TestCase):
    def test_existing(self):
        self.assertEqual(run()['failed'],0)

    def test_wrong_types_do_not_crash(self):
        rng=random.Random(17)
        values=[None,[],{},0,True,'', '   ', ['x'], {'x':'y'}]
        keys=['company','kind','status','id','claim','scope','conflict','limitation','sources','access_level','event_phase','absence_claim']
        sourcekeys=list(base()['claims'][0]['sources'][0])
        for i in range(500):
            d=base(); c=d['claims'][0]
            if i%2: c[rng.choice(keys)]=copy.deepcopy(rng.choice(values))
            else: c['sources'][0][rng.choice(sourcekeys)]=copy.deepcopy(rng.choice(values))
            with self.subTest(i=i):
                self.assertIs(type(check(d)['ok']),bool)

    def test_specific_rejections(self):
        changes=[
          lambda c:c.update(company=[]), lambda c:c.update(kind={}), lambda c:c.update(status=[]),
          lambda c:c.update(kind='entitlement',access_level=[]),
          lambda c:c.update(status='unknown',sources=[],limitation='   '),
          lambda c:c.update(absence_claim=True,checked_channels='all'),
          lambda c:c.update(absence_claim='true'),lambda c:c.update(event_phase=[]),
          lambda c:c['sources'][0].update(published_at='2027-01-01'),
          lambda c:c['sources'][0].update(updated_at='2027-01-01'),
          lambda c:c['sources'][0].update(crawled_at='2027-01-01'),
          lambda c:c['sources'][0].update(origin=[]),
          lambda c:c['sources'][0].update(locator='   '),
          lambda c:c['sources'][0].update(date_note=[]),
          lambda c:c['sources'][0].update(event_at=123),
        ]
        for index,change in enumerate(changes):
            d=base(); change(d['claims'][0])
            with self.subTest(i=index): self.assertFalse(check(d)['ok'])

    def test_origin_normalization(self):
        d=base();c=d['claims'][0];c.update(status='corroborated',limitation='Original unavailable')
        s=c['sources'][0]; s.update(official=False,url='https://example.org/a',origin='Wire-A')
        c['sources'].append(dict(s,url='https://example.net/b',origin=' wire-a '))
        self.assertFalse(check(d)['ok'])

    def test_future_announcement_allowed(self):
        d=base();d['claims'][0].update(event_phase='announced')
        d['claims'][0]['sources'][0]['event_at']='2027-01-01'
        self.assertTrue(check(d)['ok'])

class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'experiment'
        self.cases=Path(__file__).resolve().parents[1]/'references/eval-cases.json'
        init(self.root,self.cases)
        self.scores=Path(self.temp.name)/'scores.json';write(self.scores,{})

    def fill(self):
        scores={}
        for t in read(self.root/'manifest.json')['trials']:
            response=Path(self.temp.name)/'response.txt';response.write_text('SYNTHETIC ONLY',encoding='utf-8')
            meta=Path(self.temp.name)/'meta.json'
            write(meta,dict(model='synthetic-model',client='synthetic-client',plan='synthetic-plan',tools='synthetic-tools',
                 session_id=t['id'],started_at='2026-10-22T10:00:00+08:00',ended_at='2026-10-22T10:00:02+08:00',
                 trace_ref='synthetic-trace',plugin_version='none' if t['condition']=='baseline' else '2.1.0',
                 skill_loaded=None,searched=False,opened_original=False,extra_actions=0,isolated=True))
            import_trial(self.root,t['id'],response,meta)
            gold=dict(independent=True,reviewer='synthetic-reviewer',answer='SYNTHETIC',evidence='SYNTHETIC',
                 valid_from='2026-10-22T09:00:00+08:00',valid_until='2026-10-22T11:00:00+08:00')
            write(self.root/'gold'/f"{t['case_id']}.json",gold)
            scores[t['blind_id']]=dict(independent=True,reviewer='synthetic-reviewer',reason='SYNTHETIC ONLY',
                 response_sha256=digest('SYNTHETIC ONLY'),gold_sha256=digest(gold),
                 correct=True,unsupported_certain=False,abstained=False,unnecessary_search=False,fact_changed=False)
        write(self.scores,scores)

    def test_empty_is_incomplete(self):
        r=analyze(self.root,self.scores)
        self.assertEqual(r['status'],'incomplete'); self.assertEqual(len(r['pending']),48)
        self.assertIsNone(r['conditions']['baseline']['correct']['rate'])

    def test_paired_metrics_and_blind_export(self):
        self.fill();r=analyze(self.root,self.scores)
        self.assertEqual(r['status'],'complete_descriptive_only');self.assertEqual(r['paired_trials'],48)
        self.assertFalse(r['causal_improvement_proven'])
        self.assertEqual(r['conditions']['implicit']['trace_observations']['skill_loaded']['unobservable'],16)
        self.assertEqual(r['paired_differences_vs_baseline']['explicit']['correct']['pairs'],16)
        dest=Path(self.temp.name)/'blind';blind(self.root,dest)
        for p in dest.glob('*.json'):
            self.assertNotIn('metadata',read(p));self.assertNotIn('condition',read(p))

    def test_invalid_scores_do_not_pass(self):
        self.fill();s=read(self.scores);key=next(iter(s));s[key]['independent']=False;write(self.scores,s)
        r=analyze(self.root,self.scores)
        self.assertEqual(r['status'],'incomplete');self.assertEqual(r['paired_trials'],45)

    def test_model_mismatch_removes_entire_pair(self):
        self.fill();p=self.root/'raw/t0001.json';raw=read(p);raw['metadata']['model']='different';write(p,raw)
        self.assertEqual(analyze(self.root,self.scores)['paired_trials'],45)

    def test_tampered_raw(self):
        self.fill();p=self.root/'raw/t0001.json';raw=read(p);raw['response']='changed';write(p,raw)
        self.assertEqual(len(analyze(self.root,self.scores)['invalid']),1)

    def test_plugin_version_mismatch(self):
        self.fill()
        t=next(t for t in read(self.root/'manifest.json')['trials'] if t['condition']=='implicit')
        p=self.root/'raw'/f"{t['id']}.json";r=read(p);r['metadata']['plugin_version']='old';write(p,r)
        self.assertEqual(analyze(self.root,self.scores)['paired_trials'],45)

    def test_pair_window(self):
        self.fill();p=self.root/'raw/t0001.json';r=read(p)
        r['metadata']['ended_at']='2026-10-22T10:30:00+08:00';write(p,r)
        self.assertEqual(analyze(self.root,self.scores)['paired_trials'],45)

    def test_frozen_schedule(self):
        m=read(self.root/'manifest.json');m['trials'][0]['condition']='explicit';m['trials'][0]['id']='changed';write(self.root/'manifest.json',m)
        with self.assertRaises(ValueError):analyze(self.root,self.scores)

    def test_stale_gold(self):
        self.fill();p=next((self.root/'gold').glob('*.json'));g=read(p);g['valid_until']='2026-10-21T00:00:00+08:00';write(p,g)
        s=read(self.scores)
        for t in read(self.root/'manifest.json')['trials']:
            if t['case_id']==p.stem:s[t['blind_id']]['gold_sha256']=digest(g)
        write(self.scores,s)
        self.assertEqual(len(analyze(self.root,self.scores)['invalid']),3)

if __name__=='__main__':
    unittest.main(verbosity=2)
