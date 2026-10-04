"""Local corpus audit. Outputs contain sensitive source text; never publish them."""
import argparse
from collections import Counter
import hashlib
import html
import json
from pathlib import Path
import re

from .parser import extract_text, parse_text
from .sections import split_sections


def study_type(text):
    """Content-based heuristic, not a clinical label or folder-derived truth."""
    patterns = {
        "BREAST": r"молочн\w*\s+желез",
        "THYROID": r"щитовидн\w*\s+желез",
        "PROSTATE": r"предстательн\w*\s+желез",
        "PELVIS_FEMALE": r"яичник|эндометр|шейк\w*\s+матки|тело\s+матки",
        "ABDOMEN": r"желчн\w*\s+пузыр|желчного\s+пузыря",
        "LOWER_LIMB_VESSELS": r"бедренн|подколенн|нижних\s+конечност",
    }
    candidates = [key for key, pattern in patterns.items() if re.search(pattern, text, re.I)]
    return candidates[0] if len(candidates) == 1 else None, candidates


def audit_document(path, root):
    raw = extract_text(path)
    parsed = parse_text(raw)
    sections = split_sections(raw)
    reconstructed = "".join((s["title"] or "") + s["text"] for s in sections)
    if reconstructed != raw:
        raise ValueError("Section splitting lost source text")
    if " ".join(raw.split()) != parsed["full_text"]:
        raise ValueError("Text normalization changed non-whitespace content")
    kind, candidates = study_type(raw)
    names = [s["name"] for s in sections]
    flags = [f"missing_{name}" for name in ("description", "conclusion") if name not in names]
    if not kind:
        flags.append("ambiguous_study_type")
    if names.count("conclusion") > 1:
        flags.append("repeated_conclusion")
    if not parsed["full_text"]:
        flags.append("empty_text")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"documentId": hashlib.sha256(str(path.relative_to(root)).encode()).hexdigest()[:16],
            "source": str(path.relative_to(root)), "sha256": digest,
            "studyType": kind, "studyTypeCandidates": candidates,
            "studyTypeSource": "content_heuristic", "textConserved": True,
            "rawCharacters": len(raw), "flags": flags, **parsed}


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_review(output, records):
    cards = []
    for r in records:
        if "error" in r:
            body = html.escape(r["error"])
        else:
            body = "".join(f'<h3>{html.escape(s["title"] or "Без заголовка")}</h3><p>{html.escape(s["text"])}</p>' for s in r["sections"])
        annotations = {"mentions": r.get("annotations", []), "categories": r.get("categoryMentions", [])}
        cards.append(f'<details><summary>{html.escape(r["source"])} — {html.escape(", ".join(r.get("flags", [])) or "OK")}</summary>{body}<pre>{html.escape(json.dumps(annotations, ensure_ascii=False, indent=2))}</pre></details>')
    (output / "review.html").write_text('<!doctype html><meta charset="utf-8"><title>Локальная проверка протоколов</title><style>body{max-width:1100px;margin:30px auto;font:16px system-ui;background:#f4f6fa;color:#182237}details{background:white;margin:12px 0;padding:16px;border-radius:8px}summary{cursor:pointer}p,pre{white-space:pre-wrap;overflow-wrap:anywhere}</style><h1>Локальная проверка протоколов</h1><p>Предварительная автоматическая разметка. Не эталон и не клиническая рекомендация. Этот файл содержит тексты исходных документов — не публиковать.</p>' + "".join(cards), encoding="utf-8")


def audit(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    if not source.is_dir():
        raise ValueError("Source directory does not exist")
    if output == source or source in output.parents:
        raise ValueError("Output must be outside the source directory")
    paths = sorted(p for p in source.rglob('*') if p.is_file() and p.suffix.lower()=='.docx')
    if not paths:
        raise ValueError("No DOCX files found")
    output.mkdir(parents=True, exist_ok=True)
    records = []
    for path in paths:
        try:
            records.append(audit_document(path, source))
        except (ValueError, OSError) as exc:
            records.append({"source": str(path.relative_to(source)), "error": str(exc)})
    summary = {"total": len(records), "parsed": sum("error" not in r for r in records),
               "errors": sum("error" in r for r in records),
               "textConserved": sum(r.get("textConserved", False) for r in records),
               "flags": dict(Counter(flag for r in records for flag in r.get("flags", [])))}
    (output / "documents.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n", encoding="utf-8")
    write_json(output / "audit.json", summary)
    write_review(output, records)
    return summary


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("source")
    cli.add_argument("--output", default=".local/corpus")
    args = cli.parse_args()
    print(json.dumps(audit(args.source, args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
