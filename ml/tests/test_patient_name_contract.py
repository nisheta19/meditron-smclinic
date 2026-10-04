from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from app.contracts import ContractError, envelope, validate_event
from app.demo import docx
from app.dictionary import DEFAULT_DICTIONARY, load_dictionary
from app.mis import build_event
from app.processing import process_event


class PatientNameContractTests(unittest.TestCase):
    def metadata(self):
        return {'eventId': 'names-test', 'eventType': 'PROTOCOL_ANNULLED',
                'patient': {'externalId': 'names-patient', 'fullName': 'Legacy Full Name',
                            'lastName': ' де ла Крус ', 'firstName': 'Анна Мария', 'middleName': None,
                            'birthDate': '1990-01-01', 'sex': 'F'},
                'protocol': {'externalId': 'names-protocol', 'version': 1, 'studyType': 'BREAST', 'studyDate': '2026-09-07'}}

    def test_parts_are_unchanged_for_done_failed_and_annulled(self):
        dictionary = load_dictionary(DEFAULT_DICTIONARY)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'fictional.docx'
            docx(path, ['Описание', 'Патологии не выявлено.', 'Заключение', 'BI-RADS 1 справа. BI-RADS 1 слева.'])
            signed = self.metadata(); signed['eventType'] = 'PROTOCOL_SIGNED'
            good = build_event(signed, path)
            bad = deepcopy(good); bad['contentBase64'] = 'bm90IGRvY3g='
            for event, status in [(good, 'DONE'), (bad, 'FAILED'), (self.metadata(), 'ANNULLED')]:
                with self.subTest(status=status):
                    result = process_event(event, lambda: dictionary)
                    self.assertEqual(result['status'], status)
                    self.assertEqual(result['patient'], event['patient'])

    def test_name_parts_are_optional_but_must_be_strings_or_null(self):
        for field in ('lastName', 'firstName', 'middleName'):
            for value in (None, '', ' ', 'Составное имя'):
                event = self.metadata(); event['patient'][field] = value
                validate_event(event)
            for value in ([], {}, 123, True):
                event = self.metadata(); event['patient'][field] = value
                with self.assertRaises(ContractError): validate_event(event)
        legacy = self.metadata()
        for field in ('lastName', 'firstName', 'middleName'): legacy['patient'].pop(field)
        validate_event(legacy)

    def test_full_name_remains_required_for_compatibility(self):
        event = self.metadata(); event['patient'].pop('fullName')
        with self.assertRaises(ContractError): validate_event(event)

    def test_metadata_is_copied_without_mutating_the_input(self):
        event = self.metadata(); original = deepcopy(event)
        result = envelope(event); result['patient']['firstName'] = 'Изменено'
        self.assertEqual(event, original)
