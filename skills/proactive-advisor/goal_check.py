#!/usr/bin/env python3
"""Tiny local goal ledger. Stdlib only. It records outcomes; it does not run arbitrary tests."""
import argparse, json, pathlib, datetime
ROOT=pathlib.Path(__file__).resolve().parent
LEDGER=ROOT/'goal_results.json'
STATES=('PASS','FAIL','NOT_RUN')
def read():
    return json.loads(LEDGER.read_text(encoding='utf-8')) if LEDGER.exists() else {'checks':{}}
def main():
    p=argparse.ArgumentParser(description='记录与汇报验收检查，结果必须来自真实检查')
    p.add_argument('--set',metavar='CHECK');p.add_argument('--status',choices=STATES);p.add_argument('--evidence');p.add_argument('--report',action='store_true')
    a=p.parse_args(); d=read()
    if a.set:
        if not a.status: p.error('--set 需要 --status')
        if a.status=='PASS' and not a.evidence: p.error('PASS 必须提供真实的 --evidence')
        d['checks'][a.set]={'status':a.status,'evidence':a.evidence or '', 'recorded_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
        LEDGER.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
    if a.report or not a.set:
        if not d['checks']: print('NO_CHECKS: 尚无检查记录')
        for name,rec in d['checks'].items():print(f"{rec['status']:8} | {name} | {rec['evidence']}")
        statuses=[v['status'] for v in d['checks'].values()]
        print('OVERALL:', 'PASS' if statuses and all(x=='PASS' for x in statuses) else 'FAIL' if 'FAIL' in statuses else 'INCOMPLETE')
if __name__=='__main__': main()

