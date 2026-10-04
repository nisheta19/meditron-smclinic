"""MIS → ML → backend over real loopback HTTP, using synthetic documents only."""

import base64
from collections import deque
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
import subprocess
import sys
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app.backend import BackendClient, DeliveryError
from app.contracts import ContractError, validate_event, validate_result
from app.mis import build_event
from app.processing import process_event
from app.server import make_server
from app.service import EventConflict, MLService
from test_parser import paragraph, write_docx

DICTIONARY = [
    {"code": "ENDOMETRIAL_POLYP", "name": "Полип эндометрия", "synonyms": ["полипа эндометрия"],
     "studyTypes": ["PELVIS_FEMALE"]},
    {"code": "UTERINE_FIBROID", "name": "Миома матки", "synonyms": [], "studyTypes": ["PELVIS_FEMALE"]},
]


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "input.docx"
        self.database = Path(self.tmp.name) / "events.sqlite3"
        self.received = []
        self.statuses = deque()
        self.dictionary = deepcopy(DICTIONARY)
        owner = self

        class Backend(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                if self.path not in {"/api/dictionary/findings","/api/dictionary/findings?full=true"}:
                    self.send_error(404)
                    return
                data = json.dumps(owner.dictionary).encode()
                self.send_response(200)
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                if self.path != "/api/integration/ml/results":
                    self.send_error(404)
                    return
                owner.received.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                self.send_response(owner.statuses.popleft() if owner.statuses else 202)
                self.end_headers()

        self.backend_server = ThreadingHTTPServer(("127.0.0.1", 0), Backend)
        self.backend_thread = threading.Thread(target=self.backend_server.serve_forever, daemon=True)
        self.backend_thread.start()
        self.backend = BackendClient(f"http://127.0.0.1:{self.backend_server.server_port}", timeout=1)
        self.service = MLService(self.database, self.backend, self.backend.dictionary)

    def tearDown(self):
        self.service.close()
        self.backend_server.shutdown()
        self.backend_server.server_close()
        self.backend_thread.join()
        self.tmp.cleanup()

    def event(self, text="Описание\nПолип эндометрия.\nЗаключение\nМиома матки не выявлена."):
        write_docx(self.path, "".join(paragraph(line) for line in text.splitlines()))
        return build_event({
            "eventId": "synthetic-event-1", "eventType": "PROTOCOL_SIGNED",
            "patient": {"externalId": "patient-1", "fullName": "Пациент 001", "birthDate": "1999-03-15", "sex": "F"},
            "protocol": {"externalId": "protocol-1", "version": 1, "studyType": "PELVIS_FEMALE", "studyDate": "2026-09-07"},
        }, self.path)

    def test_done_passes_metadata_and_exact_quote_offsets(self):
        event = self.event()
        event["patient"]["extra"] = "preserved"
        result = self.service.accept(event)
        self.assertEqual(result["patient"], event["patient"])
        self.assertEqual(result["protocol"], event["protocol"])
        self.assertEqual(result["status"], "DONE")
        self.assertEqual(result["conclusion"], "Миома матки не выявлена.")
        self.assertEqual([f["code"] for f in result["findings"]], ["ENDOMETRIAL_POLYP"])
        self.assertEqual(result["notTriggered"][0]["reason"], "NEGATION")
        evidence = result["findings"][0]["evidence"]
        self.assertEqual(result["text"][evidence["start"]:evidence["end"]], evidence["text"])
        self.assertNotIn("\n", result["text"])
        self.assertNotIn("doctor_first_name", result)
        validate_result(result)

    def test_normal_no_matches_and_no_conclusion(self):
        result = self.service.accept(self.event("Описание\nОчаговых изменений не выявлено."))
        self.assertEqual(result["status"], "DONE")
        self.assertEqual(result["findings"], [])
        self.assertEqual(result["conclusion"], "")
        self.assertFalse(result["conclusionFound"])
        validate_result(result)

    def test_unreadable_and_bad_base64_produce_failed_messages(self):
        for content in ("!!!!", base64.b64encode(b"not docx").decode()):
            event = self.event()
            event["contentBase64"] = content
            result = process_event(event, lambda: DICTIONARY)
            self.assertEqual(result["status"], "FAILED")
            self.assertEqual(result["error"]["code"], "UNREADABLE_FILE")
            validate_result(result)

    def test_pdf_is_explicitly_unsupported(self):
        event = self.event()
        event["fileName"] = "scan.pdf"
        result = process_event(event, lambda: DICTIONARY)
        self.assertEqual(result["error"]["code"], "UNSUPPORTED_FORMAT")
        validate_result(result)

    def test_missing_or_wrong_study_dictionary_is_not_normal(self):
        for dictionary in ([], {"wrong": "shape"}, [dict(DICTIONARY[0], studyTypes=["THYROID"])]):
            result = process_event(self.event(), lambda: dictionary)
            self.assertEqual(result["status"], "FAILED")
            self.assertNotIn("findings", result)
            validate_result(result)

    def test_signed_corrected_annulled_and_duplicate(self):
        first = self.event()
        r1 = self.service.accept(first)
        corrected = deepcopy(first)
        corrected.update(eventId="synthetic-event-2", eventType="PROTOCOL_CORRECTED")
        corrected["protocol"]["version"] = 2
        r2 = self.service.accept(corrected)
        annulled = deepcopy(corrected)
        annulled.update(eventId="synthetic-event-3", eventType="PROTOCOL_ANNULLED")
        del annulled["fileName"], annulled["contentBase64"]
        r3 = self.service.accept(annulled)
        self.assertEqual(r3["status"], "ANNULLED")
        self.assertNotIn("findings", r3)
        self.assertNotIn("text", r3)
        self.assertEqual(len({r["resultId"] for r in [r1, r2, r3]}), 3)
        # Reopen the journal: same event returns the byte-equivalent saved payload.
        reopened = MLService(self.database, self.backend, lambda: [])
        self.assertEqual(reopened.accept(first), r1)
        for _ in range(3):
            self.assertTrue(self.service.deliver_one())
        self.assertFalse(self.service.deliver_one())
        self.assertEqual([r["status"] for r in self.received], ["DONE", "DONE", "ANNULLED"])
        self.assertEqual(self.service.status(first["eventId"])["delivery"], "delivered")

    def test_event_conflicts_and_old_versions(self):
        event = self.event()
        self.service.accept(event)
        conflict = deepcopy(event)
        conflict["patient"]["fullName"] = "Другой пациент"
        with self.assertRaises(EventConflict):
            self.service.accept(conflict)
        event.update(eventId="event-2", eventType="PROTOCOL_CORRECTED")
        with self.assertRaises(EventConflict):
            self.service.accept(event)

    def test_retries_same_payload_at_5_30_120_and_exhaustion(self):
        self.statuses.extend([500, 503, 500, 500])
        event = self.event()
        result = self.service.accept(event)
        self.assertTrue(self.service.deliver_one(now=0))
        self.assertFalse(self.service.deliver_one(now=4))
        self.assertTrue(self.service.deliver_one(now=5))
        self.assertFalse(self.service.deliver_one(now=34))
        self.assertTrue(self.service.deliver_one(now=35))
        self.assertFalse(self.service.deliver_one(now=154))
        self.assertTrue(self.service.deliver_one(now=155))
        self.assertEqual(self.service.status(event["eventId"])["delivery"], "exhausted")
        self.assertEqual(self.received, [result] * 4)
        self.service.retry(event["eventId"])
        self.service.deliver_one()
        self.assertEqual(self.received[-1], result)
        self.assertEqual(self.service.status(event["eventId"])["delivery"], "delivered")

    def test_400_no_retry_and_blocks_later_version(self):
        event = self.event()
        self.service.accept(event)
        event2 = deepcopy(event)
        event2.update(eventId="evt2", eventType="PROTOCOL_CORRECTED")
        event2["protocol"]["version"] = 2
        self.service.accept(event2)
        self.statuses.append(400)
        self.service.deliver_one()
        self.assertEqual(self.service.status(event["eventId"])["delivery"], "rejected")
        self.assertFalse(self.service.deliver_one())
        self.assertEqual(len(self.received), 1)

    def test_sync_retry_client_and_network_failure(self):
        result = self.service.accept(self.event())
        self.statuses.extend([500, 503, 500, 202])
        delays = []
        self.backend.send(result, sleep=delays.append)
        self.assertEqual(delays, [5, 30, 120])
        self.assertEqual(self.received, [result] * 4)
        # Closed ephemeral listener is a deterministic network error.
        unused = ThreadingHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
        port = unused.server_port
        unused.server_close()
        with self.assertRaises(DeliveryError) as error:
            BackendClient(f"http://127.0.0.1:{port}", timeout=0.1).send_once(result)
        self.assertTrue(error.exception.retryable)

    def test_new_dictionary_entry_loaded_without_code_changes(self):
        self.dictionary.append({"code": "DEMO_NEW_FINDING", "name": "Тестовая находка", "synonyms": [],
                                "studyTypes": ["PELVIS_FEMALE"]})
        result = self.service.accept(self.event("Описание\nТестовая находка."))
        self.assertEqual(result["findings"][0]["code"], "DEMO_NEW_FINDING")

    def test_uncertainty_is_not_negation(self):
        result = self.service.accept(self.event("Описание\nНельзя исключить полип эндометрия."))
        self.assertTrue(result["findings"][0]["attributes"]["uncertain"])
        self.assertEqual(result["notTriggered"], [])

    def test_contract_rejects_bad_inputs_and_bad_offsets(self):
        event = self.event()
        for field, value in [("eventType", []), ("patient", None), ("protocol", {})]:
            broken = dict(event, **{field: value})
            with self.assertRaises(ContractError):
                validate_event(broken)
        for key, value in [("version", True), ("studyDate", "2026-02-30"), ("studyType", [])]:
            broken = deepcopy(event)
            broken["protocol"][key] = value
            with self.assertRaises(ContractError):
                validate_event(broken)
        result = self.service.accept(event)
        result["findings"][0]["evidence"]["start"] += 1
        with self.assertRaises(ContractError):
            validate_result(result)

    def test_http_mis_to_ml_to_backend_and_status(self):
        server = make_server("127.0.0.1", 0, self.service)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            event = self.event()
            request = Request(base + "/api/mis/events", data=json.dumps(event).encode(),
                              headers={"Content-Type": "application/json"})
            with urlopen(request) as response:
                self.assertEqual(response.status, 202)
                self.assertEqual(json.load(response)["delivery"], "pending")
            self.service.deliver_one()
            with urlopen(base + "/api/mis/events/" + event["eventId"]) as response:
                self.assertEqual(json.load(response)["delivery"], "delivered")
            self.assertEqual(len(self.received), 1)
            validate_result(self.received[0])
            with urlopen(request) as response:
                self.assertEqual(json.load(response)["delivery"], "delivered")
            bad = Request(base + "/api/mis/events", data=b'{}', headers={"Content-Type": "application/json"})
            with self.assertRaises(HTTPError) as error:
                urlopen(bad)
            self.assertEqual(error.exception.code, 400)
            error.exception.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_cli_emulator_process_and_stage_one_sender(self):
        metadata = self.event()
        del metadata["fileName"], metadata["contentBase64"]
        metadata_path = Path(self.tmp.name) / "metadata.json"
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
        cli = subprocess.run([sys.executable, "-m", "app", "mis-event", str(metadata_path),
                              "--file", str(self.path)], capture_output=True, check=True)
        event_path = Path(self.tmp.name) / "event.json"
        event_path.write_bytes(cli.stdout)
        cli = subprocess.run([sys.executable, "-m", "app", "process", str(event_path),
                              "--database", str(self.database), "--backend-url", self.backend.base_url],
                             capture_output=True, check=True)
        result = json.loads(cli.stdout.decode("utf-8"))
        validate_result(result)
        self.assertEqual(result["status"], "DONE")
        result_path = Path(self.tmp.name) / "result.json"
        result_path.write_bytes(cli.stdout)
        cli = subprocess.run([sys.executable, "-m", "app", "send-result", str(result_path),
                              "--backend-url", self.backend.base_url], capture_output=True, check=True)
        self.assertEqual(json.loads(cli.stdout.decode("utf-8"))["delivery"], "delivered")
        self.assertEqual(self.received, [result])

    def test_background_worker_automatically_delivers(self):
        event = self.event()
        self.service.accept(event)
        self.service.start_worker()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if self.service.status(event["eventId"])["delivery"] == "delivered":
                break
            threading.Event().wait(0.02)
        self.assertEqual(self.service.status(event["eventId"])["delivery"], "delivered")
        self.assertEqual(len(self.received), 1)
