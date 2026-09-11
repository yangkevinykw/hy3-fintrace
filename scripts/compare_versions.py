"""Re-score published, unchanged traces; no credentials or model calls needed."""
from copy import deepcopy
from collections import Counter
import hashlib
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fintrace.storage import ROOT,read_json,write_json,load_dataset
from fintrace.evaluator import evaluate,VERSION
from fintrace.model import combine
from fintrace.benchmark import metrics,rate
from report_batch import breakdown,fmt

def run():
    old=ROOT/'runs/experiments/batch-v1'
    out=ROOT/'runs/experiments/batch-v2'
    ps={p['id']:p for p in load_dataset()}
    samples=read_json(ROOT/'data/controlled90.json')
    by_id={s['id']:s for s in samples}
    previous=read_json(old/'controlled_results.json')
    controlled=[];changes=[]
    for row in previous:
        r=deepcopy(row);s=by_id[r['id']]
        r['rules']=evaluate(ps[r['problem_id']],s['trace'])
        r['hybrid']=combine(r['rules'],r['semantic'])
        controlled.append(r)
        if r['rules']['process']!=row['rules']['process']:
            changes.append({'id':r['id'],'before':row['rules']['process'],'after':r['rules']['process'],
                            'first_error':r['rules']['first_error']})
    original_generated=read_json(old/'generation_results.json')
    generated=[];generation_changes=[]
    for row in original_generated:
        r=deepcopy(row);r['rules']=evaluate(ps[r['problem_id']],r['trace'])
        r['evaluation']=combine(r['rules'],row['evaluation']['semantic']);generated.append(r)
        if r['evaluation']['process']!=row['evaluation']['process']:
            generation_changes.append({'problem_id':r['problem_id'],'before':row['evaluation']['process'],
                                       'after':r['evaluation']['process'],
                                       'resolution':r['evaluation'].get('conflict_resolution')})
    def generation_metrics(rows):
        return {'total':len(rows),'generation_success':rate(sum(bool(r['trace']) for r in rows),len(rows)),
                'answer_accuracy':rate(sum(r['rules']['answer_correct'] is True for r in rows),len(rows)),
                'rules_process_pass':rate(sum(r['rules']['process']=='correct' for r in rows),len(rows)),
                'hybrid_process_pass':rate(sum(r['evaluation']['process']=='correct' for r in rows),len(rows)),
                'judge_success':rate(sum(r['evaluation']['semantic']['status']=='complete' for r in rows),len(rows)),
                'hybrid_uncertain':rate(sum(r['evaluation']['process']=='uncertain' for r in rows),len(rows))}
    summary=deepcopy(read_json(old/'summary.json'))
    before=deepcopy(summary)
    summary.update(evaluator_version=VERSION,scoring_version='batch-v2',
                   evaluation_kind='same_trace_rescore',parent='batch-v1',new_model_calls=0,
                   generation=generation_metrics(generated),controlled=breakdown(controlled))
    summary['generation_by_split']={s:generation_metrics([r for r in generated if r['split']==s]) for s in ('dev','test')}
    excluded=set(summary['ai_review']['reference_disputed_problems'])
    summary['generation_without_reference_disputes']=generation_metrics([r for r in generated if r['problem_id'] not in excluded])
    summary['reference_screened_controlled']=breakdown([r for r in controlled if r['problem_id'] not in excluded])
    reviews=read_json(ROOT/'runs/ai_review/independent_review/reviews.json')
    if isinstance(reviews,dict): reviews=reviews['reviews']
    mapping=read_json(ROOT/'runs/ai_review/mapping.json')
    labeled={mapping[r['review_id']]:r for r in reviews}
    exploratory=[]
    for row in controlled:
        label=labeled[row['id']]
        if label['process'] in ('correct','incorrect'):
            exploratory.append(dict(row,ai_label={'process':label['process'],'first_error':label['first_error_step'],'type':label['error_type']}))
    summary['ai_provisional_controlled']=breakdown(exploratory,'ai_label')
    # Deliberately remove the template cue: matched-operator and no-text ablations.
    texts={'add':'Compute the sum of both inputs.','subtract':'Subtract the second input from the first.',
           'multiply':'Multiply both values.','divide':'Divide the first input by the second.'}
    ablations={}
    for name in ('without_explanations','aligned_explanations'):
        rows=[]
        for s in samples:
            trace=deepcopy(s['trace'])
            for step in trace['steps']:
                step['explanation']='' if name=='without_explanations' else texts[step['op']]
            rows.append(dict(s,trace=trace,evaluation=evaluate(ps[s['problem_id']],trace)))
        ablations[name]={'overall':metrics(rows),'rows':rows}
    offline_rows=[dict(by_id[r['id']],evaluation=r['rules'],call_status='complete') for r in controlled]
    offline={'version':VERSION,'overall':metrics(offline_rows),
             'by_split':{s:metrics([r for r in offline_rows if r['split']==s]) for s in ('dev','test')},
             'by_error':{k:metrics([r for r in offline_rows if r['label']['type']==k]) for k in sorted({r['label']['type'] for r in offline_rows if r['label']['type']})},
             'pending':[]}
    summary['improvement']={'before':{'controlled':before['controlled'],'generation':before['generation']},
                            'controlled_changes':changes,'generation_changes':generation_changes,
                            'ablation':{k:v['overall'] for k,v in ablations.items()},
                            'scope':'Retrospective regression on unchanged data, not a new blind test; explanation-template-sensitive improvement.'}
    summary['hybrid_judge_conflicts']=[{'id':r['id'],'resolution':r['hybrid'].get('conflict_resolution')} for r in controlled if r['hybrid'].get('judge_conflict')]
    summary['generation_judge_conflicts']=[{'id':r['problem_id'],'resolution':r['evaluation'].get('conflict_resolution')} for r in generated if r['evaluation'].get('judge_conflict')]
    for name,obj in [('summary.json',summary),('controlled_results.json',controlled),('generation_results.json',generated),
                     ('rules_summary.json',offline),('rules_results.json',offline_rows),('ablations.json',ablations)]:
        write_json(out/name,obj)
    write_json(out/'manifest.json',{'evaluator_version':VERSION,'parent':'batch-v1','new_model_calls':0,
               'input_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
                    [ROOT/'data/finqa30.json',ROOT/'data/controlled90.json',old/'controlled_results.json',old/'generation_results.json']},
               'code_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
                    [*sorted((ROOT/'fintrace').glob('*.py')),Path(__file__)]}})
    lines=['# FinTrace v0.4 对照实验','',
           '对相同 30 道题、90 个受控过程和 30 份已保存的 Hy3 解答重新评分。数据、原始标签、候选解答与语义评审响应保持不变；本次不新增模型调用。原始批次保存在相邻的 batch-v1 目录。','',
           '## 改进内容','',
           '1. 核验明确的单步计算说明与实际运算是否一致。仅解析完整、肯定的单运算描述，否定、引用、多步总述等复杂文本不触发硬判。',
           '2. 对已通过规则和答案检查的步骤，按既定容差复核语义评审的算术指控，保留原始评审和冲突解决依据。',
           '3. 整数结果采用精确比较，避免相对容差吞掉大整数的一单位错误。','',
           '## 同样本对照','',
           '| 指标 | v0.3 | v0.4 |','| --- | --- | --- |']
    for mode,title in [('rules','规则'),('hybrid','混合')]:
        for key,label in [('detection','错误检出'),('localization','首错定位'),('false_positive','参考过程误报')]:
            lines.append(f'| {title}{label} | {fmt(before["controlled"][mode]["overall"][key])} | {fmt(summary["controlled"][mode]["overall"][key])} |')
    for key,label in [('hybrid_process_pass','真实解答混合过程通过'),('answer_accuracy','真实答案符合原始参考')]:
        lines.append(f'| {label} | {fmt(before["generation"][key])} | {fmt(summary["generation"][key])} |')
    lines+=['','## 贡献与消融','',
            f'规则新增检出的 {len(changes)} 个过程均存在计算说明与运算符矛盾。该提升体现说明一致性检查的作用，不能外推为一般财务公式推理能力。','',
            '| 同一组样本的说明变体 | 规则检出 |','| --- | --- |',
            f'| 原始说明 | {fmt(summary["controlled"]["rules"]["overall"]["detection"])} |',
            *[f'| {title} | {fmt(ablations[key]["overall"]["detection"])} |' for key,title in [('without_explanations','移除说明'),('aligned_explanations','说明同步改为当前运算')]],'',
            '消融变体只用于检查规则的适用范围，未替换原始主实验。它表明：当错误公式与说明一致时，规则仍需依赖进一步语义判断。','',
            '## 真实解答误判修复','',
            *[f'- `{r["problem_id"]}`：{r["before"]} → {r["after"]}。{r["resolution"]["reason"]}' for r in generation_changes],
            '', '原参考答案符合率保持 20/30。年份、范围、金额尺度与正负方向争议仍按原有口径独立记录。',
            '', '## 复现','', '```sh','python -X utf8 scripts/compare_versions.py','python -X utf8 -m unittest discover -s tests -v','```','',
            '本次属于对已见样本的回归分析。接口成功与失败状态沿用原批次，失败不因本地重评而变成成功；调用覆盖见 summary.json。所有版本的分母保持一致。']
    (out/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print({'rules_detection':summary['controlled']['rules']['overall']['detection'],
           'hybrid_detection':summary['controlled']['hybrid']['overall']['detection'],
           'hybrid_pass':summary['generation']['hybrid_process_pass'],'changed_controlled':len(changes),
           'changed_generation':len(generation_changes),'ablation_detection':{k:v['overall']['detection'] for k,v in ablations.items()}})

if __name__=='__main__': run()
