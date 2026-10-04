"""Self-contained MIS → ML → backend stub demo using synthetic DOCX only."""
import argparse
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import sys
from pathlib import Path
import tempfile
import threading
import time
import socket
from urllib.request import Request, urlopen
from xml.sax.saxutils import escape
from zipfile import ZipFile

from .backend import BackendClient
from .contracts import ContractError, validate_result
from .dictionary import DEFAULT_DICTIONARY, load_dictionary
from .corpus import write_json
from .mis import build_event
from .service import MLService

DICTIONARY = [{"code": "ENDOMETRIAL_POLYP", "name": "Полип эндометрия",
               "synonyms": ["полипа эндометрия"], "studyTypes": ["PELVIS_FEMALE"]}]


def docx(path, lines):
    # A real minimal Word package, not a renamed text file.
    with ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        z.writestr("_rels/.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        z.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>' + "".join('<w:p><w:r><w:t>' + escape(line) + '</w:t></w:r></w:p>' for line in lines) + '</w:body></w:document>')


def run_demo():
    # Validate dependencies before starting HTTP threads. Otherwise a missing
    # YAML loader becomes a FAILED result and an unrelated assertion later.
    load_dictionary(DEFAULT_DICTIONARY)
    from .asgi import create_app
    import uvicorn
    received = {}
    lock = threading.Lock()

    class Stub(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if self.path not in {"/api/dictionary/findings","/api/dictionary/findings?full=true"}:
                self.send_error(404)
                return
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps(DICTIONARY).encode())

        def do_POST(self):
            if self.path != "/api/integration/ml/results":
                self.send_error(404)
                return
            result = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            try:
                validate_result(result)
            except ValueError:
                self.send_error(400)
                return
            with lock:
                old = received.get(result["resultId"])
                if old is not None and old != result:
                    self.send_error(409)
                    return
                received[result["resultId"]] = result
            self.send_response(202)
            self.end_headers()

    backend = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
    backend_thread = threading.Thread(target=backend.serve_forever, daemon=True)
    backend_thread.start()
    try:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            client = BackendClient(f"http://127.0.0.1:{backend.server_port}")
            service = MLService(root / "events.sqlite3", client, client.dictionary)
            listener=socket.socket()
            listener.bind(('127.0.0.1',0))
            port=listener.getsockname()[1]
            ml=uvicorn.Server(uvicorn.Config(create_app(service),access_log=False,log_level='error'))
            ml_thread = threading.Thread(target=ml.run,kwargs={'sockets':[listener]}, daemon=True)
            ml_thread.start()
            try:
                deadline=time.monotonic()+10
                while not ml.started and ml_thread.is_alive() and time.monotonic()<deadline:time.sleep(.01)
                if not ml.started:raise AssertionError('FastAPI server did not start')
                base = f"http://127.0.0.1:{port}"
                meta = {"patient": {"externalId": "demo-patient-001", "fullName": "Пациент 001", "birthDate": "1999-03-15", "sex": "F"},
                        "protocol": {"externalId": "demo-protocol-001", "version": 1, "studyType": "PELVIS_FEMALE", "studyDate": "2026-09-07"}}
                report = []
                for i, kind in enumerate(("PROTOCOL_SIGNED", "PROTOCOL_CORRECTED", "PROTOCOL_ANNULLED"), 1):
                    event = deepcopy(meta)
                    event.update(eventId=f"demo-event-{i}", eventType=kind)
                    event["protocol"]["version"] = min(i, 2)
                    file = root / "synthetic.docx"
                    docx(file, ["Описание", "Полип эндометрия 8 мм." if i == 1 else "Полип эндометрия не выявлен.", "Заключение", "Контрольный синтетический протокол."])
                    event = build_event(event, file if i < 3 else None)
                    request = Request(base + "/api/mis/events", data=json.dumps(event).encode(), headers={"Content-Type": "application/json"})
                    # Re-send each event to test event-level idempotency too.
                    for _ in range(2):
                        with urlopen(request, timeout=10) as response:
                            if response.status != 202:
                                raise AssertionError("ML did not accept event")
                    deadline = time.monotonic() + 10
                    while time.monotonic() < deadline:
                        with urlopen(base + "/api/mis/events/" + event["eventId"], timeout=5) as response:
                            status = json.load(response)
                        if status["delivery"] == "delivered":
                            break
                        time.sleep(.05)
                    else:
                        raise AssertionError("Delivery timeout")
                    with lock:
                        result = deepcopy(received[status["resultId"]])
                    expected_status = "ANNULLED" if i == 3 else "DONE"
                    if result["status"] != expected_status or len(result.get("findings", [])) != (1 if i == 1 else 0):
                        raise AssertionError("Unexpected extraction/lifecycle result")
                    if result["patient"] != event["patient"] or result["protocol"] != event["protocol"]:
                        raise AssertionError("Metadata changed")
                    report.append({"eventType": kind, "delivery": status["delivery"], "result": result})
                if len(received) != 3:
                    raise AssertionError("Duplicate results created")
                return {"passed": True, "syntheticDataOnly": True, "mlServer":"FastAPI+uvicorn", "backend": "local_http_stub",
                        "frontendTested": False, "uniqueResults": len(received), "events": report}
            finally:
                ml.should_exit=True
                ml_thread.join(timeout=15)
                listener.close()
                service.close()
    finally:
        backend.shutdown()
        backend.server_close()
        backend_thread.join()


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--output", default=".local/demo.json")
    path = Path(cli.parse_args().output)
    try:
        result = run_demo()
    except ContractError as exc:
        print(f"Не удалось запустить демо: {exc}", file=sys.stderr)
        return 2
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, result)
    print(json.dumps({"passed": result["passed"], "uniqueResults": result["uniqueResults"], "report": str(path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
