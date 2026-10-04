"""FastAPI adapter around the tested durable ML service."""
from contextlib import asynccontextmanager
import json
import sqlite3
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from .contracts import ContractError
from .service import EventConflict
from .server import MAX_REQUEST_BYTES


def create_app(service):
    @asynccontextmanager
    async def lifespan(app):
        service.start_worker()
        try: yield
        finally: service.close()

    app=FastAPI(title='MEDITRON ML', version='2.1', lifespan=lifespan)

    @app.exception_handler(ContractError)
    async def contract_error(request, exc):
        return JSONResponse({'error':str(exc)},status_code=409 if isinstance(exc,EventConflict) else 400)

    @app.exception_handler(sqlite3.Error)
    async def journal_error(request, exc):
        return JSONResponse({'error':'Журнал недоступен'},status_code=503)

    @app.get('/health')
    def health():
        value=service.health()
        return JSONResponse(value,status_code=200 if value['status']=='UP' else 503)

    @app.get('/api/mis/events/{event_id:path}')
    def event_status(event_id:str):
        value=service.status(event_id)
        return JSONResponse(value or {'error':'Событие не найдено'},status_code=200 if value else 404)

    @app.post('/api/mis/events/{event_id:path}/retry',status_code=202)
    def retry(event_id:str):
        value=service.retry(event_id)
        return JSONResponse(value or {'error':'Событие не найдено'},status_code=202 if value else 404)

    @app.post('/api/mis/events',status_code=202)
    async def accept(request:Request):
        if request.headers.get('content-type','').split(';')[0].strip().lower()!='application/json':
            return JSONResponse({'error':'Ожидается application/json'},status_code=415)
        body=bytearray()
        async for chunk in request.stream():
            if len(body)+len(chunk)>MAX_REQUEST_BYTES:
                return JSONResponse({'error':'Некорректный размер тела запроса'},status_code=413)
            body.extend(chunk)
        try:event=json.loads(body)
        except (ValueError,UnicodeError):return JSONResponse({'error':'Некорректный JSON'},status_code=400)
        await run_in_threadpool(service.accept,event)
        return await run_in_threadpool(service.status,event['eventId'])

    return app


def serve(service, host, port):
    import uvicorn
    import logging
    logging.basicConfig(level=logging.INFO,format='%(message)s')
    # Identifiers and protocol text never appear in access logs.
    uvicorn.run(create_app(service),host=host,port=port,access_log=False)
