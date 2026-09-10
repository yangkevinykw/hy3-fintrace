"""Regression assertions for independent audit findings, without credentials/API."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from copy import deepcopy

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from fintrace.evaluator import evaluate
from fintrace.storage import load_dataset
from fintrace.core import number, render
from fintrace.model import judge
from fintrace.benchmark import metrics

class IndependentAuditTests(unittest.TestCase):
    def test_amplification_reports_first_arithmetic_error(self):
        p = {'id':'audit','evidence':{'a':{'value':'1','text':'a'},'b':{'value':'1000000','text':'b'}},'answer':{'value':'1','unit':'number'}}
        ev = lambda k: {'kind':'evidence','ref':k,'value':p['evidence'][k]['value']}
        t = {'steps':[{'id':'s1','op':'divide','args':[ev('a'),ev('b')],'result':'0.000001'}, {'id':'s2','op':'multiply','args':[{'kind':'step','ref':'s1'},ev('b')],'result':'1'}], 'final':{'value':'1','unit':'number'}}
        p['reference']=deepcopy(t)
        t['steps'][0]['result']='0.000002'; t['steps'][1]['result']='2'; t['final']['value']='2'
        result=evaluate(p,t)
        self.assertEqual(result['process'],'incorrect')
        self.assertEqual(result['first_error']['step'],'s1')
        self.assertEqual(result['first_error']['type'],'arithmetic')
        self.assertEqual(result['steps'][1]['affected_by'],['s1'])

    def test_percent_uses_reference_scale(self):
        p=next(x for x in load_dataset() if x['answer']['unit']=='percent')
        t=deepcopy(p['reference'])
        t['final']['value']=render(number(t['final']['value'])+number('0.0001'))
        self.assertFalse(evaluate(p,t)['answer_correct'])
        t=deepcopy(p['reference'])
        self.assertTrue(evaluate(p,t)['answer_correct'])

    def test_contradictory_judge_rejected(self):
        p={'id':'audit','question':'x','table':[],'texts':[],'evidence':{},'reference':{}}
        t={'steps':[{'id':'s1'}]}
        for process, kind in [('correct','formula'),('uncertain','arithmetic'),('incorrect','invented_taxonomy')]:
            obj={'process':process,'first_error_step':None,'error_type':kind,'reason':'test','evidence_refs':[]}
            with self.subTest(process=process,kind=kind), patch('fintrace.model.request_model',return_value={'status':'complete','output':obj}):
                self.assertNotEqual(judge(p,t,Path('unused'))['status'],'complete')

    def test_type_credit_requires_detected_error(self):
        row={'label':{'process':'incorrect','first_error':'s1','type':'formula'}, 'evaluation':{'process':'correct','first_error':{'step':None,'type':'formula'},'answer_correct':False,'correct_answer_invalid_process':False}}
        self.assertEqual(metrics([row])['error_type']['numerator'],0)

if __name__=='__main__': unittest.main()
