"""Recount saved batch results independently of fintrace metric/report code."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent

def read(path): return json.loads(path.read_text(encoding='utf-8'))
def fraction(n,d): return {'numerator':n,'denominator':d,'rate':round(n/d,6) if d else None}
def digest(obj): return hashlib.sha256(json.dumps(obj,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def recount(rows, mode):
    wrong=[r for r in rows if r['label']['process']=='incorrect']
    clean=[r for r in rows if r['label']['process']=='correct']
    located=[r for r in wrong if r['label']['first_error'] is not None]
    cair=[r for r in wrong if r[mode]['answer_correct'] is True]
    def first(r,key): return (r[mode].get('first_error') or {}).get(key)
    return {'count':len(rows),
        'detection':fraction(sum(r[mode]['process']=='incorrect' for r in wrong),len(wrong)),
        'false_positive':fraction(sum(r[mode]['process']=='incorrect' for r in clean),len(clean)),
        'localization':fraction(sum(r[mode]['process']=='incorrect' and first(r,'step')==r['label']['first_error'] for r in located),len(located)),
        'error_type':fraction(sum(r[mode]['process']=='incorrect' and first(r,'type')==r['label']['type'] for r in wrong),len(wrong)),
        'cair_recall':fraction(sum(r[mode]['process']=='incorrect' for r in cair),len(cair)),
        'uncertain':fraction(sum(r[mode]['process']=='uncertain' for r in rows),len(rows))}

def check(batch):
    rows=read(batch/'results.json'); frozen=read(batch/'frozen_inputs.json'); manifest=read(batch/'manifest.json')
    expected={( 'generation',p['id']) for p in frozen['problems']} | {('controlled',s['id']) for s in frozen['samples']}
    actual=Counter((r['kind'],r['id']) for r in rows)
    checks={'manifest_fingerprint':digest(frozen)==manifest['fingerprint'], 'row_count_144':len(rows)==144,
            'unique_kind_ids':len(actual)==len(rows),'base_cases_present':expected.issubset(actual),
            'source_hashes_match':all(hashlib.sha256((ROOT/'fintrace'/name).read_bytes()).hexdigest()==sha for name,sha in frozen['code'].items())}
    frozen_samples={s['id']:s for s in frozen['samples']}
    checks['frozen_labels_preserved']=all(r['label']==frozen_samples[r['id']]['label'] for r in rows if r['kind']!='generation')
    controlled=[r for r in rows if r['kind']=='controlled']; gen=[r for r in rows if r['kind']=='generation']
    def compare(group):
        return {mode:{split:recount([r for r in group if split=='all' or r['split']==split],mode) for split in ['all','dev','test']} for mode in ['rules','judge','hybrid']}
    comparisons=compare(controlled)
    reviews=read(ROOT/'runs/ai_review/independent_review/reviews.json')
    if isinstance(reviews,dict): reviews=reviews['reviews']
    mapping=read(ROOT/'runs/ai_review/mapping.json')
    reviewed={mapping[r['review_id']]:r for r in reviews}
    checks['ai_review_exact_coverage']=len(reviews)==90 and len(reviewed)==90 and set(reviewed)==set(frozen_samples)
    live_reviews=read(ROOT/'runs/ai_review/live_review/reviews.json')
    if isinstance(live_reviews,dict): live_reviews=live_reviews['reviews']
    live_mapping=read(ROOT/'runs/ai_review/live_mapping.json')
    live_reviewed={live_mapping[r['review_id']]:r for r in live_reviews}
    checks['generation_ai_review_exact_coverage']=len(live_reviews)==30 and len(live_reviewed)==30 and set(live_reviewed)=={r['id'] for r in gen}
    live_ai={'total':30,'answer_correct':fraction(sum(r['answer_correct'] is True for r in live_reviews),30),
             'answer_incorrect':fraction(sum(r['answer_correct'] is False for r in live_reviews),30),
             'answer_uncertain':fraction(sum(r['answer_correct'] is None for r in live_reviews),30),
             'process_counts':dict(Counter(r['process'] for r in live_reviews)),
             'original_answer_vs_ai_answer':dict(Counter(str(r.get('rules',{}).get('answer_correct'))+' / '+str(live_reviewed[r['id']]['answer_correct']) for r in gen))}
    error_files=list(batch.rglob('*_error_*.json'))
    transport_errors=dict(Counter(str(read(f).get('http_status','network')) for f in error_files))
    transport_responses=len(list(batch.rglob('*_response_*.json')))
    excluded={frozen_samples[key]['problem_id'] for key,r in reviewed.items() if key.endswith('::clean') and r['process']!='correct'}
    screened=[r for r in controlled if r['problem_id'] not in excluded]
    ai_rows=[dict(r,label={'process':reviewed[r['id']]['process'],'first_error':reviewed[r['id']]['first_error_step'],'type':reviewed[r['id']]['error_type']}) for r in controlled if reviewed[r['id']]['process'] in ('correct','incorrect')]
    sensitivity=compare(screened)
    exploratory=compare(ai_rows)
    live={split:{} for split in ['all','dev','test']}
    for split in live:
        selected=[r for r in gen if split=='all' or r['split']==split]
        live[split]={'total':len(selected),'statuses':dict(Counter(r['status'] for r in selected)),
            'generation_success':fraction(sum(r['generation']['status']=='complete' for r in selected),len(selected)),
            'answer_accuracy':fraction(sum(r.get('rules',{}).get('answer_correct') is True for r in selected),len(selected)),
            'rules_process_pass':fraction(sum(r.get('rules',{}).get('process')=='correct' for r in selected),len(selected)),
            'hybrid_process_pass':fraction(sum(r.get('hybrid',{}).get('process')=='correct' for r in selected),len(selected)),
            'judge_success':fraction(sum(r.get('semantic',{}).get('status')=='complete' for r in selected),len(selected))}
    groups={r['id']:[] for r in rows if r['kind'].startswith('repeat')}
    for r in rows:
        if r['id'] in groups and r['kind']!='generation': groups[r['id']].append(r)
    checks['repeats_twelve_groups_of_three']=len(groups)==12 and all(len(g)==3 for g in groups.values())
    checks['balanced_repeat_variants']=dict(Counter(key.rsplit('::',1)[1] for key in groups))=={'clean':4,'local':4,'challenge':4}
    full_repeat=[g for g in groups.values() if all(r['semantic']['status']=='complete' for r in g)]
    stability={'groups_total':len(groups),'groups_all_calls_complete':len(full_repeat),
        'same_process':fraction(sum(len({r['semantic']['output']['process'] for r in g})==1 for g in full_repeat),len(groups)),
        'same_process_first':fraction(sum(len({(r['semantic']['output']['process'],r['semantic']['output']['first_error_step']) for r in g})==1 for g in full_repeat),len(groups)),
        'same_process_type':fraction(sum(len({(r['semantic']['output']['process'],r['semantic']['output']['error_type']) for r in g})==1 for g in full_repeat),len(groups)),
        'same_process_first_type':fraction(sum(len({(r['semantic']['output']['process'],r['semantic']['output']['first_error_step'],r['semantic']['output']['error_type']) for r in g})==1 for g in full_repeat),len(groups)),
        'unstable_groups':[{'id':g[0]['id'],'verdicts':[{'kind':r['kind'],**{k:r['semantic']['output'].get(k) for k in ['process','first_error_step','error_type']}} for r in g]} for g in full_repeat if len({(r['semantic']['output']['process'],r['semantic']['output']['first_error_step'],r['semantic']['output']['error_type']) for r in g})>1]}
    report={'review_type':'independent_ai_recount_not_human','batch':str(batch),'checks':checks,
        'kinds':dict(Counter(r['kind'] for r in rows)),'statuses':dict(Counter(r['status'] for r in rows)),
        'controlled':comparisons,'generation':live,'repeat_stability':stability,
        'generation_ai_review':live_ai,'http_errors':transport_errors,'transport_responses':transport_responses,
        'stability_interpretation':'No conclusion about stability when zero groups have three successful calls. Zero full-denominator confirmed-agreement counts measure missing evidence, not observed disagreement.' if not full_repeat else 'Agreement counts require three successful draws; failed groups remain in coverage denominator.',
        'reference_screened_controlled':sensitivity,'ai_provisional_controlled':exploratory,
        'review_groups':{'excluded_problem_ids':sorted(excluded),'screened_count':len(screened),'ai_decisive_count':len(ai_rows)},
        'note':'Original constructed labels, reference-screened sensitivity, and decisive AI-label exploration are separate. Failed/uncertain predictions remain in each defined group denominator; uncertain AI labels are excluded only from AI-label exploration. Repeat agreement keeps failed groups in denominator.'}
    published_path=ROOT/'runs/experiments/batch-v1/summary.json'
    if published_path.exists():
        published=read(published_path)
        for key,value in [('controlled',comparisons),('reference_screened_controlled',sensitivity),('ai_provisional_controlled',exploratory)]:
            matches=[]
            for mode in value:
                for split in ['all','dev','test']:
                    expected_report=published[key][mode]['overall'] if split=='all' else published[key][mode]['by_split'][split]
                    matches.extend(value[mode][split][metric]==expected_report[metric] for metric in value[mode][split])
            checks['published_'+key]=all(matches)
        checks['published_generation']=all(live['all'][key]==published['generation'][key] for key in ['total','generation_success','answer_accuracy','rules_process_pass','hybrid_process_pass','judge_success'])
        checks['published_generation_ai_review']=all(live_ai[key]==published['generation_ai_review'][key] for key in ['total','answer_correct','answer_incorrect','answer_uncertain','process_counts'])
        checks['published_stability']=all(stability[a]==published['stability'][b] for a,b in [('same_process','process_stable'),('same_process_first','location_stable'),('same_process_type','type_stable')])
        checks['published_status']=published['status']==('partial' if any(r['status']!='complete' for r in rows) else 'complete')
        checks['published_errors']=published['http_errors']==transport_errors and published['failed_jobs']==sum(r['status']!='complete' for r in rows)
        checks['published_response_count']=published['transport_responses']==transport_responses
    (OUT/'batch_recount.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'checks':checks,'kinds':report['kinds'],'statuses':report['statuses'],'generation_all':live['all'],'repeat':{k:v for k,v in stability.items() if k!='unstable_groups'}},ensure_ascii=False,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--batch',type=Path,default=ROOT/'runs/live/batch-v1')
    check(parser.parse_args().batch)
