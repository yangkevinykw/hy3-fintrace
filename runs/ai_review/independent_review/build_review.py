"""Independent packet-only review transcription and arithmetic cross-check.

The judgments and semantic notes below were authored after reading the blinded
packet. This helper is a calculator/transcription aid, not the project evaluator.
"""
import hashlib
import json
from collections import Counter, defaultdict
from fractions import Fraction as F
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACKET = HERE.parent / "packet" / "cases.json"
raw = PACKET.read_bytes()
cases = json.loads(raw)
groups = defaultdict(list)
for case in cases:
    groups[case["problem"]["id"]].append(case)

# Per-question substantive interpretation, independently derived from packet.
notes = [
    "表内非 owned 设施为 New Haven 514000、Lexington 81000、Bogart 70000、Zurich 69000，合计 734000 平方英尺；但正文 texts[8] 另列 Cheshire 租赁 254000，texts[6:8] 还提到未量化租赁场地。题面未限定仅表内主要设施，734000 只能作为表内小计；全公司租赁总量无法唯一确定。",
    "2014 列四区域新增站点为 900、1560、190、5800，应逐项相加为 8450，不能抵减亚洲站点。",
    "候选取 2008/2007 的期初准备 16117、8940，期初变化率为 7177/8940≈80.279642%；但题面只问两年 allowance for loan losses，期末同名余额分别为 29616、16117，对应≈83.756282%。题面未指定期初，需确认口径；不能仅凭候选引用的行判为完全正确。",
    "债务行四列为母公司 192.3、CGMHI 20.6、CFI 37.4、其他子公司 109.3 十亿美元，四者合计 359.6；若 subsidiaries 严格排除母公司则是 167.3。题目措辞重复且主语不清，须确认是否包含 parent company。",
    "正文 texts[54] 明确 2010/2009 利息支付 189/201 百万美元，延续同比比例应以 189/201 乘 2010 的 189，得到 177.7164179104 百万美元。",
    "正文 texts[19] 将 227、170、120 百万美元分别对应 2015、2014、2013，三年合计 517 百万美元。",
    "表中 2009 年末未归属单位 1415 千份、加权每份公允价值 25.24 美元，1415×1000×25.24/1000000=35.7146 百万美元。",
    "按两个已报告年末累计余额比较，2018 年末 -974 减 2017 年末 862 等于 -1836 百万美元。此数包括会计准则变更 -1790；以调整后期初 -928 比较时当期 OCI 是 -46，二者需区分。本记录采用题目 net change in accumulated balance 的年末对年末口径。",
    "正文 texts[21:23] 明确 2013 与 2012 的燃油附加费收入同为 2.6 十亿美元，变化率为 0。packet 将两次 2.6 合并为 x:21:0，span 只指向第一个即 2013 数字，候选因此无法用不同 ref 明确标出 2012；整句支持答案，但精确证据对齐仍待修复/确认。",
    "农业收入行 2010、2009、2008 为 3018、2666、3174 百万美元，总数 8858，三年均值 8858/3=2952.6666667。",
    "采用表格左侧 GAAP 口径：2015 为 4664、2016 为 4570，变化额 -94，增长率 -94/4664≈-2.015437%。右侧调整口径不与左侧混用。",
    "texts[1] 说明归属期 two to four years，平均 (2+4)/2=3 年；texts[2] 本批授予公允价值 58.7 百万美元，平均年度额 58.7/3≈19.566667。题面明确平均期限，因此可算平均摊额；原文 accelerated basis 不支持声称实际每年费用完全相等。",
    "题目要求 2016→2017，表格 segment income 对应 1226.2→1193.5，增长率应为 (1193.5-1226.2)/1226.2≈-2.666775%。候选的 1685 是 2018 而非 2017，1193.5 是 2017 而非 2016，从 s1 即错配年份；41.181399% 是另一年度区间。",
    "2015 租金最低付款额 345、全部未来最低租金 3189 百万美元，所占比例 345/3189≈10.818438%；不是求两者之和。",
    "texts[0] 因期限届满/和解最多下降 8 百万美元，texts[1] 因支付最多下降 14 百万美元，合计上限 22 百万美元。数字可作为两类可能下降的合计上限，不能解释为确定实现的期望值。",
    "texts[6:8] 同一 Entergy Texas 信贷额度允许信用证 30 百万美元，2017 年末已开出 25.6 百万美元，使用率 25.6/30≈85.333333%。",
    "texts[9] 用 respectively 将 2016、2015、2014 管理费对应 4.5、6.8、8.5 百万美元。题目 2015→2016 应 (4.5-6.8)/6.8≈-33.823529%，候选反向用 (6.8-4.5)/4.5，从 s1 即把变化方向倒置，并在 s2 使用错误基期。",
    "2003/2002 资产报废义务 29/15 百万美元，增加 14 百万美元，乘 1000000 换成美元后为 14000000；没有把百万美元与美元混加。",
    "S&P 500 从 2011 年 100.00 增至 2016 年 198.18，累计增幅 (198.18-100)/100=0.9818，即 98.18%。常量 100 同时有基期表格数据支持。",
    "Citi 五年累计回报以 2010 年末 100 到 2015 年末 110.14 计算，净收益率为 (110.14-100)/100=0.1014，即 10.14%；110.14 是终值指数，不是净回报率。",
    "GAAP 总投资 2011 年 1631、2012 年 1750 百万美元，增加 119，变化率 119/1631≈7.296137%。不使用 adjusted 或 economic exposure 行。",
    "2013 年末 target date/risk 为 111408、multi-asset 总计 341214 百万美元，份额 111408/341214≈32.650477%；不能使用 2014 年列。",
    "按题目列出顺序做 A O Smith 减行业指数：两者以 100 为基期的回报分别 42.72% 与 153.33%，差为 -110.61 个百分点，即 ratio -1.1061。若报告绝对差应为正 110.61 个百分点，这里采用有方向的差。",
    "texts[25] 分别列 2013/2012/2011 已归属奖励公允价值 63/55/52 百万美元，题目只加前两年，63+55=118。",
    "2005 工业涂料销售为 2921 百万美元；texts[4] 明确 volume 增长贡献为 4%，影响额 2921×0.04=116.84 百万美元。但 x:4:0 的 span 指向同句第一个 acquisition 的 4%，第二个 volume 的 4% 未独立编号；整句可支持数值，精确引用仍有歧义。",
    "年初 571、年末 627 MMboe，绝对增加 56 MMboe，texts[0] 已明说；若问相对幅度则是 56/571≈9.807356%。题面 by how much 未要求 percentage，候选仅输出 ratio，因此所答量纲/范围待确认，不能直接判整题正确。",
    "2006/2007 backlog 为 3.2/2.6 十亿美元，带符号变化率 (2.6-3.2)/3.2=-18.75%，等价于下降 18.75%。本记录接受以负增长率表达 reduction，不能把 +81.25% 当成下降率。",
    "按题目与 texts[4] 的上下文，将收到的额外抵押品与交付的额外抵押品相比：16.9/5.8≈2.913793。题目英文残缺，本记录采用 received-to-delivered 的自然对应解释，并不把 received 与其自身比较。",
    "2008/2007 年末未归属限制股数量分别 3883230、3821707，净增加 61523 股。2008 的归属、授予、没收为年内变化，不另重复加进年末余额差。",
    "2009 两类租赁付款 657+188=845 百万美元，所有未来最低付款 5909+1898=7807，2009 份额 845/7807≈10.823620%。分母使用最低付款总额而非资本租赁现值 1270。",
]

# Explicit case-by-case adjudications: C correct; U unresolved interpretation;
# otherwise first confirmed error step and class, selected by packet reading.
judgments = [
 ["U", "s3/arithmetic", "s1/dependency"],
 ["s1/formula", "C", "s1/evidence_value"],
 ["s2/arithmetic", "U", "s1/evidence_value"],
 ["U", "s3/arithmetic", "s1/dependency"],
 ["s1/formula", "C", "s1/arithmetic"],
 ["s1/arithmetic", "C", "s1/formula"],
 ["C", "s3/arithmetic", "s1/dependency"],
 ["s1/arithmetic", "C", "s1/dependency"],
 ["s1/evidence_value", "U", "s1/formula"],
 ["s2/arithmetic", "s3/arithmetic", "C"],
 ["C", "s1/arithmetic", "s1/formula"],
 ["s1/formula", "C", "s2/arithmetic"],
 ["s1/evidence_semantics", "s1/evidence_semantics", "s1/evidence_semantics"],
 ["C", "s1/formula", "s1/dependency"],
 ["C", "s1/arithmetic", "s1/arithmetic"],
 ["s1/arithmetic", "s1/arithmetic", "C"],
 ["s1/formula", "s1/formula", "s1/evidence_value"],
 ["C", "s2/arithmetic", "s1/dependency"],
 ["s1/evidence_value", "s1/formula", "C"],
 ["s1/formula", "C", "s1/arithmetic"],
 ["C", "s1/dependency", "s1/formula"],
 ["s1/evidence_value", "s1/formula", "C"],
 ["C", "s1/formula", "s1/dependency"],
 ["s1/arithmetic", "s1/evidence_value", "C"],
 ["s1/dependency", "U", "s1/formula"],
 ["s1/arithmetic", "U", "s1/evidence_value"],
 ["s2/arithmetic", "s2/arithmetic", "C"],
 ["s1/dependency", "s1/formula", "C"],
 ["s1/arithmetic", "s1/arithmetic", "C"],
 ["C", "s1/formula", "s1/evidence_value"],
]
expected = [None,F(8450),None,None,F(189**2,201),F(517),F(357146,10000),F(-1836),F(0),F(8858,3),F(-94,4664),F(587,30),F(-327,12262),F(345,3189),F(22),F(256,300),F(-23,68),F(14000000),F(9818,10000),F(1014,10000),F(119,1631),F(111408,341214),F(-11061,10000),F(118),F(11684,100),None,F(-1875,10000),F(169,58),F(61523),F(845,7807)]

def close(a, b):
    return abs(a-b) <= max(F(1),abs(b))*F(1,10**24)

def fmt(n):
    return str(n.numerator) if n.denominator==1 else f"{n.numerator}/{n.denominator} (约 {float(n):.12g})"

def numeric_audit(case):
    seen={}; audit=[]
    for step in case['candidate']['steps']:
        values=[]; issues=[]
        for arg in step['args']:
            if arg['kind']=='step':
                if arg['ref'] not in seen:
                    issues.append(f"依赖 {arg['ref']} 在此步开始时尚未产生")
                    values.append(None)
                else: values.append(seen[arg['ref']])
            else:
                value=F(arg['value']);values.append(value)
                if arg['kind']=='evidence':
                    ev=case['problem']['evidence'].get(arg['ref'])
                    if ev is None:issues.append(f"缺少证据 {arg['ref']}")
                    elif value!=F(ev['value']):issues.append(f"{arg['ref']} 原值 {ev['value']}，候选写为 {arg['value']}")
        result=F(step['result'])
        calculated=None
        if all(v is not None for v in values):
            a,b=values;op=step['op']
            calculated={'add':lambda:a+b,'subtract':lambda:a-b,'multiply':lambda:a*b,'divide':lambda:a/b}[op]()
            if not close(result,calculated):issues.append(f"{step['op']}({fmt(a)}, {fmt(b)}) 应为 {fmt(calculated)}，候选结果 {step['result']}")
        audit.append({'step':step['id'],'issues':issues,'computed_from_claimed_inputs':None if calculated is None else fmt(calculated),'claimed_result':step['result']})
        seen[step['id']]=result
    last=case['candidate']['steps'][-1]
    final=case['candidate']['final']
    # These packet candidates express the final in the same unit as the last step.
    consistent=close(F(final['value']),F(last['result']))
    return audit,consistent

reviews=[]
audits=[]
for i,(problem_id,items) in enumerate(groups.items()):
    assert len(items)==3
    for case,j in zip(items,judgments[i]):
        audit,consistent=numeric_audit(case)
        if j in ('C','U'):
            assert all(not a['issues'] for a in audit),case['review_id']
            assert consistent
            process='correct' if j=='C' else 'uncertain'
            first=None;kind=None
        else:
            process='incorrect';first,kind=j.split('/')
            if kind in ('arithmetic','dependency','evidence_value'):
                assert next(a for a in audit if a['step']==first)['issues'],case['review_id']
        reason=notes[i]
        local=[a for a in audit if a['issues']]
        if local:
            reason+=' 逐步核验：'+'；'.join(a['step']+'：'+'；'.join(a['issues']) for a in local)+'。'
        if kind=='formula':
            st=next(s for s in case['candidate']['steps'] if s['id']==first)
            reason+=f" 首个公式错误在 {first}，候选使用 {st['op']}，与上述题意所需关系不符；局部算术成立也不能消除此错误。"
        if not consistent:
            reason+=f" 最终答案 {case['candidate']['final']['value']} 又与最后一步结果 {case['candidate']['steps'][-1]['result']} 不一致。"
        elif process=='incorrect':
            reason+=' 后续若沿用错误结果，即使局部计算一致也只是错误传播，不会使过程变正确。'
        elif process=='correct':
            reason+=' 已逐步检查证据数值、运算、先后依赖与最终值，均与该题意解释一致。'
        refs=sorted({a['ref'] for s in case['candidate']['steps'] for a in s['args'] if a['kind']=='evidence'})
        if i==12:refs=sorted(set(refs+['t:2:3:0']))
        final=F(case['candidate']['final']['value'])
        if case['candidate']['final']['unit']=='percent':final/=100
        answer=None if expected[i] is None else close(final,expected[i])
        confidence='medium' if process=='uncertain' or (process=='correct' and i in [7,11,14,22,26,27]) else 'high'
        review={'review_id':case['review_id'],'reviewer_type':'ai','process':process,'first_error_step':first,'error_type':kind,'reason':reason,'evidence_refs':refs,'confidence':confidence,'answer_correct':answer}
        if process=='incorrect' and i in [0,2,3,8,24,25]:
            review['localization_scope']='earliest_confirmed_error; preceding semantic ambiguity unresolved'
        else:review['localization_scope']='first_error_under_stated_interpretation' if process=='incorrect' else 'not_applicable'
        reviews.append(review)
        audits.append({'review_id':case['review_id'],'steps':audit,'final_matches_last_step':consistent})

assert len(reviews)==90 and len({r['review_id'] for r in reviews})==90
assert {r['review_id'] for r in reviews}=={c['review_id'] for c in cases}
for r in reviews:
    ev=next(c['problem']['evidence'] for c in cases if c['review_id']==r['review_id'])
    assert all(ref in ev for ref in r['evidence_refs']),r['review_id']

HERE.mkdir(parents=True,exist_ok=True)
(HERE/'reviews.json').write_text(json.dumps(reviews,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(HERE/'arithmetic_audit.json').write_text(json.dumps(audits,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
stats={'reviewer_type':'ai','human_review_status':'pending','cases':len(reviews),'questions':len(groups),'packet_sha256':hashlib.sha256(raw).hexdigest(),'process':dict(Counter(r['process'] for r in reviews)),'first_error_type':dict(Counter(r['error_type'] for r in reviews if r['process']=='incorrect')),'answer_correct':dict(Counter(str(r['answer_correct']).lower() for r in reviews)),'blindness':'Read only packet/cases.json; did not read mapping, original data, evaluators, benchmark outputs, model responses, or credentials.'}
(HERE/'summary.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(stats,ensure_ascii=False))
