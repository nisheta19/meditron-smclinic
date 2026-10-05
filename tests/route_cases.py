"""Route lifecycle checks against real HTTP + PostgreSQL, used by integration.py.

All patients/documents are fictional. Requires the isolated verification compose
with ROUTES_SIM_ENABLED=true; never run clock/scenario checks on a working DB.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4


class RouteIntegrationMixin:
    def rc(self, *args, **kwargs):
        return self.route_api['call'](*args, **kwargs)

    def route_clock(self, minutes=0):
        if minutes:
            return self.rc('POST', '/api/sim/clock/advance', json={'minutes': minutes})
        return self.rc('GET', '/api/sim/clock')

    def future(self, days=1):
        return (datetime.fromisoformat(self.route_clock()['now'].replace('Z', '+00:00'))
                + timedelta(days=days)).isoformat()

    def route_event(self, route, kind, expected=202, **fields):
        return self.rc('POST', '/api/integration/route-events', expected, json={
            'eventId': 'route-it-' + uuid4().hex, 'type': kind, 'routeId': route['id'], **fields})

    def get_route(self, route):
        return self.rc('GET', '/api/routes/' + route['id'])

    def routes_of(self, patient):
        return self.rc('GET', f'/api/patients/{patient}/routes')

    def new_route(self, label, text=None, study='PELVIS_FEMALE'):
        if text:
            a = self.route_api
            meta = a['metadata']('route-' + label, study)
            a['upload'](meta, a['make_file']('route-' + label, text))
            a['delivered'](meta)
            card = a['card'](meta)
        else:
            meta, _, card = self.positive('route-' + label)
        pid = card['patient']['id']
        self.rc('POST', f'/api/patients/{pid}/findings/confirm', json={
            'findingIds': [f['id'] for f in card['currentFindings']], 'doctor': 'Тестовый координатор'})
        routes = self.routes_of(pid)
        self.assertTrue(routes, card)
        return pid, routes[0], card

    def to_tactic(self, route):
        self.route_event(route, 'BOOKED', dateTime=self.future(), location='Тестовая клиника')
        self.route_event(route, 'VISIT_COMPLETED')
        self.assertEqual(self.get_route(route)['stage'], 'AWAITING_TACTIC')

    def test_18_route_review_gate_and_card_compatibility(self):
        a = self.route_api
        meta = a['metadata']('route-review-gate')
        file = a['make_file']('route-review-gate', 'Описание\nПолип эндометрия 8 мм. Миома матки 20 мм FIGO 1.\nЗаключение\nПолип эндометрия. Субмукозная миома матки FIGO 1.')
        a['upload'](meta, file); a['delivered'](meta)
        card = a['card'](meta); pid = card['patient']['id']; fs = card['currentFindings']
        self.assertGreaterEqual(len(fs), 2)
        self.assertEqual(self.routes_of(pid), [])
        self.rc('POST', f'/api/patients/{pid}/findings/confirm', json={'findingIds': [fs[0]['id']]})
        self.assertEqual(self.routes_of(pid), [])
        self.rc('POST', f'/api/patients/{pid}/findings/confirm', json={'findingIds': [f['id'] for f in fs[1:]]})
        rs = self.routes_of(pid)
        self.assertEqual(len(rs), 1)
        self.assertEqual(len(rs[0]['findings']), len(fs))
        card = a['card'](meta)
        self.assertEqual(card['routes'], [])  # legacy card never receives incompatible steps[] DTOs
        self.assertEqual(card['clinicalRoutes'][0]['id'], rs[0]['id'])
        self.assertEqual(card['patient']['activeRoutes'], 1)
        self.rc('GET', '/api/routes', params={'specialty': rs[0]['specialty'], 'open': 'true'})
        self.rc('GET', '/api/route-templates')
        self.rc('GET', '/api/notification-templates')
        self.rc('POST', '/api/sim/clock/advance', 400, json={'minutes': -1})

    def test_19_notifications_crm_and_concurrent_event_retries(self):
        pid, route, _ = self.new_route('notify')
        self.route_clock(2)
        messages = self.rc('GET', f'/api/routes/{route["id"]}/notifications')
        self.assertEqual(len(messages), 1)
        first = messages[0]
        self.assertEqual(first['templateCode'], 'INITIAL')
        self.assertEqual(first['patientId'], pid)
        self.assertTrue(first['patientExternalId'])
        self.assertNotIn('{', first['fullText'])
        payload = {'templateCode': 'REMINDER_24H', 'doctor': 'Тестовый врач'}
        preview = self.rc('GET', f'/api/routes/{route["id"]}/notification-preview', params={'templateCode': 'REMINDER_24H'})
        self.assertEqual(len(self.rc('GET', f'/api/routes/{route["id"]}/notifications')), len(messages))
        error = self.rc('POST', f'/api/routes/{route["id"]}/notifications', 409, json=payload)
        self.assertEqual(error['code'], 'CONFIRM_REQUIRED')
        second = self.rc('POST', f'/api/routes/{route["id"]}/notifications', 201, json=dict(payload, confirm=True))
        self.assertEqual(preview['fullText'], second['fullText'])
        self.assertTrue(second['manual'])
        callback = {'eventId': 'crm-it-' + uuid4().hex, 'messageId': first['id'], 'status': 'READ'}
        with ThreadPoolExecutor(max_workers=5) as pool:
            replies = list(pool.map(lambda _: self.rc('POST', '/api/integration/crm/callbacks', (200, 202), json=callback), range(5)))
        self.assertEqual(sum(r['applied'] for r in replies), 1)
        self.rc('POST', '/api/integration/crm/callbacks', 409, json=dict(callback, status='FAILED'))
        self.rc('POST', '/api/integration/crm/callbacks', 202, json=dict(callback, eventId=uuid4().hex, status='SENT'))
        messages = self.rc('GET', f'/api/patients/{pid}/notifications')
        self.assertEqual(next(n for n in messages if n['id'] == first['id'])['delivery'], 'READ')
        self.rc('GET', '/api/sim/crm/outbox')
        slots = self.rc('GET', '/api/schedule/slots', params={'routeId': route['id']})
        self.assertTrue(slots)
        ev = {'eventId': uuid4().hex, 'type': 'BOOKED', 'routeId': route['id'], 'slotId': slots[0]['id']}
        with ThreadPoolExecutor(max_workers=5) as pool:
            replies = list(pool.map(lambda _: self.rc('POST', '/api/integration/route-events', (200, 202), json=ev), range(5)))
        self.assertEqual(sum(r['applied'] for r in replies), 1)
        self.assertEqual(self.get_route(route)['stage'], 'BOOKED')
        self.rc('POST', '/api/integration/route-events', 409, json=dict(ev, type='NO_SHOW'))

    def test_20_no_show_cancel_and_manual_tasks(self):
        pid, route, _ = self.new_route('no-show')
        slots = self.rc('GET', '/api/schedule/slots', params={'routeId': route['id']})
        self.rc('POST', '/api/schedule/bookings', 202, json={'routeId': route['id'], 'slotId': slots[0]['id']})
        self.route_event(route, 'BOOKING_CANCELLED')
        self.assertEqual(self.get_route(route)['stage'], 'REBOOKING_REQUIRED')
        self.route_event(route, 'BOOKED', dateTime=self.future(), location='Тестовая клиника')
        self.route_event(route, 'NO_SHOW')
        self.assertEqual(self.get_route(route)['noShowCount'], 1)
        self.route_clock(31)
        self.route_clock(24 * 60 + 1)
        ns = self.rc('GET', f'/api/patients/{pid}/notifications')
        self.assertTrue(any(n['templateCode'] == 'NO_SHOW' for n in ns))
        self.rc('POST', '/api/integration/crm/callbacks', 202, json={
            'eventId': uuid4().hex, 'routeId': route['id'], 'reply': 'CALLBACK_REQUEST'})
        tasks = self.rc('GET', '/api/tasks', params={'patientId': pid, 'status': 'OPEN'})
        task = next(t for t in tasks if t['type'] == 'CALL_PATIENT')
        self.rc('POST', f'/api/tasks/{task["id"]}/done', json={'doctor': 'Тестовый врач', 'comment': 'Дозвонились'})
        self.rc('POST', f'/api/tasks/{task["id"]}/done', 409, json={})

    def test_21_all_tactics_and_closed_routes_do_not_reappear(self):
        for tactic in ['SURGERY_NOT_INDICATED', 'PATIENT_REFUSED', 'OTHER_PROFILE', 'ADDITIONAL_EXAM', 'OBSERVATION']:
            with self.subTest(tactic=tactic):
                pid, route, card = self.new_route('tactic-' + tactic)
                self.to_tactic(route)
                fields = {'tactic': tactic}
                if tactic == 'PATIENT_REFUSED':
                    self.route_event(route, 'TACTIC_SELECTED', 400, **fields)
                    fields['comment'] = 'Тестовый отказ'
                if tactic == 'OTHER_PROFILE': fields['newSpecialty'] = 'Эндокринолог'
                if tactic == 'ADDITIONAL_EXAM': fields['subtype'] = 'TESTS'
                if tactic == 'OBSERVATION': fields['controlDate'] = self.future(180)
                self.route_event(route, 'TACTIC_SELECTED', **fields)
                self.rc('PATCH', f'/api/findings/{card["currentFindings"][0]["id"]}', json={'comment': 'Повторная сверка'})
                rs = self.routes_of(pid)
                if tactic in ['SURGERY_NOT_INDICATED', 'PATIENT_REFUSED']:
                    self.assertEqual(sum(r['open'] for r in rs), 0)
                elif tactic == 'OTHER_PROFILE':
                    self.assertEqual([r['specialty'] for r in rs if r['open']], ['Эндокринолог'])
                elif tactic == 'ADDITIONAL_EXAM':
                    self.assertEqual(self.get_route(route)['stage'], 'ADDITIONAL_EXAM')
                    self.route_clock(15 * 24 * 60)
                    self.route_event(route, 'BOOKED', dateTime=self.future(), location='Тест')
                else:
                    self.assertEqual(self.get_route(route)['chainType'], 'OBSERVATION')
                    self.assertEqual(self.get_route(route)['pendingVisit'], 'ULTRASOUND')

    def test_22_surgical_path_and_hospitalization_sla(self):
        pid, route, _ = self.new_route('surgical')
        self.to_tactic(route)
        self.route_event(route, 'TACTIC_SELECTED', tactic='SURGERY_INDICATED')
        self.route_event(route, 'HOSPITALIZATION_REFERRED')
        self.route_clock(7 * 24 * 60)
        self.assertTrue(self.get_route(route)['slaOverdue'])
        tasks = self.rc('GET', '/api/tasks', params={'patientId': pid, 'status': 'OPEN'})
        self.assertTrue(any(t['type'] == 'MANAGER_ATTENTION' for t in tasks))
        self.route_event(route, 'HOSPITALIZATION_DATE_SET', 400)
        self.route_event(route, 'HOSPITALIZATION_DATE_SET', date=self.future(2)[:10], clinic='Тестовая клиника')
        self.assertEqual(self.get_route(route)['hospitalizationClinic'], 'Тестовая клиника')
        self.route_event(route, 'HOSPITALIZATION_FAILED', reason='Тестовый перенос')
        self.route_event(route, 'HOSPITALIZATION_DATE_SET', date=self.future(3)[:10])
        self.route_event(route, 'HOSPITALIZED')
        self.route_event(route, 'SURGERY_DONE')
        self.route_event(route, 'DISCHARGED', 400, controlVisitBooked=True)
        self.route_event(route, 'DISCHARGED', controlVisitBooked=True, controlDateTime=self.future(7), location='Тест')
        self.assertEqual(self.get_route(route)['stage'], 'CONTROL_PENDING')
        self.route_event(route, 'VISIT_COMPLETED')
        self.assertEqual(self.get_route(route)['stage'], 'COMPLETED')
        self.assertFalse(self.get_route(route)['open'])
        self.route_event(route, 'NO_SHOW', 409)

    def test_23_procedure_result_must_be_in_person(self):
        pid, route, _ = self.new_route('procedure',
            'Описание\nУзел правой доли щитовидной железы 21 мм TI-RADS 4.\nЗаключение\nУзел правой доли TI-RADS 4.', 'THYROID')
        self.to_tactic(route)
        self.route_event(route, 'TACTIC_SELECTED', tactic='ADDITIONAL_EXAM', subtype='PROCEDURE')
        self.route_event(route, 'PROCEDURE_DONE')
        self.assertEqual(self.get_route(route)['pendingVisit'], 'RESULT')
        slots = self.rc('GET', '/api/schedule/slots', params={'routeId': route['id']})
        self.assertTrue(slots)
        self.assertFalse(any(s['online'] for s in slots))
        self.route_event(route, 'BOOKED', 400, dateTime=self.future(), online=True)
        self.rc('POST', '/api/schedule/bookings', 202, json={'routeId': route['id'], 'slotId': slots[0]['id']})
        self.route_event(route, 'VISIT_COMPLETED')
        self.assertEqual(self.get_route(route)['stage'], 'AWAITING_TACTIC')

    def test_24_manual_emergency_and_full_ladder_catchup(self):
        pid, route, _ = self.new_route('emergency')
        f = self.rc('POST', f'/api/patients/{pid}/findings', 201,
                    json={'code': 'UTERINE_FIBROID', 'attributes': {'prolapsing': True}, 'doctor': 'Тестовый врач'})
        self.assertEqual(f['level'], 'EMERGENCY')
        es = self.rc('GET', '/api/escalations', params={'patientId': pid, 'open': 'true'})
        self.assertEqual(len(es), 1)
        eid = es[0]['id']
        self.assertEqual(es[0]['step'], 'AWAITING_ACCEPT')
        self.route_clock(21)
        es = self.rc('GET', '/api/escalations', params={'patientId': pid})
        self.assertEqual(es[0]['currentRole'], 'HEAD_OF_DEPARTMENT')
        self.assertEqual(self.rc('GET', f'/api/patients/{pid}/notifications'), [])
        self.rc('POST', f'/api/routes/{route["id"]}/notifications', 409, json={'templateCode': 'INITIAL', 'confirm': True})
        self.rc('POST', f'/api/escalations/{eid}/accept', json={'role': 'HEAD_OF_DEPARTMENT', 'doctor': 'Тестовый врач'})
        self.route_clock(61)
        tasks = self.rc('GET', '/api/tasks', params={'patientId': pid})
        self.assertTrue(any(t['type'] == 'EMERGENCY_CONTACT_OVERDUE' for t in tasks))
        self.rc('POST', f'/api/escalations/{eid}/contacted', json={'doctor': 'Тестовый врач'})
        self.rc('POST', f'/api/escalations/{eid}/close', 400, json={'outcome': 'PATIENT_REFUSED'})
        self.rc('POST', f'/api/escalations/{eid}/close', json={'outcome': 'PATIENT_REFUSED', 'comment': 'Тестовый отказ'})
        self.rc('PATCH', f'/api/findings/{f["id"]}', json={'comment': 'Проверка повторной сверки'})
        self.assertEqual(self.rc('GET', '/api/escalations', params={'patientId': pid, 'open': 'true'}), [])

    def test_25_recalculate_after_rejection_and_annulment(self):
        pid, route, card = self.new_route('reconcile')
        # A separate pair with the same surgeon, from two manual findings.
        planned = self.rc('POST', f'/api/patients/{pid}/findings', 201, json={'code': 'GALLSTONES', 'attributes': {}})
        urgent = self.rc('POST', f'/api/patients/{pid}/findings', 201, json={'code': 'SOFT_TISSUE_INFLAMMATION', 'attributes': {}})
        surgeon = next(r for r in self.routes_of(pid) if r['specialty'] == 'Хирург')
        self.assertEqual(surgeon['chainType'], 'URGENT')
        self.rc('PATCH', f'/api/findings/{urgent["id"]}', json={'status': 'REJECTED'})
        surgeon = self.get_route(surgeon)
        self.assertEqual(surgeon['chainType'], 'NEAR')
        self.assertEqual([f['id'] for f in surgeon['findings']], [planned['id']])
        self.rc('DELETE', f'/api/findings/{planned["id"]}', 204)
        self.assertFalse(self.get_route(surgeon)['open'])
        self.rc('PATCH', f'/api/findings/{card["currentFindings"][0]["id"]}', json={'status': 'REJECTED'})
        self.assertFalse(self.get_route(route)['open'])

    def test_26_templates_journal_dashboard_and_bad_inputs(self):
        for suffix in ['funnel', 'losses', 'escalations']:
            self.rc('GET', '/api/dashboard/' + suffix)
        self.rc('GET', '/api/dashboard/patients', params={'step': 'CREATED'})
        self.rc('GET', '/api/dashboard/patients', 400, params={'step': 'unknown'})
        pid, route, _ = self.new_route('validation')
        self.rc('GET', f'/api/patients/{pid}/journal')
        self.rc('GET', '/api/journal', params={'patientId': pid, 'limit': 3})
        self.rc('GET', '/api/journal', 400, params={'limit': -1})
        self.rc('GET', '/api/routes/bad-id', 404)
        self.rc('GET', '/api/patients/bad-id/routes', 404)
        self.route_event(route, 'BOOKED', 400, dateTime=self.future(), patientExternalId='wrong-patient')
        self.route_event(route, 'BOOKED', 400, dateTime='2000-01-01T00:00:00Z')
        self.route_event(route, 'BOGUS', 400)
        self.rc('POST', f'/api/routes/{route["id"]}/notifications', 400, json={'templateCode': 'not-a-template'})
        self.rc('POST', '/api/integration/crm/callbacks', 404, json={'eventId': uuid4().hex, 'messageId': 'bad-id', 'status': 'READ'})
        a = self.route_api
        import httpx
        with httpx.Client(timeout=20, trust_env=False) as client:
            for path in ['/api/routes', '/api/tasks', '/api/escalations', '/api/sim/clock']:
                self.assertEqual(client.get(a['ARGS'].backend + path).status_code, 401)
            headers = dict(a['CLIENT'].headers)
            headers.pop('x-csrf-token', None)
            response = client.post(a['ARGS'].backend + f'/api/routes/{route["id"]}/notifications',
                cookies=a['CLIENT'].cookies, json={'templateCode': 'INITIAL'})
            self.assertEqual(response.status_code, 403)

    def test_27_observation_new_protocol(self):
        a = self.route_api
        pid, route, card = self.new_route('observation',
            'Описание\nИнтрамуральная миома матки FIGO 4 размером 15 мм.\nЗаключение\nМиома матки FIGO 4.', 'PELVIS_FEMALE')
        self.assertEqual(route['chainType'], 'OBSERVATION')
        self.route_clock(2)
        self.assertIn('6 месяцев', self.rc('GET', f'/api/routes/{route["id"]}/notifications')[0]['fullText'])
        meta = a['metadata']('new-control')
        meta['patient']['externalId'] = card['patient']['externalId']
        file = a['make_file']('new-control', 'Описание\nМатка без очаговых образований.\nЗаключение\nПатологии не выявлено.')
        a['upload'](meta, file); a['delivered'](meta)
        self.assertEqual(self.get_route(route)['stage'], 'OBSERVATION_WAITING_VISIT')
        self.assertEqual(self.get_route(route)['pendingVisit'], 'CONSULTATION')

    def test_28_all_bundled_scenarios(self):
        scenarios = self.rc('GET', '/api/sim/scenarios')
        self.assertEqual(len(scenarios), 5)
        for scenario in scenarios:
            with self.subTest(scenario=scenario['code']):
                run = self.rc('POST', f'/api/sim/scenarios/{scenario["code"]}/start', json={'manual': True})
                for _ in range(run['totalSteps']):
                    run = self.rc('POST', f'/api/sim/scenarios/{run["runId"]}/next')
                    self.assertIsNone(run['error'], run)
                run = self.rc('GET', f'/api/sim/scenarios/runs/{run["runId"]}')
                self.assertTrue(run['finished'])
                self.assertEqual(run['step'], run['totalSteps'])
        self.rc('POST', '/api/sim/clock/reset')

    def test_29_confirmed_route_closes_on_protocol_correction_and_annulment(self):
        a = self.route_api
        meta, file, card = self.positive('route-version-lifecycle')
        pid = card['patient']['id']
        self.rc('POST', f'/api/patients/{pid}/findings/confirm', json={'findingIds': [f['id'] for f in card['currentFindings']]})
        old, = self.routes_of(pid)
        meta['eventId'] += '-corrected'; meta['eventType'] = 'PROTOCOL_CORRECTED'; meta['protocol']['version'] = 2
        a['upload'](meta, file); a['delivered'](meta)
        self.assertEqual(self.get_route(old)['closeReason'], 'PROTOCOL_CORRECTED')
        c = a['card'](meta)
        self.rc('POST', f'/api/patients/{pid}/findings/confirm', json={'findingIds': [f['id'] for f in c['currentFindings']]})
        current = next(r for r in self.routes_of(pid) if r['open'])
        meta['eventId'] += '-annulled'; meta['eventType'] = 'PROTOCOL_ANNULLED'
        self.rc('POST', '/api/integration/events', 202, json=meta); a['delivered'](meta, 'ANNULLED')
        self.assertEqual(self.get_route(current)['closeReason'], 'PROTOCOL_ANNULLED')
        self.assertEqual(sum(r['open'] for r in self.routes_of(pid)), 0)

    def test_30_other_emergency_outcomes_and_callbacks(self):
        for outcome in ['HOSPITALIZED', 'AMBULANCE', 'COMING_TODAY', 'FINDING_NOT_CONFIRMED']:
            with self.subTest(outcome=outcome):
                pid, ordinary, _ = self.new_route('outcome-' + outcome)
                self.rc('POST', f'/api/patients/{pid}/findings', 201,
                        json={'code': 'UTERINE_FIBROID', 'attributes': {'prolapsing': True}})
                e, = self.rc('GET', '/api/escalations', params={'patientId': pid, 'open': 'true'})
                self.rc('POST', f'/api/escalations/{e["id"]}/close', 409, json={'outcome': outcome})
                self.rc('POST', f'/api/escalations/{e["id"]}/accept', json={'role': 'DUTY_DOCTOR'})
                self.rc('POST', f'/api/escalations/{e["id"]}/contacted', json={})
                e = self.rc('POST', f'/api/escalations/{e["id"]}/close', json={'outcome': outcome, 'comment': 'Тестовый исход'})
                route = self.rc('GET', '/api/routes/' + e['routeId'])
                expected = {'HOSPITALIZED': 'HOSPITALIZED', 'AMBULANCE': 'CONTROL_PENDING',
                            'COMING_TODAY': 'BOOKED', 'FINDING_NOT_CONFIRMED': 'CLOSED'}
                self.assertEqual(route['stage'], expected[outcome])
                if outcome == 'AMBULANCE':
                    self.route_clock(7 * 24 * 60 + 1)
                    tasks = self.rc('GET', '/api/tasks', params={'patientId': pid, 'status': 'OPEN'})
                    self.assertTrue(any(t['routeId'] == route['id'] and t['type'] == 'CALL_PATIENT' for t in tasks))
        for reply in ['OTHER_ORGANIZATION', 'NOT_PLANNING']:
            pid, route, _ = self.new_route('reply-' + reply)
            self.rc('POST', '/api/integration/crm/callbacks', 202, json={'eventId': uuid4().hex, 'routeId': route['id'], 'reply': reply})
            self.assertFalse(self.get_route(route)['open'])
            self.rc('POST', '/api/integration/crm/callbacks', 409, json={'eventId': uuid4().hex, 'routeId': route['id'], 'reply': 'CALLBACK_REQUEST'})
        self.rc('POST', '/api/sim/clock/reset')

    def test_31_patient_daily_limit_across_routes(self):
        pid, route, _ = self.new_route('shared-limit')
        self.rc('POST', f'/api/patients/{pid}/findings', 201, json={'code': 'GALLSTONES', 'attributes': {}})
        self.assertEqual(sum(r['open'] for r in self.routes_of(pid)), 2)
        self.route_clock(2)
        self.assertEqual(len(self.rc('GET', f'/api/patients/{pid}/notifications')), 1)
        self.route_clock(24 * 60 + 2)
        messages = self.rc('GET', f'/api/patients/{pid}/notifications')
        self.assertEqual(len(messages), 2)
        self.assertEqual(len({m['routeId'] for m in messages}), 2)
        self.assertTrue(all(r['stage'] == 'NOTIFIED' for r in self.routes_of(pid)))
        times = sorted(datetime.fromisoformat(m['sentAt'].replace('Z', '+00:00')) for m in messages)
        self.assertGreaterEqual((times[1] - times[0]).total_seconds(), 86400)
        self.rc('POST', '/api/sim/clock/reset')
