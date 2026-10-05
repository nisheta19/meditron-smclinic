"""Independently rescore saved predictions; never edit the frozen gold/model.

Usage from ml/: python eval/typical-v8-20261005/audit.py --evaluation PATH --output PATH
"""
import argparse
from collections import Counter
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path


def counts(rows, mode='full', *, corrected=False, bool_defaults=False, ignore_uncertain=False):
    total = Counter(tp=0, fp=0, fn=0)
    for row in rows:
        expected = deepcopy(row['expected']['findings'])
        if corrected and row['file'] == 'typical-006.docx':
            expected[0]['attributes']['uncertain'] = True
        if ignore_uncertain:
            for fact in expected:
                fact['attributes'].pop('uncertain', None)
        predicted = row['prediction'].get('findings', [])

        def match(g, p):
            if g['code'] != p['code']:
                return False
            for k, v in g.get('attributes', {}).items():
                if mode == 'codes' or (mode == 'entities' and k not in ('side', 'location')):
                    continue
                actual = p.get('attributes', {}).get(k, False if bool_defaults and v is False else None)
                if actual != v or isinstance(v, bool) != isinstance(actual, bool):
                    return False
            return True

        # Exhaustive bitmask dynamic programming is deliberately independent
        # of app.evaluate's augmenting-path matcher. Max 2 expected facts/case.
        @lru_cache(None)
        def assign(i, used):
            if i == len(expected):
                return 0
            best = assign(i + 1, used)
            for j, p in enumerate(predicted):
                if not used & (1 << j) and match(expected[i], p):
                    best = max(best, 1 + assign(i + 1, used | (1 << j)))
            return best

        tp = assign(0, 0)
        total.update(tp=tp, fp=len(predicted)-tp, fn=len(expected)-tp)
    tp, fp, fn = (total[k] for k in ('tp', 'fp', 'fn'))
    return dict(total, precision=tp/(tp+fp) if tp+fp else None,
                recall=tp/(tp+fn) if tp+fn else None,
                f1=2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None)


def run(evaluation, output):
    summary = json.loads((evaluation/'summary.json').read_text('utf-8'))
    result = {'modelVersion': summary['modelVersion'], 'goldSha256': summary['goldSha256'],
              'clinicalValidation': False, 'independentRescoringAgrees': True,
              'variants': {}, 'posthocAnnotationErrata': [{
                  'file': 'typical-006.docx', 'attribute': 'uncertain', 'frozen': False, 'correct': True,
                  'reason': 'Dictionary ml.uncertaintyCues explicitly includes «по типу». Gold remains unchanged; corrected scoring is retrospective.'}],
              'interpretation': 'Strict scoring requires explicit presence of every labeled attribute. Boolean-default sensitivity uses the dictionary backend convention: missing boolean equals false. Neither changes the predictions.'}
    for name, original in summary['variants'].items():
        rows = json.loads((evaluation/name/'predictions.json').read_text('utf-8'))
        full, entities = counts(rows), counts(rows, 'entities')
        assert full == original['fullFacts'], (name, full, original['fullFacts'])
        assert entities == original['entities'], (name, entities, original['entities'])
        result['variants'][name] = {
            'documents': len(rows), 'fullFacts': full, 'entities': entities,
            'codeOnlyFindings': counts(rows, 'codes'),
            'correctedAnnotationStrict': counts(rows, corrected=True),
            'correctedWithBooleanDefaults': counts(rows, corrected=True, bool_defaults=True),
            'diagnosticIgnoringUncertain': counts(rows, ignore_uncertain=True),
            'attributes': original['attributes'], 'failedDocuments': original['failedDocuments'],
            'negativeCases': original['negativeCases'],
            'byStudy': {s: counts([r for r in rows if r['studyType'] == s]) for s in sorted({r['studyType'] for r in rows})}}
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', 'utf-8')
    for name, metrics in result['variants'].items():
        print(name, json.dumps({k:v for k,v in metrics.items() if k not in ('byStudy',)}, ensure_ascii=False))
    print('BY STUDY', json.dumps(result['variants']['original']['byStudy'], ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evaluation', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.evaluation, args.output)
