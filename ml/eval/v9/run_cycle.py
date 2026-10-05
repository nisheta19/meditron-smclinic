"""Freeze and evaluate an unseen synthetic cycle; refuse result overwrites."""
import argparse
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile

ML=Path(__file__).resolve().parents[2]
ROOT=ML.parent
sys.path.insert(0,str(ML))
from app.generalization import run_suite, validate_gold
from app.dictionary import load_dictionary, DEFAULT_DICTIONARY

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def independent_counts(rows):
    tp=fp=fn=0
    for row in rows:
        gs=row['expected']['findings'];ps=row['prediction'].get('findings',[])
        def matches(g,p):
            if g['code']!=p['code']:return False
            return all(k in p['attributes'] and p['attributes'][k]==v and isinstance(v,bool)==isinstance(p['attributes'][k],bool) for k,v in g.get('attributes',{}).items())
        @lru_cache(None)
        def best(i,mask):
            if i==len(gs):return 0
            return max([best(i+1,mask)]+[1+best(i+1,mask|(1<<j)) for j,p in enumerate(ps) if not mask&(1<<j) and matches(gs[i],p)])
        n=best(0,0);tp+=n;fp+=len(ps)-n;fn+=len(gs)-n
    return {'tp':tp,'fp':fp,'fn':fn,'f1':2*tp/(2*tp+fp+fn)}

def main():
    p=argparse.ArgumentParser();p.add_argument('--gold',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    assert not a.output.exists(),'Results must not be overwritten'
    g=json.loads(a.gold.read_text('utf-8'));validate_gold(g,load_dictionary(DEFAULT_DICTIONARY))
    norm=lambda s:re.sub('[^a-zа-яё]','',s.lower())
    new={norm(r['text']) for r in g['protocols']};assert len(new)==len(g['protocols'])
    previous=set()
    for base in (ML/'eval',ML/'tests/fixtures',ROOT/'.local/ml-generalization',ROOT/'.local/ml-new-blind-audit'):
        for path in base.rglob('*.json'):
            if path.resolve()==a.gold.resolve() or not any(w in path.name for w in ('gold','validation','development')):continue
            data=json.loads(path.read_text('utf-8-sig'))
            if isinstance(data,dict):previous.update(norm(r['text']) for r in data.get('protocols',[]) if 'text' in r)
    assert not new&previous,'Repeated old text/template'
    a.output.mkdir(parents=True)
    files=sorted((ML/'app').glob('*.py'))+[DEFAULT_DICTIONARY,ROOT/'backend/src/main/resources/dictionary/findings-dictionary.yaml',a.gold.resolve()]
    assert files[-2].read_bytes()==DEFAULT_DICTIONARY.read_bytes()
    snapshot={str(f.resolve().relative_to(ROOT)):sha(f) for f in files}
    manifest={'frozenAt':datetime.now(timezone.utc).isoformat(),'files':snapshot,'goldSha256':sha(a.gold),'previousUniqueNormalizedTexts':len(previous),'duplicates':0,
              'documents':len(g['protocols']),'expectedFindings':sum(len(r['expected']['findings']) for r in g['protocols']),
              'labeledAttributes':sum(len(f.get('attributes',{})) for r in g['protocols'] for f in r['expected']['findings'])}
    (a.output/'before.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),'utf-8')
    with zipfile.ZipFile(a.output/'source.zip','x') as z:
        for f in files:z.write(f,str(f.resolve().relative_to(ROOT)))
    report=run_suite(a.gold,a.output/'evaluation')
    assert all(sha(ROOT/f)==h for f,h in snapshot.items()),'Files changed during evaluation'
    for variant,m in report['variants'].items():
        rows=json.loads((a.output/'evaluation'/variant/'predictions.json').read_text('utf-8'))
        independent=independent_counts(rows)
        assert all(m['fullFacts'][k]==v for k,v in independent.items())
    report['manifest']=manifest
    report['unchangedDuringEvaluation']=True
    report['independentCountsAgree']=True
    report['userGoalPassed']=all(v['fullFacts']['f1']>.90 and not v['failedDocuments'] for v in report['variants'].values())
    (a.output/'first-pass.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    print(json.dumps({k:{'fullFacts':v['fullFacts'],'negativeCases':v['negativeCases'],'failed':v['failedDocuments']} for k,v in report['variants'].items()},ensure_ascii=False,indent=2))
    return 0 if report['userGoalPassed'] else 1

if __name__=='__main__':raise SystemExit(main())
