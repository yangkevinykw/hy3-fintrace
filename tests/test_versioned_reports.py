"""Version selection must preserve the original experiment and serve re-scores."""
import json
import threading
import unittest
from urllib.request import urlopen
from urllib.error import HTTPError
from scripts.serve_batch_workbench import create_batch_server


class VersionedReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=create_batch_server(0)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.base=f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join()

    def get(self,path):
        with urlopen(self.base+path) as r: return json.load(r)

    def test_default_and_historical_versions(self):
        current=self.get('/api/experiment')
        old=self.get('/api/experiment?version=batch-v1')
        self.assertEqual(current['controlled']['rules']['overall']['detection']['numerator'],60)
        self.assertEqual(old['controlled']['rules']['overall']['detection']['numerator'],45)
        self.assertEqual(current['new_model_calls'],0)
        self.assertEqual(self.get('/api/summary')['version'],'fintrace-rules-0.4')

    def test_saved_case_follows_selected_version(self):
        prefix='/api/experiment/case?id=BLK%2F2017%2Fpage_77.pdf-2&version='
        old=self.get(prefix+'batch-v1');new=self.get(prefix+'batch-v2')
        self.assertEqual(old['trace'],new['trace'])
        self.assertEqual(old['evaluation']['process'],'incorrect')
        self.assertEqual(new['evaluation']['process'],'correct')
        self.assertTrue(new['evaluation']['judge_conflict'])

    def test_unknown_version_rejected(self):
        with self.assertRaises(HTTPError) as cm:self.get('/api/experiment?version=../../private')
        self.assertEqual(cm.exception.code,400)
        cm.exception.close()

if __name__=='__main__':unittest.main()
