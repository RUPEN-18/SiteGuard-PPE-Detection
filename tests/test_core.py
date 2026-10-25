import unittest
from safety.core import *

class CoreTests(unittest.TestCase):
    def setUp(self):
        self.worker = Detection((100,100,200,500),.99,'person',1)
        self.helmet = Detection((120,105,180,165),.93,'helmet')
        self.vest = Detection((110,200,190,340),.92,'vest')
        self.shape = (600,800)
    def test_truth_table(self):
        self.assertEqual(status(PRESENT,PRESENT),'SAFE')
        for pair in [(MISSING,PRESENT),(PRESENT,MISSING),(MISSING,MISSING),(MISSING,UNKNOWN)]:
            self.assertEqual(status(*pair),'VIOLATION')
        self.assertEqual(status(PRESENT,UNKNOWN),'UNKNOWN')
    def test_known_classes(self):
        self.assertEqual(class_map({0:'Person',1:'Hardhat',2:'NO-Hardhat',3:'Safety Vest',4:'NO-Safety Vest'})['no_vest'],4)
    def test_stock_model_rejected(self):
        with self.assertRaises(ValueError): class_map({0:'person',1:'bicycle'})
    def test_manual_map(self):
        m = class_map({i:str(i) for i in range(5)},dict(zip(ALIASES,range(5))))
        self.assertEqual(m['helmet'],1)
    def test_bad_map_rejected(self):
        with self.assertRaises(ValueError): class_map({i:str(i) for i in range(5)},dict.fromkeys(ALIASES,0))
    def test_positive(self):
        self.assertEqual(match_equipment([self.worker],[self.helmet],'helmet',self.shape)[0][0],PRESENT)
    def test_negative(self):
        self.helmet.role='no_helmet'
        self.assertEqual(match_equipment([self.worker],[self.helmet],'helmet',self.shape)[0][0],MISSING)
    def test_absence_unknown(self):
        self.assertEqual(match_equipment([self.worker],[],'helmet',self.shape)[0][0],UNKNOWN)
    def test_conflict_unknown(self):
        neg = Detection(self.helmet.box,.90,'no_helmet')
        self.assertEqual(match_equipment([self.worker],[self.helmet,neg],'helmet',self.shape)[0][0],UNKNOWN)
    def test_one_item_not_two_workers(self):
        other = Detection((105,100,205,500),.99,'person',2)
        results = match_equipment([self.worker,other],[self.helmet],'helmet',self.shape)
        self.assertTrue(all(s==UNKNOWN for s,c in results))
    def test_separate_workers(self):
        other = Detection((300,100,400,500),.99,'person',2)
        neg = Detection((320,105,380,165),.90,'no_helmet')
        result = match_equipment([self.worker,other],[self.helmet,neg],'helmet',self.shape)
        self.assertEqual([s for s,c in result],[PRESENT,MISSING])
    def test_wrong_body_region(self):
        self.helmet.box=(120,300,180,360)
        self.assertEqual(match_equipment([self.worker],[self.helmet],'helmet',self.shape)[0][0],UNKNOWN)
    def test_whole_person_negative_rejected(self):
        d = Detection(self.worker.box,.99,'no_helmet')
        self.assertEqual(match_equipment([self.worker],[d],'helmet',self.shape)[0][0],UNKNOWN)
    def test_clipped_head_unknown(self):
        self.worker.box=(100,0,200,400)
        self.helmet.box=(120,0,180,60)
        self.assertEqual(match_equipment([self.worker],[self.helmet],'helmet',self.shape)[0][0],UNKNOWN)
    def test_tiny_worker_unknown(self):
        self.worker.box=(100,100,120,150)
        self.assertEqual(match_equipment([self.worker],[self.helmet],'helmet',self.shape)[0][0],UNKNOWN)
    def test_confirm_and_episode(self):
        a = Assessor(confirm=3)
        self.helmet.role='no_helmet'
        for i in range(3):
            active,events = a.update([self.worker],[self.helmet,self.vest],self.shape,i*.1)
            self.assertEqual(len(events),int(i==2))
        for i in range(3,9): a.update([self.worker],[self.helmet,self.vest],self.shape,i*.1)
        self.assertEqual(a.events,1)
        self.assertEqual(a.metrics(active)['session']['total'],1)
    def test_unknown_does_not_rearm(self):
        a = Assessor(confirm=1)
        self.helmet.role='no_helmet'
        a.update([self.worker],[self.helmet,self.vest],self.shape,0)
        a.update([self.worker],[],self.shape,.1)
        a.update([self.worker],[self.helmet,self.vest],self.shape,.2)
        self.assertEqual(a.events,1)
    def test_safe_rearms(self):
        a = Assessor(confirm=1)
        self.helmet.role='no_helmet'
        a.update([self.worker],[self.helmet,self.vest],self.shape,0)
        self.helmet.role='helmet'
        a.update([self.worker],[self.helmet,self.vest],self.shape,.1)
        self.helmet.role='no_helmet'
        a.update([self.worker],[self.helmet,self.vest],self.shape,.2)
        self.assertEqual(a.events,2)
    def test_current_vs_session(self):
        a = Assessor(confirm=1)
        a.update([self.worker],[self.helmet,self.vest],self.shape,0)
        active,_=a.update([],[],self.shape,.1)
        m=a.metrics(active)
        self.assertEqual(m['current']['total'],0)
        self.assertEqual(m['session']['total'],1)
    def test_still_immediate(self):
        a=Assessor(confirm=3)
        active,_=a.update([self.worker],[self.helmet,self.vest],self.shape,0,still=True)
        self.assertEqual(a.metrics(active)['current']['safe'],1)
    def test_zero_division(self):
        self.assertEqual(Assessor().metrics([])['current']['compliance'],0)

    def test_missed_frame_resets_confirmation(self):
        a=Assessor(confirm=3)
        for i in range(2): a.update([self.worker],[self.helmet,self.vest],self.shape,i*.1)
        a.update([],[],self.shape,.2)
        active,_=a.update([self.worker],[self.helmet,self.vest],self.shape,.3)
        self.assertEqual(active[0].helmet,UNKNOWN)
    def test_slow_inference_can_confirm(self):
        a=Assessor(confirm=3)
        for i in range(3): active,_=a.update([self.worker],[self.helmet,self.vest],self.shape,i*5)
        self.assertEqual(active[0].helmet,PRESENT)
