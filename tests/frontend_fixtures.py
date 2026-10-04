"""Create fictional UI fixtures through nginx -> backend -> ML -> callback.

Use only a local demo database. Never reads the supplied medical corpus.
"""
import argparse
import base64
from copy import deepcopy
import json
from pathlib import Path
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'ml'))
import httpx
from app.demo import docx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frontend', default='http://127.0.0.1:13000')
    parser.add_argument('--output', type=Path, default=ROOT / '.local/frontend-fixtures.json')
    args = parser.parse_args()
    run = 'ui-' + uuid4().hex[:10]
    work = ROOT / '.local' / run
    work.mkdir(parents=True)
    client = httpx.Client(base_url=args.frontend, timeout=40, trust_env=False)

    def request(method, path, **kwargs):
        response = client.request(method, path, **kwargs)
        response.raise_for_status()
        return response.json()

    def meta(label, study='PELVIS_FEMALE'):
        event = {'eventId': f'{run}-{label}', 'eventType': 'PROTOCOL_SIGNED',
                'patient': {'externalId': f'{run}-{label}', 'fullName': 'Петрова-Водкина Анна Мария Ивановна',
                            'lastName': 'Петрова-Водкина', 'firstName': 'Анна Мария', 'middleName': 'Ивановна',
                            'birthDate': '1990-01-01', 'sex': 'F'},
                'protocol': {'externalId': f'{run}-protocol-{label}', 'version': 1, 'studyType': study, 'studyDate': '2026-09-07'}}
        if label == 'normal':
            event['patient'].update(fullName='Smith Jane', lastName='Smith', firstName='Jane', middleName=None)
        return event

    def send(m, text, expected='DONE'):
        if m['eventType'] == 'PROTOCOL_ANNULLED':
            request('POST', '/api/integration/events', json=m)
        else:
            path = work / (m['eventId'] + '.docx')
            if text is None: path.write_bytes(b'fictional invalid document')
            else: docx(path, text.split('\n'))
            request('POST', '/api/integration/protocols', files={
                'metadata': ('metadata.json', json.dumps(m, ensure_ascii=False).encode(), 'application/json'),
                'file': (path.name, path.read_bytes(), 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')})
        deadline = time.monotonic() + 40
        while True:
            state = request('GET', '/api/integration/events/status', params={'eventId': m['eventId']})
            if state['delivery'] == 'delivered': break
            if state['delivery'] in ('rejected', 'exhausted') or time.monotonic() > deadline: raise AssertionError(state)
            time.sleep(.2)
        assert state['status'] == expected, state
        page = request('GET', '/api/patients', params={'search': m['patient']['externalId']})
        patient_id, = [p['id'] for p in page['items'] if p['externalId'] == m['patient']['externalId']]
        c = request('GET', '/api/patients/' + patient_id)
        return {'id': patient_id, 'externalId': m['patient']['externalId'], 'protocolId': c['currentProtocol']['id'],
                'findings': c['currentFindings'], 'status': state['status']}

    cases = {}
    positive = 'Описание\n😀 Полип эндометрия 8 мм.\nЗаключение\nПолип эндометрия 8 мм.'
    cases['positive'] = send(meta('positive'), positive)
    assert cases['positive']['findings'][0]['attributes']['sizeMm'] == 8
    cases['breast'] = send(meta('breast', 'BREAST'), 'Описание\nОбразование левой молочной железы 18 мм.\nЗаключение\nBI-RADS 4 слева.')
    cases['failed'] = send(meta('failed'), None, 'FAILED')
    cases['missing'] = send(meta('missing'), 'Описание\nПолип эндометрия 9 мм.')
    cases['normal'] = send(meta('normal', 'BREAST'), 'Описание\nПатологии не выявлено.\nЗаключение\nBI-RADS 1 справа. BI-RADS 1 слева.')
    cases['emergency'] = send(meta('emergency', 'LOWER_LIMB_VESSELS'), 'Описание\nТромбоз глубоких вен левой голени.\nЗаключение\nТромбоз глубоких вен левой голени.')
    cases['urgent'] = send(meta('urgent', 'SOFT_TISSUE'), 'Описание\nВоспалительные изменения ПЖК.\nЗаключение\nВоспалительные изменения ПЖК.')
    assert cases['urgent']['findings'][0]['level'] == 'URGENT'
    v1 = meta('versions')
    old = send(v1, positive)
    v2 = deepcopy(v1); v2['eventId'] += '-v2'; v2['eventType'] = 'PROTOCOL_CORRECTED'; v2['protocol']['version'] = 2
    cases['versions'] = send(v2, positive.replace('8 мм', '12 мм'))
    cases['versions']['oldProtocolId'] = old['protocolId']
    annul = meta('annulled'); send(annul, positive)
    annul['eventId'] += '-annul'; annul['eventType'] = 'PROTOCOL_ANNULLED'
    cases['annulled'] = send(annul, None, 'ANNULLED')
    # A different, older protocol remains editable; only previous versions are retired.
    older = meta('independent'); old = send(older, positive)
    newer = deepcopy(older); newer['eventId'] += '-another'; newer['protocol']['externalId'] += '-another'
    cases['independent'] = send(newer, positive.replace('8 мм', '9 мм'))
    cases['independent']['oldProtocolId'] = old['protocolId']
    live_doc = work / 'live-arrival.docx'
    docx(live_doc, positive.split('\n'))
    auto_event = dict(meta('live-arrival'), fileName=live_doc.name, contentBase64=base64.b64encode(live_doc.read_bytes()).decode('ascii'))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({'frontend': args.frontend, 'run': run, 'cases': cases, 'autoRefreshEvent': auto_event}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Created {len(cases)} fictional UI cases through the real ML pipeline: {args.output}')


if __name__ == '__main__':
    main()
