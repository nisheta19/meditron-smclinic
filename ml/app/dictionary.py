"""Safe dictionary loading and normalization. Routing fields are never executed."""
from copy import deepcopy
import json
from pathlib import Path
from .contracts import ContractError, STUDY_TYPES
from .extensions import validate_extensions

DEFAULT_DICTIONARY = Path(__file__).resolve().parent.parent / "configs/findings-dictionary.yaml"


def uses_v2_contract(data):
    return isinstance(data,dict) and (str(data.get('version','')).startswith('dict-v2')
        or isinstance(data.get('ml'),dict) and 'returnPolicy' in data['ml'])


def normalize_dictionary(data):
    items = data.get("findings") if isinstance(data, dict) else data
    if not isinstance(items, list) or not items:
        raise ContractError("Словарь должен содержать непустой массив findings")
    result, codes = [], set()
    for source in items:
        if not isinstance(source, dict):
            raise ContractError("Элемент словаря должен быть объектом")
        item = deepcopy(source)
        for key in ("code", "name"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                raise ContractError(f"Словарь: требуется {key}")
        if item["code"] in codes:
            raise ContractError("Словарь: повторяющийся code")
        codes.add(item["code"])
        synonyms = item.get("synonyms")
        if isinstance(synonyms, dict):
            if set(synonyms) - {"certain", "suspected"}:
                raise ContractError("Неизвестная группа synonyms")
            if any(not isinstance(v, list) for v in synonyms.values()):
                raise ContractError("Группы synonyms должны быть массивами")
            item["suspectedSynonyms"] = synonyms.get("suspected", [])
            synonyms = synonyms.get("certain", []) + synonyms.get("suspected", [])
        if not isinstance(synonyms, list) or any(not isinstance(s, str) or not s.strip() for s in synonyms):
            raise ContractError("Словарь: synonyms должен содержать строки")
        item["synonyms"] = synonyms
        suspected=item.get("suspectedSynonyms",[])
        if not isinstance(suspected,list) or any(not isinstance(s,str) or not s.strip() for s in suspected):
            raise ContractError("Словарь: suspectedSynonyms должен содержать строки")
        studies = item.get("studyTypes")
        if not isinstance(studies, list) or not studies or any(not isinstance(s, str) or s not in STUDY_TYPES for s in studies):
            raise ContractError("Словарь: некорректные studyTypes")
        if "attributes" in item and (not isinstance(item["attributes"], list) or any(not isinstance(a, str) for a in item["attributes"])):
            raise ContractError("Словарь: attributes должен быть массивом строк")
        validate_extensions(item)
        result.append(item)
    return result


def load_dictionary(path):
    path = Path(path)
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ContractError("Словарь превышает 2 МБ")
    content = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml
        except ImportError as exc:
            raise ContractError("В текущем Python отсутствует PyYAML. Установите зависимости: python -m pip install -r requirements.txt. Либо используйте готовый .venv/Scripts/python.exe") from exc
        try:
            data = yaml.safe_load(content)
        except yaml.YAMLError as exc:
            raise ContractError("Некорректный YAML-словарь") from exc
    else:
        data = json.loads(content)
    normalize_dictionary(data)
    return data


def enrich_remote(data):
    """Remote list remains authority for codes, types and synonyms.

    Backend GET may expose only four documented fields. Fill extraction metadata
    for those SAME codes from the supplied approved snapshot; never add codes.
    """
    snapshot = load_dictionary(DEFAULT_DICTIONARY)
    local = {f["code"]: f for f in normalize_dictionary(snapshot)}
    items = normalize_dictionary(data)
    explicit_version = data.get('version') if isinstance(data,dict) else None
    compatible = explicit_version in (None,snapshot.get('version'))
    for item in items:
        fallback = local.get(item["code"], {}) if compatible else {}
        for key in ("attributes", "extraction", "notThis", "mlApproved", "extractionProfile", "attributeExtractors"):
            if key not in item and key in fallback:
                item[key] = deepcopy(fallback[key])
        if "suspectedSynonyms" not in item:
            item["suspectedSynonyms"] = [s for s in fallback.get("suspectedSynonyms", []) if s in item["synonyms"]]
    result = deepcopy(data) if isinstance(data,dict) else {}
    if explicit_version is None:
        result['version'] = snapshot.get('version', 'remote')
        result['metadataSource'] = 'bundled-fallback-for-unversioned-remote'
        for key in ('ml','flags'):
            if key not in result:result[key]=deepcopy(snapshot.get(key,{}))
    result['findings']=items
    return result
