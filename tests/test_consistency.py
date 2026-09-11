"""Independent counterexamples for explanation consistency and judge conflicts."""
from copy import deepcopy
import unittest
from fintrace.core import calculate, number, render
from fintrace.evaluator import evaluate
from fintrace.explanation import explicit_operation
from fintrace.model import combine


def fixture(op='add'):
    evidence={k:{'value':str(v),'text':k} for k,v in [('a',7),('b',3)]}
    trace={'steps':[{'id':'s1','op':op,'args':[{'kind':'evidence','ref':k,'value':evidence[k]['value']} for k in evidence],
                    'result':render(calculate(op,number('7'),number('3'))),'explanation':''}],
           'final':{'value':render(calculate(op,number('7'),number('3'))),'unit':'number'}}
    return {'id':'independent-example','evidence':evidence,'reference':deepcopy(trace),'answer':deepcopy(trace['final'])},trace


class ConsistencyTests(unittest.TestCase):
    def test_bilingual_operator_matrix(self):
        descriptions={'add':['把两个输入值求和。','Compute the sum of both inputs.'],
                      'subtract':['用第一个操作数减去第二个操作数。','Subtract the second input from the first.'],
                      'multiply':['把两个操作数相乘。','Calculate the product of the two values.'],
                      'divide':['计算第一项与第二项的商。','Divide the first value by the second.']}
        for actual in descriptions:
            for described,texts in descriptions.items():
                for text in texts:
                    with self.subTest(actual=actual,text=text):
                        p,t=fixture(actual);t['steps'][0]['explanation']=text
                        result=evaluate(p,t)
                        self.assertEqual(result['process'],'correct' if actual==described else 'incorrect')
                        if actual!=described:
                            self.assertEqual(result['first_error']['step'],'s1')
                            self.assertEqual(result['first_error']['evidence']['subtype'],'explanation_operator_conflict')

    def test_abstains_on_negation_quote_and_multi_operation(self):
        for text in ['不要将所列两项数值相加。','本步不是求和，而是计算增长率。','先相减再除以基期。',
                     '报告写着“计算所列两项数值的乘积。”','Do not multiply both values.',
                     'Compute the sum of both inputs, then divide by two.',
                     'The prior step computed the sum of both inputs.',
                     '将本期值加上上期的相反数，得到两期差额。',
                     '减去第二项负数，相当于加上其绝对值。',
                     'Compute the difference by adding the negative prior value.',
                     '若求和，则将所列两项数值相加。','两项收入的差异值得关注。',
                     '前者乘以后者；再减去税费。','Calculate a weighted average.']:
            with self.subTest(text=text): self.assertIsNone(explicit_operation(text))

    def test_consistent_description_does_not_prove_wrong_financial_formula(self):
        p,t=fixture('add')
        t['steps'][0].update(op='multiply',result='21',explanation='Multiply both values.')
        t['final']['value']='21'
        self.assertEqual(evaluate(p,t)['process'],'uncertain')

    def test_equivalent_reordered_addition_passes(self):
        p,t=fixture();t['steps'][0]['args'].reverse();t['steps'][0]['explanation']='Compute the sum of both inputs.'
        self.assertEqual(evaluate(p,t)['process'],'correct')

    def test_verified_arithmetic_rejects_judge_tolerance_override(self):
        p,t=fixture('divide');t['steps'][0]['result']='2.3333333333333';t['final']['value']='2.3333333333333'
        rules=evaluate(p,t)
        semantic={'status':'complete','output':{'process':'incorrect','first_error_step':'s1',
                  'error_type':'arithmetic','reason':'Truncated decimal differs from exact rational.'}}
        result=combine(rules,semantic)
        self.assertEqual(result['process'],'correct')
        self.assertTrue(result['judge_conflict'])
        self.assertEqual(result['semantic'],semantic)
        self.assertEqual(rules.get('judge_conflict'),None)

    def test_semantic_or_unverified_accusation_not_overridden(self):
        p,t=fixture();rules=evaluate(p,t)
        for location,kind in [('s1','formula'),('s1','evidence_semantics'),('final','arithmetic'),(None,'arithmetic')]:
            semantic={'status':'complete','output':{'process':'incorrect','first_error_step':location,'error_type':kind,'reason':'different claim'}}
            self.assertEqual(combine(rules,semantic)['process'],'incorrect')
        rules['process']='uncertain'
        semantic={'status':'complete','output':{'process':'incorrect','first_error_step':'s1','error_type':'arithmetic','reason':'unverified'}}
        self.assertEqual(combine(rules,semantic)['process'],'incorrect')

    def test_real_arithmetic_error_survives_correct_judge(self):
        p,t=fixture();t['steps'][0]['result']='11';t['final']['value']='11'
        self.assertEqual(combine(evaluate(p,t),{'status':'complete','output':{'process':'correct'}})['process'],'incorrect')

    def test_large_integer_one_unit_error_is_not_rounding(self):
        p,t=fixture();p['evidence']['a']['value']='1000000000'
        p['reference']['steps'][0]['args'][0]['value']='1000000000'
        p['reference']['steps'][0]['result']='1000000003'
        p['reference']['final']['value']='1000000003';p['answer']['value']='1000000003'
        t=deepcopy(p['reference']);t['steps'][0]['result']='1000000002';t['final']['value']='1000000002'
        result=evaluate(p,t)
        self.assertEqual(result['process'],'incorrect')
        self.assertEqual(result['first_error']['type'],'arithmetic')

    def test_incorrect_final_prevents_arithmetic_conflict_override(self):
        p,t=fixture();rules=evaluate(p,t);rules['answer_correct']=False
        semantic={'status':'complete','output':{'process':'incorrect','first_error_step':'s1','error_type':'arithmetic','reason':'check final'}}
        self.assertEqual(combine(rules,semantic)['process'],'incorrect')

if __name__=='__main__': unittest.main()
