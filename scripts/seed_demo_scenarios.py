"""Явно помеченные вымышленные пациенты: backend -> ML -> backend.

Повторный запуск пропускает существующих пациентов, сохраняя действия врача.
Никакие исходные медицинские файлы не читаются и не изменяются.
"""
import argparse
from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'ml'))
import httpx
from app.demo import docx


def report(text):
    return f'ТЕСТОВЫЙ ПРОТОКОЛ. Вымышленный пациент.\nОписание\n{text}\nЗаключение\n{text}'


POLYP = report('Полип эндометрия 8 мм.')
CASES = [
    dict(key='01-emergency', name='Экстренный', study='LOWER_LIMB_VESSELS', text=report('Тромбоз глубоких вен левой голени.'), level='EMERGENCY', days=0, inbox=False),
    dict(key='02-urgent-one', name='Срочный ОдинДень', study='LOWER_LIMB_VESSELS', text=report('Тромбофлебит ствола БПВ слева. Верхушка тромба на 18 см от СФС.'), level='URGENT', days=1, inbox=False),
    dict(key='03-urgent-three', name='Срочный ТриДня', study='SOFT_TISSUE', text=report('Воспалительные изменения ПЖК.'), level='URGENT', days=3, inbox=False),
    dict(key='04-planned', name='Плановый', study='PELVIS_FEMALE', text=POLYP, level='PLANNED', days=7, inbox=False),
    dict(key='05-normal', name='БезНаходок', study='BREAST', text=report('BI-RADS 1 справа. BI-RADS 1 слева. Патологии не выявлено.'), level=None, inbox=False, count=0),
    dict(key='06-no-conclusion', name='НетЗаключения', study='PELVIS_FEMALE', text='ТЕСТОВЫЙ ПРОТОКОЛ\nОписание\nПолип эндометрия 9 мм.', inbox=True, flag='NO_CONCLUSION'),
    dict(key='07-incomplete', name='НеполноеОписание', study='BREAST', text=report('Фиброаденома левой молочной железы 18 мм.'), inbox=True, flag='INCOMPLETE'),
    dict(key='08-uncertain', name='Подозрение', study='PELVIS_FEMALE', text=report('Подозрение на полип эндометрия 8 мм.'), inbox=True),
    dict(key='09-discrepancy', name='Расхождение', study='PELVIS_FEMALE', text='ТЕСТОВЫЙ ПРОТОКОЛ\nОписание\nПолип эндометрия 8 мм.\nЗаключение\nПатологии не выявлено.', inbox=True, flag='DISCREPANCY'),
    dict(key='10-manual-review', name='РучнойРазбор', study='ABDOMEN', text=report('Аневризма брюшной аорты.'), inbox=True),
    dict(key='11-failed', name='ОшибкаДокумента', study='PELVIS_FEMALE', text=None, inbox=True, status='FAILED'),
    dict(key='12-corrected', name='Исправленный', study='PELVIS_FEMALE', text=POLYP, inbox=False, action='correct'),
    dict(key='13-annulled', name='Аннулированный', study='PELVIS_FEMALE', text=POLYP, inbox=False, action='annul', status='ANNULLED'),
    dict(key='14-confirmed', name='Подтверждённый', study='PELVIS_FEMALE', text=POLYP, inbox=False, action='confirm'),
    dict(key='15-rejected', name='Отклонённый', study='PELVIS_FEMALE', text=POLYP, inbox=False, action='reject'),
    dict(key='16-minor', name='Несовершеннолетний', study='PELVIS_FEMALE', text=POLYP, birth='2012-01-01', inbox=False, flag='MINOR'),
    dict(key='17-multiple', name='НесколькоНаходок', study='PELVIS_FEMALE', text=report('Полип эндометрия 8 мм. Гидросальпинкс слева.'), inbox=False, count=2),
]


def seed(backend, prefix='demo-scenario-v1'):
    with httpx.Client(base_url=backend.rstrip('/'), timeout=40, trust_env=False) as client:
        def request(method, path, **kwargs):
            response = client.request(method, path, **kwargs)
            response.raise_for_status()
            return response.json() if response.content else None

        def find(external_id):
            page = request('GET', '/api/patients', params={'search': external_id, 'size': 200})
            return next((p for p in page['items'] if p['externalId'] == external_id), None)

        def send(meta, text):
            if meta['eventType'] == 'PROTOCOL_ANNULLED':
                request('POST', '/api/integration/events', json=meta)
            else:
                file = BytesIO()
                if text is None: file.write(b'TEST ONLY: intentionally invalid DOCX')
                else: docx(file, text.split('\n'))
                request('POST', '/api/integration/protocols', files={
                    'metadata': ('metadata.json', json.dumps(meta, ensure_ascii=False).encode('utf-8'), 'application/json'),
                    'file': ('TEST-' + meta['eventId'] + '.docx', file.getvalue(), 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')})
            deadline = time.monotonic() + 40
            while time.monotonic() < deadline:
                state = request('GET', '/api/integration/events/status', params={'eventId': meta['eventId']})
                if state['delivery'] == 'delivered': return
                if state['delivery'] in ('rejected', 'exhausted'): raise AssertionError(state)
                time.sleep(.2)
            raise AssertionError('ML callback timeout: ' + meta['eventId'])

        results = []
        for case in CASES:
            external_id = prefix + '-' + case['key']
            patient = find(external_id)
            if patient:
                results.append(dict(scenario=case['key'], id=patient['id'], created=False))
                continue
            # The marker belongs to lastName, so it is visible in the shortened list name too.
            name = '[ТЕСТ ' + case['key'][:2] + '] ' + case['name']
            meta = dict(eventId=external_id + '-signed', eventType='PROTOCOL_SIGNED',
                        patient=dict(externalId=external_id, fullName=name + ' Пациент', lastName=name,
                                     firstName='Пациент', middleName=None, birthDate=case.get('birth', '1990-01-01'), sex='F'),
                        protocol=dict(externalId=external_id + '-protocol', version=1, studyType=case['study'], studyDate='2026-09-07'))
            send(meta, case['text'])
            if case.get('action') in ('correct', 'annul'):
                next_event = deepcopy(meta)
                next_event['eventId'] = external_id + '-' + case['action']
                next_event['eventType'] = 'PROTOCOL_CORRECTED' if case['action'] == 'correct' else 'PROTOCOL_ANNULLED'
                if case['action'] == 'correct': next_event['protocol']['version'] = 2
                send(next_event, POLYP.replace('8 мм', '12 мм') if case['action'] == 'correct' else None)
            patient = find(external_id)
            card = request('GET', '/api/patients/' + patient['id'])
            if case.get('action') in ('confirm', 'reject'):
                for finding in card['currentFindings']:
                    request('PATCH', '/api/findings/' + finding['id'], json={
                        'status': 'CONFIRMED' if case['action'] == 'confirm' else 'REJECTED',
                        'doctor': 'Тестовый врач', 'comment': 'Вымышленный демонстрационный сценарий'})
                card = request('GET', '/api/patients/' + patient['id'])
            check_case(case, card)
            results.append(dict(scenario=case['key'], id=patient['id'], created=True,
                                inbox=card['patient']['needsRouteReview'], level=card['patient']['maxLevel'],
                                status=card['currentProtocol']['status']))
            print('OK ' + case['key'], flush=True)
        return results


def check_case(case, card):
    patient = card['patient']
    assert '[ТЕСТ ' in patient['fullName'] and '[ТЕСТ ' in patient['shortName'], case['key']
    assert patient['needsRouteReview'] == case['inbox'], (case['key'], patient)
    assert card['currentProtocol']['status'] == case.get('status', 'DONE'), case['key']
    if 'level' in case: assert patient['maxLevel'] == case['level'], (case['key'], patient)
    if 'days' in case: assert patient['topFindings'][0]['targetDays'] == case['days'], (case['key'], patient)
    if 'count' in case: assert patient['activeFindings'] == case['count'], (case['key'], patient)
    if 'flag' in case:
        flags = card['currentProtocol'].get('flags', []) + [flag for f in card['currentFindings'] for flag in f.get('flags', [])]
        assert case['flag'] in [f['code'] for f in flags], (case['key'], flags)
    if case.get('action') == 'correct':
        assert card['currentProtocol']['version'] == 2 and card['history']['protocols'], case['key']
    if case.get('action') in ('confirm', 'reject'):
        expected = 'CONFIRMED' if case['action'] == 'confirm' else 'REJECTED'
        assert card['currentFindings'] and all(f['status'] == expected for f in card['currentFindings']), case['key']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', default='http://127.0.0.1:8080')
    parser.add_argument('--prefix', default='demo-scenario-v1')
    parser.add_argument('--report', type=Path, default=ROOT / '.local/demo-scenarios.json')
    args = parser.parse_args()
    results = seed(args.backend, args.prefix)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'{len(results)} scenarios; {sum(r["created"] for r in results)} created. {args.report}')


if __name__ == '__main__': main()
