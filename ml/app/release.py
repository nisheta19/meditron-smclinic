"""Prepare immutable local backend payloads; never sends patient data by itself."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import statistics
import time
from uuid import uuid4

from .contracts import MODEL_VERSION
from .corpus import study_type, write_json
from .dictionary import DEFAULT_DICTIONARY, load_dictionary
from .mis import build_event
from .parser import extract_text, parse_text
from .processing import process_event
from .validation import validate_for_dictionary


def prepare(source, output, dictionary_path=DEFAULT_DICTIONARY, studies=None):
    source,output=Path(source).resolve(),Path(output).resolve()
    if not source.is_dir() or output==source or source in output.parents:
        raise ValueError("Укажите существующий источник и отдельную папку результата")
    if output.exists():
        raise ValueError("Пакет не перезаписывается: выберите новую папку, чтобы сохранить resultId и JSON для повторной доставки")
    paths=sorted(p for p in source.rglob('*') if p.is_file() and p.suffix.lower()=='.docx')
    if not paths: raise ValueError("DOCX не найдены")
    dictionary=load_dictionary(dictionary_path)
    # Resolve metadata before writing any output. The supplied mapping, when
    # present, is authoritative. Otherwise the content heuristic is demo-only.
    plans=[]
    for path in paths:
        relative=str(path.relative_to(source))
        raw=extract_text(path)
        kind=(studies or {}).get(relative) or study_type(raw)[0]
        if not kind: raise ValueError(f"Неоднозначный studyType для {relative}; укажите --studies JSON")
        plans.append((path,relative,kind,parse_text(raw).get('examination_date') or '2026-09-07'))
    output.mkdir(parents=True)
    run_id=str(uuid4())
    manifest={"runId":run_id,"modelVersion":MODEL_VERSION,"syntheticMetadata":True,
              "dictionaryVersion":dictionary.get("version","custom") if isinstance(dictionary,dict) else "custom",
              "dictionarySha256":hashlib.sha256(Path(dictionary_path).read_bytes()).hexdigest(),
              "sent":False,"documents":[]}
    timings=[]
    codes=Counter()
    for i,(path,relative,kind,study_date) in enumerate(plans,1):
        source_hash=hashlib.sha256(path.read_bytes()).hexdigest()
        event=build_event({"eventId":f"release-{run_id}-{i}","eventType":"PROTOCOL_SIGNED",
                           "patient":{"externalId":f"demo-{run_id}-{i}","fullName":f"Пациент {i:03d}","birthDate":"1999-03-15","sex":"M" if kind=="PROSTATE" else "F"},
                           "protocol":{"externalId":f"protocol-{run_id}-{i}","version":1,"studyType":kind,"studyDate":study_date}},path)
        begin=time.perf_counter()
        result=process_event(event,lambda:dictionary)
        timings.append(time.perf_counter()-begin)
        validate_for_dictionary(result,dictionary)
        if result["patient"]!=event["patient"] or result["protocol"]!=event["protocol"]:
            raise AssertionError("МИС-метаданные изменились")
        if hashlib.sha256(path.read_bytes()).hexdigest()!=source_hash: raise AssertionError("Источник изменился")
        name=f"result-{i:03d}.json"
        write_json(output/name,result)
        codes.update(f["code"] for f in result.get("findings",[]))
        manifest["documents"].append({"source":relative,"sourceSha256":source_hash,"file":name,
                                      "payloadSha256":hashlib.sha256((output/name).read_bytes()).hexdigest(),
                                      "resultId":result["resultId"],"status":result["status"],"findings":len(result.get("findings",[]))})
    manifest["summary"]={"total":len(paths),"statuses":dict(Counter(r["status"] for r in manifest["documents"])),
                         "codes":dict(codes),"medianSeconds":round(statistics.median(timings),4),
                         "maxSeconds":round(max(timings),4),"clinicalAccuracyMeasured":False}
    write_json(output/"manifest.json",manifest)
    return manifest


def check_package(folder, dictionary_path=DEFAULT_DICTIONARY):
    folder=Path(folder).resolve()
    manifest=json.loads((folder/"manifest.json").read_text(encoding="utf-8"))
    documents=manifest.get('documents')
    if not isinstance(documents,list) or not documents or manifest.get('summary',{}).get('total')!=len(documents):
        raise ValueError('Некорректное число документов в манифесте')
    files=[doc.get('file') for doc in documents]
    if len(set(files))!=len(files) or set(files)!={p.name for p in folder.glob('result-*.json')}:
        raise ValueError('Манифест и файлы пакета не совпадают')
    dictionary=load_dictionary(dictionary_path)
    if hashlib.sha256(Path(dictionary_path).read_bytes()).hexdigest()!=manifest["dictionarySha256"]:
        raise ValueError("Словарь отличается от использованного при подготовке")
    ids=set()
    for doc in manifest["documents"]:
        path=(folder/doc["file"]).resolve()
        if path.parent!=folder: raise ValueError("Некорректный путь результата")
        if hashlib.sha256(path.read_bytes()).hexdigest()!=doc["payloadSha256"]: raise ValueError("JSON был изменён")
        result=json.loads(path.read_text(encoding="utf-8"))
        validate_for_dictionary(result,dictionary)
        if result['status']!=doc['status'] or len(result.get('findings',[]))!=doc['findings']:
            raise ValueError('Сводка результата не совпадает с манифестом')
        if result["resultId"]!=doc["resultId"] or result["resultId"] in ids: raise ValueError("Неверный или повторный resultId")
        ids.add(result["resultId"])
    return {"checked":len(ids),"passed":True,"sent":False}


if __name__=="__main__":
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument("source",nargs="?")
    cli.add_argument("--output",default=".local/backend-release")
    cli.add_argument("--dictionary",default=str(DEFAULT_DICTIONARY))
    cli.add_argument("--studies",help="JSON relative source path → studyType for demo metadata")
    cli.add_argument("--check",action="store_true")
    args=cli.parse_args()
    if args.check:
        report=check_package(args.output,args.dictionary)
    else:
        if not args.source: cli.error("source required")
        studies=json.loads(Path(args.studies).read_text(encoding="utf-8-sig")) if args.studies else None
        report=prepare(args.source,args.output,args.dictionary,studies)["summary"]
    print(json.dumps(report,ensure_ascii=False,indent=2))
