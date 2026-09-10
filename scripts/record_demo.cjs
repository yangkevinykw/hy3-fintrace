/* Record the real local workbench. Captions/spotlights are editorial overlays. */
const fs = require('fs');
const path = require('path');
const {chromium} = require('playwright');
const root = path.resolve(__dirname,'..');
const work = path.join(root,'demo','.work');
const scenes = JSON.parse(fs.readFileSync(path.join(work,'scenes.json'),'utf8').replace(/^\uFEFF/,''));
(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:process.env.DEMO_CHROMIUM});
  const context=await browser.newContext({viewport:{width:1440,height:900},recordVideo:{dir:work,size:{width:1440,height:900}},reducedMotion:'reduce',bypassCSP:true});
  const started=Date.now();
  const page=await context.newPage();
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  // No model calls or review submissions while making a demonstration.
  await page.route('**/api/solve',r=>r.abort());
  await page.route('**/api/review',r=>r.request().method()==='POST'?r.abort():r.continue());
  await page.goto(process.env.DEMO_URL||'http://127.0.0.1:8765/');
  await page.locator('#steps .step').first().waitFor();
  await page.addStyleTag({content:`body{padding-bottom:100px}#demo-caption{position:fixed;bottom:0;left:0;right:0;z-index:99999;background:#10271f;color:#f6faf7;padding:15px 35px 18px;border-top:3px solid #8acd9c;min-height:83px;font-family:'Microsoft YaHei',sans-serif;box-sizing:border-box}#demo-caption b{font-size:23px;display:block;letter-spacing:1px}#demo-caption span{font-size:17px;color:#c9e0d1;display:block;margin-top:5px}#demo-chapter{position:fixed;right:25px;top:15px;background:#133c2d;color:white;padding:8px 16px;border-radius:20px;z-index:99998;font-size:14px;pointer-events:none}.demo-focus{outline:3px solid #b39334!important;outline-offset:4px!important}html{scroll-behavior:smooth}`});
  await page.evaluate(()=>{for(const id of ['demo-caption','demo-chapter']){const e=document.createElement('div');e.id=id;document.body.appendChild(e)}});
  for(let i=0;i<scenes.length;i++){
    const s=scenes[i];
    await page.evaluate(({s,i,n})=>{
      document.querySelectorAll('.demo-focus').forEach(e=>e.classList.remove('demo-focus'));
      const cap=document.querySelector('#demo-caption');cap.replaceChildren();
      const title=document.createElement('b');title.textContent=s.title;const sub=document.createElement('span');sub.textContent=s.caption;cap.append(title,sub);
      document.querySelector('#demo-chapter').textContent=`FINTRACE  ·  ${String(i+1).padStart(2,'0')} / ${n}`;
    },{s,i,n:scenes.length});
    if(s.action==='error'){
      await page.locator('.verdict-panel').evaluate(e=>e.classList.add('demo-focus'));
    }else if(s.action==='evidence'){
      await page.locator('#steps .step').first().click();
      await page.locator('.evidence-panel').evaluate(e=>e.classList.add('demo-focus'));
    }else if(s.action==='edit'){
      await page.locator('.editor summary').click();
      const trace=JSON.parse(await page.locator('#trace-editor').inputValue());trace.steps[0].result='22';
      await page.locator('#trace-editor').fill(JSON.stringify(trace,null,2));
      await page.locator('#evaluate-button').click();
      await page.locator('#verdict').getByText('成立',{exact:true}).waitFor();
      await page.locator('.editor summary').click();
      await page.evaluate(()=>window.scrollTo(0,0));
    }else if(s.action==='batch'){
      await page.locator('[data-tab="benchmark"]').click();
      await page.locator('#experiment-results .metrics').waitFor();
      await page.evaluate(()=>window.scrollTo(0,0));
    }else if(s.action==='disputes'){
      await page.getByText('查看逐题争议依据',{exact:true}).click();
      const box=page.locator('#experiment-results article').filter({has:page.getByRole('heading',{name:'AI 复核与参考争议',exact:true})});
      await box.evaluate(e=>window.scrollTo(0,e.offsetTop-65));
    }else if(s.action==='live'){
      await page.locator('#batch-case-select').selectOption({label:'RCL/2016/page_37.pdf-2'});
      await page.locator('#batch-case-open').click();
      await page.locator('#source-notice').filter({hasText:'真实 Hy3 输出'}).waitFor();
      await page.evaluate(()=>window.scrollTo(0,0));
    }else if(s.action==='end'){
      await page.evaluate(()=>{
        const e=document.createElement('div');e.style.cssText='position:fixed;inset:0;z-index:99997;background:#10271f;color:white;display:flex;align-items:center;justify-content:center;font-family:Microsoft YaHei;text-align:center';
        e.innerHTML='<div><div style="font-size:22px;color:#a7d6ba;letter-spacing:6px">EVIDENCE BEFORE VERDICT</div><h1 style="font-size:76px;color:white;margin:25px">FinTrace</h1><p style="font-size:28px;line-height:1.8">从原始证据，到每一步计算。<br>让判断有据可查。</p><p style="font-size:24px;color:#a7d6ba">github.com/yangkevinykw/hy3-fintrace</p></div>';document.body.appendChild(e);
      });
    }
    await page.waitForTimeout(400);
    s.start=(Date.now()-started)/1000;
    console.log(`Recording ${i+1}/${scenes.length}: ${s.title}`);
    if(i===0)await page.screenshot({path:path.join(root,'demo','poster.png')});
    await page.waitForTimeout(s.duration*1000+650);
  }
  const video=page.video();
  await context.close();
  const videoPath=await video.path();
  await browser.close();
  fs.writeFileSync(path.join(work,'recording.json'),JSON.stringify({videoPath,scenes,errors},null,2));
  if(errors.length)throw new Error('Browser errors: '+errors.join('; '));
  console.log('Recorded '+videoPath);
})().catch(e=>{console.error(e);process.exit(1)});
