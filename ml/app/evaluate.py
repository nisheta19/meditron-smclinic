"""Score independently reviewed JSONL labels, never machine labels as gold."""
import argparse
from collections import Counter
import json
from pathlib import Path


def metric(tp,fp,fn):
    return {'tp':tp,'fp':fp,'fn':fn,'precision':tp/(tp+fp) if tp+fp else None,
            'recall':tp/(tp+fn) if tp+fn else None,
            'f1':2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None}


def index(rows):
    result={}
    for row in rows:
        key=row.get('documentId')
        if not isinstance(key,str) or not key or key in result:
            raise ValueError('documentId должен быть непустым и уникальным')
        if not isinstance(row.get('findings'),list):raise ValueError('Требуется массив findings')
        for f in row['findings']:
            if not isinstance(f,dict) or not isinstance(f.get('code'),str) or not isinstance(f.get('attributes',{}),dict):
                raise ValueError('Некорректная находка')
        result[key]=row
    if not result:raise ValueError('Пустой набор оценки')
    return result


def fact_matches(expected,actual):
    if expected['code']!=actual['code']:return False
    attrs=actual.get('attributes',{})
    for key,value in expected.get('attributes',{}).items():
        if key not in attrs or attrs[key]!=value:return False
        if isinstance(value,bool) != isinstance(attrs[key],bool):return False
    return True


def matched_count(expected,actual,matches=fact_matches):
    # Maximum one-to-one matching: a prediction cannot satisfy two gold lesions.
    matched={}
    def assign(i,seen):
        for j,pred in enumerate(actual):
            if j in seen or not matches(expected[i],pred):continue
            seen.add(j)
            if j not in matched or assign(matched[j],seen):
                matched[j]=i
                return True
        return False
    return sum(assign(i,set()) for i in range(len(expected)))


def evaluate(gold,predictions):
    expected,actual=index(gold),index(predictions)
    if set(expected)!=set(actual):raise ValueError('Наборы documentId различаются; нельзя оценивать только успешные документы')
    statuses={r.get('annotationStatus') for r in expected.values()}
    if not statuses <= {'reviewed','synthetic'}:
        raise ValueError('Нужна независимая reviewed-разметка либо явно synthetic; машинная разметка не эталон')
    totals=Counter();facts=Counter();by_code={};failures=[];mismatches=[]
    for key,truth in expected.items():
        prediction=actual[key]
        status=prediction.get('status','DONE')
        if status not in {'DONE','FAILED'}:raise ValueError('Оценка поддерживает только DONE и FAILED')
        wanted=truth['findings'];found=prediction['findings'] if status=='DONE' else []
        if status=='FAILED':failures.append(key)
        gold_codes={f['code'] for f in wanted};pred_codes={f['code'] for f in found}
        for code in gold_codes|pred_codes:
            counts=by_code.setdefault(code,Counter())
            field='tp' if code in gold_codes&pred_codes else 'fp' if code in pred_codes else 'fn'
            counts[field]+=1;totals[field]+=1
        tp=matched_count(wanted,found)
        facts.update(tp=tp,fp=len(found)-tp,fn=len(wanted)-tp)
        if tp!=len(wanted) or tp!=len(found):mismatches.append(key)
    return {'documents':len(expected),'annotationStatus':sorted(statuses),
            'clinicalValidationClaimed':False,
            'definition':'Codes: document+code. Facts: one-to-one code and all labeled attributes; unlabeled attributes are not scored.',
            'codes':metric(totals['tp'],totals['fp'],totals['fn']),
            'facts':metric(facts['tp'],facts['fp'],facts['fn']),
            'byCode':{c:metric(n['tp'],n['fp'],n['fn']) for c,n in sorted(by_code.items())},
            'failedDocuments':failures,'mismatchedDocuments':mismatches}


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8-sig').splitlines() if line.strip()]


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('gold',help='JSONL: documentId, annotationStatus=reviewed|synthetic, findings')
    cli.add_argument('predictions',help='JSONL: documentId, status, findings')
    cli.add_argument('--output',default='.local/evaluation.json')
    args=cli.parse_args()
    try:
        result=evaluate(read_jsonl(args.gold),read_jsonl(args.predictions))
        output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(result,ensure_ascii=True,indent=2))
    except (ValueError,OSError) as exc:
        cli.exit(2,str(exc)+'\n')


if __name__=='__main__':main()
