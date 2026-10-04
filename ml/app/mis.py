"""Minimal MIS emulator: locally package DOCX + explicitly fictional metadata."""

import base64
from copy import deepcopy
from pathlib import Path

from .contracts import validate_event


def build_event(metadata, file_path=None):
    event = deepcopy(metadata)
    if event.get("eventType") != "PROTOCOL_ANNULLED":
        if file_path is None:
            raise ValueError("Для подписания и исправления требуется --file")
        path = Path(file_path)
        event["fileName"] = path.name
        event["contentBase64"] = base64.b64encode(path.read_bytes()).decode("ascii")
    validate_event(event)
    return event
