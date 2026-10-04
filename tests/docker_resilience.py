"""Verify Compose outages and volume persistence using fictional patients.

Run against the local demo stack only: this stops/recreates its containers.
Named volumes are preserved. All services are started again in finally.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'ml'))
from app.demo import docx
from app.mis import build_event


def compose(*args):
    result = subprocess.run(['docker', 'compose', *args], cwd=ROOT,
                            capture_output=True, text=True, encoding='utf-8',
                            errors='replace', timeout=180)
    if result.returncode:
        raise RuntimeError(f'Compose {args} failed: {result.stdout}\n{result.stderr}')
    return result.stdout.strip()


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--report', type=Path, default=ROOT / '.local/docker-resilience.json')
    args = cli.parse_args()
    backend = 'http://' + compose('port', 'backend', '8080')
    ml = 'http://' + compose('port', 'ml', '8000')
    frontend = 'http://' + compose('port', 'frontend', '80')
    frontend_id = compose('ps', '-q', 'frontend')
    identity = 'docker-recovery-' + uuid4().hex[:12]
    work = ROOT / '.local' / identity
    work.mkdir(parents=True)
    checks = []

    with httpx.Client(timeout=35, trust_env=False) as client:
        def request(method, url, expected=200, **kwargs):
            response = client.request(method, url, **kwargs)
            assert response.status_code == expected, (url, response.status_code, response.text[:300])
            return response.json()

        def healthy(url):
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                try:
                    if client.get(url, timeout=2).status_code == 200:
                        return
                except httpx.HTTPError:
                    pass
                time.sleep(.3)
            raise AssertionError('Service did not become healthy: ' + url)

        def wait_status(event_id, predicate, timeout=150):
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                status = request('GET', ml + '/api/mis/events/' + event_id)
                assert status['delivery'] not in ('exhausted', 'rejected'), status
                if predicate(status):
                    return status
                time.sleep(.3)
            raise AssertionError('Delivery deadline exceeded: ' + str(status))

        def card():
            page = request('GET', backend + '/api/patients', params={'search': identity})
            assert len(page['items']) == 1, page
            return request('GET', backend + '/api/patients/' + page['items'][0]['id'])

        def passed(name):
            checks.append(name)
            print('PASS: ' + name, flush=True)

        healthy(backend + '/actuator/health')
        healthy(ml + '/health')
        path = work / 'synthetic.docx'
        docx(path, ['Описание', 'Полип эндометрия 8 мм.', 'Заключение', 'Полип эндометрия 8 мм.'])
        meta = {'eventId': identity + '-signed', 'eventType': 'PROTOCOL_SIGNED',
                'patient': {'externalId': identity, 'fullName': 'Пациент проверки Docker',
                            'birthDate': '1990-01-01', 'sex': 'F'},
                'protocol': {'externalId': identity, 'version': 1,
                             'studyType': 'PELVIS_FEMALE', 'studyDate': '2026-09-07'}}
        event = build_event(meta, path)
        try:
            compose('stop', 'ml')
            request('POST', backend + '/api/integration/events', 502, json=event)
            passed('gateway_502_without_ml')
            compose('up', '-d', '--no-deps', 'ml')
            healthy(ml + '/health')
            # The host health URL may recover before the backend's Docker DNS
            # cache/connection does. Retry the identical idempotent event only
            # on the documented temporary 502, with a bounded deadline.
            deadline = time.monotonic() + 35
            recovery_retries = 0
            while True:
                response = client.post(backend + '/api/integration/events', json=event)
                if response.status_code == 202:
                    break
                assert response.status_code == 502 and time.monotonic() < deadline, response.text[:300]
                recovery_retries += 1
                time.sleep(.5)
            signed = wait_status(meta['eventId'], lambda s: s['delivery'] == 'delivered')
            assert signed['status'] == 'DONE'
            initial_card = card()
            assert initial_card['currentFindings']
            passed('same_event_succeeds_after_ml_recovery')

            assert request('GET', frontend + '/api/ping')['status'] == 'ok'
            compose('stop', 'backend')
            assert client.get(frontend + '/api/ping').status_code in (502, 504)
            passed('frontend_proxy_reports_backend_outage')
            annul = dict(meta, eventId=identity + '-annul', eventType='PROTOCOL_ANNULLED')
            request('POST', ml + '/api/mis/events', 202, json=annul)
            pending = wait_status(annul['eventId'], lambda s: s['attempts'] >= 1, timeout=20)
            assert pending['delivery'] == 'pending', pending
            passed('callback_retained_when_backend_down')

            compose('up', '-d', '--no-deps', '--force-recreate', 'ml')
            healthy(ml + '/health')
            restored = request('GET', ml + '/api/mis/events/' + annul['eventId'])
            assert restored['resultId'] == pending['resultId']
            assert restored['attempts'] >= pending['attempts']
            passed('sqlite_queue_and_result_id_survive_container_recreation')

            compose('up', '-d', '--no-deps', '--force-recreate', 'backend')
            healthy(backend + '/actuator/health')
            healthy(frontend + '/api/ping')
            assert compose('ps', '-q', 'frontend') == frontend_id
            assert request('GET', frontend + '/api/ping')['status'] == 'ok'
            passed('frontend_proxy_recovers_without_frontend_restart')
            done = wait_status(annul['eventId'], lambda s: s['delivery'] == 'delivered')
            assert done['resultId'] == pending['resultId'] and done['status'] == 'ANNULLED'
            passed('automatic_delivery_after_backend_recovery')
            recovered_card = card()
            assert recovered_card['patient']['id'] == initial_card['patient']['id']
            assert recovered_card['currentProtocol']['status'] == 'ANNULLED'
            assert not recovered_card['currentFindings'] and not recovered_card['history']['protocols']
            passed('one_patient_one_protocol_no_duplicates')

            compose('up', '-d', '--force-recreate', '--wait', '--wait-timeout', '120')
            assert card() == recovered_card
            assert request('GET', ml + '/api/mis/events/' + annul['eventId']) == done
            passed('postgres_and_sqlite_survive_recreation_of_all_containers')
            report = {'checkedAt': datetime.now(timezone.utc).isoformat(), 'passed': True,
                      'checks': checks, 'attempts': done['attempts'], 'mlRecoveryRetries': recovery_retries}
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=2), encoding='utf-8')
        finally:
            compose('up', '-d', '--wait', '--wait-timeout', '120')


if __name__ == '__main__':
    main()
