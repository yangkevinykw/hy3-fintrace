"""Bounded, resumable real experiment. A single judge draw feeds both comparison arms."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fintrace.storage import ROOT, load_dataset, read_json, write_json
from fintrace.model import config, solve, judge, combine, new_run_id, SOLVER_PROMPT, JUDGE_PROMPT
from fintrace.evaluator import evaluate
from fintrace.benchmark import metrics, rate

def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

def judge_only(rules, semantic):
    obj = semantic.get('output', {}) if semantic.get('status') == 'complete' else {}
    process = obj.get('process', 'uncertain')
    return {'mode': 'judge', 'process': process, 'answer_correct': rules['answer_correct'],
            'first_error': {'step': obj.get('first_error_step'), 'type': obj.get('error_type')},
            'correct_answer_invalid_process': rules['answer_correct'] is True and process == 'incorrect'}

def run(args):
    cfg, ready = config()
    if not ready:
        raise ValueError('Hy3 is not configured')
    problems = load_dataset()
    samples = read_json(ROOT / 'data/controlled90.json')
    by_id = {p['id']: p for p in problems}
    code = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'fintrace').glob('*.py'))}
    frozen = {'problems': problems, 'samples': samples, 'code': code,
              'solver_prompt': SOLVER_PROMPT, 'judge_prompt': JUDGE_PROMPT,
              'model': cfg['HY3_MODEL'], 'endpoint_sha256': digest(cfg['HY3_BASE_URL']),
              'max_tokens': cfg.get('HY3_MAX_TOKENS', '8192'), 'protocol': 'batch-v1-paired-judge',
              'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    stamp = digest(frozen)
    path = args.out / 'manifest.json'
    if path.exists():
        if not args.resume or read_json(path)['fingerprint'] != stamp:
            raise ValueError('Existing run needs --resume with unchanged data, prompts and code; otherwise select a new directory.')
    else:
        write_json(path, {'fingerprint': stamp, 'created_at': datetime.now(timezone.utc).isoformat(),
                         'model': cfg['HY3_MODEL'], 'counts': {'generation':30,'controlled_judge':90,'repeat_judge':24},
                         'human_review':'pending', 'evaluation_protocol':'fixed before batch; not preregistered blind evaluation'})
        write_json(args.out/'frozen_inputs.json', frozen)
    # Balanced repeats: four cases of each source, selected without seeing predictions.
    repeat_samples = []
    for variant in sorted({s['id'].rsplit('::',1)[-1] for s in samples}):
        group = sorted([s for s in samples if s['id'].rsplit('::',1)[-1]==variant], key=lambda s: digest('repeat-v1:'+s['id']))
        repeat_samples.extend(group[:4])
    if len(repeat_samples) != 12:
        raise ValueError('Expected 12 repeated cases from three balanced variants')
    jobs = [('generation', p['id'], p) for p in problems]
    jobs += [('controlled', s['id'], s) for s in samples]
    jobs += [(f'repeat{trial}', s['id'], s) for s in repeat_samples for trial in (1,2)]

    def worker(job):
        kind, identity, item = job
        folder = args.out / kind / digest(identity)[:16]
        result_path = folder / 'result.json'
        if result_path.exists() and read_json(result_path).get('status') == 'complete':
            return read_json(result_path)
        attempt = folder / new_run_id(identity)
        if kind == 'generation':
            p = item
            response = solve(p, attempt)
            row = {'kind':kind,'id':identity,'problem_id':identity,'split':p['split'],
                   'difficulty':p['difficulty'], 'generation':response, 'status':response['status']}
            if response['status'] == 'complete':
                rules = evaluate(p, response['output'])
                semantic = judge(p, response['output'], attempt)
                row.update(rules=rules, semantic=semantic, hybrid=combine(rules,semantic),
                           status='complete' if semantic['status']=='complete' else 'judge_failed')
        else:
            p = by_id[item['problem_id']]
            rules = evaluate(p, item['trace'])
            semantic = judge(p, item['trace'], attempt)
            row = {'kind':kind,'id':identity,'problem_id':p['id'],'split':p['split'],'difficulty':p['difficulty'],
                   'source':item['source'],'label':item['label'],'rules':rules,'semantic':semantic,
                   'judge':judge_only(rules,semantic),'hybrid':combine(rules,semantic),'status':semantic['status']}
        write_json(attempt/'result.json', row)
        write_json(result_path, row)
        return row

    rows = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(worker, j): j for j in jobs}
        for future in as_completed(futures):
            row = future.result()
            rows.append(row)
            print(f"{len(rows)}/{len(jobs)} {row['kind']} {row['id']}: {row['status']}", flush=True)
            write_json(args.out/'progress.json', {'finished':len(rows),'total':len(jobs),
                       'statuses':dict(Counter(r['status'] for r in rows))})
    rows.sort(key=lambda r:(r['kind'],r['id']))
    write_json(args.out/'results.json', rows)
    print(json.dumps({'finished':len(rows),'statuses':dict(Counter(r['status'] for r in rows))}),flush=True)

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',type=Path,default=ROOT/'runs/live/batch-v1')
    parser.add_argument('--workers',type=int,choices=(1,2,3),default=3)
    parser.add_argument('--resume',action='store_true')
    run(parser.parse_args())
