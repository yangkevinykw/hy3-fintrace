"""Phase-two AI review: reads only live_packet/cases.json.

The reviewer previously saw controlled candidates for these same questions.
Semantic judgments are written explicitly below; arithmetic is an independent
Fraction calculation, not an invocation of project code or model judging.
"""
import hashlib
import json
from collections import Counter
from fractions import Fraction as F
from pathlib import Path

HERE=Path(__file__).resolve().parent
PACKET=HERE.parent/'live_packet'/'cases.json'
raw=PACKET.read_bytes();cases=json.loads(raw)

# One independently authored substantive reasoning and answer interpretation per
# candidate, in the live packet order. No reference programs or original labels.
decisions=[
 ('correct',True,'high',
  'texts[9] 的 respectively 明确 2016/2015 管理费为 4.5/6.8 百万美元。s1 用新减旧为 -2.3，s2 以 2015 的 6.8 为基期，s3 乘 100，年份、方向与分母均正确。',
  '(4.5-6.8)/6.8×100≈-33.8235294118%，与最终答案一致；这是下降而非增长。'),
 ('uncertain',True,'medium',
  '候选明确取 2005 工业涂料销售 2921 百万美元，乘正文说明的 volume 贡献 4%，题意关系和数值正确。但 x:4:0 的 span 指向同一句 acquisitions 的第一个 4%，而 volume 的第二个 4% 没有独立 ref。整句证据支持该数值，精确指标定位仍有歧义，不能把 acquisition 引用直接等同于 volume 引用。',
  '正文明确销量增加贡献 4%，2005 基数 2921×0.04=116.84 百万美元，最终数值正确。'),
 ('correct',True,'medium',
  'texts[0] 因到期/和解最多可能下降 8 百万美元，texts[1] 因支付最多可能下降 14 百万美元，s1 相加为 22。两项原因不同，没有将同一笔重复相加。题面 expected 的合理读取是已披露的可能下降额合计。',
  '22 百万美元可作为两项 up to 金额的合计上限；不是概率加权期望或保证发生的实际下降额，复核按这个边界接受。'),
 ('correct',True,'high',
  '表头将 1193.5 对应 2017、1226.2 对应 2016；s1 差额 -32.7，s2 除 2016 基数，s3 转百分数。没有误用 2018 年的 1685。题目称 increase 并不要求强行输出正值。',
  '(1193.5-1226.2)/1226.2×100≈-2.666775403686%，等价于下降约 2.67%，最终答案正确。'),
 ('correct',True,'high',
  'texts[6] 2006/2007 backlog 为 3.2/2.6 十亿美元。为回答 reduction，s1 旧减新得到正减少额 0.6，s2 以旧值 3.2 为基期，s3 转百分数，符号符合题目。',
  '(3.2-2.6)/3.2×100=18.75%，表示减少 18.75%；无需强制用负的增长率。'),
 ('correct',True,'medium',
  'texts[4] 明确收到额外抵押品 16.9、交付 5.8 十亿美元。候选说明 received-to-delivered，s1 相除符合该解释。英文题目残缺，按相邻两项的自然对比解读，未使用表格中已经净额结算的另一组抵押品。',
  '16.9/5.8≈2.913793103448，即收到额约为交付额 2.914 倍，最终 ratio 正确；解释前提为收到/交付。'),
 ('correct',True,'high',
  'texts[25] 分别列出 2013、2012、2011 的已归属奖励公允价值 63、55、52 百万美元。s1 只相加题目指定的前两年，没有使用未归属表内授予日均值替代已归属公允价值。',
  '63+55=118 百万美元，最终答案正确。'),
 ('correct',True,'medium',
  '两指数均以 2002 年 100 为基期。候选明确用行业指数 253.33 减公司指数 142.72，得到绝对差 110.61。共同基期下终值指数差等于两净累计回报的百分点差；题目 difference between 未指定相减方向，可接受明确说明的绝对差。',
  '行业累计回报 153.33%、公司 42.72%，绝对差 110.61 个百分点。候选用 number 并说明 index difference，数值可接受；不能把它解释成相对回报率 110.61% 或强制等于公司减行业的 -1.1061 ratio。'),
 ('uncertain',None,'medium',
  's1 读取表中 other citigroup subsidiaries 的 109.3 十亿美元，再乘 1，无算术问题。但题目用了 total/subsidiaries，可能要求 CGMHI 20.6、CFI 37.4 与其他子公司 109.3 合计 167.3，也可能包含母公司成为 359.6；正文重排的列名又省略 other。109.3 仅能确定是该列金额，不能确定满足问题范围。',
  '109.3 是 other subsidiaries 列值；它不是所有列合计，也不是排除母公司后的子公司合计。由于题面/正文列名范围不清，保留 null，建议真人核定，不能按单一预置答案判对或判错。'),
 ('correct',True,'high',
  '2009 年末未归属单位数 1415 的单位是千份，每份加权公允价值 25.24 美元。s1 相乘得 35714.6 千美元，s2 除 1000 转成百万美元；这个两步写法在量纲上正确。',
  '1415×25.24/1000=35.7146 百万美元，最终答案正确。'),
 ('uncertain',None,'medium',
  's1-s3 将表中四处非 owned 设施相加为 734000；s4 又加 texts[8] 截至 2015 年末仍租赁的 Cheshire 254000，得 988000。没有把自有设施计入。该数是披露量化面积的合计；texts[6:8] 还说明其他美国和境外租赁地点，题面未限定披露范围或日期，因此不能确认它等于全公司租赁总面积。',
  '988000 平方英尺是表内四处租赁面积与正文 Cheshire 的正确合计；若仅问表内为 734000，若问全部租赁则还有未量化面积。最终题意范围未定，保留 null。'),
 ('uncertain',True,'medium',
  'texts[21] 以 respectively 明确 2013 与 2012 都为 2.6 十亿美元。候选解释明确两年，s1 相减为 0、s2/s3 换算均正确。但 packet 的 x:21:0 span 只指向第一个 2.6，两个年份重复数值被合并，不能在 ref 层面独立确认第二个取数位置。',
  '(2.6-2.6)/2.6×100=0%，整句充分支持最终答案；过程不确定仅针对精确引用粒度。'),
 ('correct',True,'medium',
  '表中 2003/2002 年末义务余额为 29/15，texts[10] 说明这些金额以百万美元计。s1 新减旧得 14，直接保留原题上下文单位，没有必要强制转换成美元。候选 number 字段未显式保存百万美元，展示时应补充单位。',
  '14 应读为 14 百万美元，等价于 14000000 美元。按材料上下文单位判断正确，不能把 number=14 无条件解释成 14 美元。'),
 ('correct',True,'high',
  '年末 627 减年初 571 为 56；正文 texts[0] 直接确认增加 56 MMboe，texts[1] 标注表的单位。题目 by how much 没有要求百分率，求绝对增量是直接回答。',
  '最终 56 的单位沿用材料，为 MMboe；不是要求一定改写为 56/571 的增长率。'),
 ('correct',True,'high',
  'texts[19] 2015/2014/2013 三年员工福利计划发股金额为 227/170/120 百万美元。s1 前两项相加 397，s2 加第三项 120 得 517，依赖和年份正确。',
  '三年总额 517 百万美元，与最终答案一致。'),
 ('correct',True,'medium',
  '候选明确说明用 2008/2007 的年末准备余额，取表中 allowance for loan losses at end of year 29616/16117；差额 13499，除以 2007 年末基数并转百分数。这是年度余额变化的自然解释，且在步骤中显式说明，未混入 unfunded commitment 准备。',
  '年末对年末口径为 (29616-16117)/16117×100≈83.7562821865%。表中也有期初余额，若任务另行指定期初则结果会不同；题面当前没有该限制，故按候选明确的合理年末口径接受，不宣称唯一金标。'),
 ('correct',True,'medium',
  '使用左侧 GAAP 2016/2015 营业利润 4570/4664，s1 差额 -94、s2 除以旧基数，语义和公式正确。精确商约 -0.0201543739279588，候选 -0.0201543739278563 的误差约 1.03e-13，属于极小尾数偏差；该小数不能视为所展示全部位数都精确。',
  '按实用财务显示精度答案约 -2.0154373928% 正确；本轮数值容差内接受，但保留尾数不精确记录，不能宣称严格任意精度相等。'),
 ('correct',True,'high',
  'S&P 500 行 2011 基数 100、2016 为 198.18。s1 减去基数，s2 除原基数，s3 转百分数，表格取数没有混入公司或旅行休闲指数。',
  '(198.18-100)/100×100=98.18%，最终答案正确。'),
 ('correct',True,'high',
  '题目指定 GAAP 投资总余额；s1 取 2012 的 1750 减 2011 的 1631，s2 除旧基数，s3 转百分数，没有使用 adjusted/economic investment 行。',
  '119/1631×100≈7.2961373390558%，最终有限小数在正常显示精度内正确。'),
 ('correct',True,'high',
  '农业一行对应 2010/2009/2008 收入 3018/2666/3174 百万美元。s1=5684，s2=8858，s3 除三年数，步骤和依赖均正确。',
  '8858/3≈2952.6666666667 百万美元，与最终答案的循环小数显示一致。'),
 ('correct',True,'medium',
  '候选明确采用调整后 opening balance as of Dec 31 2017 的 -928，与 Dec 29 2018 的 -974 比较，净变化 -46，表中 2018 other comprehensive income 总计也为 -46。该口径回答调整后期初到期末期间变化，支持 during 2018。',
  '-46 百万美元在已说明的调整后期初口径下正确；若从未调整 2017 年末 862 比较，则含会计准则变更 -1790 的总差为 -1836。两种口径不能混同，本审接受明确且有表格交叉支持的当期口径，建议真人确认最终任务定义。'),
 ('correct',True,'high',
  '2013 年末 target date/risk 111408 与 multi-asset 总额 341214 均来自同一日期列。s1/s2 乘 1 只是保留数值，s3 比例正确，未误用 2014 列。',
  '111408/341214≈0.326504774130018，最终 0.3265047741 是合理截断，即约 32.65047741%。'),
 ('correct',True,'high',
  'texts[54] 2010/2009 利息支付 189/201。s1 得变动 -12，s2 得同比 -12/201，s3 加 1 得增长因子，s4 乘 2010 金额 189，符合延续同一变化率的预测。',
  '189×(189/201)=177.716417910448 百万美元，最终数值在有限小数舍入范围内一致；多步代数写法合理。'),
 ('correct',True,'high',
  '2009 经营与资本租赁最低付款相加 657+188=845，全部最低付款 5909+1898=7807，s3 比例、s4 百分换算正确。分母没有混用扣除利息后的资本租赁现值。',
  '845/7807×100≈10.8236198283592%，最终答案正确。'),
 ('correct',True,'high',
  '2014 列美国、亚洲、EMEA、拉美新增站点 900/1560/190/5800。s1-s3 顺次相加为 2460、2650、8450，选年、总量关系和依赖正确。',
  '四区域新增站点共 8450，最终答案正确。'),
 ('correct',True,'medium',
  'texts[1] two to four years 支持常量 2 与 4；s1 相加、s2 除 2 得平均期限 3 年；texts[2] 本批受限普通股及 RSU 公允价值为 58.7，s3 除平均期限。题目明确平均期限假设，因此可报告平均年度额。',
  '58.7/3≈19.5666666667 百万美元。原文 accelerated basis 不表示实际每年相等，故接受的是平均年度费用，不是实际逐年费用预测。'),
 ('correct',True,'high',
  '2015 未来最低租金 345 与全部未来最低租金 3189 来自同表，s1 比例、s2 转百分数正确；没有使用历史租金费用作为分母。',
  '345/3189×100≈10.8184383819379%，最终答案正确。'),
 ('correct',True,'high',
  'texts[6:8] 同一 Entergy Texas 信贷额度的信用证上限 30、2017 年末已开出 25.6 百万美元。s1 实际/额度，s2 转百分数，指标和日期匹配。',
  '25.6/30×100≈85.3333333333%，最终答案正确。'),
 ('correct',True,'high',
  's1 用 2008 年末未归属限制股 3883230 减 2007 年末 3821707，净增 61523，未把 RSU 或年内授予额重复计入。',
  '61523 股，与最终答案一致。'),
 ('correct',True,'high',
  'Citi 2010 年末指数 100 与 2015 年末 110.14，s1 终值/初值、s2 减 1、s3 转百分数，得到净累计总回报，未混入 S&P 500/financials 列。',
  '(110.14/100-1)×100=10.14%，最终答案正确。'),
]

def fmt(x):return str(x.numerator) if x.denominator==1 else f'{x.numerator}/{x.denominator}'
def close(a,b):return abs(a-b)<=max(F(1),abs(b))*F(1,10**9)

reviews=[];audits=[]
assert len(cases)==len(decisions)==30
for c,d in zip(cases,decisions):
    process,answer,confidence,reason,answer_reason=d
    seen={};steps=[]
    for s in c['candidate']['steps']:
        inputs=[];issues=[]
        for a in s['args']:
            if a['kind']=='step':
                assert a['ref'] in seen,(c['review_id'],s['id'])
                inputs.append(seen[a['ref']])
            else:
                value=F(a['value']);inputs.append(value)
                if a['kind']=='evidence':
                    assert a['ref'] in c['problem']['evidence']
                    assert value==F(c['problem']['evidence'][a['ref']]['value'])
        a,b=inputs
        val={'add':lambda:a+b,'subtract':lambda:a-b,'multiply':lambda:a*b,'divide':lambda:a/b}[s['op']]()
        result=F(s['result']);error=abs(val-result)
        assert close(result,val),(c['review_id'],s['id'],float(error))
        steps.append({'step':s['id'],'op':s['op'],'computed_fraction':fmt(val),'claimed_result':s['result'],'absolute_error':float(error),'within_review_tolerance':True})
        seen[s['id']]=result
    assert close(F(c['candidate']['final']['value']),seen[c['candidate']['steps'][-1]['id']])
    refs=sorted({a['ref'] for s in c['candidate']['steps'] for a in s['args'] if a['kind']=='evidence'})
    reason+=' 已独立逐步核对引用值、四则计算、先后依赖及最后值一致性；有限小数按报告所列实用显示容差判断。'
    reviews.append({'review_id':c['review_id'],'reviewer_type':'ai','review_phase':'phase_2_live','prior_exposure':'same reviewer previously reviewed controlled candidates for these questions','process':process,'first_error_step':None,'error_type':None,'reason':reason,'evidence_refs':refs,'confidence':confidence,'answer_correct':answer,'answer_reason':answer_reason})
    audits.append({'review_id':c['review_id'],'steps':steps,'final_matches_last_step':True})
assert len({r['review_id'] for r in reviews})==30
HERE.mkdir(parents=True,exist_ok=True)
for name,payload in [('reviews.json',reviews),('arithmetic_audit.json',audits)]:
    (HERE/name).write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
summary={'reviewer_type':'ai','phase':'phase_2_live','human_review_status':'pending','prior_exposure':'Same AI reviewer previously read controlled candidates for the same questions; this is not a fresh blind review.','packet_sha256':hashlib.sha256(raw).hexdigest(),'cases':30,'process':dict(Counter(r['process'] for r in reviews)),'answer_correct':dict(Counter('null' if r['answer_correct'] is None else str(r['answer_correct']).lower() for r in reviews)),'arithmetic_tolerance':'abs(claimed-computed) <= 1e-9 * max(1, abs(computed)); all citation numeric values exact','access_boundary':'Only live_packet/cases.json read in this phase; no mapping, original data, project evaluators, live run outputs, other review results, or credentials read.'}
(HERE/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False))
