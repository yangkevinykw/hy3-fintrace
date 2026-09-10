"""Create a shuffled label-free review packet; mapping stays outside the packet."""
import hashlib
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fintrace.storage import ROOT, load_dataset, read_json, write_json
from fintrace.model import public_problem

def main():
    problems = {p['id']: p for p in load_dataset()}
    samples = read_json(ROOT / 'data/controlled90.json')
    mapping, packet = {}, []
    for s in samples:
        code = 'case-' + hashlib.sha256(('ai-review-v1:' + s['id']).encode()).hexdigest()[:12]
        p = public_problem(problems[s['problem_id']])
        p['id'] = 'report-' + hashlib.sha256(s['problem_id'].encode()).hexdigest()[:10]
        packet.append({'review_id': code, 'problem': p, 'candidate': s['trace']})
        mapping[code] = s['id']
    packet.sort(key=lambda x: x['review_id'])
    write_json(ROOT / 'runs/ai_review/packet/cases.json', packet)
    write_json(ROOT / 'runs/ai_review/mapping.json', mapping)
    write_json(ROOT / 'runs/ai_review/packet/manifest.json', {
        'reviewer_type': 'ai', 'human_review': 'pending', 'count': len(packet),
        'sha256': hashlib.sha256(json.dumps(packet, sort_keys=True).encode()).hexdigest(),
        'omitted': ['labels', 'reference', 'standard_answer', 'mutation', 'evaluator_results'],
        'limitation': 'Label-hidden packet, not an independently secured human blind study.'})
    print('Prepared 90 label-hidden AI review cases.')

if __name__ == '__main__':
    main()
