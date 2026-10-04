"""Backend HTTP client. Retry the identical message, never regenerate its ID."""

import json
import time
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, HTTPRedirectHandler

from .contracts import ContractError, validate_result
from .dictionary import enrich_remote

RETRY_DELAYS = (5, 30, 120)
MAX_DICTIONARY_BYTES = 2 * 1024 * 1024


class DeliveryError(Exception):
    def __init__(self, message, retryable=False, status_code=None):
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code


class NoRedirect(HTTPRedirectHandler):
    # Results must not be forwarded to an unexpected redirect destination.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class BackendClient:
    def __init__(self, base_url, timeout=10):
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("BACKEND_URL должен начинаться с http:// или https://")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.opener = build_opener(NoRedirect())

    def dictionary(self):
        try:
            with self.opener.open(self.base_url + "/api/dictionary/findings?full=true", timeout=self.timeout) as response:
                data=response.read(MAX_DICTIONARY_BYTES+1)
                if len(data)>MAX_DICTIONARY_BYTES:
                    raise ContractError("Словарь превышает 2 МБ")
                return enrich_remote(json.loads(data))
        except HTTPError as exc:
            exc.close()
            raise ContractError("Не удалось загрузить корректный словарь бэкенда") from exc
        except (OSError, ValueError, URLError, HTTPException) as exc:
            raise ContractError("Не удалось загрузить корректный словарь бэкенда") from exc

    def send_once(self, result):
        validate_result(result)
        body = json.dumps(result, ensure_ascii=False, allow_nan=False).encode("utf-8")
        request = Request(self.base_url + "/api/integration/ml/results", data=body,
                          headers={"Content-Type": "application/json"}, method="POST")
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                if response.status != 202:
                    raise DeliveryError(f"Ожидался 202, получен HTTP {response.status}",status_code=response.status)
        except HTTPError as exc:
            try:
                detail = exc.read(2048).decode("utf-8",errors="replace") if exc.code == 400 else ""
            finally:
                exc.close()
            raise DeliveryError(f"Бэкенд ответил HTTP {exc.code}" + (": " + detail if detail else ""), retryable=500 <= exc.code < 600,status_code=exc.code) from exc
        except (URLError, OSError, TimeoutError, HTTPException) as exc:
            raise DeliveryError("Бэкенд недоступен", retryable=True) from exc

    def send(self, result, sleep=time.sleep):
        for attempt in range(len(RETRY_DELAYS) + 1):
            try:
                self.send_once(result)
                return
            except DeliveryError as exc:
                if not exc.retryable or attempt == len(RETRY_DELAYS):
                    raise
                sleep(RETRY_DELAYS[attempt])
