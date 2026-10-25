import tempfile
import unittest
import queue
import time
from pathlib import Path
from datetime import date
from safety.engine import Runner,Config,demo_frame,annotate
from safety.core import Assessor
from safety.storage import Store,export_csv,export_pdf

class PipelineTests(unittest.TestCase):
    def test_demo_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            q=queue.Queue()
            runner=Runner(Config(output=tmp),q)
            runner.start()
            deadline=time.monotonic()+6
            latest=None
            while time.monotonic()<deadline:
                frame=runner.take_frame()
                if frame: latest=frame
                if latest and latest[1]['events']==3: break
                time.sleep(.05)
            runner.stop(); runner.join(5)
            self.assertFalse(runner.is_alive())
            self.assertIsNone(runner.error)
            self.assertIsNotNone(latest)
            self.assertEqual(latest[1]['session']['total'],4)
            self.assertEqual(latest[1]['current']['safe'],1)
            self.assertEqual(latest[1]['current']['compliance'],25)
            store=Store(Path(tmp)/'demo')
            rows=store.events()
            self.assertEqual(len(rows),3)
            self.assertTrue(all(Path(r['evidence']).is_file() for r in rows))
            summary=store.daily(date.today().isoformat())
            self.assertEqual(summary['track_ids'],4)
            self.assertEqual(summary['events'],3)
            export_csv(Path(tmp)/'events.csv',rows)
            export_pdf(Path(tmp)/'report.pdf',rows,summary)
            self.assertTrue((Path(tmp)/'report.pdf').read_bytes().startswith(b'%PDF'))
            self.assertIn('Helmet missing',(Path(tmp)/'events.csv').read_text(encoding='utf-8-sig'))
            store.close()
    def test_csv_formula_escaped(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'events.csv'
            export_csv(path,[{'camera':'=SUM(1,2)'}])
            self.assertIn("'=SUM",path.read_text())
    def test_date_camera_filter(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(tmp)
            a=Assessor(confirm=1)
            image,workers,ppe=demo_frame(0)
            active,events=a.update(workers,ppe,(650,1080),0)
            for s in events: store.add('session',s,'CAM-2',0,'evidence.jpg')
            self.assertEqual(len(store.events('','CAM-2')),3)
            self.assertEqual(len(store.events('','CAM-1')),0)
            self.assertEqual(len(store.events('1900-01-01')),0)
            store.close()
    def test_empty_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(tmp)
            export_pdf(Path(tmp)/'empty.pdf',[],store.daily(date.today().isoformat()))
            store.close()
            self.assertGreater((Path(tmp)/'empty.pdf').stat().st_size,1000)
    def test_annotation(self):
        image,workers,ppe=demo_frame(0)
        active,_=Assessor(confirm=1).update(workers,ppe,(650,1080),0)
        output=annotate(image,active,True)
        self.assertEqual(output.size,(1080,650))
        self.assertNotEqual(output.tobytes(),image.tobytes())

if __name__=='__main__': unittest.main()
