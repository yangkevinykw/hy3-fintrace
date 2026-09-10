const fs=require('fs'),path=require('path');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'..');
(async()=>{
 const b=await chromium.launch({headless:true,executablePath:process.env.DEMO_CHROMIUM,args:['--autoplay-policy=no-user-gesture-required']});
 const p=await b.newPage({viewport:{width:1440,height:900}});
 const meta=await p.evaluate(async data=>{
   document.body.style.margin='0';const v=document.createElement('video');v.style.width='1440px';v.src='data:video/mp4;base64,'+data;document.body.appendChild(v);
   await new Promise((resolve,reject)=>{v.onloadeddata=resolve;v.onerror=()=>reject(new Error('MP4 decode error'))});
   const seek=async t=>{const done=new Promise(r=>v.onseeked=r);v.currentTime=t;await done};
   await seek(3);
   const a=new AudioContext(),source=a.createMediaElementSource(v),meter=a.createAnalyser(),mute=a.createGain();mute.gain.value=0;
   source.connect(meter);meter.connect(mute);mute.connect(a.destination);await a.resume();await v.play();
   let peak=0;const values=new Float32Array(meter.fftSize);
   for(let i=0;i<8;i++){await new Promise(r=>setTimeout(r,100));meter.getFloatTimeDomainData(values);peak=Math.max(peak,...Array.from(values,Math.abs))}
   v.pause();await seek(55);
   return {duration:v.duration,width:v.videoWidth,height:v.videoHeight,decodedAudioPeak:peak,canPlay:v.canPlayType('video/mp4')};
 },fs.readFileSync(path.join(root,'demo/fintrace-demo.mp4')).toString('base64'));
 await p.screenshot({path:path.join(root,'demo/.work/qa-mp4.png')});await b.close();
 if(meta.duration>120||meta.duration<90||meta.decodedAudioPeak<0.001)throw new Error('Video QA failed: '+JSON.stringify(meta));
 fs.writeFileSync(path.join(root,'demo/validation.json'),JSON.stringify(meta,null,2));console.log(JSON.stringify(meta));
})().catch(e=>{console.error(e);process.exit(1)});
