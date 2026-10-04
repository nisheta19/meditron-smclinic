"""Local demo HTTP entrypoint for MIS events."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import sqlite3
from urllib.parse import unquote

from .contracts import ContractError
from .service import EventConflict

MAX_REQUEST_BYTES = 29 * 1024 * 1024


def make_server(host, port, service):
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(15)

        def log_message(self, *args):
            pass  # Do not log patient identifiers, document contents or request paths.

        def respond(self, code, value):
            data = json.dumps(value, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == "/health":
                try:
                    value=service.health()
                except sqlite3.Error:
                    return self.respond(503,{"status":"DEGRADED","error":"Журнал недоступен"})
                return self.respond(200 if value['status']=='UP' else 503,value)
            if self.path.startswith("/api/mis/events/"):
                value = service.status(unquote(self.path[len("/api/mis/events/"):]))
                return self.respond(200 if value else 404, value or {"error": "Событие не найдено"})
            self.respond(404, {"error": "Неизвестный путь"})

        def do_POST(self):
            if self.path.startswith("/api/mis/events/") and self.path.endswith("/retry"):
                event_id = unquote(self.path[len("/api/mis/events/"):-len("/retry")])
                value = service.retry(event_id)
                return self.respond(202 if value else 404, value or {"error": "Событие не найдено"})
            if self.path != "/api/mis/events":
                return self.respond(404, {"error": "Неизвестный путь"})
            if self.headers.get_content_type() != "application/json":
                return self.respond(415, {"error": "Ожидается application/json"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_REQUEST_BYTES:
                    return self.respond(413, {"error": "Некорректный размер тела запроса"})
                body=self.rfile.read(length)
                if len(body)!=length:
                    return self.respond(400,{"error":"Неполное тело запроса"})
                event = json.loads(body)
                service.accept(event)
                self.respond(202, service.status(event["eventId"]))
            except EventConflict as exc:
                self.respond(409, {"error": str(exc)})
            except (ContractError, ValueError, UnicodeError) as exc:
                self.respond(400, {"error": str(exc) if isinstance(exc, ContractError) else "Некорректный JSON"})
            except TimeoutError:
                self.respond(408,{"error":"Истекло время чтения запроса"})
            except (sqlite3.Error,OSError):
                self.respond(503,{"error":"Не удалось сохранить событие; повторите отправку с тем же eventId"})

    return ThreadingHTTPServer((host, port), Handler)
