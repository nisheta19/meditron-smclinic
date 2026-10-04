import json
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import unittest
from app.backend import BackendClient,DeliveryError
from app.dictionary import DEFAULT_DICTIONARY,load_dictionary
from app.demo import docx
from app.mis import build_event
from app.service import MLService
from app.release import validate_for_dictionary


class ApprovedTransportTests(unittest.TestCase):
    def test_400_reports_backend_field_without_retry(self):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                self.send_response(400);self.end_headers()
                self.wfile.write(b'{"field":"patient.birthDate","message":"invalid date"}')
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            result=json.loads((Path(__file__).resolve().parent.parent/'examples/result-positive.json').read_text(encoding='utf-8'))
            with self.assertRaises(DeliveryError) as ctx:
                BackendClient(f'http://127.0.0.1:{server.server_port}').send_once(result)
            self.assertFalse(ctx.exception.retryable)
            self.assertIn('patient.birthDate',str(ctx.exception))
        finally:server.shutdown();server.server_close();thread.join()

    def test_real_http_approved_dictionary_and_result(self):
        dictionary=load_dictionary(DEFAULT_DICTIONARY)
        received=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                self.send_response(200);self.end_headers();self.wfile.write(json.dumps(dictionary).encode())
            def do_POST(self):
                r=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                validate_for_dictionary(r,dictionary)
                received.append(r)
                self.send_response(202);self.end_headers()
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);path=root/'protocol.docx'
                docx(path,['Описание','Молочные железы.','Заключение','BI-RADS 1 справа. BI-RADS 1 слева.'])
                backend=BackendClient(f'http://127.0.0.1:{server.server_port}')
                service=MLService(root/'state.sqlite3',backend,backend.dictionary)
                event=build_event({'eventId':'approved-1','eventType':'PROTOCOL_SIGNED',
                    'patient':{'externalId':'demo-1','fullName':'Пациент 001','birthDate':'2000-01-01','sex':'F'},
                    'protocol':{'externalId':'proto-1','version':1,'studyType':'BREAST','studyDate':'2026-09-07'}},path)
                try:
                    result=service.accept(event)
                    self.assertEqual(result['status'],'DONE')
                    self.assertEqual(result['findings'],[])
                    self.assertEqual(len([x for x in result['notTriggered'] if x['reason']=='NORMAL']),2)
                    service.deliver_one()
                    self.assertEqual(received,[result])
                    self.assertEqual(service.accept(event),result)
                    service.deliver_one()
                    self.assertEqual(len(received),1)
                finally:service.close()
        finally:
            server.shutdown();server.server_close();thread.join()
