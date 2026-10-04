"""Fault and contract checks for the review changes."""
from copy import deepcopy
from http.client import IncompleteRead
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import time
import unittest
from unittest.mock import Mock, patch
from zipfile import ZipFile

from app.backend import BackendClient, MAX_DICTIONARY_BYTES
from app.contracts import ContractError, validate_event
from app.demo import docx
from app.dictionary import DEFAULT_DICTIONARY, load_dictionary, normalize_dictionary
from app.mis import build_event
from app.parser import DocumentError, extract_text
from app.processing import process_event
from app.service import MLService
from app.validation import validate_for_dictionary
from app.release import prepare,check_package
import json


class ReliabilityReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.path=self.root/'test.docx'
        docx(self.path,['Заключение','Узел справа 9 мм, EU-TIRADS 3.'])
        self.event=build_event({'eventId':'review-001','eventType':'PROTOCOL_SIGNED',
            'patient':{'externalId':'demo-1','fullName':'Пациент 001','birthDate':'2000-01-01','sex':'F'},
            'protocol':{'externalId':'demo-proto-1','version':1,'studyDate':'2026-09-01','studyType':'THYROID'}},self.path)
        self.dictionary=load_dictionary(DEFAULT_DICTIONARY)

    def test_nonfinite_metadata_and_oversized_version_rejected(self):
        for value in (float('nan'),float('inf'),float('-inf')):
            event=deepcopy(self.event);event['patient']['extra']=value
            with self.assertRaises(ContractError):validate_event(event)
        self.event['protocol']['version']=2**63
        with self.assertRaises(ContractError):validate_event(self.event)

    def test_live_processing_validates_attribute_types(self):
        found=[{'code':'THYROID_NODULE','attributes':{'uncertain':'false'},'evidence':{'text':'Узел','start':11,'end':15}}]
        with patch('app.processing.analyze_protocol',return_value=(found,[])):
            result=process_event(self.event,lambda:self.dictionary)
        self.assertEqual(result['status'],'FAILED')
        self.assertEqual(result['error']['code'],'ANALYSIS_ERROR')
        self.assertNotIn('findings',result)

    def test_exception_is_not_mislabeled_as_dictionary_or_normal(self):
        with patch('app.processing.analyze_protocol',side_effect=RuntimeError('sensitive source text')):
            result=process_event(self.event,lambda:self.dictionary)
        self.assertEqual(result['error']['code'],'ANALYSIS_ERROR')
        self.assertNotIn('sensitive',result['error']['message'])

    def test_invalid_categories_and_booleans_rejected(self):
        result=process_event(self.event,lambda:self.dictionary)
        self.assertEqual(result['status'],'DONE')
        for name,value in [('tirads',6),('uncertain','false'),('count',0),('sizeMm',float('nan'))]:
            changed=deepcopy(result);changed['findings'][0]['attributes'][name]=value
            with self.subTest(name=name),self.assertRaises(ContractError):validate_for_dictionary(changed,self.dictionary)

    def test_malformed_suspected_synonyms_rejected(self):
        data=deepcopy(self.dictionary)
        data['findings'][0]['suspectedSynonyms']=123
        # Use a flat synonym list so the grouped form does not legitimately replace it.
        data['findings'][0]['synonyms']=['полип эндометрия']
        with self.assertRaises(ContractError):normalize_dictionary(data)

    def test_incomplete_and_oversized_http_dictionary(self):
        client=BackendClient('http://127.0.0.1:1')
        response=Mock();client.opener=Mock()
        client.opener.open.return_value.__enter__=Mock(return_value=response)
        client.opener.open.return_value.__exit__=Mock(return_value=False)
        for value in (IncompleteRead(b'partial',10),b' '* (MAX_DICTIONARY_BYTES+1)):
            response.read.side_effect=value if isinstance(value,Exception) else None
            response.read.return_value=value
            with self.assertRaises(ContractError):client.dictionary()

    def test_utf16_entity_declarations_rejected(self):
        xml='''<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE doc [<!ENTITY payload "expanded">]><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>&payload;</w:t></w:r></w:p></w:body></w:document>'''
        with ZipFile(self.path,'w') as z:z.writestr('word/document.xml',xml.encode('utf-16'))
        with self.assertRaises(DocumentError):extract_text(self.path)

    def test_deep_docx_does_not_crash_recursive_reader(self):
        xml='<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'+'<w:sdt>'*1500+'<w:p><w:r><w:t>Текст</w:t></w:r></w:p>'+'</w:sdt>'*1500+'</w:document>'
        with ZipFile(self.path,'w') as z:z.writestr('word/document.xml',xml)
        self.assertEqual(extract_text(self.path).strip(),'Текст')

    def test_worker_recovers_without_duplicate_thread(self):
        service=MLService(self.root/'events.sqlite3',Mock(),lambda:self.dictionary)
        self.addCleanup(service.close)
        retried=threading.Event()
        def deliver():
            if not getattr(deliver,'called',False):
                deliver.called=True
                raise OSError('sensitive details')
            retried.set();return False
        service.deliver_one=deliver
        service.start_worker();first=service.worker;service.start_worker()
        self.assertIs(service.worker,first)
        self.assertTrue(retried.wait(3))
        self.assertEqual(service.health()['status'],'UP')
        self.assertIsNone(service.health()['workerError'])

    def test_release_detects_omitted_files_and_accepts_uppercase_extension(self):
        source=self.root/'source';source.mkdir()
        docx(source/'study.DOCX',['Описание','УЗИ щитовидной железы.','Заключение','Узел слева 7 мм.'])
        output=self.root/'release'
        result=prepare(source,output)
        self.assertEqual(result['summary']['total'],1)
        self.assertTrue(check_package(output)['passed'])
        result['documents']=[];result['summary']['total']=0
        (output/'manifest.json').write_text(json.dumps(result),encoding='utf-8')
        with self.assertRaises(ValueError):check_package(output)
