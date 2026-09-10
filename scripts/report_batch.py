"""Report real calls, paired controlled comparisons, AI review and disagreement."""
from __future__ import annotations
from collections import Counter
from datetime import datetime, timezone
import csv
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fintrace.storage import ROOT, read_json, write_json
from fintrace.benchmark import metrics, rate

MODES = ('rules', 'judge', 'hybrid')

def breakdown(rows, label_key='label'):
    result = {}
    for mode in MODES:
        selected = [dict(r, label=r[label_key], evaluation=r[mode]) for r in rows]
        result[mode] = {'overall': metrics(selected),
                        'by_split': {s: metrics([r for r in selected if r['split']==s]) for s in ('dev','test')}}
    return result

def fmt(x):
    return f"{x['numerator']}/{x['denominator']}" + (f" ({x['rate']:.1%})" if x['rate'] is not None else ' (不适用)')

def main():
    source = ROOT/'runs/live/batch-v1'
    target = ROOT/'runs/experiments/batch-v1'
    all_rows = read_json(source/'results.json')
    frozen = read_json(source/'frozen_inputs.json')
    problems = {p['id']:p for p in frozen['problems']}
    samples = {s['id']:s for s in frozen['samples']}
    generated = [r for r in all_rows if r['kind']=='generation']
    controlled = [r for r in all_rows if r['kind']=='controlled']
    if len(generated)!=30 or len(controlled)!=90:
        raise ValueError('Incomplete primary experiment')
    valid = [r for r in generated if r['generation']['status']=='complete']
    def generation_metrics(rows):
        return {'total':len(rows), 'generation_success':rate(sum(r['generation']['status']=='complete' for r in rows),len(rows)),
                'answer_accuracy':rate(sum(r.get('rules',{}).get('answer_correct') is True for r in rows),len(rows)),
                'rules_process_pass':rate(sum(r.get('rules',{}).get('process')=='correct' for r in rows),len(rows)),
                'hybrid_process_pass':rate(sum(r.get('hybrid',{}).get('process')=='correct' for r in rows),len(rows)),
                'judge_success':rate(sum(r.get('semantic',{}).get('status')=='complete' for r in rows),len(rows)),
                'hybrid_uncertain':rate(sum(r.get('hybrid',{}).get('process')=='uncertain' for r in rows),len(rows))}
    review_path = ROOT/'runs/ai_review/independent_review/reviews.json'
    reviews = read_json(review_path)
    if isinstance(reviews,dict):
        reviews=reviews['reviews']
    mapping=read_json(ROOT/'runs/ai_review/mapping.json')
    if len(reviews)!=90 or len({r['review_id'] for r in reviews})!=90 or set(r['review_id'] for r in reviews)!=set(mapping):
        raise ValueError('AI review coverage must be exactly 90 unique cases')
    reviewed={mapping[r['review_id']]:r for r in reviews}
    live_reviews=read_json(ROOT/'runs/ai_review/live_review/reviews.json')
    if isinstance(live_reviews,dict):
        live_reviews=live_reviews['reviews']
    live_mapping=read_json(ROOT/'runs/ai_review/live_mapping.json')
    if len(live_reviews)!=30 or set(r['review_id'] for r in live_reviews)!=set(live_mapping):
        raise ValueError('Need exactly 30 live AI reviews')
    live_reviewed={live_mapping[r['review_id']]:r for r in live_reviews}
    disagreements=[]
    excluded=set()
    for identity, review in reviewed.items():
        s=samples[identity]
        agrees=(review['process']==s['label']['process'])
        location_agrees=review['first_error_step']==s['label']['first_error']
        if not agrees or not location_agrees:
            disagreements.append({'sample_id':identity,'problem_id':s['problem_id'],'original_label':s['label'],
                                  'ai_review':review,'process_agrees':agrees,'location_agrees':location_agrees})
        if identity.endswith('::clean') and review['process']!='correct':
            excluded.add(s['problem_id'])
    eligible=[r for r in controlled if r['problem_id'] not in excluded]
    ai_labeled=[]
    for r in controlled:
        review=reviewed[r['id']]
        if review['process'] not in ('correct','incorrect'):
            continue
        ai_labeled.append(dict(r, ai_label={'process':review['process'],'first_error':review['first_error_step'],
                                           'type':review['error_type']}))
    repeats=[]
    base={r['id']:r for r in controlled}
    repeat_ids=sorted({r['id'] for r in all_rows if r['kind'].startswith('repeat')})
    if len(repeat_ids)!=12:
        raise ValueError('Expected exactly 12 stability cases')
    for identity in repeat_ids:
        draws=[base[identity]]+[r for r in all_rows if r['id']==identity and r['kind'].startswith('repeat')]
        if len(draws)!=3:
            raise ValueError('Each stability case must have three draws')
        okay=all(r['semantic']['status']=='complete' for r in draws)
        votes=[r['semantic'].get('output',{}) for r in draws]
        repeats.append({'sample_id':identity,'draws':len(draws),'complete':okay,
                        'process_stable':okay and len({v.get('process') for v in votes})==1,
                        'location_stable':okay and len({(v.get('process'),v.get('first_error_step')) for v in votes})==1,
                        'type_stable':okay and len({(v.get('process'),v.get('error_type')) for v in votes})==1,
                        'votes':votes})
    response_files=list(source.rglob('*_response_*.json'))
    error_files=list(source.rglob('*_error_*.json'))
    http_errors=dict(Counter(str(read_json(p).get('http_status','network')) for p in error_files))
    failed=[r for r in all_rows if r['status']!='complete']
    usage=Counter()
    for path in response_files:
        u=read_json(path).get('usage') or {}
        for k in ('prompt_tokens','completion_tokens','total_tokens'):
            usage[k]+=u.get(k,0) or 0
    conflicts=[r['id'] for r in controlled if r['hybrid'].get('judge_conflict')]
    reference_issues=[{'problem_id':pid,'question':problems[pid]['question'],
                      'review':reviewed[pid+'::clean']} for pid in sorted(excluded)]
    summary={'created_at':datetime.now(timezone.utc).isoformat(),
             'manifest':read_json(source/'manifest.json'),'status':'partial' if failed else 'complete','human_review':'pending',
             'failed_jobs':len(failed),'http_errors':http_errors,
             'jobs_by_kind':{kind:dict(Counter(r['status'] for r in all_rows if r['kind']==kind)) for kind in sorted({r['kind'] for r in all_rows})},
             'generation':generation_metrics(generated),
             'generation_by_split':{s:generation_metrics([r for r in generated if r['split']==s]) for s in ('dev','test')},
             'generation_without_reference_disputes':generation_metrics([r for r in generated if r['problem_id'] not in excluded]),
             'generation_ai_review':{'reviewer_type':'ai','total':30,
                 'answer_correct':rate(sum(r['answer_correct'] is True for r in live_reviews),30),
                 'answer_incorrect':rate(sum(r['answer_correct'] is False for r in live_reviews),30),
                 'answer_uncertain':rate(sum(r['answer_correct'] is None for r in live_reviews),30),
                 'process_counts':dict(Counter(r['process'] for r in live_reviews)),
                 'note':'Same AI reviewer saw controlled solutions earlier; second-stage label-hidden review, not new human blind evaluation.'},
             'controlled':breakdown(controlled),
             'reference_screened_controlled':breakdown(eligible),
             'ai_provisional_controlled':breakdown(ai_labeled,'ai_label'),
             'ai_provisional_answer_basis':'Original FinQA answer matching is retained for answer_correct and CAIR subset; only process/location/type labels are replaced by AI provisional labels.',
             'ai_review':{'reviewer_type':'ai','total':len(reviews),'process_counts':dict(Counter(r['process'] for r in reviews)),
                          'decisive_count':len(ai_labeled),'disagreement_count':len(disagreements),
                          'process_disagreement_count':sum(not r['process_agrees'] for r in disagreements),
                          'reference_disputed_problems':sorted(excluded),'reference_issues':reference_issues,
                          'human_review':'pending'},
             'stability':{'cases':len(repeats),'draws_per_case':3,
                          'complete_cases':sum(r['complete'] for r in repeats),
                          **{key:rate(sum(r[key] for r in repeats),len(repeats)) for key in ('process_stable','location_stable','type_stable')}},
             'call_statuses':dict(Counter(r['status'] for r in all_rows)),
             'transport_responses':len(response_files),'usage':dict(usage),'hybrid_judge_conflicts':conflicts,
             'limitations':['AI 复核不是独立人工金标；原始标签保留，不覆盖争议。',
                            '同一 Hy3 解题与评审存在相关偏差；三组共用同一次评审。',
                            '按 AI 对参考过程的意见筛除题目仅为敏感性分析，不是重新挑选的主实验。',
                            '开发/评测按报告隔离，但没有预注册或外部盲测。']}
    write_json(target/'summary.json',summary)
    write_json(target/'review_disagreements.json',disagreements)
    write_json(target/'stability.json',repeats)
    write_json(target/'controlled_results.json',controlled)
    cases=[{'problem_id':r['problem_id'],'split':r['split'],'status':r['status'],
            'trace':r['generation'].get('output'),'rules':r.get('rules'),'evaluation':r.get('hybrid'),
            'ai_review':live_reviewed[r['problem_id']],
            'reference_disputed':r['problem_id'] in excluded} for r in generated]
    write_json(target/'generation_results.json',cases)
    with (target/'comparison.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['sample_id','split','original_process','ai_process','rules','judge','hybrid','call_status'])
        for r in controlled:
            w.writerow([r['id'],r['split'],r['label']['process'],reviewed[r['id']]['process'],
                        *[r[m]['process'] for m in MODES],r['status']])
    lines=['# Hy3 FinTrace 批量实验报告','',
           f"运行状态：{'部分调用失败，待恢复接口后续跑' if failed else '全部作业成功完成'}。失败作业 {len(failed)}/144；HTTP 错误记录 {http_errors}。",'',
           '本轮计划覆盖 30 道题、90 个受控过程及 12 例三次评审，全部作业尝试均已记录，成功覆盖与失败状态见下文。AI 子智能体完成 90 条标签隐藏复核，另有独立 AI 评测审计；真人复核仍待完成。','',
           '## 真实模型解答','',
           '|指标|全部 30 题|开发集|评测集|','|---|---|---|---|']
    for key,title in [('generation_success','格式有效解答'),('answer_accuracy','答案与 FinQA 程序一致'),('rules_process_pass','规则过程通过'),('hybrid_process_pass','混合过程通过'),('judge_success','语义评审成功')]:
        lines.append('|'+title+'|'+ '|'.join(fmt(m[key]) for m in [summary['generation'],summary['generation_by_split']['dev'],summary['generation_by_split']['test']])+'|')
    lines+=['','答案准确率是对原始 FinQA 程序结果的符合率；存在下文列出的参考争议。过程通过率是评估器判断，不等同独立金标准确率。','',
            f"第二阶段 AI 对真实答案的复核：正确 {fmt(summary['generation_ai_review']['answer_correct'])}，错误 {fmt(summary['generation_ai_review']['answer_incorrect'])}，无法确定 {fmt(summary['generation_ai_review']['answer_uncertain'])}。过程判断：{summary['generation_ai_review']['process_counts']}。",'',
            '此为同一 AI 审阅者的第二阶段复核，已见过同题受控解答；没有接收原标签和评估结果，不是全新真人盲评。逐例见 runs/ai_review/live_review/reviews.json。','',
            '## 三组受控对照：原始构造标签','',
            '|指标|规则|Hy3 Judge|混合|','|---|---|---|---|']
    for key,title in [('detection','错误检出'),('localization','首错定位'),('error_type','错误类型'),('false_positive','正确过程误报'),('cair_recall','答案对过程错检出'),('uncertain','无法确定')]:
        lines.append('|'+title+'|'+'|'.join(fmt(summary['controlled'][m]['overall'][key]) for m in MODES)+'|')
    lines+=['','三个评估组使用相同样本。Judge 与混合组共用一次语义响应，排除额外抽样差异；所有失败和弃权保留在主分母中。','',
            '## AI 复核与参考争议','',
            f"90 条复核中：{dict(Counter(r['process'] for r in reviews))}；与构造标签的过程判断不同 {summary['ai_review']['process_disagreement_count']} 条。",'',
            f'AI 对 {len(excluded)} 道题的参考过程提出错误或不确定意见。原始标签与预测均完整保留。', '',
            '|争议题|AI 意见|依据|','|---|---|---|']
    for issue in reference_issues:
        r=issue['review'];lines.append(f"|{issue['problem_id']}|{r['process']}|{r['reason'].replace('|','/').replace(chr(10),' ')}|")
    lines+=['','### 排除参考争议题的敏感性分析','',
            f"保留 {len(eligible)//3} 道题 / {len(eligible)} 个过程，筛选仅依据 AI 对参考过程的意见。不能将筛后数字替代全量主结果。",'',
            '|指标|规则|Hy3 Judge|混合|','|---|---|---|---|']
    for key,title in [('detection','错误检出'),('localization','首错定位'),('false_positive','误报')]:
        lines.append('|'+title+'|'+'|'.join(fmt(summary['reference_screened_controlled'][m]['overall'][key]) for m in MODES)+'|')
    lines+=['','### 使用 AI 暂定标签的探索性评估','',
            f"仅使用 AI 明确判为正确或错误的 {len(ai_labeled)} 条；不确定案例不进入此探索性标签分母，但完整保留在主实验。",'',
            '|指标|规则|Hy3 Judge|混合|','|---|---|---|---|']
    for key,title in [('detection','错误检出'),('localization','首错定位'),('false_positive','误报')]:
        lines.append('|'+title+'|'+'|'.join(fmt(summary['ai_provisional_controlled'][m]['overall'][key]) for m in MODES)+'|')
    lines+=['','## 重复评审稳定性','',
            '预先按 clean/local/challenge 各选 4 条，共 12 条，每条含主实验一次及额外两次。结果衡量重复一致性，不代表正确性。','',
            f"已获得完整三次成功评审：{summary['stability']['complete_cases']}/12。若不满 12 组，下列数字仅表示全预选案例中成功且一致的数量；缺失不是实证不稳定，不据此得出稳定性结论。",'',
            *[f"- {title}：{fmt(summary['stability'][key])}" for key,title in [('process_stable','过程判定三次一致'),('location_stable','判定及首错三次一致'),('type_stable','判定及类型三次一致')]],'',
            '## 调用记录与边界','',
            f"保存的服务响应 {len(response_files)} 份；服务报告的总 token 数 {usage['total_tokens']}，不据此推测费用。",'',
            f"任务状态：{summary['call_statuses']}；规则硬错误与 Judge 判正确发生冲突 {len(conflicts)} 条，混合组保留规则硬错误。",'',
            *['- '+x for x in summary['limitations']], '',
            '原始请求与响应：runs/live/batch-v1/（本地 Git 忽略）。可分享的统计、显式解答、逐例预测、争议与稳定性文件：runs/experiments/batch-v1/。']
    (target/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'generation':summary['generation'],'ai_reviewed':len(reviews),'reference_disputes':len(excluded),'responses':len(response_files)},ensure_ascii=True))

if __name__=='__main__':
    main()
