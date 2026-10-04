import argparse
import json
import sys
import os
from pathlib import Path
from urllib.request import Request, urlopen

from .parser import DocumentError, parse_docx
from .backend import BackendClient, DeliveryError
from .contracts import ContractError, validate_result
from .mis import build_event
from .service import MLService
from .dictionary import load_dictionary


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Локальный DOCX-парсер и интеграция МИС → ML → backend")
    parser.add_argument("command", help="Путь к DOCX или process / serve / mis-event / send-result")
    parser.add_argument("input", nargs="?", help="JSON события, метаданных или результата")
    parser.add_argument("--file", help="Локальный DOCX для mis-event")
    parser.add_argument("--dictionary", default=os.environ.get("ML_DICTIONARY"), help="Локальный YAML/JSON-словарь вместо GET бэкенда")
    parser.add_argument("--backend-url", default=os.environ.get("BACKEND_URL", "http://localhost:8080"))
    parser.add_argument("--database", default=os.environ.get("ML_DATABASE", ".state/events.sqlite3"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--ml-url", help="Для mis-event: отправить событие в ML вместо вывода base64")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    try:
        if args.command not in {"serve", "process", "mis-event", "send-result"}:
            result = parse_docx(args.command)
        elif args.command == "mis-event":
            if not args.input:
                raise ContractError("Требуется путь к JSON метаданных")
            result = build_event(read_json(args.input), args.file)
            if args.ml_url:
                request = Request(args.ml_url.rstrip("/") + "/api/mis/events",
                                  data=json.dumps(result, ensure_ascii=False).encode("utf-8"),
                                  headers={"Content-Type": "application/json"}, method="POST")
                with urlopen(request, timeout=30) as response:
                    result = json.load(response)
        elif args.command == "send-result":
            if not args.input:
                raise ContractError("Требуется JSON результата")
            result = read_json(args.input)
            validate_result(result)
            backend = BackendClient(args.backend_url)
            from .release import validate_for_dictionary
            validate_for_dictionary(result,load_dictionary(args.dictionary) if args.dictionary else backend.dictionary())
            backend.send(result)
            result = {"resultId": result["resultId"], "delivery": "delivered"}
        else:
            backend = BackendClient(args.backend_url)
            provider = (lambda: load_dictionary(args.dictionary)) if args.dictionary else backend.dictionary
            service = MLService(args.database, backend, provider)
            if args.command == "process":
                if not args.input:
                    raise ContractError("Требуется JSON события МИС")
                result = service.accept(read_json(args.input))
            else:
                from .asgi import serve
                try:
                    serve(service,args.host,args.port)
                except KeyboardInterrupt:
                    pass
                finally:
                    service.close()
                return 0
    except (DocumentError, ContractError, DeliveryError, OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
