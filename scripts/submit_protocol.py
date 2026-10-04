"""Send a local DOCX to BACKEND, wait for the ML callback, print backend JSON."""
import argparse
from datetime import date
import json
from pathlib import Path
import sys
import time
from uuid import uuid4
import httpx


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--file', type=Path, help='Local DOCX; omitted for ANNULLED metadata')
    cli.add_argument('--metadata', type=Path, help='Full MIS metadata JSON; required for specific patients/corrections')
    cli.add_argument('--study-type', choices=['PELVIS_FEMALE','ABDOMEN','BREAST','THYROID','PROSTATE','LOWER_LIMB_VESSELS','KIDNEY','SOFT_TISSUE'])
    cli.add_argument('--backend', default='http://127.0.0.1:18080')
    cli.add_argument('--timeout', type=float, default=90)
    args=cli.parse_args()
    if hasattr(sys.stdout,'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
    if args.metadata:
        meta=json.loads(args.metadata.read_text(encoding='utf-8-sig'))
    else:
        if not args.study_type or not args.file: cli.error('Supply --file and --study-type, or --metadata')
        identity=uuid4().hex
        meta={'eventId':'demo-event-'+identity,'eventType':'PROTOCOL_SIGNED',
              'patient':{'externalId':'demo-patient-'+identity,'fullName':'Демо-'+identity[:6]+' Пациент','lastName':'Демо-'+identity[:6],'firstName':'Пациент',
                         'birthDate':'1990-01-01','sex':'M' if args.study_type=='PROSTATE' else 'F'},
              'protocol':{'externalId':'demo-protocol-'+identity,'version':1,
                          'studyType':args.study_type,'studyDate':date.today().isoformat()}}
    try:
        with httpx.Client(base_url=args.backend.rstrip('/'), timeout=40, trust_env=False) as client:
            if args.file:
                with args.file.open('rb') as stream:
                    response=client.post('/api/integration/protocols',files={
                        'metadata':('metadata.json',json.dumps(meta,ensure_ascii=False).encode(),'application/json'),
                        'file':(args.file.name,stream,'application/vnd.openxmlformats-officedocument.wordprocessingml.document')})
            else:
                response=client.post('/api/integration/events',json=meta)
            response.raise_for_status()
            status=response.json()
            deadline=time.monotonic()+args.timeout
            while status['delivery']!='delivered':
                if status['delivery'] in ('rejected','exhausted') or time.monotonic()>=deadline:
                    raise RuntimeError(json.dumps(status,ensure_ascii=False))
                time.sleep(.25)
                response=client.get('/api/integration/events/status',params={'eventId':meta['eventId']})
                response.raise_for_status(); status=response.json()
            response=client.get('/api/patients',params={'search':meta['patient']['externalId'],'size':200})
            response.raise_for_status()
            patient=next(p for p in response.json()['items'] if p['externalId']==meta['patient']['externalId'])
            response=client.get('/api/patients/'+patient['id']); response.raise_for_status()
            card=response.json()
            protocols=[card['currentProtocol'],*card['history']['protocols']]
            protocol=next(p for p in protocols if p and p['externalId']==meta['protocol']['externalId'] and p['version']==meta['protocol']['version'])
            response=client.get('/api/protocols/'+protocol['id']); response.raise_for_status()
            print(json.dumps({'receipt':status,'patientId':patient['id'],'backendProtocol':response.json()},ensure_ascii=False,indent=2))
            return 0
    except httpx.HTTPStatusError as exc:
        print(f'HTTP {exc.response.status_code}: {exc.response.text}',file=sys.stderr)
    except (httpx.HTTPError,OSError,RuntimeError,StopIteration) as exc:
        print(str(exc) or 'Patient/protocol not found in backend after callback',file=sys.stderr)
    return 1


if __name__=='__main__': raise SystemExit(main())
