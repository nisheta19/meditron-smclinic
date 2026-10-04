"""Provisional lexical annotations. LOCAL_* codes must not be sent to production."""
import argparse
from collections import Counter
import json
from pathlib import Path

from .contracts import STUDY_TYPES
from .corpus import write_json, write_review
from .findings import analyze
from .attributes import categories

# Explicit lexical forms, not clinical thresholds, diagnoses or routing rules.
TERMS = {
    "POLYP": ["полип", "полипа", "полипы", "полипов", "полипом"],
    "FIBROID": ["миома", "миомы", "миому", "миоматозный узел", "миоматозные узлы"],
    "CYST": ["киста", "кисты", "кист", "кистозное образование"],
    "NODE": ["узел", "узлы", "узлов", "узловое образование"],
    "MASS": ["образование", "образования", "образований"],
    "STONE": ["конкремент", "конкременты", "конкрементов", "камень", "камни", "камней"],
    "SLUDGE": ["сладж", "билиарный сладж"],
    "HYPERPLASIA": ["гиперплазия", "гиперплазии"],
    "CALCIFICATION": ["кальцинат", "кальцинаты", "кальцинатов"],
    "THROMBOSIS": ["тромбоз", "тромбоза", "тромб", "тромбы"],
    "STENOSIS": ["стеноз", "стеноза", "стенозы"],
    "FIBROADENOMA": ["фиброаденома", "фиброаденомы"],
}


def provisional_dictionary():
    return [{"code": "LOCAL_" + code, "name": forms[0], "synonyms": forms[1:],
             "studyTypes": sorted(STUDY_TYPES)} for code, forms in TERMS.items()]


def annotate_record(record):
    if "error" in record:
        return record
    # Concepts are lexical across all study types, including ambiguous studies.
    positives, negatives = analyze(record["full_text"], record["studyType"] or "BREAST", provisional_dictionary())
    record["annotations"] = [dict(f, assertion="historical" if f["attributes"].get("temporality") == "historical" else "uncertain" if f["attributes"]["uncertain"] else "present") for f in positives]
    record["annotations"] += [dict(f, assertion="historical" if f["reason"] == "POST_SURGERY" else "negated") for f in negatives]
    record["annotationStatus"] = "machine_preliminary_unreviewed"
    record["categoryMentions"] = categories(record["full_text"])
    record["annotationVersion"] = "local-lexical-v2"
    record["reviewRequired"] = True
    conflicting = {f["code"] for f in positives} & {f["code"] for f in negatives}
    if conflicting and "mixed_assertions_check_context" not in record["flags"]:
        record["flags"].append("mixed_assertions_check_context")
    return record


def annotate(folder):
    folder = Path(folder)
    records = [annotate_record(json.loads(line)) for line in (folder / "documents.jsonl").read_text(encoding="utf-8").splitlines()]
    (folder / "annotations.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n", encoding="utf-8")
    summary = {"documents": len(records), "annotationStatus": "machine_preliminary_unreviewed",
               "mentions": sum(len(r.get("annotations", [])) for r in records),
               "assertions": dict(Counter(a["assertion"] for r in records for a in r.get("annotations", []))),
               "clinicalAccuracyMeasured": False}
    write_json(folder / "annotation-summary.json", summary)
    write_review(folder, records)
    return summary


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("folder", nargs="?", default=".local/corpus")
    print(json.dumps(annotate(cli.parse_args().folder), ensure_ascii=False, indent=2))
