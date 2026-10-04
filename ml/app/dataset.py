"""Reproducible conservative grouping; machine annotations are not gold labels."""
import argparse
from collections import Counter, defaultdict
from difflib import SequenceMatcher
import hashlib
import json
from pathlib import Path
import re

from .corpus import write_json


def clinical_text(record):
    selected = [s["text"] for s in record["sections"] if s["name"] in {"description", "conclusion"}]
    return re.sub(r"\s+", " ", " ".join(selected) or record["full_text"]).lower().strip()


def split_records(records, threshold=0.90):
    records = sorted((r for r in records if "error" not in r), key=lambda r: r["documentId"])
    parent = list(range(len(records)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    links = []
    texts = [clinical_text(r) for r in records]
    # Same DOB is deliberately over-conservative. It is a possible same-patient
    # link, NOT a patient identity assertion; DOB is never included in manifest.
    births = [re.search(r"Дата\s+рождения\s*:\s*(\d{2}[./-]\d{2}[./-]\d{4})", r["full_text"], re.I) for r in records]
    for i, a in enumerate(records):
        for j in range(i):
            b = records[j]
            reason = None
            if a["sha256"] == b["sha256"] or (texts[i] and texts[i] == texts[j]):
                reason = "exact_content"
            elif births[i] and births[j] and births[i][1] == births[j][1]:
                reason = "possible_same_patient_dob"
            elif a["studyType"] == b["studyType"] and min(len(texts[i]), len(texts[j])) >= 100:
                matcher = SequenceMatcher(None, texts[i], texts[j], autojunk=False)
                if matcher.real_quick_ratio() >= threshold and matcher.quick_ratio() >= threshold and matcher.ratio() >= threshold:
                    reason = "near_duplicate"
            if reason:
                parent[find(i)] = find(j)
                links.append({"a": a["documentId"], "b": b["documentId"], "reason": reason})
    groups = defaultdict(list)
    for i, row in enumerate(records):
        groups[find(i)].append(row)
    ratios = {"train": .6, "dev": .2, "test": .2}
    totals = Counter(r["studyType"] or "UNKNOWN" for r in records)
    counts = {part: Counter() for part in ratios}
    assigned = []
    # Largest groups first, maximize remaining proportional capacity by type.
    for group in sorted(groups.values(), key=lambda g: (-len(g), g[0]["documentId"])):
        kinds = Counter(r["studyType"] or "UNKNOWN" for r in group)
        part = max(ratios, key=lambda p: sum(n * (ratios[p] * totals[k] - counts[p][k]) for k, n in kinds.items()))
        counts[part].update(kinds)
        gid = hashlib.sha256("|".join(r["documentId"] for r in group).encode()).hexdigest()[:16]
        assigned.extend({"documentId": r["documentId"], "sha256": r["sha256"], "groupId": gid,
                         "split": part, "studyType": r["studyType"]} for r in group)
    by_id = {r["documentId"]: r["split"] for r in assigned}
    if any(by_id[l["a"]] != by_id[l["b"]] for l in links):
        raise ValueError("Duplicate group leaked across splits")
    return {"version": 1, "seed": "deterministic-largest-group-first-v1", "similarityThreshold": threshold,
            "purpose": "frozen_future_regression_not_blind_clinical_evaluation",
            "patientIdentityGuaranteed": False, "clinicalGoldLabels": False,
            "counts": dict(Counter(r["split"] for r in assigned)), "groups": len(groups),
            "links": links, "documents": assigned}


def build_split(folder):
    folder = Path(folder)
    records = [json.loads(line) for line in (folder / "documents.jsonl").read_text(encoding="utf-8").splitlines()]
    result = split_records(records)
    path = folder / "split.json"
    if path.exists() and json.loads(path.read_text(encoding="utf-8")) != result:
        raise ValueError("Frozen split differs; use a new output directory for a new corpus version")
    write_json(path, result)
    return {k: result[k] for k in ("counts", "groups", "purpose")}


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("folder", nargs="?", default=".local/corpus")
    print(json.dumps(build_split(cli.parse_args().folder), ensure_ascii=False, indent=2))
