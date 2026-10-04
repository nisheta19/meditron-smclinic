import json
from pathlib import Path
import tempfile
import unittest
from app.demo import docx
from app.release import prepare,check_package


class ReleaseTests(unittest.TestCase):
    def test_immutable_package_validates_and_detects_edits(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            source=root/'source';source.mkdir()
            docx(source/'sample.docx',['Описание','Молочные железы.','Заключение','BI-RADS 1 справа. BI-RADS 1 слева.'])
            output=root/'output'
            m=prepare(source,output)
            self.assertEqual(m['summary']['statuses'],{'DONE':1})
            self.assertEqual(check_package(output)['checked'],1)
            self.assertEqual(m['documents'][0]['findings'],0)
            with self.assertRaises(ValueError):prepare(source,output)
            p=output/m['documents'][0]['file'];r=json.loads(p.read_text(encoding='utf-8'))
            r['resultId']='changed';p.write_text(json.dumps(r),encoding='utf-8')
            with self.assertRaises(ValueError):check_package(output)
