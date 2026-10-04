"""Independent synthetic acceptance cases derived from the supplied ML contract."""
import unittest
import tempfile
from pathlib import Path
from app.contracts import ContractError
from app.clinical import analyze_protocol
from app.dictionary import DEFAULT_DICTIONARY, load_dictionary, normalize_dictionary, enrich_remote
from app.parser import parse_text


class ApprovedDictionaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dictionary = load_dictionary(DEFAULT_DICTIONARY.with_name('findings-dictionary-v1.yaml'))

    def run_text(self, text, study):
        parsed = parse_text(text)
        found, rejected = analyze_protocol(parsed,text,study,self.dictionary)
        dictionary = {i["code"]:i for i in normalize_dictionary(self.dictionary)}
        for f in found:
            e=f["evidence"]
            self.assertEqual(parsed["full_text"][e["start"]:e["end"]],e["text"])
            self.assertLessEqual(set(f["attributes"]),set(dictionary[f["code"]]["attributes"]))
            self.assertNotIn("route",f)
        return found,rejected

    def test_all_17_active_codes_positive(self):
        cases = [
            ("ENDOMETRIAL_POLYP","PELVIS_FEMALE","Полип эндометрия 3 мм.",{"sizeMm":3}),
            ("ENDOMETRIAL_HYPERPLASIA","PELVIS_FEMALE","Гиперплазия эндометрия.",{}),
            ("UTERINE_FIBROID","PELVIS_FEMALE","Субмукозный узел на ножке 12 мм.",{"figo":0}),
            ("OVARIAN_LESION","PELVIS_FEMALE","Фолликулярная киста левого яичника 20 мм, O-RADS II.",{"functional":True,"side":"left","orads":2}),
            ("ECTOPIC_PREGNANCY","PELVIS_FEMALE","Нельзя исключить внематочную беременность.",{"uncertain":True}),
            ("OVARIAN_TORSION","PELVIS_FEMALE","Перекрут яичника справа?",{"uncertain":True,"side":"right"}),
            ("OVARIAN_APOPLEXY","PELVIS_FEMALE","Апоплексия яичника слева, жидкость 40 мл.",{"freeFluidMl":40}),
            ("GALLSTONES","ABDOMEN","Конкременты желчного пузыря до 6–8 мм.",{"sizeMm":8,"location":"gallbladder"}),
            ("GALLBLADDER_POLYP","ABDOMEN","Полип желчного пузыря 3 мм, без динамики.",{"sizeMm":3,"growth":False}),
            ("ACUTE_CHOLECYSTITIS","ABDOMEN","Острый холецистит, стенка 5 мм.",{"wallThicknessMm":5}),
            ("FREE_FLUID","ABDOMEN","Свободная жидкость в брюшной полости 40 мл со взвесью.",{"volumeMl":40,"echogenic":"со взвесью"}),
            ("BREAST_LESION","BREAST","BI-RADS 1 справа, BI-RADS 2 слева.",{}),
            ("THYROID_NODULE","THYROID","Узел слева 1.4*1.1*1.5 см, EU-TIRADS 3.",{"sizeMm":15,"tirads":3,"tiradsSystem":"EU"}),
            ("DEEP_VEIN_THROMBOSIS","LOWER_LIMB_VESSELS","Флотирующий тромб БПВ справа.",{"floating":True,"vein":"БПВ"}),
            ("HERNIA","SOFT_TISSUE","Паховая грыжа слева, грыжевые ворота 12 мм, невправимая.",{"sizeMm":12,"reducible":False}),
            ("HYDRONEPHROSIS","KIDNEY","Гидронефроз 2 степени справа, лоханка 22 мм.",{"grade":2,"pelvisMm":22}),
            ("KIDNEY_STONES","KIDNEY","Камень мочеточника справа 6 мм, признаки обструкции.",{"sizeMm":6,"location":"ureter","obstruction":True}),
        ]
        self.assertEqual({c[0] for c in cases},{i["code"] for i in normalize_dictionary(self.dictionary) if i.get("active")})
        for code,study,text,expected in cases:
            with self.subTest(code=code):
                found,_=self.run_text("Заключение\n"+text,study)
                selected=[f for f in found if f["code"]==code]
                self.assertTrue(selected,code)
                for key,value in expected.items(): self.assertEqual(selected[0]["attributes"].get(key),value,key)

    def test_breast_low_categories_separate_sides_and_no_third_finding(self):
        found,_=self.run_text("Описание\nОбъемные образования не лоцируются.\nЗаключение\nКатегория BI-RADS 1 (правая молочная железа)\nКатегория BI-RADS 1 (левая молочная железа)","BREAST")
        self.assertEqual(len(found),2)
        self.assertEqual({(f["attributes"]["side"],f["attributes"]["birads"]) for f in found},{("right",1),("left",1)})

    def test_description_enriches_conclusion(self):
        found,_=self.run_text("Описание\nПолип эндометрия 8 мм.\nЗаключение\nПолип эндометрия.","PELVIS_FEMALE")
        p=[f for f in found if f["code"]=="ENDOMETRIAL_POLYP"]
        self.assertEqual(len(p),1)
        self.assertEqual(p[0]["attributes"]["sizeMm"],8)

    def test_conclusion_negation_overrides_description(self):
        found,rejected=self.run_text("Описание\nПолип эндометрия 8 мм.\nЗаключение\nПолип эндометрия не выявлен.","PELVIS_FEMALE")
        self.assertFalse(found)
        self.assertEqual(rejected[0]["reason"],"NEGATION")

    def test_menopause_measurement_below_threshold_still_returned(self):
        found,_=self.run_text("Описание\nМенопауза 5 лет.\nМ-эхо 3 мм.\nЗаключение\nБез особенностей.","PELVIS_FEMALE")
        f=next(f for f in found if f["code"]=="ENDOMETRIAL_HYPERPLASIA")
        self.assertEqual(f["attributes"],{"thicknessMm":3,"menopause":True,"fromMeasurement":True,"uncertain":True})

    def test_hcg_condition_and_missing_egg_not_automatic_negation(self):
        sentence="Плодное яйцо в полости матки не визуализируется."
        self.assertFalse(self.run_text("Описание\n"+sentence,"PELVIS_FEMALE")[0])
        f,_=self.run_text("Описание\nХГЧ положительный.\n"+sentence,"PELVIS_FEMALE")
        self.assertTrue(f[0]["attributes"]["hcgPositive"])
        self.assertTrue(f[0]["attributes"]["uncertain"])

    def test_negative_and_not_this_traps(self):
        for study,text in [("ABDOMEN","Сладж, холестероз желчного пузыря. Хронический холецистит вне обострения."),
                           ("THYROID","АИТ, расширенные фолликулы. Лимфатические узлы не увеличены."),
                           ("PELVIS_FEMALE","Желтое тело, доминантный фолликул, гидросальпингс. O-RADS I."),
                           ("KIDNEY","Код МКБ: N80.0. Кальцинаты паренхимы. ЧЛС не расширена."),
                           ("SOFT_TISSUE","Грыжа диска. Диастаз прямых мышц без грыжевого дефекта."),
                           ("LOWER_LIMB_VESSELS","Данных за тромбоз не получено.")]:
            with self.subTest(text=text): self.assertFalse(self.run_text("Заключение\n"+text,study)[0])

    def test_post_surgery_and_history_not_current(self):
        found,rejected=self.run_text("Заключение\nСостояние после холецистэктомии.","ABDOMEN")
        self.assertFalse(found)
        self.assertTrue(any(r["code"]=="GALLSTONES" and r["reason"]=="POST_SURGERY" for r in rejected))
        found,_=self.run_text("Анамнез\nПолип эндометрия удален в 2020 году.\nЗаключение\nБез патологии.","PELVIS_FEMALE")
        self.assertFalse(found)

    def test_grouped_synonyms_and_remote_codes_authority(self):
        found,_=self.run_text("Заключение\nЛокальное утолщение эндометрия.","PELVIS_FEMALE")
        self.assertTrue(found[0]["attributes"]["uncertain"])
        remote=[{"code":"NEW","name":"Новая находка","synonyms":["новый признак"],"studyTypes":["BREAST"]}]
        self.assertEqual([i["code"] for i in enrich_remote(remote)["findings"]],["NEW"])
        parsed=parse_text("Новый признак.")
        f,_=analyze_protocol(parsed,"Новый признак.","BREAST",remote)
        self.assertEqual(f[0]["code"],"NEW")

    def test_real_template_regressions_with_synthetic_values(self):
        for study,text in [("PELVIS_FEMALE","Структура миометрия однородная. Свободная жидкость в малом тазу: не лоцируется."),
                           ("ABDOMEN","Желчный пузырь\nКонкременты - нет."),
                           ("PELVIS_FEMALE","Свободная жидкость за маткой\nне определяется")]:
            with self.subTest(text=text): self.assertFalse(self.run_text("Описание\n"+text,study)[0])
        found,_=self.run_text("Описание\nУзел слева 8 мм, без признаков вертикального роста и микрокальцинатов.\nЗаключение\nEU-TIRADS справа 2, слева 3.","THYROID")
        self.assertEqual({(f['attributes']['side'],f['attributes']['tirads']) for f in found},{('right',2),('left',3)})
        self.assertTrue(all('suspiciousFeatures' not in f['attributes'] for f in found))

    def test_table_measurement_and_abbreviated_side_category(self):
        found,_=self.run_text("Описание\nМенопауза 2 года\nЭндометрий:\n2,5 мм\nЗаключение\nБез особенностей.","PELVIS_FEMALE")
        self.assertEqual(found[0]['attributes']['thicknessMm'],2.5)
        found,_=self.run_text("Заключение\nПравая мол. железа Bi-RADS 3\nЛевая мол. железа Bi-RADS 3", "BREAST")
        self.assertEqual({f['attributes']['side'] for f in found},{'right','left'})

    def test_long_scoped_negation_does_not_create_emergency_findings(self):
        cases=[('LOWER_LIMB_VESSELS','Данных за тромбоз поверхностных и глубоких вен нижних конечностей на момент исследования не получено.'),
               ('LOWER_LIMB_VESSELS','Данных за флеботромбоз и тромбофлебит на момент исследования не получено.'),
               ('PELVIS_FEMALE','Свободной жидкости в полости малого таза нет.'),
               ('PELVIS_FEMALE','Свободная жидкость в позадиматочном пространстве: не определяется.'),
               ('PELVIS_FEMALE','Свободная жидкость в малом тазу: не вуизуализируется.')]
        for study,text in cases:
            with self.subTest(text=text):
                f,n=self.run_text('Заключение\n'+text,study)
                self.assertFalse(f)
                self.assertTrue(n)

    def test_sizes_do_not_use_normal_range_or_another_organ(self):
        found,_=self.run_text('Описание\nУзел 8 мм (N до 20 мм), железа 40 мм.\nЗаключение\nУзел щитовидной железы.', 'THYROID')
        self.assertEqual(found[0]['attributes']['sizeMm'],8)
        found,_=self.run_text('Описание\nМенопауза 5 лет.\nЭндометрий неоднородный, полип 8 мм.\nЗаключение\nБез особенностей.', 'PELVIS_FEMALE')
        self.assertTrue(all(not f['attributes'].get('fromMeasurement') for f in found))

    def test_missing_category_number_is_not_a_lesion(self):
        self.assertFalse(self.run_text('Заключение\nКатегория BI-RADS не указана.', 'BREAST')[0])

    def test_yaml_unsafe_tags_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'dictionary.yaml'
            p.write_text('!!python/object/apply:builtins.print [should_not_execute]',encoding='utf-8')
            with self.assertRaises(ContractError):load_dictionary(p)
