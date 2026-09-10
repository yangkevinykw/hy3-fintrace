'use strict';
const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const words = {correct:'成立',incorrect:'错误',uncertain:'无法确定',affected:'受上游影响'};
const types = {evidence_value:'取数不一致',evidence_missing:'证据不存在',arithmetic:'计算错误',dependency:'依赖错误',formula:'公式错误',semantic_unverified:'语义待验证',answer_consistency:'答案与过程不一致',execution:'无法执行',format:'格式错误',upstream_unavailable:'上游结果不可用',unproven_constant:'常量来源待确认'};
const opSymbols = {add:'+',subtract:'−',multiply:'×',divide:'÷'};
let boot, current, summary, experiment, currentReview, toastTimer;
async function api(path, body){
  const options = body === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json','X-FinTrace-Token':boot.token},body:JSON.stringify(body)};
  const response = await fetch(path, options);
  const result = await response.json();
  if(!response.ok) throw new Error(result.error || '请求失败');
  return result;
}
function toast(message){$('toast').textContent=message;$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,6000);}
function download(name, data){const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function formatNumber(value){const n=Number(value);return Number.isFinite(n)?new Intl.NumberFormat('en-US',{maximumFractionDigits:8}).format(n):String(value??'—');}
function tableHTML(problem){return '<table><tbody>'+problem.table.map((row,r)=>'<tr>'+row.map((cell,c)=>`<${r===0?'th':'td'} data-row="${r}" data-col="${c}">${esc(cell)}</${r===0?'th':'td'}>`).join('')+'</tr>').join('')+'</tbody></table>';}
function setCases(filter='all'){
  const cases=boot.cases.filter(c=>filter==='all'||c.id.endsWith('::'+filter));
  $('case-select').innerHTML=cases.map((c,i)=>`<option value="${esc(c.id)}">${String(i+1).padStart(2,'0')} · ${esc(c.problem_id)} · ${c.id.endsWith('::clean')?'标准过程':c.id.endsWith('::local')?'局部错误':'挑战案例'}</option>`).join('');
  if(current&&cases.some(c=>c.id===current.sample.id)) $('case-select').value=current.sample.id;
}
async function loadCase(id){
  current=await api('/api/case?id='+encodeURIComponent(id));
  renderCurrent();
}
function renderCurrent(){
  const p=current.problem;
  $('question').textContent=p.question;
  $('problem-id').textContent=p.id;
  $('difficulty').textContent={easy:'基础 · 1 步',medium:'进阶 · 2 步',hard:'挑战 · 3 步以上'}[p.difficulty];
  $('split').textContent=p.split==='dev'?'开发集':'评测集';
  $('source-notice').textContent=(current.live?'真实 Hy3 输出 · 原始响应和评估结果已保存在本地。过程结论尚待人工复核。':'离线回放 · 参考程序及受控注错样本，非真实模型输出。')+((current.referenceDisputed||boot.reference_disputes?.includes(p.id))?' 此题参考过程存在 AI 复核争议；数值符合参考不代表语义正确，请查看批量评测中的依据。':' 证据对齐及语义标签待人工确认。');
  $('table-wrap').innerHTML=tableHTML(p);
  $('texts').innerHTML=p.texts.map((t,i)=>`<p data-text="${i}"><strong>文字 ${i+1}</strong><br>${esc(t)}</p>`).join('');
  $('text-count').textContent=`(${p.texts.length})`;
  $('trace-editor').value=JSON.stringify(current.sample.trace,null,2);
  renderEvaluation();
}
function renderEvaluation(){
  const t=current.sample.trace, v=current.evaluation;
  $('step-count').textContent=`${t.steps?.length||0} STEPS`;
  $('steps').innerHTML=(t.steps||[]).map((step,i)=>{
    const checked=(v.steps||[])[i]||{status:'uncertain'};
    const args=(step.args||[]).map(a=>a.kind==='step'?esc(a.ref):formatNumber(a.value));
    const refs=(step.args||[]).filter(a=>a.kind==='evidence').map(a=>`<span>${esc(a.ref)}</span>`).join('');
    return `<button class="step ${esc(checked.status)}" data-step="${i}"><div class="step-top"><span class="step-number">STEP ${String(i+1).padStart(2,'0')}</span><span class="status ${esc(checked.status)}">${esc(words[checked.status]||checked.status)}</span></div><div class="expression">${args.join(' '+esc(opSymbols[step.op]||step.op)+' ')}<br>= ${esc(formatNumber(step.result))}</div><div class="reference-chips">${refs}</div><p>${esc(step.explanation||'未提供文字说明')}</p>${checked.affected_by?.length?`<p>继承 ${esc(checked.affected_by.join(', '))} 的错误</p>`:''}</button>`;
  }).join('');
  $('steps').querySelectorAll('[data-step]').forEach(b=>b.addEventListener('click',()=>selectStep(Number(b.dataset.step))));
  const answerLabel=v.answer_correct===true?'正确':v.answer_correct===false?'错误':'待判断';
  $('verdict').innerHTML=`<div class="result-cards"><div class="result-card ${v.answer_correct===false?'bad':v.answer_correct===null?'wait':''}"><small>最终答案</small><strong>${answerLabel}</strong></div><div class="result-card ${v.process==='incorrect'?'bad':v.process==='uncertain'?'wait':''}"><small>结构化过程</small><strong>${esc(words[v.process])}</strong></div></div>${v.correct_answer_invalid_process?'<div class="cair">答案正确，但当前过程存在已确认错误。</div>':''}${v.first_error?`<div class="first-error"><strong>首个已确认错误 · ${esc(v.first_error.step||'格式阶段')}</strong>${esc(types[v.first_error.type]||v.first_error.type)}<br>${esc(v.first_error.message)}</div>`:`<div class="verdict-note">${v.process==='correct'?'证据取数、局部计算与标准计算表达式通过当前检查。':'当前证据尚不足以判定整个过程成立。'}</div>`}<div class="verdict-note">候选答案：${esc(formatNumber(t.final?.value))} ${t.final?.unit==='percent'?'%':''}<br>标准执行结果：${esc(formatNumber(current.problem.answer.value))}<br>公式等价验证：${v.reference_equivalent===true?'通过':v.reference_equivalent===false?'未证明等价':'无法完成'}<br>判定来源：${v.mode==='hybrid'?'规则 + Hy3 语义评审':'确定性规则'}</div>`;
  $('findings').innerHTML=(v.findings||[]).map(f=>`<div class="finding"><strong>${esc(f.step||'整体')} · ${esc(types[f.type]||f.type)}</strong>${esc(f.message)}${f.evidence?.expected!==undefined?`<br>应为 <code>${esc(formatNumber(f.evidence.expected))}</code>，实际 <code>${esc(formatNumber(f.evidence.actual))}</code>`:''}</div>`).join('');
  if(v.mode==='hybrid'&&v.process==='correct'&&!v.first_error)$('verdict').querySelector('.verdict-note').textContent='当前局部规则检查与 Hy3 语义评审支持过程成立；规则是否证明公式等价另列如下。';
  if(v.semantic?.status==='complete')$('findings').insertAdjacentHTML('afterbegin',`<div class="finding"><strong>Hy3 语义评审 · ${esc(words[v.semantic.output.process])}</strong>${esc(v.semantic.output.reason)}<p>下方保留原规则发现，便于区分规则证据与模型判断。</p></div>`);
  let focus=t.steps?.findIndex(s=>s.id===v.first_error?.step);
  if(t.steps?.length)selectStep(focus>=0?focus:0);
}
function selectStep(index){
  const step=current.sample.trace.steps[index];
  $('steps').querySelectorAll('.step').forEach((b,i)=>{b.classList.toggle('selected',i===index);b.setAttribute('aria-pressed',String(i===index));});
  document.querySelectorAll('#table-wrap .highlight,#texts .highlight').forEach(e=>e.classList.remove('highlight'));
  const details=[];
  const visit=(s,seen=new Set())=>{
    if(!s||seen.has(s.id))return;seen.add(s.id);
    for(const arg of s.args||[]){
      if(arg.kind==='step')visit(current.sample.trace.steps.find(x=>x.id===arg.ref),seen);
      if(arg.kind!=='evidence')continue;
      const e=current.problem.evidence[arg.ref];if(!e)continue;
      const loc=e.location;
      if(loc.kind==='table')$('table-wrap').querySelector(`[data-row="${loc.row}"][data-col="${loc.col}"]`)?.classList.add('highlight');
      else{$('text-details').open=true;$('texts').querySelector(`[data-text="${loc.index}"]`)?.classList.add('highlight');}
      details.push(`<strong>${esc(arg.ref)}</strong> · ${esc(e.token)}<br>${esc(e.text)}`);
    }
  };
  visit(step);
  $('evidence-detail').innerHTML=details.length?details.join('<br><br>'):'此步骤未引用可定位的原始证据。';
}
function metricText(x){return x?.rate==null?'—':(x.rate*100).toFixed(1)+'%';}
function fraction(x){return `${x?.numerator??0} / ${x?.denominator??0}`;}
async function renderSummary(){
  await renderExperiment();
  summary=await api('/api/summary');if(summary.pending===true){$('metrics').textContent='尚未生成评测报告。';return;}
  const m=summary.by_split.test;
  $('metrics').innerHTML=[['detection','错误检出率'],['localization','首错定位准确率'],['false_positive','正确过程误报率'],['uncertain','无法确定比例']].map(([k,label])=>`<div class="metric"><small>${label}</small><strong>${metricText(m[k])}</strong><p>评测集 · ${fraction(m[k])}</p></div>`).join('');
  $('split-table').innerHTML='<table><thead><tr><th>数据划分</th><th>样本数</th><th>错误检出</th><th>首错定位</th><th>误报</th></tr></thead><tbody>'+Object.entries(summary.by_split).map(([k,x])=>`<tr><td>${k==='dev'?'开发集':'评测集'}</td><td>${x.count}</td><td>${fraction(x.detection)}</td><td>${fraction(x.localization)}</td><td>${fraction(x.false_positive)}</td></tr>`).join('')+'</tbody></table>';
  $('error-bars').innerHTML=Object.entries(summary.by_error).map(([k,x])=>`<div class="error-row"><div class="bar-meta"><span>${esc(types[k]||k)}</span><span>${fraction(x.detection)}</span></div><div class="bar-track"><meter min="0" max="1" value="${Number(x.detection.rate)||0}" aria-label="${esc(types[k]||k)}检出率"></meter></div></div>`).join('');
  const pending=experiment&&!experiment.pending?['真人裁定参考争议并建立人工金标','完善数值舍入契约',...(experiment.status==='partial'?['恢复接口后续跑 '+experiment.failed_jobs+' 项失败评审；稳定性暂不可判断']:[])]:summary.pending;
  $('pending').innerHTML='<ul>'+pending.map(x=>'<li>'+esc(x)+'</li>').join('')+'</ul>';
}
async function renderExperiment(){
  const host=$('experiment-results');
  try{
    const x=await api('/api/experiment');
    experiment=x;
    if(x.pending){host.innerHTML='<div class="source-notice">批量实验正在生成结果，完成后可在此查看。</div>';return;}
    const g=x.generation, labels={rules:'确定性规则',judge:'Hy3 Judge',hybrid:'规则 + Hy3'};
    const tr=(key,title,source)=>'<tr><td>'+title+'</td>'+Object.keys(labels).map(k=>'<td>'+fraction(source[k].overall[key])+' · '+metricText(source[k].overall[key])+'</td>').join('')+'</tr>';
    const table=(source)=>'<div class="table-wrap"><table><thead><tr><th>指标</th>'+Object.values(labels).map(n=>'<th>'+n+'</th>').join('')+'</tr></thead><tbody>'+[['detection','错误检出'],['localization','首错定位'],['false_positive','误报'],['uncertain','无法确定']].map(([k,n])=>tr(k,n,source)).join('')+'</tbody></table></div>';
    host.innerHTML=`<div class="source-notice"> · 30 道题 / 90 个受控过程。AI 复核已完成，真人复核仍待确认。</div><div class="metrics">${[['generation_success','有效解答'],['answer_accuracy','符合原始参考答案'],['hybrid_process_pass','混合过程通过'],['judge_success','语义评审成功']].map(([k,n])=>`<div class="metric"><small>${n}</small><strong>${metricText(g[k])}</strong><p>${fraction(g[k])}</p></div>`).join('')}</div><article class="panel next-panel"><h3>三组对照 · 全部构造标签</h3><p>同一份 Hy3 判断用于评审与混合组。失败、漏检及弃权保留在分母中。</p>${table(x.controlled)}</article><article class="panel next-panel"><h3>AI 复核与参考争议</h3><p>${x.ai_review.total} 条 AI 复核，${x.ai_review.process_counts.correct||0} 条正确、${x.ai_review.process_counts.incorrect||0} 条错误、${x.ai_review.process_counts.uncertain||0} 条无法确定。${x.ai_review.reference_disputed_problems.length} 道题的参考过程需进一步确认。</p><details><summary>查看逐题争议依据</summary>${x.ai_review.reference_issues.map(i=>`<div class="finding"><strong>${esc(i.problem_id)}</strong>${esc(i.review.reason)}</div>`).join('')}</details><details><summary>排除参考争议题的敏感性分析</summary><p>仅作辅助分析，不替代全量主结果。</p>${table(x.reference_screened_controlled)}</details><details><summary>AI 暂定标签下的探索性评估</summary><p>仅 ${x.ai_review.decisive_count} 条明确 AI 判断进入此分母，不等同人工金标。</p>${table(x.ai_provisional_controlled)}</details></article><article class="panel next-panel"><h3>重复评审稳定性</h3><p>同一案例三次过程判断一致：${fraction(x.stability.process_stable)}；首错一致：${fraction(x.stability.location_stable)}；类型一致：${fraction(x.stability.type_stable)}。重复一致不等于正确。</p><p>服务响应 ${x.transport_responses} 份 · 服务报告 ${Number(x.usage.total_tokens||0).toLocaleString()} tokens。</p></article><article class="panel next-panel"><h3>查看已完成的真实解答</h3><p>直接载入本次保存的结果，不会再次调用接口。</p><div class="toolbar"><select id="batch-case-select" aria-label="选择批量解答">${boot.cases.filter(c=>c.id.endsWith('::clean')).map(c=>`<option value="${esc(c.problem_id)}">${esc(c.problem_id)}</option>`).join('')}</select><button id="batch-case-open" class="secondary">查看解答与证据</button></div></article>`;
    boot.reference_disputes=x.ai_review.reference_disputed_problems;
    host.querySelector('.source-notice').textContent=(x.status==='complete'?'真实批量实验已完成':'真实批量实验部分完成：'+x.failed_jobs+' 项调用失败，待恢复接口后续跑')+'。30 道题的解答已采集；AI 复核已完成，真人复核仍待确认。';
    host.querySelector('.metrics').insertAdjacentHTML('afterend','<div class="source-notice">对原始参考答案的符合率与 AI 答案复核分开报告。AI 认为 '+fraction(x.generation_ai_review.answer_correct)+' 份真实答案有题面支持，另 '+fraction(x.generation_ai_review.answer_uncertain)+' 份范围未定；这不是人工准确率。</div>');
    if(x.stability.complete_cases<x.stability.cases){for(const h of host.querySelectorAll('h3'))if(h.textContent==='重复评审稳定性')h.nextElementSibling.textContent='完整三次成功评审 '+x.stability.complete_cases+' / '+x.stability.cases+' 组；接口失败导致数据不足，目前不能判断稳定性。';}
    $('batch-case-open').addEventListener('click',async()=>{
      try{const id=$('batch-case-select').value;const saved=await api('/api/experiment/case?id='+encodeURIComponent(id));if(!saved.trace||!saved.evaluation){toast('此题调用未形成有效解答，请查看实验失败记录。');return;}await loadCase(id+'::clean');current.sample.trace=saved.trace;current.evaluation=saved.evaluation;current.live=true;current.referenceDisputed=saved.reference_disputed;renderCurrent();document.querySelector('[data-tab="workbench"]').click();$('case-select').value=id+'::clean';if(saved.reference_disputed)toast('这道题的参考过程存在 AI 复核争议，请结合原始证据判断。');}catch(e){toast(e.message);}
    });
  }catch(e){host.innerHTML='<div class="source-notice">真实实验结果尚未发布到工作台。</div>';}
}
async function renderReview(id){
  currentReview=await api('/api/review'+(id?'?id='+encodeURIComponent(id):''));
  const r=currentReview;
  $('review-select').innerHTML=r.ids.map((key,i)=>`<option value="${key}">案例 ${String(i+1).padStart(2,'0')} · ${key.slice(0,6)}</option>`).join('');
  $('review-select').value=r.id;
  $('review-question').textContent=r.problem.question;
  $('review-evidence').innerHTML='<div class="table-wrap">'+tableHTML(r.problem)+'</div><details><summary>报告全文</summary><div class="texts">'+r.problem.texts.map(t=>'<p>'+esc(t)+'</p>').join('')+'</div></details><details><summary>证据 ID 与数值</summary><pre>'+esc(JSON.stringify(r.problem.evidence,null,2))+'</pre></details>';
  $('review-trace').textContent=JSON.stringify(r.trace,null,2);
  $('review-first').innerHTML='<option value="">无 / 无法定位</option>'+r.trace.steps.map(s=>`<option value="${s.id}">${s.id}</option>`).join('')+'<option value="final">最终答案</option>';
  for(const id of ['reviewer','review-process','review-first','review-reason','review-save'])$(id).disabled=!!r.saved;
  $('reviewer').value=r.saved?.reviewer||'';$('review-process').value=r.saved?.process||'uncertain';$('review-first').value=r.saved?.first_error||'';$('review-reason').value=r.saved?.reason||'';
  $('review-saved').textContent=r.saved?`已保存初始复核。评估器判定：${words[r.evaluation.process]}；首错：${r.evaluation.first_error?.step||'无已确认错误'}。`:'提交前不显示评估器结论，也不自动填入标签。';
}
document.querySelectorAll('[data-tab]').forEach(b=>b.addEventListener('click',async()=>{
  document.querySelectorAll('.view').forEach(v=>v.hidden=v.id!==b.dataset.tab);
  document.querySelectorAll('[data-tab]').forEach(n=>n.classList.toggle('active',n===b));
  $('crumb').textContent=b.textContent.trim();
  try{if(b.dataset.tab==='benchmark')await renderSummary();if(b.dataset.tab==='review')await renderReview();}catch(e){toast(e.message);}
}));
document.querySelectorAll('[data-filter]').forEach(b=>b.addEventListener('click',async()=>{
  document.querySelectorAll('[data-filter]').forEach(x=>x.classList.toggle('active',x===b));setCases(b.dataset.filter);try{await loadCase($('case-select').value);}catch(e){toast(e.message);}
}));
$('case-select').addEventListener('change',()=>loadCase($('case-select').value).catch(e=>toast(e.message)));
$('export-button').addEventListener('click',()=>current&&download('fintrace-case.json',current));
$('summary-export').addEventListener('click',()=>summary&&download('fintrace-summary.json',{offline:summary,experiment}));
$('evaluate-button').addEventListener('click',async()=>{
  try{const trace=JSON.parse($('trace-editor').value);if(!Array.isArray(trace.steps)||!trace.steps.every(s=>s&&Array.isArray(s.args)&&s.args.every(a=>a&&typeof a==='object')))throw new Error('请提供 steps 数组和有效的 args 对象数组。');const out=await api('/api/evaluate',{problem_id:current.problem.id,trace});current.sample.trace=trace;current.evaluation=out.evaluation;renderEvaluation();toast('已重新评估，原始样本未被覆盖。');}catch(e){toast(e.message);}
});
$('live-button').addEventListener('click',async()=>{
  if(!boot.config.ready){toast('请复制项目中的 .env.example 为 .env，填写 Hy3 接口、模型和密钥后刷新。');return;}
  const b=$('live-button');b.disabled=true;b.textContent='Hy3 正在解答…';
  const originalId=current.sample.id;
  try{const out=await api('/api/solve',{problem_id:current.problem.id,semantic:true});if(current.sample.id===originalId){current.sample.trace=out.trace;current.evaluation=out.evaluation;current.live=true;renderCurrent();}toast('真实调用已完成，记录已保存。');}catch(e){toast(e.message);}finally{b.disabled=false;b.textContent='使用 Hy3 解答 ↗';}
});
$('review-select').addEventListener('change',()=>renderReview($('review-select').value).catch(e=>toast(e.message)));
$('review-save').addEventListener('click',async()=>{
  try{await api('/api/review',{id:currentReview.id,reviewer:$('reviewer').value,process:$('review-process').value,first_error:$('review-first').value,reason:$('review-reason').value});await renderReview(currentReview.id);toast('初始复核已保存。');}catch(e){toast(e.message);}
});
(async()=>{
  try{boot=await api('/api/bootstrap');$('config-status').textContent=boot.config.ready?'Hy3 已配置':'Hy3 待配置 · 离线可用';$('config-dot').classList.toggle('amber',!boot.config.ready);setCases();const initial=boot.cases[5]||boot.cases[0];$('case-select').value=initial.id;await loadCase(initial.id);}catch(e){toast('加载失败：'+e.message);}
})();
