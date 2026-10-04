import unittest
from app.evaluate import evaluate,matched_count


class EvaluationTests(unittest.TestCase):
    def gold(self,findings,id='doc'):
        return {'documentId':id,'annotationStatus':'synthetic','findings':findings}

    def test_known_counts_and_attribute_error(self):
        truth=[self.gold([{'code':'A','attributes':{'sizeMm':8}},{'code':'B'}])]
        pred=[{'documentId':'doc','findings':[{'code':'A','attributes':{'sizeMm':9}},{'code':'C'}]}]
        r=evaluate(truth,pred)
        self.assertEqual((r['codes']['tp'],r['codes']['fp'],r['codes']['fn']),(1,1,1))
        self.assertEqual(r['codes']['f1'],.5)
        self.assertEqual(r['facts']['tp'],0)

    def test_failed_documents_count_as_missed(self):
        r=evaluate([self.gold([{'code':'A'}])],[{'documentId':'doc','status':'FAILED','findings':[]}])
        self.assertEqual(r['codes']['fn'],1)
        self.assertEqual(r['failedDocuments'],['doc'])

    def test_incomplete_coverage_and_machine_gold_rejected(self):
        with self.assertRaises(ValueError):evaluate([self.gold([],id='a')],[{'documentId':'b','findings':[]}])
        with self.assertRaises(ValueError):evaluate([dict(self.gold([]),annotationStatus='machine_preliminary_unreviewed')],[{'documentId':'doc','findings':[]}])

    def test_matching_is_one_to_one_and_not_greedy(self):
        expected=[{'code':'A'},{'code':'A','attributes':{'sizeMm':8}}]
        actual=[{'code':'A','attributes':{'sizeMm':8}},{'code':'A','attributes':{'sizeMm':9}}]
        self.assertEqual(matched_count(expected,actual),2)
        self.assertEqual(matched_count(expected,actual[:1]),1)

    def test_empty_denominator_not_perfect_quality(self):
        result=evaluate([self.gold([])],[{'documentId':'doc','findings':[]}])
        self.assertIsNone(result['codes']['f1'])
        self.assertFalse(result['clinicalValidationClaimed'])
