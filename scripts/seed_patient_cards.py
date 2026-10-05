"""Create clearly labelled fictional patient cards using local backend -> ML.

Uses public APIs only. Does not change global model time or existing patients.
Existing external IDs are skipped to preserve subsequent doctor actions.
"""
import argparse
from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
from pathlib import Path
import sys
import time
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'ml'))
import httpx
from app.demo import docx
from backend_session import authenticate

POLYP = ('PELVIS_FEMALE', 'Полип эндометрия 8 мм.')
BREAST = ('BREAST', 'Образование левой молочной железы 18 мм, BI-RADS 4.')
THYROID = ('THYROID', 'Узел правой доли щитовидной железы 21 мм, TI-RADS 4.')
CASES = [
    ('01', 'Ожидание', [POLYP], 'waiting', ['NOTIFIED']),
    ('02', 'Записан', [BREAST], 'booked', ['BOOKED']),
    ('03', 'Срочный', [('SOFT_TISSUE', 'Воспалительные изменения ПЖК.')], 'urgent', ['NOTIFIED']),
    ('04', 'Госпитализация', [('PELVIS_FEMALE', 'Полип эндометрия 8 мм. Субмукозная миома матки FIGO 1 размером 20 мм.')], 'hospital', ['HOSPITALIZATION_REFERRED']),
    ('05', 'Наблюдение', [('PELVIS_FEMALE', 'Интрамуральная миома матки FIGO 4 размером 15 мм.')], 'observation', ['OBSERVATION_WAITING_US']),
    ('06', 'Неявка', [BREAST], 'no-show', ['NO_SHOW']),
    ('07', 'Процедура', [THYROID], 'procedure', ['PROCEDURE_REFERRED']),
    ('08', 'Закрытый', [POLYP], 'closed', ['CLOSED']),
    ('09', 'НесколькоМаршрутов', [POLYP, THYROID, ('ABDOMEN', 'Желчнокаменная болезнь. Конкремент желчного пузыря 12 мм.')], 'multiple', ['BOOKED', 'NOTIFIED', 'NOTIFIED']),
]


def seed(backend, prefix, report_path):
    if urlparse(backend).hostname not in {'localhost', '127.0.0.1', '::1'}:
        raise ValueError('This demo seeder only supports a local backend.')
    if not prefix.startswith('demo-'):
        raise ValueError('Use a demo- prefix for fictional patient IDs.')
    results = []
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(base_url=backend.rstrip('/'), timeout=45, trust_env=False) as client:
        authenticate(client)

        def request(method, path, **kwargs):
            r = client.request(method, path, **kwargs)
            if r.is_error:
                raise RuntimeError(f'{method} {path}: {r.status_code} {r.text}')
            return r.json() if r.content else None

        def find(external_id):
            items = request('GET', '/api/patients', params={'search': external_id, 'size': 200})['items']
            return next((p for p in items if p['externalId'] == external_id), None)

        def routes(pid):
            return request('GET', f'/api/patients/{pid}/routes')

        def future(days=1):
            return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()

        for number, label, protocols, action, expected_stages in CASES:
            external_id = f'{prefix}-{number}'
            name = f'[ТЕСТ М{number}] {label}'
            existing = find(external_id)
            created = existing is None
            if existing and not existing['fullName'].startswith(f'[ТЕСТ М{number}]'):
                raise RuntimeError('Existing ID is not one of these test patients: ' + external_id)
            if created:
                for index, (study, text) in enumerate(protocols, 1):
                    event_id = f'{external_id}-protocol-{index}'
                    meta = {
                        'eventId': event_id, 'eventType': 'PROTOCOL_SIGNED',
                        'patient': {'externalId': external_id, 'fullName': name + ' Пациент',
                                    'lastName': name, 'firstName': 'Пациент', 'middleName': None,
                                    'birthDate': f'{1980 + int(number)}-02-10', 'sex': 'F'},
                        'protocol': {'externalId': event_id, 'version': 1, 'studyType': study,
                                     'studyDate': datetime.now(timezone(timedelta(hours=3))).date().isoformat()}}
                    document = BytesIO()
                    docx(document, ['ТЕСТОВЫЙ ПРОТОКОЛ. Вымышленный пациент для демонстрации интерфейса.',
                                    'Описание', text, 'Заключение', text])
                    request('POST', '/api/integration/protocols', files={
                        'metadata': ('metadata.json', json.dumps(meta, ensure_ascii=False).encode(), 'application/json'),
                        'file': ('TEST-' + event_id + '.docx', document.getvalue(),
                                 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')})
                    deadline = time.monotonic() + 45
                    while True:
                        status = request('GET', '/api/integration/events/status', params={'eventId': event_id})
                        if status['delivery'] == 'delivered':
                            break
                        if status['delivery'] in ('rejected', 'exhausted') or time.monotonic() > deadline:
                            raise RuntimeError(f'ML did not deliver {event_id}: {status}')
                        time.sleep(.2)
                    patient = find(external_id)
                    pid = patient['id']
                    card = request('GET', f'/api/patients/{pid}')
                    assert card['currentProtocol']['status'] == 'DONE', card['currentProtocol']
                    assert card['currentFindings'], (external_id, 'ML found no findings')
                    request('POST', f'/api/patients/{pid}/findings/confirm', json={
                        'findingIds': [f['id'] for f in card['currentFindings']], 'doctor': 'Тестовый врач'})

                patient_routes = sorted(routes(pid), key=lambda r: r['createdAt'])
                assert len(patient_routes) == len(expected_stages), (external_id, patient_routes)
                assert all(r['chainType'] != 'EMERGENCY' for r in patient_routes), external_id
                route = patient_routes[0]
                def event(kind, chosen=route, **fields):
                    return request('POST', '/api/integration/route-events', json={
                        'eventId': f'{external_id}-{chosen["id"]}-{kind}', 'type': kind,
                        'routeId': chosen['id'], 'comment': 'Вымышленный демонстрационный сценарий', **fields})

                def notify(chosen, template='INITIAL', delivery='READ'):
                    n = request('POST', f'/api/routes/{chosen["id"]}/notifications', json={
                        'templateCode': template, 'confirm': True, 'doctor': 'Тестовый врач'})
                    if delivery:
                        request('POST', '/api/integration/crm/callbacks', json={
                            'eventId': external_id + '-crm-' + n['id'], 'messageId': n['id'], 'status': delivery})
                    return n

                for r in patient_routes:
                    notify(r, delivery=None if action in ('waiting', 'urgent') else 'READ')

                def book(chosen=route, immediate=False):
                    when = (datetime.now(timezone.utc) + timedelta(seconds=2)).isoformat() if immediate else future()
                    event('BOOKED', chosen, dateTime=when, location='Тестовая клиника — демонстрация',
                          doctorName='Тестовый специалист', online=False)
                    if immediate:
                        time.sleep(2.1)

                if action in ('booked', 'multiple'):
                    book()
                elif action == 'no-show':
                    book(immediate=True)
                    event('NO_SHOW')
                    request('POST', '/api/integration/crm/callbacks', json={
                        'eventId': external_id + '-callback-request', 'routeId': route['id'], 'reply': 'CALLBACK_REQUEST'})
                elif action in ('hospital', 'procedure', 'closed'):
                    book(immediate=True)
                    event('VISIT_COMPLETED')
                    if action == 'hospital':
                        event('TACTIC_SELECTED', tactic='SURGERY_INDICATED')
                        event('HOSPITALIZATION_REFERRED')
                        event('HOSPITALIZATION_DATE_SET', date=future(5)[:10], clinic='Тестовая клиника')
                        event('HOSPITALIZATION_FAILED', reason='Тестовый перенос: требуется новая дата')
                    elif action == 'procedure':
                        event('TACTIC_SELECTED', tactic='ADDITIONAL_EXAM', subtype='PROCEDURE')
                    else:
                        event('TACTIC_SELECTED', tactic='SURGERY_NOT_INDICATED')
                elif action == 'urgent':
                    assert route['chainType'] == 'URGENT', route

            patient = find(external_id)
            pid = patient['id']
            card = request('GET', f'/api/patients/{pid}')
            patient_routes = routes(pid)
            notifications = request('GET', f'/api/patients/{pid}/notifications')
            findings = request('GET', f'/api/patients/{pid}/findings')
            assert patient_routes and notifications and findings, external_id
            assert '[ТЕСТ М' in card['patient']['shortName'], external_id
            if created:
                assert sorted(r['stage'] for r in patient_routes) == sorted(expected_stages), (external_id, patient_routes)
                assert all(f['status'] == 'CONFIRMED' for f in findings), external_id
            results.append({'scenario': number, 'name': name, 'id': pid, 'externalId': external_id,
                            'created': created, 'routes': len(patient_routes), 'findings': len(findings),
                            'notifications': len(notifications), 'stages': [r['stage'] for r in patient_routes],
                            'tasks': sum(len(r['openTasks']) for r in patient_routes)})
            report_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
            print(f'OK {number} {label}: routes={len(patient_routes)}, findings={len(findings)}, notifications={len(notifications)}, created={created}', flush=True)
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', default='http://127.0.0.1:8080')
    parser.add_argument('--prefix', default='demo-card-v1')
    parser.add_argument('--report', type=Path, default=ROOT / '.local/demo-patient-cards.json')
    args = parser.parse_args()
    rows = seed(args.backend, args.prefix, args.report)
    print(f'{len(rows)} patients; {sum(r["created"] for r in rows)} created. {args.report}')
