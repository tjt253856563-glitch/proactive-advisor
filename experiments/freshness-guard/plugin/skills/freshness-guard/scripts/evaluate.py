#!/usr/bin/env python3
"""Prepare/import/blind/score real Chat trials. Never generates model responses."""
import argparse
import hashlib
import json
import math
import random
from pathlib import Path
from datetime import datetime

CONDITIONS = ('baseline', 'implicit', 'explicit')
METRICS = ('correct', 'unsupported_certain', 'abstained', 'unnecessary_search')

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def write(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

def nonblank(value):
    return isinstance(value, str) and bool(value.strip())

def init(root, cases_path, seed=42, repeats=1):
    if repeats < 1:
        raise ValueError('repeats must be positive')
    cases = read(cases_path)['cases']
    ids = [c['id'] for c in cases]
    if len(ids) < 12 or len(set(ids)) != len(ids) or not all(nonblank(i) for i in ids):
        raise ValueError('at least 12 uniquely identified cases required')
    rng = random.Random(seed)
    rows=[]
    for repeat in range(repeats):
        order=cases.copy(); rng.shuffle(order)
        for c in order:
            conditions=list(CONDITIONS); rng.shuffle(conditions)
            for condition in conditions:
                rows.append({'id': f't{len(rows)+1:04d}', 'case_id':c['id'], 'repeat':repeat,
                             'condition':condition, 'blind_id':f'b{rng.getrandbits(96):024x}'})
    root.mkdir(parents=True, exist_ok=False)
    (root/'raw').mkdir()
    (root/'gold').mkdir()
    write(root/'manifest.json', {'schema_version':1,'seed':seed,'cases':cases,
          'cases_sha256':digest(cases), 'trials':rows,'trials_sha256':digest(rows),'max_pair_window_seconds':900,
          'notice':'Planned order only; contains no executed Chat trials.'})

def load(root):
    m=read(root/'manifest.json')
    if m['cases_sha256'] != digest(m['cases']):
        raise ValueError('frozen case set changed')
    if m['trials_sha256'] != digest(m['trials']):
        raise ValueError('frozen schedule changed')
    return m

def import_trial(root, trial_id, response_path, metadata_path):
    m=load(root)
    trial=next((t for t in m['trials'] if t['id']==trial_id), None)
    if trial is None:
        raise ValueError('unknown trial')
    dest=root/'raw'/f'{trial_id}.json'
    if dest.exists():
        raise ValueError('trial already imported; preserve original and create a new experiment')
    response=Path(response_path).read_text(encoding='utf-8')
    meta=read(metadata_path)
    for key in ('model','client','plan','tools','session_id','started_at','ended_at','trace_ref','plugin_version'):
        if not nonblank(meta.get(key)):
            raise ValueError(f'metadata requires {key}')
    times=[]
    for key in ('started_at','ended_at'):
        value=datetime.fromisoformat(meta[key].replace('Z','+00:00'))
        if value.tzinfo is None:
            raise ValueError('timestamps require timezone')
        times.append(value)
    if times[1]<times[0] or not nonblank(response):
        raise ValueError('empty response or reversed time')
    for key in ('skill_loaded','searched','opened_original'):
        if key not in meta or (meta[key] is not None and type(meta[key]) is not bool):
            raise ValueError(f'{key} requires boolean or null (unobservable)')
    if type(meta.get('extra_actions')) is not int or meta['extra_actions']<0:
        raise ValueError('extra_actions requires nonnegative integer')
    if type(meta.get('isolated')) is not bool:
        raise ValueError('isolated requires boolean')
    if (trial['condition']=='baseline') != (meta['plugin_version']=='none'):
        raise ValueError('baseline requires plugin_version none; other conditions require installed version')
    write(dest, {'response':response, 'response_sha256':digest(response), 'metadata':meta})

def blind(root, dest):
    m=load(root)
    dest.mkdir(parents=True, exist_ok=False)
    cases={c['id']:c for c in m['cases']}
    for t in m['trials']:
        p=root/'raw'/f"{t['id']}.json"
        if not p.exists():
            continue
        raw=read(p); gold=root/'gold'/f"{t['case_id']}.json"
        # No condition, model, session, trace or installation metadata in scoring copies.
        write(dest/f"{t['blind_id']}.json", {'blind_id':t['blind_id'],
          'case':cases[t['case_id']], 'response':raw['response'],
          'response_sha256':raw['response_sha256'], 'gold':read(gold) if gold.exists() else None})

def rate(values):
    if not values:
        return {'n':0,'rate':None,'wilson95':None}
    n=len(values); p=sum(values)/n; z=1.96
    center=(p+z*z/(2*n))/(1+z*z/n)
    half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/(1+z*z/n)
    return {'n':n,'rate':p,'wilson95':[max(0,center-half),min(1,center+half)]}

def analyze(root, scores_path):
    m=load(root); scores=read(scores_path)
    allowed={t['blind_id'] for t in m['trials']}
    if not isinstance(scores,dict) or set(scores)-allowed:
        raise ValueError('scores must map known blind IDs to judgments')
    pending=[]; invalid=[]; accepted={}; sessions=set()
    cases={c['id']:c for c in m['cases']}
    for t in m['trials']:
        tid=t['id']; p=root/'raw'/f'{tid}.json'; score=scores.get(t['blind_id'])
        if not p.exists():
            pending.append({'trial':tid,'reason':'missing output'}); continue
        raw=read(p); meta=raw['metadata']
        if raw['response_sha256'] != digest(raw['response']):
            invalid.append({'trial':tid,'reason':'raw response hash mismatch'}); continue
        if meta['session_id'] in sessions or meta['isolated'] is not True:
            invalid.append({'trial':tid,'reason':'reused or non-isolated session'}); continue
        sessions.add(meta['session_id'])
        if score is None:
            pending.append({'trial':tid,'reason':'not scored'}); continue
        if not isinstance(score,dict):
            raise ValueError('score must be an object')
        if score.get('response_sha256') != raw['response_sha256']:
            invalid.append({'trial':tid,'reason':'score not bound to raw response'}); continue
        if score.get('independent') is not True or not nonblank(score.get('reviewer')) or not nonblank(score.get('reason')):
            invalid.append({'trial':tid,'reason':'independent documented judgment required'}); continue
        if any(type(score.get(k)) is not bool for k in METRICS+('fact_changed',)):
            raise ValueError('all score decisions require boolean values')
        if score['fact_changed']:
            invalid.append({'trial':tid,'reason':'fact changed during paired window'}); continue
        gold_path=root/'gold'/f"{t['case_id']}.json"
        if not gold_path.exists():
            pending.append({'trial':tid,'reason':'missing independent gold'}); continue
        gold=read(gold_path)
        if (gold.get('independent') is not True or not nonblank(gold.get('reviewer'))
            or not nonblank(gold.get('answer')) or not nonblank(gold.get('evidence'))
            or score.get('gold_sha256') != digest(gold)):
            invalid.append({'trial':tid,'reason':'missing/unbound gold evidence'}); continue
        try:
            start=datetime.fromisoformat(gold['valid_from'].replace('Z','+00:00'))
            end=datetime.fromisoformat(gold['valid_until'].replace('Z','+00:00'))
            observed=datetime.fromisoformat(meta['ended_at'].replace('Z','+00:00'))
            if start.tzinfo is None or end.tzinfo is None or not start<=observed<=end:
                raise ValueError()
        except (KeyError, TypeError, ValueError):
            invalid.append({'trial':tid,'reason':'gold outside declared validity window'}); continue
        accepted[tid]=(t,score,meta)
    groups={}
    paired=[]; unpaired=[]
    for t in m['trials']:
        groups.setdefault((t['case_id'],t['repeat']),[]).append(t)
    for key, ts in groups.items():
        vals=[accepted[t['id']] for t in ts if t['id'] in accepted]
        # Tools/client/plan are compared as well as model; no cross-host causal claim.
        config={tuple(v[2][k] for k in ('model','client','plan','tools')) for v in vals}
        versions={v[2]['plugin_version'] for v in vals if v[0]['condition']!='baseline'}
        window=None
        if len(vals)==3:
            window=(max(datetime.fromisoformat(v[2]['ended_at']) for v in vals)
                   -min(datetime.fromisoformat(v[2]['started_at']) for v in vals)).total_seconds()
        if len(vals)==3 and len(config)==1 and len(versions)==1 and window<=m['max_pair_window_seconds']:
            paired.extend(vals)
        else:
            unpaired.append({'case':key[0],'repeat':key[1],'accepted':len(vals),'configurations':len(config),'plugin_versions':len(versions),'window_seconds':window})
    summary={}
    for condition in CONDITIONS:
        values=[v for v in paired if v[0]['condition']==condition]
        summary[condition]={metric:rate([int(v[1][metric]) for v in values
             if metric!='unnecessary_search' or cases[v[0]['case_id']]['category']=='stable']) for metric in METRICS}
        summary[condition]['trace_observations']={k:{'true':sum(v[2][k] is True for v in values),
           'false':sum(v[2][k] is False for v in values),'unobservable':sum(v[2][k] is None for v in values)}
           for k in ('skill_loaded','searched','opened_original')}
        durations=[(datetime.fromisoformat(v[2]['ended_at'])-datetime.fromisoformat(v[2]['started_at'])).total_seconds() for v in values]
        summary[condition]['mean_seconds']=sum(durations)/len(durations) if durations else None
        summary[condition]['extra_actions']=sum(v[2]['extra_actions'] for v in values)
    differences={}
    for condition in ('implicit','explicit'):
        diffs={k:[] for k in METRICS}
        for ts in groups.values():
            vs={t['condition']:accepted[t['id']] for t in ts if any(v[0]['id']==t['id'] for v in paired)}
            if len(vs)!=3: continue
            for metric in METRICS:
                if metric=='unnecessary_search' and cases[ts[0]['case_id']]['category']!='stable': continue
                diffs[metric].append(int(vs[condition][1][metric])-int(vs['baseline'][1][metric]))
        differences[condition]={k:{'pairs':len(v),'mean_delta':sum(v)/len(v) if v else None,
              'up':v.count(1),'down':v.count(-1),'tied':v.count(0)} for k,v in diffs.items()}
    complete=not pending and not invalid and not unpaired
    return {'status':'complete_descriptive_only' if complete else 'incomplete',
       'planned':len(m['trials']),'accepted':len(accepted),'paired_trials':len(paired),
       'pending':pending,'invalid':invalid,'unpaired':unpaired,'conditions':summary,'paired_differences_vs_baseline':differences,
       'causal_improvement_proven':False,
       'notice':'Declared metadata/judgments are not authenticated. Wilson intervals describe trials, not independent case clusters. No automatic efficacy verdict; inspect paired case differences, repetition dependence, contamination and blinding leaks.'}

def main():
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest='cmd',required=True)
    a=sub.add_parser('init'); a.add_argument('root',type=Path); a.add_argument('--cases',type=Path,default=Path(__file__).resolve().parents[1]/'references/eval-cases.json'); a.add_argument('--seed',type=int,default=42); a.add_argument('--repeats',type=int,default=1)
    a=sub.add_parser('import'); a.add_argument('root',type=Path); a.add_argument('trial'); a.add_argument('--response',type=Path,required=True); a.add_argument('--metadata',type=Path,required=True)
    a=sub.add_parser('blind'); a.add_argument('root',type=Path); a.add_argument('dest',type=Path)
    a=sub.add_parser('analyze'); a.add_argument('root',type=Path); a.add_argument('--scores',type=Path,required=True); a.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    try:
        if args.cmd=='init': init(args.root,args.cases,args.seed,args.repeats)
        elif args.cmd=='import': import_trial(args.root,args.trial,args.response,args.metadata)
        elif args.cmd=='blind': blind(args.root,args.dest)
        else:
            result=analyze(args.root,args.scores); write(args.output,result)
            print(json.dumps({'status':result['status'],'planned':result['planned'],'paired_trials':result['paired_trials']}))
            return 0 if result['status']=='complete_descriptive_only' else 2
    except (OSError, ValueError, KeyError, TypeError) as exc:
        p.exit(1,f'{exc}\n')
    return 0

if __name__=='__main__':
    raise SystemExit(main())
