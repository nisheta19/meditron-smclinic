"""Offline DOCX evaluation on authored synthetic cases and formatting variants.

Labels are never inferred from predictions. This is engineering validation, not
an estimate of clinical performance on an independently annotated population.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import textwrap

from .benchmark_v2 import run
from .contracts import MODEL_VERSION
from .demo import docx
from .dictionary import DEFAULT_DICTIONARY, load_dictionary, normalize_dictionary


def wrap(text, width):
    return '\n'.join(textwrap.fill(line, width, break_long_words=False,
                                  break_on_hyphens=False) for line in text.splitlines())


TRANSFORMS = {
    'original': lambda text: text,
    'wrap35': lambda text: wrap(text, 35),
    'wrap55': lambda text: wrap(text, 55),
    'upper': str.upper,
    'upper_wrap55': lambda text: wrap(text.upper(), 55),
    'nbsp': lambda text: text.replace(' ', '\u00a0'),
    'decimal_dot': lambda text: re.sub(r'(?<=\d),(?=\d)', '.', text),
    'multiplication': lambda text: re.sub(r'(?<=\d)\s*[хx*]\s*(?=\d)', ' × ', text),
    'headers': lambda text: re.sub(r'(?im)^Заключение\s*:', 'Заключение врача:',
                            re.sub(r'(?im)^Описание\s*:', 'Описание исследования:', text)),
}


def validate_gold(gold, dictionary):
    if gold.get('annotationStatus') != 'synthetic' or not gold.get('protocols'):
        raise ValueError('Expected nonempty, explicitly synthetic text cases')
    items = {item['code']: item for item in normalize_dictionary(dictionary)}
    names = set()
    for row in gold['protocols']:
        name = row['file']
        if name in names or '/' in name or '\\' in name or not name.endswith('.docx'):
            raise ValueError('Invalid or duplicate synthetic document name')
        names.add(name)
        if not isinstance(row['text'], str) or not row['text'].strip():
            raise ValueError('Missing synthetic source text')
        for fact in row['expected']['findings']:
            item = items.get(fact['code'])
            if not item or not item.get('active', True) or row['studyType'] not in item['studyTypes']:
                raise ValueError(f"Unsupported code/study in gold: {fact['code']}")
            if set(fact.get('attributes', {})) - set(item.get('attributes', [])):
                raise ValueError(f"Unknown gold attributes for {fact['code']}")


def run_suite(gold_path, output, dictionary=DEFAULT_DICTIONARY, variants=None):
    gold_path, output = Path(gold_path), Path(output)
    gold = json.loads(gold_path.read_text('utf-8'))
    validate_gold(gold, load_dictionary(dictionary))
    report = {'modelVersion': MODEL_VERSION,
              'goldSha256': hashlib.sha256(gold_path.read_bytes()).hexdigest(),
              'clinicalValidation': False, 'variants': {}}
    for name in variants or TRANSFORMS:
        dest = output / name
        documents = dest / 'documents'
        documents.mkdir(parents=True, exist_ok=True)
        for row in gold['protocols']:
            docx(documents / row['file'], TRANSFORMS[name](row['text']).splitlines())
        metrics, rows = run(gold_path, documents, dictionary)
        normal = [row for row in rows if not row['expected']['findings']]
        metrics['negativeCases'] = {
            'total': len(normal),
            'withFalseFindings': sum(bool(row['prediction'].get('findings')) for row in normal),
        }
        for filename, data in [('metrics.json', metrics), ('predictions.json', rows)]:
            (dest / filename).write_text(json.dumps(data, ensure_ascii=False, indent=2), 'utf-8')
        report['variants'][name] = {key: metrics[key] for key in
                                   ('documents', 'entities', 'fullFacts', 'attributes',
                                    'failedDocuments', 'negativeCases', 'timingSeconds')}
    output.mkdir(parents=True, exist_ok=True)
    (output / 'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gold', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--dictionary', default=str(DEFAULT_DICTIONARY))
    parser.add_argument('--variants', nargs='+', choices=list(TRANSFORMS))
    parser.add_argument('--min-f1', type=float, default=.95)
    parser.add_argument('--max-negative-fp', type=int, default=0)
    args = parser.parse_args()
    if not 0 <= args.min_f1 <= 1 or args.max_negative_fp < 0:
        parser.error('Invalid quality threshold')
    report = run_suite(args.gold, args.output, args.dictionary, args.variants)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return int(any(result['failedDocuments'] or result['fullFacts']['f1'] < args.min_f1
                   or result['negativeCases']['withFalseFindings'] > args.max_negative_fp
                   for result in report['variants'].values()))


if __name__ == '__main__':
    raise SystemExit(main())
