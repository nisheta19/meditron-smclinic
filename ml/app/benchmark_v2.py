"""Reproducible scoring against external, immutable v2 semantic gold."""
import argparse
import json
from pathlib import Path
import time
import hashlib
from .mis import build_event
from .processing import process_event
from .validation import validate_for_dictionary
from .dictionary import DEFAULT_DICTIONARY, load_dictionary
from .evaluate import fact_matches, matched_count, metric
from .parser import DocumentError, extract_text, parse_text


def score(rows):
    counts={k:[0,0,0] for k in ('entities','fullFacts')}
    by_code={};mismatches=[];trap_count=0;nt_hit=nt_total=flag_hit=flag_total=urgent_hit=urgent_total=0
    attribute_hit=attribute_total=0
    for row in rows:
        expected=row['expected'];gold=expected['findings'];pred=row['prediction'].get('findings',[])
        optional=row.get('optional',{}).get('findings',[])
        for mode in counts:
            def matches(g,p):
                return fact_matches(g,p) if mode=='fullFacts' else g['code']==p['code'] and all(p.get('attributes',{}).get(k)==v for k,v in g.get('attributes',{}).items() if k in {'side','location'})
            tp=matched_count(gold,pred,matches)
            # Optional matches never absorb predictions required by the gold.
            extra=matched_count(gold+optional,pred,matches)-tp
            values=[tp,len(pred)-tp-extra,len(gold)-tp]
            for i,v in enumerate(values):counts[mode][i]+=v
            if mode=='fullFacts' and any(values[1:]):
                missing=[g for g in gold if not any(matches(g,p) for p in pred)]
                unexpected=[p for p in pred if not any(matches(g,p) for g in gold+optional)]
                mismatches.append({'file':row['file'],'missing':missing,'unexpected':unexpected})
        for code in {f['code'] for f in gold+pred}:
            gs=[f for f in gold if f['code']==code];ps=[f for f in pred if f['code']==code]
            tp=matched_count(gs,ps,fact_matches);opt=[f for f in optional if f['code']==code]
            extra=matched_count(gs+opt,ps,fact_matches)-tp
            bucket=by_code.setdefault(code,[0,0,0])
            for i,v in enumerate((tp,len(ps)-tp-extra,len(gs)-tp)):bucket[i]+=v
        unused=list(range(len(pred)))
        for g in sorted(gold,key=lambda x:len(x.get('attributes',{})),reverse=True):
            candidates=[j for j in unused if pred[j]['code']==g['code'] and all(pred[j].get('attributes',{}).get(k)==v for k,v in g.get('attributes',{}).items() if k in {'side','location','figo','birads','orads','tirads'})]
            best=max(candidates,key=lambda j:sum(pred[j].get('attributes',{}).get(k)==v for k,v in g.get('attributes',{}).items()),default=None)
            p=pred[best] if best is not None else {}
            if best is not None:unused.remove(best)
            for k,v in g.get('attributes',{}).items():
                attribute_total+=1;attribute_hit+=p.get('attributes',{}).get(k)==v
            if g.get('backendExpected',{}).get('level') in {'ЭКСТРЕННО','СРОЧНО','EMERGENCY','URGENT'}:
                urgent_total+=1;urgent_hit+=best is not None
            for fl in g.get('flags',[]):
                if fl=='DISCREPANCY':flag_total+=1;flag_hit+=any(x.get('code')==fl for x in p.get('flags',[]))
        for g in expected.get('notTriggered',[]):
            nt_total+=1;nt_hit+=any(p['code']==g['code'] and p['reason']==g['reason'] for p in row['prediction'].get('notTriggered',[]))
        trap_count+=sum(any(p['code']==code for p in pred) for code in row.get('mustNotFind',[]))
    return {'documents':len(rows),'failedDocuments':[r['file'] for r in rows if r['prediction'].get('status','DONE')!='DONE'],**{k:metric(*v) for k,v in counts.items()},
            'byCode':{k:metric(*v) for k,v in sorted(by_code.items())},
            'attributes':{'correct':attribute_hit,'total':attribute_total,'accuracy':attribute_hit/attribute_total if attribute_total else None},
            'requiredNotTriggered':{'correct':nt_hit,'total':nt_total},'trapFalsePositives':trap_count,
            'discrepancyRecall':{'found':flag_hit,'total':flag_total},
            'urgentRecall':{'found':urgent_hit,'total':urgent_total},'mismatches':mismatches,
            'timingSeconds':{'mean':sum(r['seconds'] for r in rows)/len(rows) if rows else None,'max':max((r['seconds'] for r in rows),default=None)}}


def run(gold_path, documents, dictionary=DEFAULT_DICTIONARY):
    gold=json.loads(Path(gold_path).read_text('utf-8'));d=load_dictionary(dictionary)
    files=list(Path(documents).rglob('*.docx'))
    paths={p.name:p for p in files};rows=[]
    if len(paths)!=len(files):raise ValueError('Неоднозначные имена файлов')
    if len({r['file'] for r in gold['protocols']})!=len(gold['protocols']):raise ValueError('Повторяющийся документ в эталоне')
    for row in gold['protocols']:
        try:parsed=parse_text(extract_text(paths[row['file']]))
        except DocumentError:parsed={}
        start=time.perf_counter()
        event=build_event({'eventId':'benchmark-'+row['file'],'eventType':'PROTOCOL_SIGNED',
            'patient':{'externalId':'benchmark-demo','fullName':'Пациент 001','birthDate':'2000-01-01','sex':row.get('patient',{}).get('sex','M' if row['studyType']=='PROSTATE' else 'F')},
            'protocol':{'externalId':'benchmark-'+row['file'],'version':1,'studyType':row['studyType'],'studyDate':parsed.get('examination_date') or '2026-09-08'}},paths[row['file']])
        result=process_event(event,lambda:d)
        validate_for_dictionary(result,d)
        rows.append({**row,'seconds':time.perf_counter()-start,'prediction':result})
    report=score(rows)
    report['goldSha256']=hashlib.sha256(Path(gold_path).read_bytes()).hexdigest()
    report['dictionarySha256']=hashlib.sha256(Path(dictionary).read_bytes()).hexdigest()
    report['metadata']='Synthetic MIS identifiers; sex from gold, otherwise demo M for PROSTATE / F for other studies (same convention as app.release); examination date from document. This is not verified demographic data.'
    report['partitions']={tag:score([r for r in rows if r.get('partition','synthetic')==tag]) for tag in sorted({r.get('partition','synthetic') for r in rows})}
    return report,rows


def main():
    p=argparse.ArgumentParser();p.add_argument('--gold',required=True);p.add_argument('--documents',required=True);p.add_argument('--output',required=True);p.add_argument('--dictionary',default=str(DEFAULT_DICTIONARY));a=p.parse_args()
    report,rows=run(a.gold,a.documents,a.dictionary)
    dest=Path(a.output);dest.mkdir(parents=True,exist_ok=True)
    (dest/'metrics.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    (dest/'predictions.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),'utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in {'mismatches','byCode','partitions'}},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
