"""Real service outage/restart test on separate ports. Creates synthetic DB records.

Uses DB_URL/DB_USER/DB_PASSWORD (a test PostgreSQL database), existing Java jar,
and the invoking Python environment. Only terminates subprocesses it starts.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from uuid import uuid4
import httpx
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from backend_session import authenticate

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ml'))
from app.demo import docx
from app.mis import build_event

ML_BOOT='''
import sys,threading,time
from pathlib import Path
import uvicorn
from app.service import MLService
from app.backend import BackendClient
from app.asgi import create_app
backend=BackendClient(sys.argv[1])
service=MLService(sys.argv[2],backend,backend.dictionary)
server=uvicorn.Server(uvicorn.Config(create_app(service),host='127.0.0.1',port=int(sys.argv[3]),access_log=False))
def shutdown_watch():
    while not Path(sys.argv[4]).exists(): time.sleep(.1)
    server.should_exit=True
threading.Thread(target=shutdown_watch,daemon=True).start()
server.run()
'''


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--java',default=shutil.which('java'))
    cli.add_argument('--backend-port',type=int,default=19080)
    cli.add_argument('--ml-port',type=int,default=19000)
    args=cli.parse_args()
    if not args.java or not os.environ.get('DB_URL'): cli.error('Set DB_URL and supply --java')
    for port in (args.backend_port,args.ml_port):
        with socket.socket() as sock: sock.bind(('127.0.0.1',port))
    work=ROOT/'.local'/('resilience-'+uuid4().hex[:10]); work.mkdir()
    backend_url=f'http://127.0.0.1:{args.backend_port}'
    ml_url=f'http://127.0.0.1:{args.ml_port}'
    env=dict(os.environ,ML_SERVICE_URL=ml_url,DEMO_SEED='false')
    client=httpx.Client(timeout=35,trust_env=False)
    logs=[]; backend=None; ml=None; stop_file=None
    def request(method,url,status=200,**kwargs):
        response=client.request(method,url,**kwargs)
        assert response.status_code==status,(url,response.status_code,response.text[:200])
        return response.json() if response.content else None
    def healthy(url):
        deadline=time.monotonic()+45
        while time.monotonic()<deadline:
            try:
                if client.get(url,timeout=1).status_code==200:return
            except httpx.HTTPError:pass
            time.sleep(.3)
        raise AssertionError('Service did not start: '+url)
    def start_backend():
        log=(work/('backend-'+uuid4().hex[:5]+'.log')).open('wb'); logs.append(log)
        process=subprocess.Popen([args.java,'-jar',str(ROOT/'backend/target/routing-0.0.1-SNAPSHOT.jar'),
            f'--server.port={args.backend_port}','--server.address=127.0.0.1'],cwd=ROOT,env=env,
            stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        return process
    def start_ml():
        marker=work/('stop-'+uuid4().hex)
        log=(work/('ml-'+uuid4().hex[:5]+'.log')).open('wb'); logs.append(log)
        process=subprocess.Popen([sys.executable,'-c',ML_BOOT,backend_url,str(work/'events.sqlite3'),str(args.ml_port),str(marker)],
            cwd=ROOT/'ml',stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        return process,marker
    def stop_ml(process,marker):
        marker.touch(); process.wait(timeout=25)
    try:
        backend=start_backend(); healthy(backend_url+'/actuator/health')
        path=work/'synthetic.docx'; docx(path,['Описание','Полип эндометрия 8 мм.','Заключение','Полип эндометрия 8 мм.'])
        identity=work.name
        metadata={'eventId':identity+'-signed','eventType':'PROTOCOL_SIGNED',
            'patient':{'externalId':identity,'fullName':'Пациент проверки восстановления','birthDate':'1990-01-01','sex':'F'},
            'protocol':{'externalId':identity,'version':1,'studyType':'PELVIS_FEMALE','studyDate':'2026-09-07'}}
        event=build_event(metadata,path)
        request('POST',backend_url+'/api/integration/events',502,json=event)
        print('ML unavailable: backend correctly returned 502',flush=True)
        ml,stop_file=start_ml(); healthy(ml_url+'/health')
        receipt=request('POST',backend_url+'/api/integration/events',202,json=event)
        def wait_delivery(event_id):
            deadline=time.monotonic()+65
            while time.monotonic()<deadline:
                status=request('GET',ml_url+'/api/mis/events/'+event_id)
                if status['delivery']=='delivered':return status
                assert status['delivery']=='pending',status
                time.sleep(.3)
            raise AssertionError(status)
        wait_delivery(metadata['eventId'])
        backend.terminate(); backend.wait(timeout=15); backend=None
        annul=dict(metadata,eventId=identity+'-annul',eventType='PROTOCOL_ANNULLED')
        pending=request('POST',ml_url+'/api/mis/events',202,json=annul)
        deadline=time.monotonic()+12
        while time.monotonic()<deadline:
            pending=request('GET',ml_url+'/api/mis/events/'+annul['eventId'])
            if pending['attempts']>=1:break
            time.sleep(.2)
        assert pending['delivery']=='pending' and pending['attempts']>=1,pending
        print('Backend unavailable: callback retained in SQLite, retry scheduled',flush=True)
        stop_ml(ml,stop_file); ml=None
        ml,stop_file=start_ml(); healthy(ml_url+'/health')
        restored=request('GET',ml_url+'/api/mis/events/'+annul['eventId'])
        assert restored['resultId']==pending['resultId'] and restored['attempts']>=pending['attempts']
        backend=start_backend(); healthy(backend_url+'/actuator/health')
        done=wait_delivery(annul['eventId'])
        assert done['resultId']==pending['resultId'] and done['status']=='ANNULLED'
        authenticate(client, backend_url)
        page=request('GET',backend_url+'/api/patients',params={'search':identity})
        assert len(page['items'])==1
        card=request('GET',backend_url+'/api/patients/'+page['items'][0]['id'])
        assert card['currentProtocol']['status']=='ANNULLED' and not card['currentFindings']
        assert not card['history']['protocols']
        report={'passed':True,'checks':['gateway_502_without_ml','callback_retries_when_backend_down',
                'sqlite_queue_survives_ml_restart','same_result_id_after_restart','delivered_after_backend_restart',
                'one_patient_one_protocol_no_duplicates'],'attempts':done['attempts']}
        (ROOT/'.local/resilience-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print('Recovery passed: same resultId, delivered, no duplicates',flush=True)
    finally:
        if ml and ml.poll() is None:stop_ml(ml,stop_file)
        if backend and backend.poll() is None:backend.terminate();backend.wait(timeout=15)
        for log in logs:log.close()
        client.close()


if __name__=='__main__':main()
