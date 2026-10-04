"""Local event journal and persistent delivery queue for the demo service."""

import hashlib
import json
from pathlib import Path
import sqlite3
import threading
import time
import logging
from contextlib import contextmanager

from .backend import DeliveryError, RETRY_DELAYS
from .contracts import ContractError, validate_event, validate_result
from .processing import process_event

logger=logging.getLogger('meditron.ml')


class EventConflict(ContractError):
    pass


class MLService:
    def __init__(self, database, backend, dictionary_provider):
        Path(database).parent.mkdir(parents=True, exist_ok=True)
        self.database = str(database)
        self.backend = backend
        self.dictionary_provider = dictionary_provider
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.worker = None
        self.worker_error = None
        with self.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL,
                protocol_id TEXT NOT NULL, patient_id TEXT NOT NULL, version INTEGER NOT NULL,
                event_type TEXT NOT NULL, result TEXT NOT NULL,
                delivery TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
                due REAL NOT NULL DEFAULT 0, error TEXT)''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def accept(self, event):
        validate_event(event)
        fingerprint = hashlib.sha256(json.dumps(event, ensure_ascii=False, sort_keys=True,
                                                allow_nan=False).encode("utf-8")).hexdigest()
        with self.lock, self.connect() as db:
            previous = db.execute("SELECT * FROM events WHERE event_id=?", (event["eventId"],)).fetchone()
            if previous:
                if previous["fingerprint"] != fingerprint:
                    raise EventConflict("eventId уже использован для другого содержимого")
                return json.loads(previous["result"])
            protocol, patient = event["protocol"], event["patient"]
            last = db.execute("SELECT * FROM events WHERE protocol_id=? ORDER BY rowid DESC LIMIT 1",
                              (protocol["externalId"],)).fetchone()
            if last:
                if last["patient_id"] != patient["externalId"]:
                    raise EventConflict("Протокол уже связан с другим пациентом")
                minimum = last["version"] + (event["eventType"] != "PROTOCOL_ANNULLED")
                if protocol["version"] < minimum:
                    raise EventConflict("Исправление требует новой версии; старая версия недопустима")
            start=time.perf_counter()
            result = process_event(event, self.dictionary_provider)
            validate_result(result)
            db.execute('''INSERT INTO events
                (event_id, fingerprint, protocol_id, patient_id, version, event_type, result)
                VALUES (?, ?, ?, ?, ?, ?, ?)''',
                (event["eventId"], fingerprint, protocol["externalId"], patient["externalId"],
                 protocol["version"], event["eventType"], json.dumps(result, ensure_ascii=False)))
            logger.info(json.dumps({'event':'processed','resultId':result['resultId'],
                'protocolId':protocol['externalId'],'version':protocol['version'],'status':result['status'],
                'codes':[f['code'] for f in result.get('findings',[])],'seconds':round(time.perf_counter()-start,4)},ensure_ascii=False))
            return result

    def status(self, event_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM events WHERE event_id=?", (event_id,)).fetchone()
            if not row:
                return None
            result = json.loads(row["result"])
            return {"eventId": event_id, "resultId": result["resultId"], "status": result["status"],
                    "delivery": row["delivery"], "attempts": row["attempts"], "deliveryError": row["error"]}

    def retry(self, event_id):
        with self.lock, self.connect() as db:
            db.execute("UPDATE events SET delivery='pending', attempts=0, due=0, error=NULL "
                       "WHERE event_id=? AND delivery IN ('exhausted', 'rejected')", (event_id,))
        return self.status(event_id)

    def deliver_one(self, now=None):
        now = time.time() if now is None else now
        with self.lock, self.connect() as db:
            # Preserve protocol event order even while an earlier result retries.
            row = db.execute('''SELECT e.* FROM events e WHERE e.delivery='pending' AND e.due<=?
                AND NOT EXISTS (SELECT 1 FROM events older WHERE older.protocol_id=e.protocol_id
                    AND older.rowid<e.rowid AND older.delivery!='delivered')
                ORDER BY e.rowid LIMIT 1''', (now,)).fetchone()
            if not row:
                return False
            attempts = row["attempts"] + 1
            delivery, due, error = "delivered", 0, None
            backend_status=202
            try:
                self.backend.send_once(json.loads(row["result"]))
            except DeliveryError as exc:
                backend_status=exc.status_code
                error = str(exc)
                if not exc.retryable:
                    delivery = "rejected"
                elif attempts <= len(RETRY_DELAYS):
                    delivery, due = "pending", now + RETRY_DELAYS[attempts - 1]
                else:
                    delivery = "exhausted"
            db.execute("UPDATE events SET delivery=?, attempts=?, due=?, error=? WHERE event_id=?",
                       (delivery, attempts, due, error, row["event_id"]))
            logger.info(json.dumps({'event':'delivery','resultId':json.loads(row['result'])['resultId'],
                'attempt':attempts,'delivery':delivery,'backendStatus':backend_status}))
            return True

    def start_worker(self):
        if self.worker and self.worker.is_alive():
            return
        self.stop.clear()
        def run():
            while not self.stop.is_set():
                try:
                    delivered=self.deliver_one()
                    self.worker_error=None
                except Exception as exc:
                    # A transient local error must not silently kill delivery.
                    # Only the exception type is exposed, never clinical payloads.
                    self.worker_error=type(exc).__name__
                    self.stop.wait(1)
                    continue
                if not delivered:
                    self.stop.wait(0.25)
        self.worker = threading.Thread(target=run, daemon=True)
        self.worker.start()

    def health(self):
        with self.connect() as db:
            states={row['delivery']:row['n'] for row in db.execute('SELECT delivery,COUNT(*) AS n FROM events GROUP BY delivery')}
        alive=bool(self.worker and self.worker.is_alive())
        return {'status':'DEGRADED' if self.worker_error or (self.worker and not alive) else 'UP',
                'workerRunning':alive,'workerError':self.worker_error,'deliveryCounts':states}

    def close(self):
        self.stop.set()
        if self.worker:
            self.worker.join(timeout=12)
