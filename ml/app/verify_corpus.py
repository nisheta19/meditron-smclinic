"""Check source integrity, annotations, frozen split and result schema locally."""
import argparse
import hashlib
import json
from pathlib import Path

from .annotation import provisional_dictionary
from .contracts import validate_result
from .corpus import write_json
from .mis import build_event
from .processing import process_event


def verify(source, folder):
    source, folder = Path(source).resolve(), Path(folder)
    records = [json.loads(line) for line in (folder / "annotations.jsonl").read_text(encoding="utf-8").splitlines()]
    split = json.loads((folder / "split.json").read_text(encoding="utf-8"))
    ids = [r["documentId"] for r in records]
    assigned = {r["documentId"]: r for r in split["documents"]}
    if len(ids) != len(set(ids)) or set(ids) != set(assigned) or len(assigned) != len(split["documents"]):
        raise ValueError("Documents/split mismatch")
    for link in split["links"]:
        if assigned[link["a"]]["split"] != assigned[link["b"]]["split"]:
            raise ValueError("Duplicate-group leakage")
    checked, mentions, categories = 0, 0, 0
    for row in records:
        path = (source / row["source"]).resolve()
        if source not in path.parents:
            raise ValueError("Source outside corpus")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != row["sha256"] or digest != assigned[row["documentId"]]["sha256"]:
            raise ValueError("Source changed since audit/split")
        for annotation in row["annotations"]:
            quote = annotation["evidence"]
            if quote["text"] not in row["full_text"]:
                raise ValueError("Missing annotation evidence")
            if "start" in quote and row["full_text"][quote["start"]:quote["end"]] != quote["text"]:
                raise ValueError("Invalid annotation offsets")
            mentions += 1
        for category in row["categoryMentions"]:
            if row["full_text"][category["start"]:category["end"]] != category["text"]:
                raise ValueError("Invalid category offsets")
            categories += 1
        # Fictional metadata for a contract smoke test, never patient gold truth.
        # Ambiguous type uses BREAST solely because provisional terms cover all
        # types; this fallback is not written into annotations or split labels.
        event = build_event({"eventId": "audit-" + row["documentId"], "eventType": "PROTOCOL_SIGNED",
                            "patient": {"externalId": "synthetic-001", "fullName": "Пациент 001", "birthDate": "1999-03-15", "sex": "F"},
                            "protocol": {"externalId": row["documentId"], "version": 1,
                                         "studyType": row["studyType"] or "BREAST", "studyDate": "2026-09-07"}}, path)
        result = process_event(event, provisional_dictionary)
        validate_result(result)
        if result["status"] != "DONE" or result["text"] != row["full_text"]:
            raise ValueError("Contract processing failed")
        if result["patient"] != event["patient"] or result["protocol"] != event["protocol"]:
            raise ValueError("Metadata changed")
        checked += 1
    summary = {"passed": True, "documentsChecked": checked, "annotationEvidenceChecked": mentions,
               "categoryEvidenceChecked": categories, "sourceHashesUnchanged": True,
               "detectedGroupsDoNotLeak": True, "backendSchemaChecked": checked,
               "realBackendUsed": False, "clinicalAccuracyMeasured": False}
    write_json(folder / "verification.json", summary)
    return summary


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("source")
    cli.add_argument("--folder", default=".local/corpus")
    args = cli.parse_args()
    print(json.dumps(verify(args.source, args.folder), indent=2))
