#!/usr/bin/env python3
"""Collect ordinary-Chat evidence around the frozen PR #2 evaluator; never call a model."""
import argparse
import hashlib
import importlib.util
import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
SOURCE_COMMIT = '2aaca6b69a3d5b2862e0688d6a15d271b765a499'
SELECTED = ('meta-release', 'api-subscription', 'translation')
OUTCOMES = ('captured', 'page_timeout', 'read_timeout', 'send_unknown',
            'generation_failed', 'incomplete_output', 'condition_unavailable', 'aborted')


def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8'))


def write(p, data):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def timestamp(value):
    t = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if t.tzinfo is None:
        raise ValueError('timestamp requires timezone')
    return t


def text_required(value):
    return isinstance(value, str) and bool(value.strip())


def require(value, message):
    if not value:
        raise ValueError(message)


def local(root, value):
    require(text_required(value), 'evidence path is missing')
    p = (root / value).resolve()
    require(p.is_relative_to(root.resolve()) and p.is_file(), 'evidence must be a file inside run directory')
    return p


def evaluator(root):
    spec = importlib.util.spec_from_file_location('frozen_evaluator', root / 'version/scripts/evaluate.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load(root):
    p = read(root / 'pilot.json')
    require(sha(root / 'manifest.json') == p['manifest_file_sha256'], 'frozen 48-trial manifest changed')
    require(sha(__file__) == p['collector_sha256'], 'collector version changed; create a new run')
    for name, digest in p['version_files'].items():
        require(sha(root / 'version' / name) == digest, f'frozen plugin changed: {name}')
    e = evaluator(root)
    return p, e, e.load(root)


def init(root):
    source = BASE / 'recorded/2026-10-22/chat-evaluation-pending/manifest.json'
    m = read(source)
    require(m['cases_sha256'] == '940af37599230a66a14f2025d78b818a70233de15307e431ff3f6fbe262511db'
            and m['trials_sha256'] == 'c97377785bc46d9a02094961e3c6c00cb849272ec3a1feb841fed20384c1aeec',
            'unexpected source schedule')
    root.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(source, root / 'manifest.json')
    shutil.copytree(BASE / 'plugin/skills/freshness-guard', root / 'version',
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    for d in ('raw', 'gold', 'gold-drafts', 'gold-seals', 'attempts', 'evidence', 'imports'):
        (root / d).mkdir()
    selected = [t for t in m['trials'] if t['case_id'] in SELECTED]
    write(root / 'pilot.json', {
        'schema_version': 1, 'created_at': now(), 'source_pr': 'https://github.com/tjt253856563-glitch/proactive-advisor/pull/2',
        'source_commit': SOURCE_COMMIT, 'manifest_file_sha256': sha(source),
        'collector_sha256': sha(__file__), 'version_files': {
            str(p.relative_to(root / 'version')): sha(p) for p in sorted((root / 'version').rglob('*')) if p.is_file()},
        'selected_cases': list(SELECTED), 'trial_ids': [t['id'] for t in selected],
        'selection_reason': 'First release, entitlement and stable case in frozen order; chosen before responses.',
        'notice': 'Nine-trial feasibility pilot only. Original 48-trial schedule unchanged. No efficacy verdict.'})
    write(root / 'environment.json', {
        'operator': None, 'model': None, 'client': None, 'plan': None, 'tools': None,
        'model_version_observation': None,
        'isolation_method': None,
        'conditions': {c: {'available': None, 'isolated': None, 'setup_evidence': None,
                            'explanation': None} for c in ('baseline', 'implicit', 'explicit')}})
    write(root / 'scores.json', {})
    for case_id in SELECTED:
        write(root / 'gold-drafts' / f'{case_id}.json', {
            'reviewer': None, 'independent': False, 'answer': None, 'evidence': None,
            'prepared_at': None, 'valid_from': None, 'valid_until': None,
            'source_files': [], 'scope': None,
            'independence_note': None})
    for t in selected:
        c = next(c for c in m['cases'] if c['id'] == t['case_id'])
        folder = root / 'intake' / t['id']
        folder.mkdir(parents=True)
        (folder / 'prompt.txt').write_text(c['prompt'], encoding='utf-8')
        write(folder / 'trial.json', t)
    print(json.dumps({'run': str(root), 'selected': [t['id'] for t in selected], 'real_outputs': 0}))


def environment(root):
    env = read(root / 'environment.json')
    for k in ('operator', 'model', 'client', 'plan', 'tools', 'model_version_observation', 'isolation_method'):
        require(text_required(env.get(k)), f'environment requires {k}')
    for c, config in env['conditions'].items():
        require(config.get('available') is True and config.get('isolated') is True,
                f'{c}: unavailable/unisolated; keep trial blocked, do not relabel a substitute')
        require(text_required(config.get('explanation')), f'{c}: setup explanation required')
        local(root, config.get('setup_evidence'))
    require(set(env['conditions']) == {'baseline', 'implicit', 'explicit'}, 'all three conditions required')
    return env


def freeze_gold(root, case_id, input_path):
    p, e, _ = load(root)
    require(case_id in p['selected_cases'], 'case not selected')
    # The real start check uses case_id in the immutable attempt-start record.
    for path in (root / 'attempts').glob('*/a*/start.json'):
        require(read(path)['case_id'] != case_id, 'gold must be frozen before any attempt for the case')
    gold = read(input_path)
    env = read(root / 'environment.json')
    require(gold.get('independent') is True and text_required(gold.get('reviewer')),
            'independent named gold reviewer required')
    require(text_required(env.get('operator')) and gold['reviewer'] != env['operator'],
            'gold reviewer must differ from collector/operator')
    for k in ('answer', 'evidence', 'scope', 'independence_note'):
        require(text_required(gold.get(k)), f'gold requires {k}')
    start, end, prepared = (timestamp(gold[k]) for k in ('valid_from', 'valid_until', 'prepared_at'))
    require(start <= end and prepared <= datetime.now(timezone.utc), 'invalid gold times')
    require(bool(gold.get('source_files')), 'archive official sources, or stable derivation, before capture')
    evidence_hashes = {f: sha(local(root, f)) for f in gold['source_files']}
    require(not (root / 'gold' / f'{case_id}.json').exists(), 'gold already frozen; create a new run to replace')
    write(root / 'gold' / f'{case_id}.json', gold)
    write(root / 'gold-seals' / f'{case_id}.json', {
        'frozen_at': now(), 'gold_sha256': e.digest(gold), 'evidence_hashes': evidence_hashes})


def gold_check(root, case_id, e):
    gold = read(root / 'gold' / f'{case_id}.json')
    seal = read(root / 'gold-seals' / f'{case_id}.json')
    require(e.digest(gold) == seal['gold_sha256'], 'gold changed after freezing')
    for f, h in seal['evidence_hashes'].items():
        require(sha(local(root, f)) == h, 'gold source file changed')
    return gold, seal


def begin(root, tid):
    p, e, m = load(root)
    require(tid in p['trial_ids'], 'trial not selected')
    require(not (root / 'raw' / f'{tid}.json').exists(), 'already captured; do not select a preferred answer')
    ts = [t for t in m['trials'] if t['id'] in p['trial_ids']]
    for earlier in ts[:next(i for i, t in enumerate(ts) if t['id'] == tid)]:
        require(list((root / 'attempts' / earlier['id']).glob('a*/event.json')), 'follow frozen pilot order')
    trial = next(t for t in ts if t['id'] == tid)
    position = {t['id']: i for i, t in enumerate(ts)}
    for path in (root / 'attempts').glob('*/a*/start.json'):
        require(position[read(path)['id']] <= position[tid], 'cannot return to an earlier trial after advancing')
    gold, seal = gold_check(root, trial['case_id'], e)
    require(timestamp(gold['valid_from']) <= datetime.now(timezone.utc) <= timestamp(gold['valid_until']),
            'gold window is not current; start a new run with fresh gold')
    env = environment(root)
    folder = root / 'attempts' / tid
    folder.mkdir(exist_ok=True)
    require(not any(not (a / 'event.json').exists() for a in folder.glob('a*')), 'previous attempt still open')
    # One retry is for UI access before sending only. Never retry a sent/unknown/partial answer.
    previous = sorted(folder.glob('a*'))
    require(len(previous) < 2, 'two attempts exhausted; block case and create new run for fallback')
    if previous:
        event = read(previous[-1] / 'event.json')
        require(event['outcome'] in ('page_timeout', 'read_timeout') and event['submission_state'] == 'not_sent',
                'sent or ambiguous attempt cannot be retried in the same run')
    attempt = folder / f'a{len(previous)+1:04d}'
    attempt.mkdir()
    config = env['conditions'][trial['condition']]
    prompt = root / 'intake' / tid / 'prompt.txt'
    require(prompt.read_text(encoding='utf-8') == next(c['prompt'] for c in m['cases'] if c['id'] == trial['case_id']),
            'prompt changed')
    (attempt / 'response.txt').write_text('', encoding='utf-8')
    shutil.copyfile(prompt, attempt / 'sent-prompt.txt')
    write(attempt / 'metadata.json', {
        **{k: env[k] for k in ('model', 'client', 'plan', 'tools')},
        'session_id': None, 'started_at': None, 'ended_at': None,
        'trace_ref': None, 'plugin_version': 'none' if trial['condition'] == 'baseline' else '2.1.0',
        'skill_loaded': None, 'searched': None, 'opened_original': None,
        'selection_observation': None,
        'extra_actions': None, 'isolated': True,
        'capture_path': None, 'output_complete': False, 'output_unedited': False,
        'evidence_files': [], 'observation_notes': None})
    write(attempt / 'start.json', {
        **trial, 'attempt': attempt.name, 'command_at': now(), 'environment': env,
        'setup_sha256': sha(local(root, config['setup_evidence'])),
        'gold_sha256': seal['gold_sha256'], 'prompt_file_sha256': sha(prompt)})
    print(str(attempt))


def finish(root, tid, attempt_id, outcome, submission, reason, evidence):
    _, e, m = load(root)
    require(outcome in OUTCOMES, 'unknown outcome')
    a = root / 'attempts' / tid / attempt_id
    s = read(a / 'start.json')
    require(s['id'] == tid and s['attempt'] == attempt_id, 'attempt identity changed')
    require(not (a / 'event.json').exists(), 'attempt already closed; original is immutable')
    hashes = {f: sha(local(root, f)) for f in evidence}
    record = {'outcome': outcome, 'submission_state': submission, 'reason': reason,
              'closed_at': now(), 'evidence_hashes': hashes}
    if outcome == 'captured':
        require(submission == 'sent', 'captured answer requires confirmed send')
        meta = read(a / 'metadata.json')
        require(meta.get('output_complete') is True and meta.get('output_unedited') is True,
                'complete unedited output required; otherwise close as incomplete_output')
        require(meta.get('capture_path') in ('chat_web_ui', 'chat_android_ui', 'chat_export'),
                'only ordinary Chat UI/export; no API/Work substitution')
        require(text_required(meta.get('observation_notes')), 'observation notes required, including unobservable traces')
        env = s['environment']
        require(meta.get('selection_observation') in ('none', 'natural', 'manual', 'unobservable'),
                'record actual selection observation, distinct from loading')
        require(s['condition'] != 'explicit' or meta['selection_observation'] == 'manual',
                'explicit condition requires actual manual plugin selection')
        require(s['condition'] != 'implicit' or meta['selection_observation'] != 'manual',
                'natural trigger cannot use manual selection')
        require(s['condition'] != 'baseline' or meta['selection_observation'] == 'none',
                'baseline must have no Freshness Guard selection')
        require(s['condition'] != 'baseline' or meta.get('skill_loaded') is not True,
                'baseline cannot declare Freshness Guard loaded')
        for k in ('model', 'client', 'plan', 'tools'):
            require(meta.get(k) == env[k], f'{k} differs from frozen environment')
        require(meta.get('isolated') is True, 'non-isolated output is not a qualified capture')
        require(meta.get('plugin_version') == ('none' if s['condition'] == 'baseline' else '2.1.0'), 'wrong plugin version')
        require(text_required(meta.get('session_id')), 'unique pseudonymous session ID required')
        for path in (root / 'raw').glob('*.json'):
            require(read(path)['metadata']['session_id'] != meta['session_id'], 'session reused')
        gold, seal = gold_check(root, s['case_id'], e)
        require(timestamp(seal['frozen_at']) <= timestamp(meta['started_at']), 'gold was not frozen before send')
        require(timestamp(s['command_at']) <= timestamp(meta['started_at']) <= timestamp(meta['ended_at']) <= datetime.now(timezone.utc),
                'send/end timestamps must be observed after begin and before finish')
        require(timestamp(gold['valid_from']) <= timestamp(meta['started_at']) <= timestamp(meta['ended_at']) <= timestamp(gold['valid_until']),
                'response outside gold validity window')
        require(sha(a / 'sent-prompt.txt') == s['prompt_file_sha256'], 'actual sent prompt differs')
        require(bool(meta.get('evidence_files')), 'original UI/export evidence required')
        for f in meta['evidence_files']:
            hashes[f] = sha(local(root, f))
        local(root, meta.get('trace_ref'))
        hashes[meta['trace_ref']] = sha(local(root, meta['trace_ref']))
        setup = env['conditions'][s['condition']]['setup_evidence']
        require(sha(local(root, setup)) == s['setup_sha256'], 'setup evidence changed')
        hashes[setup] = s['setup_sha256']
        e.import_trial(root, tid, a / 'response.txt', a / 'metadata.json')
        record['raw_file_sha256'] = sha(root / 'raw' / f'{tid}.json')
        record['source_files_sha256'] = {name: sha(a / name) for name in ('response.txt', 'metadata.json', 'sent-prompt.txt', 'start.json')}
        write(root / 'imports' / f'{tid}.json', {'attempt_path': str(a.relative_to(root)), **record})
    else:
        require(text_required(reason), 'failure reason required; never replace failure with a pass')
        # Preserve any partial response and metadata even for a failure.
        record['source_files_sha256'] = {name: sha(a / name) for name in ('response.txt', 'metadata.json', 'sent-prompt.txt', 'start.json')}
    write(a / 'event.json', record)


def block(root, tid, reason):
    p, _, m = load(root)
    require(tid in p['trial_ids'] and text_required(reason), 'selected trial and concrete blocking reason required')
    folder = root / 'blockers'
    folder.mkdir(exist_ok=True)
    path = folder / f'{tid}.json'
    require(not path.exists(), 'blocker already recorded; preserve original')
    write(path, {'trial': tid, 'status': 'NOT_RUN', 'recorded_at': now(), 'reason': reason,
                 'notice': 'No model output or trial success implied; this is a prerequisite/access blocker.'})


def invalid_capture(root, tid, e, score):
    try:
        seal = read(root / 'imports' / f'{tid}.json')
        require(sha(root / 'raw' / f'{tid}.json') == seal['raw_file_sha256'], 'imported raw/metadata changed')
        a = root / seal['attempt_path']
        require(read(a / 'event.json')['outcome'] == 'captured', 'capture not closed')
        for f, h in seal['source_files_sha256'].items():
            require(sha(a / f) == h, f'capture source changed: {f}')
        for f, h in seal['evidence_hashes'].items():
            require(sha(local(root, f)) == h, f'capture evidence changed: {f}')
        start = read(a / 'start.json')
        gold_check(root, start['case_id'], e)
        if score is not None:
            require(score.get('reviewer') != start['environment']['operator'], 'collector cannot independently score own run')
            require(score.get('independent_of_response_producer') is True, 'response-producer independence declaration required')
            require(type(score.get('blinding_broken')) is bool, 'blinding status required')
            require(text_required(score.get('blinding_note')), 'blinding note required')
            require(timestamp(read(root / 'raw' / f'{tid}.json')['metadata']['ended_at'])
                    <= timestamp(score['scored_at']) <= datetime.now(timezone.utc),
                    'score timestamp must follow response and cannot be in future')
        return None
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return str(exc)


def report(root):
    p, e, m = load(root)
    scores = read(root / 'scores.json')
    require(isinstance(scores, dict), 'scores must be a mapping')
    selected = [t for t in m['trials'] if t['id'] in p['trial_ids']]
    exclusions = []
    with tempfile.TemporaryDirectory() as temp:
        clean = Path(temp)
        shutil.copyfile(root / 'manifest.json', clean / 'manifest.json')
        shutil.copytree(root / 'raw', clean / 'raw')
        shutil.copytree(root / 'gold', clean / 'gold')
        for t in selected:
            if (root / 'raw' / f"{t['id']}.json").exists():
                issue = invalid_capture(root, t['id'], e, scores.get(t['blind_id']))
                if issue:
                    exclusions.append({'trial': t['id'], 'reason': issue})
                    (clean / 'raw' / f"{t['id']}.json").unlink()
        full = e.analyze(clean, root / 'scores.json')
    write(root / 'report-48.json', full)
    events = []
    for path in sorted((root / 'attempts').glob('*/a*/start.json')):
        event_path = path.parent / 'event.json'
        events.append({'trial': read(path)['id'], 'attempt': path.parent.name,
                       **(read(event_path) if event_path.exists() else {'outcome': 'in_progress'})})
    paired = full['paired_trials']  # Only selected trials can be imported through this collector.
    require(set(x.stem for x in (root / 'raw').glob('*.json')) <= set(p['trial_ids']), 'nonpilot output in pilot run')
    result = {
        'status': 'complete_descriptive_only' if paired == 9 and not exclusions else 'incomplete',
        'planned_pilot': 9, 'captured_outputs': len(list((root / 'raw').glob('*.json'))),
        'independently_scored_paired_trials': paired,
        'pending': [x for x in full['pending'] if x['trial'] in p['trial_ids']],
        'excluded': exclusions + [x for x in full['invalid'] if x['trial'] in p['trial_ids']],
        'unpaired': [x for x in full['unpaired'] if x['case'] in p['selected_cases']],
        'attempts': events, 'conditions': full['conditions'],
        'blockers': [read(f) for f in sorted((root / 'blockers').glob('*.json'))],
        'paired_differences_vs_baseline': full['paired_differences_vs_baseline'],
        'full_plan_status': full['status'], 'full_plan_planned': 48,
        'causal_improvement_proven': False, 'automatic_trigger_proven': False,
        'english_behavior_proven': False,
        'notice': '结构测试通过不等于效果证明。0-output rates are null. This is a 3-case feasibility pilot, not evidence of efficacy, automatic invocation or English behavior. Hashes and identity declarations do not authenticate logs or independence.'}
    write(root / 'report-pilot.json', result)
    print(json.dumps({k: result[k] for k in ('status', 'captured_outputs', 'independently_scored_paired_trials', 'full_plan_status')}))
    return 0 if result['status'] == 'complete_descriptive_only' else 2


def blind(root, dest):
    p, e, m = load(root)
    for t in m['trials']:
        if (root / 'raw' / f"{t['id']}.json").exists():
            require(invalid_capture(root, t['id'], e, None) is None, 'capture integrity failed before blinding')
    e.blind(root, dest)
    template = {}
    for path in dest.glob('b*.json'):
        row = read(path)
        template[row['blind_id']] = {
            'reviewer': None, 'independent': False, 'independent_of_response_producer': False,
            'reason': None, 'response_sha256': row['response_sha256'],
            'gold_sha256': e.digest(row['gold']),
            **{k: None for k in (*e.METRICS, 'fact_changed')},
            'scored_at': None, 'blinding_broken': None, 'blinding_note': None}
    write(dest / 'scores.template.json', template)
    print(f'{len(template)} actual outputs exported; no score prefilled as passing')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='cmd', required=True)
    for cmd in ('init', 'report'):
        sub.add_parser(cmd).add_argument('root', type=Path)
    a = sub.add_parser('gold'); a.add_argument('root', type=Path); a.add_argument('case_id'); a.add_argument('--input', type=Path, required=True)
    a = sub.add_parser('begin'); a.add_argument('root', type=Path); a.add_argument('trial')
    a = sub.add_parser('block'); a.add_argument('root', type=Path); a.add_argument('trial'); a.add_argument('--reason', required=True)
    a = sub.add_parser('finish'); a.add_argument('root', type=Path); a.add_argument('trial'); a.add_argument('attempt')
    a.add_argument('--outcome', choices=OUTCOMES, required=True)
    a.add_argument('--submission', choices=('not_sent', 'sent', 'unknown'), required=True)
    a.add_argument('--reason', default=''); a.add_argument('--evidence', nargs='*', default=[])
    a = sub.add_parser('blind'); a.add_argument('root', type=Path); a.add_argument('dest', type=Path)
    args = parser.parse_args()
    try:
        if args.cmd == 'init': init(args.root)
        elif args.cmd == 'gold': freeze_gold(args.root, args.case_id, args.input)
        elif args.cmd == 'begin': begin(args.root, args.trial)
        elif args.cmd == 'block': block(args.root, args.trial, args.reason)
        elif args.cmd == 'finish': finish(args.root, args.trial, args.attempt, args.outcome, args.submission, args.reason, args.evidence)
        elif args.cmd == 'blind': blind(args.root, args.dest)
        else: return report(args.root)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f'{exc}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
