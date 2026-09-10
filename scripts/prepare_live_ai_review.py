"""Hide scores and reference answers when reviewing generated explicit solutions."""
import hashlib
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fintrace.storage import ROOT, read_json, write_json
from fintrace.model import public_problem

base=ROOT/'runs/live/batch-v1'
ps={p['id']:p for p in read_json(base/'frozen_inputs.json')['problems']}
rows=[read_json(p) for p in (base/'generation').glob('*/result.json')]
if len(rows)!=30:
    raise ValueError('Need all 30 generation records first')
packet=[];mapping={}
for row in rows:
    code='live-'+hashlib.sha256(('ai-live-v1:'+row['id']).encode()).hexdigest()[:12]
    problem=public_problem(ps[row['id']])
    problem['id']='report-'+hashlib.sha256(row['id'].encode()).hexdigest()[:10]
    packet.append({'review_id':code,'problem':problem,'candidate':row['generation'].get('output'),
                   'generation_status':row['generation']['status']})
    mapping[code]=row['id']
write_json(ROOT/'runs/ai_review/live_packet/cases.json',sorted(packet,key=lambda r:r['review_id']))
write_json(ROOT/'runs/ai_review/live_mapping.json',mapping)
print('Prepared 30 generated-solution packets without reference or evaluator labels.')
