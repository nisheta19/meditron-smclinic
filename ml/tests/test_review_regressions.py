"""Synthetic adversarial cases found during the project review; no patient data."""
import unittest
from app.clinical import analyze_protocol
from app.dictionary import DEFAULT_DICTIONARY, load_dictionary
from app.parser import parse_text


class ReviewExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dictionary = load_dictionary(DEFAULT_DICTIONARY.with_name('findings-dictionary-v1.yaml'))

    def analyze(self, text, study):
        parsed = parse_text(text)
        found, rejected = analyze_protocol(parsed, text, study, self.dictionary)
        for finding in found:
            e = finding['evidence']
            self.assertEqual(parsed['full_text'][e['start']:e['end']], e['text'])
        return found, rejected

    def test_abbreviated_side_changes_inside_paragraph(self):
        found, _ = self.analyze('Заключение\nПравая мол.железа BI-RADS 3. Левая мол.железа BI-RADS 2.', 'BREAST')
        self.assertEqual({(f['attributes'].get('side'),f['attributes'].get('birads')) for f in found}, {('right',3),('left',2)})

    def test_recommendation_categories_are_not_current_findings(self):
        found, _ = self.analyze('Заключение\nБез очаговых изменений.\nРекомендации\nПри выявлении BI-RADS 4 требуется консультация.', 'BREAST')
        self.assertEqual(found, [])

    def test_attribute_negation_does_not_cancel_finding_negation(self):
        found, rejected = self.analyze('Заключение\nПолип желчного пузыря не выявлен, стенка без признаков воспаления.', 'ABDOMEN')
        self.assertFalse(found)
        self.assertTrue(any(f['code']=='GALLBLADDER_POLYP' for f in rejected))

    def test_negated_suspicious_features_are_not_positive(self):
        found, _ = self.analyze('Описание\nУзел слева 8 мм, микрокальцинаты не выявлены, контуры ровные.\nЗаключение\nEU-TIRADS 3 слева.', 'THYROID')
        self.assertTrue(found)
        self.assertTrue(all('микрокальцинаты' not in f['attributes'].get('suspiciousFeatures',[]) for f in found))

    def test_two_nodes_on_same_side_keep_size_category_pair(self):
        found, _ = self.analyze('Описание\nПравая доля.\nУзел 7 мм, EU-TIRADS 5.\nУзел 24 мм, EU-TIRADS 2.\nЗаключение\nУзлы правой доли.', 'THYROID')
        pairs={(f['attributes'].get('sizeMm'),f['attributes'].get('tirads')) for f in found if f['attributes'].get('sizeMm')}
        self.assertEqual(pairs,{(7,5),(24,2)})

    def test_unsided_size_is_not_copied_to_both_sides(self):
        found, _ = self.analyze('Описание\nОбъемное образование 9 мм.\nЗаключение\nBI-RADS 2 справа. BI-RADS 3 слева.', 'BREAST')
        self.assertFalse(any(f['attributes'].get('side') and 'sizeMm' in f['attributes'] for f in found))

    def test_residual_urine_is_not_prostate_volume(self):
        found, _ = self.analyze('Описание\nПредстательная железа: объем 45 мл.\nОстаточная моча 110 мл.\nЗаключение\nДГПЖ.', 'PROSTATE')
        self.assertEqual(len(found),1)
        self.assertEqual(found[0]['attributes'].get('residualUrineMl'),110)
        self.assertEqual(found[0]['attributes'].get('volumeMl'),45)

    def test_history_does_not_supply_current_biliary_measurement(self):
        found, _ = self.analyze('Анамнез\nХоледох 15 мм.\nОписание\nКонкременты желчного пузыря 6 мм.\nЗаключение\nЖКБ.', 'ABDOMEN')
        self.assertTrue(found)
        self.assertTrue(all('choledochMm' not in f['attributes'] for f in found))

    def test_history_and_recommendations_excluded_for_custom_dictionary(self):
        dictionary=[{'code':'CUSTOM','name':'Специальная находка','synonyms':[], 'studyTypes':['BREAST']}]
        text='Анамнез\nСпециальная находка.\nЗаключение\nБез патологии.\nРекомендации\nИсключить: специальная находка.'
        found,_=analyze_protocol(parse_text(text),text,'BREAST',dictionary)
        self.assertEqual(found,[])

    def test_breast_category_without_scale_label(self):
        found,_=self.analyze('Заключение\nПравая молочная железа: категория 4а.\nЛевая молочная железа: категория 1.', 'BREAST')
        self.assertEqual({(f['attributes'].get('side'),f['attributes'].get('birads'),f['attributes'].get('biradsSub')) for f in found},{('right',4,'a'),('left',1,None)})

    def test_no_size_invented_from_negated_mass(self):
        found,_=self.analyze('Описание\nОбразование правой молочной железы 8 мм.\nЛевая молочная железа.\nОбразования не выявлены.\nЗаключение\nBI-RADS 3 справа. BI-RADS 1 слева.', 'BREAST')
        left=[f for f in found if f['attributes'].get('side')=='left']
        self.assertTrue(left)
        self.assertTrue(all('sizeMm' not in f['attributes'] for f in left))

    def test_standalone_category_after_recommendation_is_retained(self):
        found,_=self.analyze('Заключение\nДиффузные изменения.\nРекомендовано: наблюдение.\nСправа категория TI-RADS -2\nСлева категория TI-RADS -2', 'THYROID')
        self.assertEqual({(f['attributes'].get('side'),f['attributes'].get('tirads')) for f in found},{('right',2),('left',2)})

    def test_prostate_volume_excludes_reference_and_node_volume(self):
        found,_=self.analyze('Описание\nПредстательная железа.\nОбъем железы (в норме до 30 мл): 62 мл.\nУзлы объемом 4 мл.\nЗаключение\nДГПЖ.', 'PROSTATE')
        self.assertEqual(found[0]['attributes'].get('volumeMl'),62)

    def test_long_negated_reflux_does_not_make_positive(self):
        found,_=self.analyze('Описание\nПравая нижняя конечность.\nРефлюкс на клапанах ствола МПВ не регестируется.', 'LOWER_LIMB_VESSELS')
        self.assertFalse(found)

    def test_conclusion_uncertainty_survives_multiple_measured_findings(self):
        found,_=self.analyze('Описание\nКиста справа 5 мм.\nОчаговое образование справа 13 мм, фиброаденома.\nЗаключение\nФиброаденома справа?', 'BREAST')
        self.assertTrue(any(f['attributes'].get('uncertain') for f in found))

    def test_endometrial_polyp_with_inverted_word_order(self):
        found,_=self.analyze('Заключение\nПризнаки патологии эндометрия ( полип ), образование левого яичника.', 'PELVIS_FEMALE')
        self.assertIn('ENDOMETRIAL_POLYP',{f['code'] for f in found})

    def test_ovarian_growth_with_intervening_side(self):
        found,_=self.analyze('Заключение\nОбразование правого яичника с динамикой роста. Киста правого яичника?', 'PELVIS_FEMALE')
        self.assertTrue(any(f['attributes'].get('growth') for f in found))

    def test_cyrillic_letter_in_category(self):
        found,_=self.analyze('Заключение\nУзел слева 8 мм, Тi-rads-2.', 'THYROID')
        self.assertEqual(found[0]['attributes'].get('tirads'),2)

    def test_other_finding_question_does_not_change_polyp_assertion(self):
        found,_=self.analyze('Заключение\nПолип эндометрия, полип шейки матки?', 'PELVIS_FEMALE')
        self.assertFalse(next(f for f in found if f['code']=='ENDOMETRIAL_POLYP')['attributes']['uncertain'])
        self.assertTrue(next(f for f in found if f['code']=='CERVICAL_POLYP')['attributes']['uncertain'])

    def test_dostoverno_negation_is_not_stone(self):
        found,rejected=self.analyze('Описание\nЖелчный пузырь.\nЭховзвеси и конкрементов достоверно не определяется.', 'ABDOMEN')
        self.assertFalse(found)
        self.assertTrue(rejected)

    def test_stone_description_under_conclusion_supplies_size(self):
        found,_=self.analyze('Заключение\nЖелчный пузырь.\nГиперэхогенные образования от 5 мм до 12 мм, перемещающиеся, дающие акустические тени.\nУЗ-признаки конкрементов желчного пузыря.', 'ABDOMEN')
        self.assertEqual(found[0]['attributes'].get('sizeMm'),12)

    def test_stenosis_attributes_by_side(self):
        found,_=self.analyze('Заключение\nСправа стеноз 40–55%.\nСлева окклюзия артерии.', 'LOWER_LIMB_VESSELS')
        right=next(f['attributes'] for f in found if f['attributes'].get('side')=='right')
        left=next(f['attributes'] for f in found if f['attributes'].get('side')=='left')
        self.assertEqual(right.get('stenosisPct'),55)
        self.assertTrue(left.get('occlusion'))
        self.assertNotIn('occlusion',right)

    def test_unsided_percentage_is_not_assigned_to_both_legs(self):
        found,_=self.analyze('Описание\nСтенозы до 60%.\nСправа стеноз 35%.\nСлева стеноз 45%.', 'LOWER_LIMB_VESSELS')
        right=next(f['attributes'] for f in found if f['attributes'].get('side')=='right')
        left=next(f['attributes'] for f in found if f['attributes'].get('side')=='left')
        self.assertEqual(right['stenosisPct'],35)
        self.assertEqual(left['stenosisPct'],45)

    def test_stenosis_ranges_both_sides_one_sentence(self):
        found,_=self.analyze('Заключение\nМаксимальный стеноз справа до 35–40%, слева 40–45%.', 'LOWER_LIMB_VESSELS')
        self.assertEqual({(f['attributes'].get('side'),f['attributes'].get('stenosisPct')) for f in found},{('right',40),('left',45)})
