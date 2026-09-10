"""Inspect saved generation errors against explicit decimal-place rounding."""
from pathlib import Path
from decimal import Decimal, localcontext
from collections import Counter
import json
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from fintrace.core import number

def main():
    cases=[]
    files=list((ROOT/'runs/live/batch-v1/generation').glob('*/result.json'))
    for path in files:
        row=json.loads(path.read_text(encoding='utf-8'))
        relevant=[f for f in row.get('rules',{}).get('findings',[]) if f['type'] in ('arithmetic','answer_consistency')]
        for finding in relevant:
            ev=finding['evidence']
            expected=ev.get('expected',ev.get('last_result'))
            claimed=ev.get('actual',ev.get('final'))
            delta=abs(number(expected)-number(claimed))
            candidate=Decimal(str(claimed))
            decimal_places=max(0,-candidate.as_tuple().exponent)
            with localcontext() as ctx:
                ctx.prec=100
                exact=Decimal(number(expected).numerator)/Decimal(number(expected).denominator)
                half_quantum=Decimal(5).scaleb(-decimal_places-1)
                rounding_compatible=decimal_places>=8 and abs(exact-candidate)<=half_quantum
            cases.append({'problem_id':row['id'],'step':finding['step'],'finding_type':finding['type'],
                'expected':expected,'claimed':claimed,'absolute_difference':str(delta),'decimal_places':decimal_places,
                'compatible_with_normal_rounding_at_stated_precision':rounding_compatible,
                'audit_judgment':'Possible ordinary rounding within the prompt precision; requires separate rescore, preserve frozen verdict.' if rounding_compatible else 'Difference exceeds ordinary rounding at the stated >=8 decimal precision, or the output provides fewer than 8 decimal places.',
                'hybrid_process':row.get('hybrid',{}).get('process'),'judge':row.get('semantic',{}).get('output')})
    out={'review_type':'AI numeric review, not human','generation_records_scanned':len(files),'numeric_findings':len(cases),
         'rounding_compatible':sum(c['compatible_with_normal_rounding_at_stated_precision'] for c in cases),'cases':cases,
         'boundary':'Checks arithmetic and final consistency hard findings only. Other semantic/scale issues are not classified as rounding. Original batch records are untouched.'}
    (Path(__file__).resolve().parent/'rounding_review.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in out.items() if k!='cases'}))

if __name__=='__main__':main()
