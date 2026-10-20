#!/usr/bin/env python3
"""Deterministic contract regression; generated fixtures are NOT live facts."""
import argparse
import copy
import json
from pathlib import Path
from check_evidence import check

NOW = '2026-10-19T14:10:00+08:00'

def base(company='OpenAI', kind='release'):
    hosts = {'OpenAI': 'openai.com', 'Google': 'blog.google', 'Anthropic': 'anthropic.com', 'Meta': 'ai.meta.com'}
    c = {'id': 'fixture', 'company': company, 'kind': kind, 'claim': 'Synthetic claim, not a real event',
         'status': 'verified', 'scope': 'Synthetic scope', 'conflict': False, 'limitation': '',
         'sources': [{'url': 'https://' + hosts[company] + '/fixture', 'official': True, 'opened': True,
           'retrieval_at': NOW, 'published_at': '2026-10-18', 'event_at': '2026-10-18', 'date_note': 'Synthetic dates',
           'locator': 'Synthetic fixture only', 'supports_exact': True, 'current_scope': True, 'origin': hosts[company]}]}
    if kind == 'entitlement':
        c['access_level'] = 'plan'
    return {'as_of': NOW, 'claims': [c]}

def run():
    cases = []
    def add(name, data, expected):
        result = check(data)
        cases.append({'id': name, 'expected_accept': expected, 'actual_accept': result['ok'],
                      'pass': result['ok'] == expected, 'errors': result['errors']})
    for company in ('OpenAI', 'Google', 'Anthropic', 'Meta'):
        for kind in ('release', 'entitlement', 'leadership'):
            add(company + '-' + kind, base(company, kind), True)
    mutations = [
        ('snippet-not-opened', lambda c: c['sources'][0].update(opened=False)),
        ('wrong-product-scope', lambda c: c['sources'][0].update(current_scope=False)),
        ('nonmatching-claim', lambda c: c['sources'][0].update(supports_exact=False)),
        ('same-scope-conflict', lambda c: c.update(conflict=True)),
        ('lookalike-domain', lambda c: c['sources'][0].update(url='https://openai.com.evil.example/')),
        ('http-not-https', lambda c: c['sources'][0].update(url='http://openai.com/')),
        ('domain-userinfo', lambda c: c['sources'][0].update(url='https://openai.com@evil.example/')),
        ('missing-publish-date-note', lambda c: c['sources'][0].update(published_at=None, date_note='')),
        ('timezone-missing', lambda c: c['sources'][0].update(retrieval_at='2026-10-19T12:00:00')),
        ('future-retrieval', lambda c: c['sources'][0].update(retrieval_at='2026-10-20T00:00:00Z')),
        ('bad-date', lambda c: c['sources'][0].update(published_at='2026-02-30')),
        ('missing-locator', lambda c: c['sources'][0].update(locator='')),
        ('boolean-string', lambda c: c['sources'][0].update(opened='true')),
        ('no-source', lambda c: c.update(sources=[])),
        ('account-from-plan', lambda c: c.update(kind='entitlement', access_level='account')),
        ('unscoped-absence', lambda c: c.update(absence_claim=True)),
        ('future-appointment-effective', lambda c: (c.update(event_phase='effective'), c['sources'][0].update(event_at='2027-01-01'))),
    ]
    for name, change in mutations:
        d = base(); change(d['claims'][0]); add(name, d, False)
    d = base(); d['claims'][0]['sources'][0].update(published_at=None)
    add('unknown-date-honest', d, True)
    d = base(); d['claims'][0].update(status='unknown', sources=[], limitation='Original unavailable')
    add('offline-safe-unknown', d, True)
    d = copy.deepcopy(d); d['claims'][0]['limitation'] = ''
    add('unknown-without-reason', d, False)
    d = base(); d['claims'][0].update(status='provisional', limitation='Screenshot only')
    d['claims'][0]['sources'][0].update(opened=False, official=False)
    add('screenshot-provisional', d, True)
    d = base(); c = d['claims'][0]; c.update(status='corroborated', limitation='Original blocked')
    a = c['sources'][0]; a.update(official=False, url='https://example.org/story', origin='wire-A')
    c['sources'].append(copy.deepcopy(a)); c['sources'][1]['url'] = 'https://example.net/copy'
    add('syndication-not-independent', d, False)
    d = copy.deepcopy(d); d['claims'][0]['sources'][1]['origin'] = 'independent-B'
    add('declared-independent-reports', d, True)
    d = base('Google', 'leadership'); d['claims'][0]['sources'][0]['url'] = 'https://about.google/company-info/'
    add('google-current-leadership-domain', d, True)
    d = base(); d['claims'].append(copy.deepcopy(d['claims'][0])); add('duplicate-id', d, False)
    add('empty-claims', {'as_of': NOW, 'claims': []}, False)
    add('invalid-root', [], False)
    d = base(); d['as_of'] = '2026-10-19'; add('cutoff-needs-timezone', d, False)
    # This probe documents a known trust boundary, not fact-checking success.
    d = base(); d['claims'][0]['claim'] = 'DELIBERATELY FALSE: a fabricated model was released.'
    boundary = {'fabricated_semantics_still_accepted': check(d)['ok'],
                'meaning': 'Reviewer-provided supports_exact cannot be proven by this checker.'}
    passed = sum(x['pass'] for x in cases)
    return {'suite': 'offline-structural-contract', 'total': len(cases), 'passed': passed,
            'failed': len(cases)-passed, 'rate': passed/len(cases), 'cases': cases, 'known_boundary': boundary,
            'not_measured': ['model accuracy', 'automatic Skill triggering', 'real-time index latency']}

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path)
    args = p.parse_args()
    result = run()
    out = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(out + '\n', encoding='utf-8')
    print(out)
    raise SystemExit(bool(result['failed']))
