"""Reproducible local verification: tests, HTTP demo and optional DOCX package."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

from .contracts import MODEL_VERSION
from .release import check_package


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--output',default='.local/check')
    cli.add_argument('--package',help='Previously prepared immutable release folder')
    cli.add_argument('--source',help='Optional original DOCX directory for source hash checks')
    args=cli.parse_args()
    root=Path(__file__).resolve().parent.parent
    output=Path(args.output).resolve();output.mkdir(parents=True,exist_ok=True)
    report={'modelVersion':MODEL_VERSION,'python':sys.version.split()[0],
            'checkedAt':datetime.now(timezone.utc).isoformat(),'clinicalAccuracyMeasured':False,'steps':{}}
    for name,command in [('tests',['-m','unittest','discover','-s','tests','-v']),
                         ('demo',['-m','app.demo','--output',str(output/'demo.json')])]:
        completed=subprocess.run([sys.executable,'-X','utf8',*command],cwd=root,
                                  stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf-8')
        (output/f'{name}.log').write_text(completed.stdout,encoding='utf-8')
        step={'passed':completed.returncode==0,'exitCode':completed.returncode}
        if name=='tests':
            match=re.search(r'Ran (\d+) tests? in ([\d.]+)s',completed.stdout)
            if match:step.update(count=int(match[1]),seconds=float(match[2]))
        report['steps'][name]=step
    if args.package:
        try:
            report['steps']['package']=check_package(args.package)
            if args.source:
                source=Path(args.source).resolve()
                manifest=json.loads((Path(args.package)/'manifest.json').read_text(encoding='utf-8'))
                for doc in manifest['documents']:
                    path=(source/doc['source']).resolve()
                    if source not in path.parents or hashlib.sha256(path.read_bytes()).hexdigest()!=doc['sourceSha256']:
                        raise ValueError('Исходный документ изменён или находится вне источника')
                report['steps']['source']={'passed':True,'checked':len(manifest['documents'])}
        except (OSError,ValueError) as exc:
            report['steps']['package']={'passed':False,'error':str(exc)}
    elif args.source:
        report['steps']['source']={'passed':False,'error':'--source requires --package'}
    digest=hashlib.sha256()
    for path in sorted((root/'app').glob('*.py'))+[root/'configs/findings-dictionary.yaml']:
        digest.update(path.relative_to(root).as_posix().encode());digest.update(path.read_bytes())
    report['implementationSha256']=digest.hexdigest()
    report['passed']=all(s.get('passed') for s in report['steps'].values())
    (output/'checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=True,indent=2))
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
