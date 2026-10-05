"""Real backend -> ML -> PostgreSQL integration. Uses synthetic patients and DOCX.

Run only against a demo/test database: this suite creates records through the API.
No mocks are used. Optional --corpus processes local DOCX without copying them.
"""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import time
import unittest
from route_cases import RouteIntegrationMixin
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'ml'))
sys.path.insert(0, str(ROOT / 'scripts'))
from backend_session import authenticate
import httpx
import yaml
from app.demo import docx
from app.contracts import validate_result
from app.processing import process_event
from app.corpus import study_type
from app.parser import extract_text, parse_text
from app.validation import validate_for_dictionary

CLI = argparse.ArgumentParser(description=__doc__)
CLI.add_argument('--backend', default='http://127.0.0.1:18081')
CLI.add_argument('--ml', default='http://127.0.0.1:18001')
CLI.add_argument('--corpus', type=Path)
CLI.add_argument('--report', type=Path, default=ROOT / '.local/integration-report.json')
ARGS = CLI.parse_args()
RUN = 'it-' + uuid4().hex[:12]
WORK = ROOT / '.local' / RUN
WORK.mkdir(parents=True)
CLIENT = httpx.Client(timeout=40, trust_env=False)
CALLS = []
DICTIONARY = yaml.safe_load((ROOT/'ml/configs/findings-dictionary.yaml').read_text(encoding='utf-8'))


def call(method, path, expected=200, ml=False, **kwargs):
    response = CLIENT.request(method, (ARGS.ml if ml else ARGS.backend).rstrip('/') + path, **kwargs)
    CALLS.append({'service': 'ml' if ml else 'backend', 'method': method, 'path': path.split('?')[0],
                  'status': response.status_code})
    allowed = expected if isinstance(expected, tuple) else (expected,)
    if response.status_code not in allowed:
        # This suite's payloads are fictional; do not persist response bodies in the coverage report.
        raise AssertionError(f'{method} {path}: expected {allowed}, got {response.status_code}: {response.text[:600]}')
    return response.json() if response.content and 'json' in response.headers.get('content-type', '') else response


def metadata(label, study='PELVIS_FEMALE', version=1, event_type='PROTOCOL_SIGNED'):
    return {'eventId': f'{RUN}-{label}-v{version}-{event_type}', 'eventType': event_type,
            'patient': {'externalId': f'{RUN}-{label}', 'fullName': f'Пациент тест {RUN} {label}',
                        'birthDate': '1990-01-01', 'sex': 'M' if study == 'PROSTATE' else 'F'},
            'protocol': {'externalId': f'{RUN}-protocol-{label}', 'version': version,
                         'studyType': study, 'studyDate': '2026-09-07'}}


def make_file(label, text):
    path = WORK / (label + '.docx')
    docx(path, text.split('\n'))
    return path


def event_with_file(meta, path):
    return dict(deepcopy(meta), fileName=path.name, contentBase64=base64.b64encode(path.read_bytes()).decode('ascii'))


def upload(meta, path, expected=202):
    return call('POST', '/api/integration/protocols', expected, files={
        'metadata': ('metadata.json', json.dumps(meta, ensure_ascii=False).encode(), 'application/json'),
        'file': (path.name, path.read_bytes(), 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')})


def delivered(meta, expected_status='DONE'):
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        status = call('GET', '/api/integration/events/status', params={'eventId': meta['eventId']})
        if status['delivery'] == 'delivered':
            assert status['status'] == expected_status, status
            return status
        if status['delivery'] in ('rejected', 'exhausted'):
            raise AssertionError(status)
        time.sleep(.15)
    raise AssertionError('Callback was not delivered in 25s: ' + str(status))


def card(meta):
    page = call('GET', '/api/patients', params={'search': meta['patient']['externalId'], 'size': 200})
    patients = [p for p in page['items'] if p['externalId'] == meta['patient']['externalId']]
    assert len(patients) == 1, page
    return call('GET', '/api/patients/' + patients[0]['id'])


class Integration(RouteIntegrationMixin, unittest.TestCase):
    route_api = globals()
    def setUp(self):
        CLIENT.cookies.clear()
        CLIENT.headers.pop('X-CSRF-TOKEN', None)
        if self._testMethodName != 'test_16_session_authentication':
            authenticate(CLIENT, ARGS.backend)

    def positive(self, label='positive'):
        meta = metadata(label)
        file = make_file(label, 'Описание\nПолип эндометрия 8 мм.\nЗаключение\nПолип эндометрия 8 мм.')
        upload(meta, file); delivered(meta)
        return meta, file, card(meta)

    def test_01_health_schema_and_dictionary(self):
        self.assertEqual(call('GET', '/api/ping')['status'], 'ok')
        self.assertEqual(call('GET', '/actuator/health')['status'], 'UP')
        call('GET', '/actuator'); call('GET', '/actuator/info')
        self.assertTrue(call('GET', '/health', ml=True)['workerRunning'])
        short = call('GET', '/api/dictionary/findings')
        self.assertEqual(len(short), 48)
        full = call('GET', '/api/dictionary/findings', params={'full': 'true'})
        self.assertEqual(full, DICTIONARY)
        breast = call('GET', '/api/dictionary/findings', params={'studyType': 'BREAST', 'q': 'молоч'})
        self.assertTrue(breast)
        self.assertTrue(all('BREAST' in f['studyTypes'] for f in breast))
        for path in ('/v3/api-docs', '/v3/api-docs/swagger-config', '/swagger-ui/index.html'):
            call('GET', path)
        call('GET', '/swagger-ui.html', (200, 302))
        for path in ('/openapi.json', '/docs', '/redoc', '/docs/oauth2-redirect'):
            call('GET', path, ml=True)

    def test_02_docx_roundtrip_and_doctor_actions(self):
        meta, file, c = self.positive('doctor')
        self.assertEqual(c['patient']['lastName'], 'Пациент')
        self.assertEqual(c['patient']['firstName'], 'тест')
        self.assertEqual(c['patient']['middleName'], f'{RUN} doctor')
        self.assertEqual(c['patient']['reviewState'], 'PENDING')
        self.assertEqual(c['currentProtocol']['version'], 1)
        self.assertEqual(c['patient']['birthDate'], meta['patient']['birthDate'])
        f, = c['currentFindings']
        self.assertEqual(f['code'], 'ENDOMETRIAL_POLYP')
        self.assertEqual(f['attributes']['sizeMm'], 8)
        self.assertEqual(f['targetDays'], 7)
        p = call('GET', '/api/protocols/' + f['protocolId'])
        e = f['evidence']; self.assertEqual(p['text'][e['start']:e['end']], e['text'])
        pid, fid = c['patient']['id'], f['id']
        self.assertEqual(len(call('GET', f'/api/patients/{pid}/findings', params={'status': 'SUGGESTED'})), 1)
        confirmed = call('POST', f'/api/patients/{pid}/findings/confirm', json={'findingIds': [fid], 'doctor': 'Тестовый врач'})
        self.assertEqual(confirmed[0]['status'], 'CONFIRMED')
        self.assertEqual(card(meta)['patient']['reviewState'], 'OK')
        updated = call('PATCH', f'/api/findings/{fid}', json={'attributes': {'sizeMm': 9, 'uncertain': True}, 'doctor': 'Тестовый врач'})
        self.assertEqual(updated['targetDays'], 14)
        self.assertEqual(updated['attributes']['sizeMm'], 9)
        self.assertEqual(call('PATCH', f'/api/findings/{fid}', json={'status': 'REJECTED'})['status'], 'REJECTED')
        manual = call('POST', f'/api/patients/{pid}/findings', 201, json={
            'code': 'ENDOMETRIAL_POLYP', 'protocolId': f['protocolId'], 'attributes': {'uncertain': False}, 'doctor': 'Тестовый врач'})
        self.assertEqual(manual['source'], 'MANUAL'); self.assertEqual(manual['targetDays'], 7)
        call('DELETE', '/api/findings/' + manual['id'], 204, params={'reason': 'Тест удаления'})
        call('PATCH', '/api/findings/' + manual['id'], 400, json={'status': 'CONFIRMED'})
        call('POST', f'/api/patients/{pid}/findings/confirm', 400, json={'findingIds': [None]})
        call('POST', f'/api/patients/{pid}/findings/confirm', 400, json={'findingIds': []})
        call('PATCH', f'/api/findings/{fid}', 400, json={'status': 'SUGGESTED'})
        call('POST', f'/api/patients/{pid}/findings', 400, json={'code': 'UNKNOWN'})
        call('POST', f'/api/patients/{pid}/findings', 400, json={'code': 'BREAST_LESION', 'protocolId': f['protocolId']})

    def test_03_correction_annulment_and_idempotency(self):
        meta, file, c = self.positive('versions')
        pid = c['patient']['id']; old_id = c['currentProtocol']['id']; old_fid = c['currentFindings'][0]['id']
        duplicate = upload(meta, file); self.assertEqual(duplicate['delivery'], 'delivered')
        changed = deepcopy(meta); changed['patient']['fullName'] = 'Другой тестовый пациент'
        upload(changed, file, 409)
        fixed = deepcopy(meta); fixed['eventId'] += '-fix'; fixed['eventType'] = 'PROTOCOL_CORRECTED'; fixed['protocol']['version'] = 2
        file2 = make_file('corrected', 'Описание\nПолип эндометрия 12 мм.\nЗаключение\nПолип эндометрия 12 мм.')
        upload(fixed, file2); delivered(fixed)
        now = card(fixed)
        self.assertEqual(now['currentProtocol']['version'], 2)
        self.assertEqual(len(now['history']['protocols']), 1)
        self.assertEqual(call('GET', '/api/protocols/' + old_id)['findings'][0]['status'], 'REMOVED')
        call('POST', f'/api/patients/{pid}/findings/confirm', 400, json={'findingIds': [old_fid]})
        stale = deepcopy(meta); stale['eventId'] += '-stale'; upload(stale, file, 409)
        annul = deepcopy(fixed); annul['eventId'] += '-annul'; annul['eventType'] = 'PROTOCOL_ANNULLED'
        call('POST', '/api/integration/events', 202, json=annul); delivered(annul, 'ANNULLED')
        final = card(annul)
        self.assertEqual(final['currentProtocol']['status'], 'ANNULLED')
        self.assertEqual(final['currentFindings'], [])
        status = call('GET', '/api/mis/events/' + annul['eventId'], ml=True)
        self.assertEqual(status['delivery'], 'delivered')
        call('POST', '/api/integration/events/retry', 202, params={'eventId': annul['eventId']})
        call('POST', '/api/mis/events/' + annul['eventId'] + '/retry', 202, ml=True)

    def test_04_failure_and_no_conclusion_are_visible(self):
        broken = WORK/'broken.docx'; broken.write_bytes(b'not a ZIP archive')
        meta = metadata('broken'); upload(meta, broken); delivered(meta, 'FAILED')
        c = card(meta); self.assertEqual(c['patient']['reviewState'], 'ATTENTION')
        self.assertEqual(call('GET', '/api/protocols/' + c['currentProtocol']['id'])['error']['code'], 'UNREADABLE_FILE')
        missing = metadata('no-conclusion')
        file = make_file('no-conclusion', 'Описание\nПолип эндометрия 9 мм.')
        upload(missing, file); delivered(missing)
        c = card(missing); self.assertEqual(c['patient']['reviewState'], 'ATTENTION')
        self.assertFalse(c['currentProtocol']['conclusionFound'])
        self.assertIn('NO_CONCLUSION', [f['code'] for f in c['currentProtocol']['flags']])
        self.assertEqual(c['routes'], [])

    def test_05_route_thresholds_emergency_and_minor(self):
        cases = [
            ('normal', 'BREAST', 'BI-RADS 1 справа. BI-RADS 1 слева.', None, None),
            ('observation', 'ABDOMEN', 'Полип желчного пузыря 3 мм, без динамики.', 'GALLBLADDER_POLYP', 'PLANNED'),
            ('below', 'THYROID', 'Узел левой доли щитовидной железы 5 мм, EU-TIRADS 2.', None, None),
            ('breast-high', 'BREAST', 'Образование левой молочной железы 18 мм. BI-RADS 5 слева.', 'BREAST_LESION', 'PLANNED'),
            ('emergency', 'LOWER_LIMB_VESSELS', 'Тромбоз глубоких вен левой голени.', 'DEEP_VEIN_THROMBOSIS', 'EMERGENCY'),
            ('minor', 'PELVIS_FEMALE', 'Полип эндометрия 8 мм.', 'ENDOMETRIAL_POLYP', 'PLANNED')]
        for label, study, text, code, level in cases:
            with self.subTest(label=label):
                meta = metadata(label, study)
                if label == 'minor': meta['patient']['birthDate'] = '2012-01-01'
                upload(meta, make_file(label, 'Описание\n' + text + '\nЗаключение\n' + text)); delivered(meta)
                c = card(meta)
                if code:
                    finding = next(f for f in c['currentFindings'] if f['code'] == code)
                    self.assertEqual(finding['level'], level)
                    self.assertEqual(c['patient']['maxLevel'], level)
                    if label == 'observation': self.assertEqual(finding['targetDays'], 180)
                    if label == 'breast-high': self.assertEqual(finding['targetDays'], 3)
                    if label == 'minor':
                        self.assertIn('Детский', finding['targetSpecialty'])
                        self.assertIn('MINOR', [f['code'] for f in finding['flags']])
                else:
                    self.assertFalse(c['currentFindings'])
                    self.assertTrue(call('GET', '/api/protocols/' + c['currentProtocol']['id'])['notTriggered'])

    def test_06_direct_callback_validation_concurrency_and_tombstone(self):
        meta = metadata('callback')
        file = make_file('callback', 'Описание\n😀 Полип эндометрия 8 мм.\nЗаключение\nПолип эндометрия 8 мм.')
        result = process_event(event_with_file(meta, file), lambda: DICTIONARY)
        validate_result(result)
        # Deliver the identical result concurrently, like network retries from multiple senders.
        with ThreadPoolExecutor(max_workers=6) as pool:
            responses = list(pool.map(lambda _: call('POST', '/api/integration/ml/results', 202, json=result), range(8)))
        c = card(meta); self.assertEqual(len(c['currentFindings']), 1)
        corrupt = deepcopy(result); corrupt['patient']['fullName'] = 'Изменённое содержимое'
        call('POST', '/api/integration/ml/results', 409, json=corrupt)
        for label, mutate in [
            ('missing', lambda r: r.pop('findings')),
            ('null-entry', lambda r: r.update(findings=[None])),
            ('bad-code', lambda r: r['findings'][0].update(code='UNKNOWN')),
            ('bad-evidence', lambda r: r['findings'][0]['evidence'].update(start=9999)),
            ('bad-confidence', lambda r: r['findings'][0].update(confidence=2)),
            ('bad-attr', lambda r: r['findings'][0]['attributes'].update(uncertain='false')),
            ('bad-flag', lambda r: r.update(flags=[{'code': 'MINOR'}])),
            ('bad-nt', lambda r: r.update(notTriggered=[{'code': 'UNKNOWN', 'reason':'NEGATION','evidence':{'text':'Полип'}}]))]:
            with self.subTest(label=label):
                bad = deepcopy(result); bad['resultId'] += label; mutate(bad)
                call('POST', '/api/integration/ml/results', 400, json=bad)
        other = deepcopy(result); other['resultId'] += '-other'; other['protocol']['version'] = 2
        other['patient']['externalId'] += '-other'
        call('POST', '/api/integration/ml/results', 409, json=other)
        newer = deepcopy(result); newer['resultId'] += '-v3'; newer['protocol']['version'] = 3
        call('POST', '/api/integration/ml/results', 202, json=newer)
        late = deepcopy(result); late['resultId'] += '-late'; late['status'] = 'ANNULLED'; late['findings'] = []
        late['patient']['fullName'] = 'Устаревшие метаданные'
        call('POST', '/api/integration/ml/results', 202, json=late)
        c = card(meta); self.assertEqual(c['currentProtocol']['version'], 3)
        self.assertEqual(c['currentProtocol']['status'], 'DONE')
        self.assertEqual(c['patient']['fullName'], meta['patient']['fullName'])
        tomb = deepcopy(late); tomb['resultId'] += '-v5'; tomb['protocol']['version'] = 5
        call('POST', '/api/integration/ml/results', 202, json=tomb)
        late4 = deepcopy(newer); late4['resultId'] += '-v4'; late4['protocol']['version'] = 4
        call('POST', '/api/integration/ml/results', 202, json=late4)
        c = card(meta); self.assertEqual(c['currentProtocol']['version'], 5)
        self.assertEqual(c['currentProtocol']['status'], 'ANNULLED')
        self.assertEqual(c['currentFindings'], [])

    def test_07_filters_invalid_requests_and_missing_ids(self):
        for params in ({'page': -1}, {'size':0}, {'size':201}, {'dateFrom':'2026-10-01','dateTo':'2026-01-01'},
                       {'reviewState':'UNKNOWN'}, {'maxLevel':'INVALID'}, {'dateFrom':'not-date'}):
            call('GET', '/api/patients', 400, params=params)
        self.assertEqual(call('GET', '/api/patients', params={'page':2147483647, 'size':200})['items'], [])
        for params in ({'reviewState':'ATTENTION'}, {'studyType':'BREAST'}, {'maxLevel':'EMERGENCY'},
                       {'dateFrom':'2026-09-07','dateTo':'2026-09-07'}, {'search':RUN,'page':0,'size':2}):
            page = call('GET', '/api/patients', params=params)
            self.assertGreater(page['total'], 0)
            if 'size' in params: self.assertLessEqual(len(page['items']), params['size'])
            if 'maxLevel' in params: self.assertTrue(all(p['maxLevel'] == params['maxLevel'] for p in page['items']))
        for path in ('/api/patients/not-uuid', '/api/patients/'+str(uuid4()), '/api/protocols/'+str(uuid4()),
                     '/api/patients/'+str(uuid4())+'/findings'):
            call('GET', path, 404)
        call('PATCH', '/api/findings/'+str(uuid4()), 404, json={})
        call('DELETE', '/api/findings/'+str(uuid4()), 404)
        call('POST', '/api/integration/ml/results', 400, json={})
        call('POST', '/api/integration/events', 400, json={})
        call('POST', '/api/integration/events', 400, content='{', headers={'Content-Type':'application/json'})
        call('POST', '/api/integration/protocols', 400, files={'metadata': ('meta.json', '{}', 'application/json')})
        call('POST', '/api/integration/protocols', 400, files={'metadata': ('meta.json', '[]', 'application/json')})
        call('POST', '/api/integration/protocols', 400, files={'metadata': ('meta.json', '{}', 'application/json'), 'file': ('a.txt', b'x', 'text/plain')})
        call('POST', '/api/integration/protocols', 413, files={'metadata': ('meta.json', '{}', 'application/json'), 'file': ('large.docx', b'x'*(20*1024*1024+1), 'application/octet-stream')})
        call('GET', '/api/integration/events/status', 404, params={'eventId':'absent'})
        call('POST', '/api/integration/events/retry', 404, params={'eventId':'absent'})
        call('GET', '/api/mis/events/absent', 404, ml=True)
        call('POST', '/api/mis/events/absent/retry', 404, ml=True)
        call('POST', '/api/mis/events', 400, ml=True, json={})
        call('POST', '/api/mis/events', 400, ml=True, content='{', headers={'Content-Type':'application/json'})
        call('POST', '/api/mis/events', 415, ml=True, content='{}', headers={'Content-Type':'text/plain'})
        call('POST', '/api/mis/events', 413, ml=True, content=b' '*(29*1024*1024+1), headers={'Content-Type':'application/json'})
        call('OPTIONS', '/api/patients', 200, headers={'Origin':'http://localhost:3000','Access-Control-Request-Method':'GET'})

    def test_08_direct_ml_api_accepts_event_and_preserves_metadata(self):
        meta=metadata('direct'); meta['patient']['customField']='preserved'; meta['protocol']['customField']=42
        file=make_file('direct','Заключение\nПолип эндометрия 7 мм.')
        event=event_with_file(meta,file)
        call('POST','/api/mis/events',202,ml=True,json=event); delivered(meta)
        result=process_event(event,lambda:DICTIONARY)
        self.assertEqual(result['patient'],meta['patient']); self.assertEqual(result['protocol'],meta['protocol'])
        self.assertEqual(card(meta)['currentProtocol']['status'],'DONE')

    def test_09_cross_patient_manual_actions_are_rejected(self):
        meta, _, one=self.positive('owner-a'); _, _, two=self.positive('owner-b')
        call('POST', f"/api/patients/{two['patient']['id']}/findings/confirm", 400,
             json={'findingIds':[one['currentFindings'][0]['id']]})
        call('POST', f"/api/patients/{two['patient']['id']}/findings", 400,
             json={'code':'ENDOMETRIAL_POLYP','protocolId':one['currentProtocol']['id']})

    def test_10_older_unreviewed_emergency_stays_visible(self):
        first=metadata('multistudy','LOWER_LIMB_VESSELS')
        upload(first,make_file('multistudy-first','Заключение\nТромбоз глубоких вен левой голени.')); delivered(first)
        second=metadata('multistudy-next','PELVIS_FEMALE'); second['patient']=deepcopy(first['patient'])
        upload(second,make_file('multistudy-next','Заключение\nПолип эндометрия 8 мм.')); delivered(second)
        c=card(first)
        self.assertEqual(c['patient']['maxLevel'],'EMERGENCY')
        self.assertEqual(c['patient']['pendingFindings'],2)
        self.assertTrue(any(f['code']=='DEEP_VEIN_THROMBOSIS' and f['status']=='SUGGESTED' for f in c['history']['findings']))

    def test_11_special_event_id_roundtrip(self):
        meta=metadata('special-id'); meta['eventId'] += '/пробел + вопрос?'
        upload(meta,make_file('special-id','Заключение\nПолип эндометрия 8 мм.')); delivered(meta)
        self.assertEqual(call('POST','/api/integration/events/retry',202,params={'eventId':meta['eventId']})['delivery'],'delivered')

    def test_12_all_imported_demo_payloads_are_accepted(self):
        for path in sorted((ROOT/'backend/src/main/resources/demo').glob('*.json')):
            with self.subTest(file=path.name):
                result=json.loads(path.read_text(encoding='utf-8'))
                validate_for_dictionary(result,DICTIONARY)
                result['resultId']=RUN+'-'+result['resultId']
                result['patient']['externalId']=RUN+'-'+result['patient']['externalId']
                result['protocol']['externalId']=RUN+'-'+result['protocol']['externalId']
                call('POST','/api/integration/ml/results',202,json=result)

    def test_13_structured_names_roundtrip_search_and_corrections(self):
        meta = metadata('structured-name')
        meta['patient'].update(fullName='Устаревшее ФИО', lastName=' де ла Крус ', firstName=' Анна   Мария ', middleName=' ')
        file = make_file('structured-name', 'Заключение\nПолип эндометрия 8 мм.')
        upload(meta, file); delivered(meta)
        expected = {'lastName': 'де ла Крус', 'firstName': 'Анна Мария', 'middleName': None,
                    'fullName': 'де ла Крус Анна Мария', 'shortName': 'де ла Крус А.'}
        patient = card(meta)['patient']
        for key, value in expected.items(): self.assertEqual(patient[key], value, key)
        found = call('GET', '/api/patients', params={'search': 'ДЕ ЛА КРУС', 'size': 200})
        row = next(p for p in found['items'] if p['id'] == patient['id'])
        for key, value in expected.items(): self.assertEqual(row[key], value, key)

        # Raw metadata is preserved by ML; only the backend normalizes the patient row.
        result = process_event(event_with_file(meta, file), lambda: DICTIONARY)
        self.assertEqual(result['patient'], meta['patient'])
        result['resultId'] = f'{RUN}-name-fingerprint'
        call('POST', '/api/integration/ml/results', 202, json=result)
        call('POST', '/api/integration/ml/results', 202, json=result)
        altered = deepcopy(result); altered['patient']['firstName'] = 'Другое имя'
        call('POST', '/api/integration/ml/results', 409, json=altered)

        corrected = deepcopy(meta); corrected['eventId'] += '-v2'
        corrected['eventType'] = 'PROTOCOL_CORRECTED'; corrected['protocol']['version'] = 2
        corrected['patient']['middleName'] = 'Ивановна'
        upload(corrected, file); delivered(corrected)
        self.assertEqual(card(corrected)['patient']['shortName'], 'де ла Крус А. И.')
        self.assertEqual(card(corrected)['patient']['id'], patient['id'])
        annulled = deepcopy(corrected); annulled['eventId'] += '-annul'
        annulled['eventType'] = 'PROTOCOL_ANNULLED'
        call('POST', '/api/integration/events', 202, json=annulled); delivered(annulled, 'ANNULLED')
        self.assertEqual(card(annulled)['patient']['middleName'], 'Ивановна')

        schema = call('GET', '/v3/api-docs')['components']['schemas']
        self.assertTrue({'lastName', 'firstName', 'middleName', 'shortName'} <= schema['PatientShortDto']['properties'].keys())
        self.assertIn('fullName', schema['PatientPart']['required'])

    def test_14_invalid_name_parts_rejected_before_processing(self):
        file = make_file('bad-name', 'Заключение\nПолип эндометрия 8 мм.')
        for field in ('lastName', 'firstName', 'middleName'):
            invalid = metadata('bad-' + field); invalid['patient'][field] = ['not a string']
            upload(invalid, file, 400)
        missing = metadata('missing-fullname'); missing['patient'].pop('fullName')
        missing['patient'].update(lastName='Соколова', firstName='Анна')
        upload(missing, file, 400)

    def test_15_direction_queues_and_urgent_status(self):
        def queue(meta, expected):
            patient = card(meta)['patient']
            self.assertEqual(patient['needsRouteReview'], expected)
            for flag in (True, False):
                page = call('GET', '/api/patients', params={
                    'search': meta['patient']['externalId'], 'needsRouteReview': str(flag).lower(), 'size': 1})
                self.assertEqual(page['total'], int(flag == expected))
                self.assertEqual(len(page['items']), int(flag == expected))
            return patient

        auto, _, _ = self.positive('queue-auto')
        queue(auto, False)  # SUGGESTED alone does not mean an undetermined direction.
        missing = metadata('queue-missing')
        upload(missing, make_file('queue-missing', 'Описание\nПолип эндометрия 8 мм.')); delivered(missing)
        patient = queue(missing, True)
        f = card(missing)['currentFindings'][0]
        call('POST', f"/api/patients/{patient['id']}/findings/confirm", json={'findingIds': [f['id']], 'doctor': 'Тестовый врач'})
        queue(missing, False)

        urgent = metadata('queue-urgent', 'SOFT_TISSUE')
        upload(urgent, make_file('queue-urgent', 'Описание\nВоспалительные изменения ПЖК.\nЗаключение\nВоспалительные изменения ПЖК.')); delivered(urgent)
        self.assertEqual(queue(urgent, False)['maxLevel'], 'URGENT')
        page = call('GET', '/api/patients', params={'search': urgent['patient']['externalId'], 'maxLevel': 'URGENT', 'needsRouteReview': 'false'})
        self.assertEqual(page['total'], 1)
        self.assertEqual(page['items'][0]['topFindings'][0]['targetDays'], 3)

        unknown = metadata('queue-unknown', 'ABDOMEN')
        upload(unknown, make_file('queue-unknown', 'Заключение\nАневризма брюшной аорты.')); delivered(unknown)
        patient = queue(unknown, True)
        fs = card(unknown)['currentFindings']
        self.assertTrue(any(f['code'] == 'UNRECOGNIZED_ABNORMALITY' for f in fs))
        call('POST', f"/api/patients/{patient['id']}/findings/confirm", json={'findingIds': [f['id'] for f in fs]})
        queue(unknown, True)  # Confirmation without a concrete direction cannot hide the case.
        unknown['eventId'] += '-annul'; unknown['eventType'] = 'PROTOCOL_ANNULLED'
        call('POST', '/api/integration/events', 202, json=unknown); delivered(unknown, 'ANNULLED')
        queue(unknown, False)


    def test_16_session_authentication(self):
        schema = call('GET', '/v3/api-docs')
        self.assertFalse(schema['paths']['/api/auth/csrf']['get'].get('parameters'))
        call('GET', '/api/auth/me', 401)
        call('GET', '/api/patients', 401)
        call('POST', '/api/auth/login', 403, json={'login': '123', 'password': '123'})
        token = call('GET', '/api/auth/csrf')
        headers = {token['headerName']: token['token']}
        call('POST', '/api/auth/login', 401, headers=headers, json={'login': '123', 'password': 'bad'})
        session_before = CLIENT.cookies.get('JSESSIONID')
        account = call('POST', '/api/auth/login', headers=headers, json={'login': '123', 'password': '123'})
        self.assertEqual(account, {'login': '123', 'roles': ['DOCTOR']})
        self.assertNotEqual(CLIENT.cookies.get('JSESSIONID'), session_before)
        self.assertEqual(call('GET', '/api/auth/me'), account)
        call('POST', '/api/auth/logout', 403)
        call('POST', '/api/auth/logout', 403, headers=headers)  # old CSRF token revoked on login
        token = call('GET', '/api/auth/csrf')
        call('POST', '/api/auth/logout', 204, headers={token['headerName']: token['token']})
        call('GET', '/api/auth/me', 401)

    def test_17_server_sort_and_pagination(self):
        for key in ('patient', 'finding', 'due', 'receivedAt', 'studyDate'):
            for direction in ('asc', 'desc'):
                query = {'search': RUN, 'sortBy': key, 'sortDirection': direction}
                all_items = call('GET', '/api/patients', params=dict(query, size=200))['items']
                pages = [call('GET', '/api/patients', params=dict(query, size=3, page=p))['items'] for p in range((len(all_items) + 2) // 3)]
                self.assertEqual([p['id'] for chunk in pages for p in chunk], [p['id'] for p in all_items])
                if key == 'due':
                    values = [p['topFindings'][0]['targetDays'] if p['topFindings'] else None for p in all_items]
                    ordered = sorted([v for v in values if v is not None], reverse=direction == 'desc')
                    self.assertEqual(values, ordered + [None] * values.count(None))
        for key in ('stage', 'notified', 'invalid'):
            call('GET', '/api/patients', 400, params={'sortBy': key})
        call('GET', '/api/patients', 400, params={'sortDirection': 'invalid'})


def coverage():
    report = {}
    for service, path in [('backend','/v3/api-docs'),('ml','/openapi.json')]:
        schema = call('GET',path,ml=service=='ml')
        expected = {(method.upper(),route) for route, operations in schema['paths'].items()
                    for method in operations if method.lower() in {'get','post','put','patch','delete','options','head'}}
        hits=[]; missing=[]
        for method,route in sorted(expected):
            pattern='^'+re.sub(r'\{[^}]+\}',r'[^?]+',route)+'$'
            hit=any(c['service']==service and c['method']==method and re.match(pattern,c['path']) for c in CALLS)
            (hits if hit else missing).append(method+' '+route)
        report[service]={'covered':hits,'uncovered':missing,'total':len(expected)}
    return report


def corpus(directory):
    report=[]
    paths=sorted(directory.rglob('*.docx'))
    if not paths: raise AssertionError('No DOCX in corpus')
    for i,path in enumerate(paths,1):
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        raw=extract_text(path); kind=study_type(raw)[0]
        if not kind: raise AssertionError('Ambiguous studyType; supply metadata explicitly')
        meta=metadata(f'corpus-{i:03d}',kind)
        meta['protocol']['studyDate']=parse_text(raw).get('examination_date') or '2026-09-07'
        start=time.perf_counter()
        upload(meta,path); receipt=delivered(meta); c=card(meta)
        p=call('GET','/api/protocols/'+c['currentProtocol']['id'])
        for f in p['findings']:
            e=f['evidence']; assert p['text'][e['start']:e['end']]==e['text']
        assert hashlib.sha256(path.read_bytes()).hexdigest()==digest
        report.append({'document':i,'sourceSha256':digest,'status':receipt['status'],
                       'delivery':receipt['delivery'],'findingsAfterRules':len(p['findings']),
                       'seconds':round(time.perf_counter()-start,3)})
        print(f'Corpus {i}/{len(paths)}: DONE, delivered',flush=True)
    return report


if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Integration))
    report={'createdAt':datetime.now(timezone.utc).isoformat(),'runId':RUN,'backend':ARGS.backend,'ml':ARGS.ml,
            'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
            'coverage':coverage(),'requests':CALLS}
    if ARGS.corpus and result.wasSuccessful(): report['corpus']=corpus(ARGS.corpus)
    ARGS.report.parent.mkdir(parents=True,exist_ok=True)
    ARGS.report.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    CLIENT.close()
    raise SystemExit(0 if result.wasSuccessful() and not any(v['uncovered'] for v in report['coverage'].values()) else 1)
