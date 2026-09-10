"""Independent offline AI audit. No credentials, no network, no source mutations."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from fintrace.evaluator import evaluate
from fintrace.core import number, render, close
from fintrace.storage import load_dataset
from fintrace.model import judge
from fintrace.benchmark import metrics

OUT = Path(__file__).resolve().parent

def main(output='probe_results.json'):
    p = {'id':'audit_amplification','evidence':{'a':{'value':'1','text':'amount'},'b':{'value':'1000000','text':'scale'}},'answer':{'value':'1','unit':'number'}}
    def ev(k): return {'kind':'evidence','ref':k,'value':p['evidence'][k]['value']}
    t = {'steps':[{'id':'s1','op':'divide','args':[ev('a'),ev('b')],'result':'0.000001'}, {'id':'s2','op':'multiply','args':[{'kind':'step','ref':'s1'},ev('b')],'result':'1'}], 'final':{'value':'1','unit':'number'}}
    p['reference'] = deepcopy(t)
    t['steps'][0]['result']='0.000002'; t['steps'][1]['result']='2'; t['final']['value']='2'
    amplified = {'problem':p,'trace':t,'evaluation':evaluate(p,t)}

    p = next(x for x in load_dataset() if x['answer']['unit']=='percent')
    t = deepcopy(p['reference'])
    t['final']['value'] = render(number(t['final']['value'])+number('0.0001'))
    percent = {'problem_id':p['id'],'answer':p['answer'],'candidate_final':t['final'], 'evaluation':evaluate(p,t), 'expected_source_scale_equal':close(number(t['final']['value']),number(p['answer']['value']))}

    p = {'id':'audit_judge','question':'x','table':[],'texts':[],'evidence':{},'reference':{}}
    t = {'steps':[{'id':'s1'}]}
    obj = {'process':'correct','first_error_step':None,'error_type':'formula','reason':'candidate is correct','evidence_refs':[]}
    with patch('fintrace.model.request_model', return_value={'status':'complete','output':obj}):
        protocol = judge(p,t,OUT/'never_written')
    row = {'label':{'process':'incorrect','first_error':'s1','type':'formula'},'evaluation':{'process':'correct','first_error':{'step':None,'type':'formula'},'answer_correct':False,'correct_answer_invalid_process':False}}
    contradictory = {'judge':protocol,'metric':metrics([row])}

    abstain = deepcopy(row)
    abstain['evaluation'].update(process='uncertain',first_error=None)
    denominator = metrics([abstain])
    hashes = {str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted((ROOT/'fintrace').glob('*.py'))}
    result = {'review_type':'AI independent evaluator audit, not human audit','source_hashes':hashes,'amplification':amplified,'percentage_scale':percent,'contradictory_judge':contradictory,'abstention_denominator':denominator}
    (OUT/output).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'amplification_process':amplified['evaluation']['process'],'percent_answer_correct':percent['evaluation']['answer_correct'],'judge_status':protocol['status'],'type_numerator':contradictory['metric']['error_type']['numerator'],'abstention_denominator':denominator['detection']['denominator']},ensure_ascii=False))

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='probe_results.json')
    args = parser.parse_args()
    main(args.output)
